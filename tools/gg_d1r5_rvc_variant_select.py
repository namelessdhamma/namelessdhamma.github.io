#!/usr/bin/env python3
import argparse, json, pathlib, re, tempfile, math
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from faster_whisper import WhisperModel
from jiwer import wer, cer

def norm(s):
    s=s.lower().replace("ё","е")
    s=re.sub(r"[^а-я0-9 ]+"," ",s)
    return re.sub(r"\s+"," ",s).strip()

def load_mono(path):
    y,sr=sf.read(path,always_2d=False)
    if getattr(y,"ndim",1)>1: y=y.mean(axis=1)
    return np.asarray(y,dtype=np.float32),sr

def resample_to(y,src,dst):
    if src==dst:return y.astype(np.float32)
    g=math.gcd(src,dst)
    return resample_poly(y,dst//g,src//g).astype(np.float32)

def tempo_converter(score):
    tpb=score["ticks_per_beat"]; BAR=tpb*4
    pts=sorted(score.get("tempo_map") or [{"bar":0,"bpm":score["bpm"]}],key=lambda x:int(x["bar"]))
    pts=[(int(p["bar"])*BAR,float(p["bpm"])) for p in pts]
    def sec(tick):
        total=0.0; last=0; bpm=pts[0][1]
        for pos,nbpm in pts[1:]:
            if tick<=pos: break
            total+=(pos-last)*60.0/(bpm*tpb); last=pos; bpm=nbpm
        total+=(tick-last)*60.0/(bpm*tpb)
        return total
    return sec

def phrase_bounds(score,ph,to_sec):
    tpb=score["ticks_per_beat"]; BAR=tpb*4
    st=ph["bar"]*BAR+ph["offset"]; en=st
    for w in ph["words"]: en+=sum(w["durations"])+w["rest"]
    return max(0.0,to_sec(st)-0.12),to_sec(en)+0.18

def transcribe(model,x,sr,path):
    sf.write(path,x,sr)
    segs,_=model.transcribe(str(path),language="ru",beam_size=5,vad_filter=False,
                            condition_on_previous_text=False,temperature=0.0)
    return " ".join(s.text.strip() for s in list(segs)).strip()

def score_text(model,x,sr,target,path):
    txt=transcribe(model,x,sr,path); nt,nr=norm(target),norm(txt)
    return {"transcript":txt,"wer":float(wer(nt,nr)),"cer":float(cer(nt,nr))}

def crossfade_replace(dst,a,b,src,sr):
    n=b-a
    if len(src)!=n:
        if len(src)<2: return
        old=np.linspace(0,1,len(src),endpoint=True)
        new=np.linspace(0,1,n,endpoint=True)
        src=np.interp(new,old,src).astype(np.float32)
    fade=min(n//4,max(1,int(0.065*sr)))
    env=np.ones(n,dtype=np.float32)
    if fade>1:
        env[:fade]=np.linspace(0,1,fade,endpoint=False)
        env[-fade:]=np.linspace(1,0,fade,endpoint=False)
    dst[a:b]=dst[a:b]*(1-env)+src*env

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--score",required=True); ap.add_argument("--guide",required=True)
    ap.add_argument("--candidate",action="append",required=True,
                    help="label=path, e.g. p025=song/vocal/D_P025.wav")
    ap.add_argument("--output",required=True); ap.add_argument("--report",required=True)
    ap.add_argument("--threshold",type=float,default=0.20)
    args=ap.parse_args()

    score=json.loads(pathlib.Path(args.score).read_text())
    guide,gsr=load_mono(args.guide)
    candidates={}
    for item in args.candidate:
        label,path=item.split("=",1)
        y,sr=load_mono(path); candidates[label]=(y,sr,path)
    # Use highest candidate sample rate as common assembly rate.
    sr=max([gsr]+[v[1] for v in candidates.values()])
    guide=resample_to(guide,gsr,sr)
    bank={}
    for label,(y,ysr,path) in candidates.items():
        bank[label]=resample_to(y,ysr,sr)
    n=max([len(guide)]+[len(x) for x in bank.values()])
    guide=np.pad(guide,(0,n-len(guide)))
    for k in list(bank): bank[k]=np.pad(bank[k],(0,n-len(bank[k])))

    to_sec=tempo_converter(score)
    model=WhisperModel("small",device="cpu",compute_type="int8")
    tmp=pathlib.Path(tempfile.mkdtemp(prefix="gg-rvc-select-"))
    rows=[]

    # First score guide + every RVC candidate phrase-by-phrase.
    for ph in score["phrases"]:
        target=" ".join(w["text"] for w in ph["words"])
        st,en=phrase_bounds(score,ph,to_sec)
        a=max(0,int(st*sr)); b=min(n,int(en*sr))
        gscore=score_text(model,guide[a:b],sr,target,tmp/f"{ph['id']}-guide.wav")
        vals={}
        for label,y in bank.items():
            vals[label]=score_text(model,y[a:b],sr,target,tmp/f"{ph['id']}-{label}.wav")
        best_label=min(vals,key=lambda k:(vals[k]["cer"],vals[k]["wer"]))
        row={"id":ph["id"],"target":target,"start":st,"end":en,
             "guide":gscore,"candidates":vals,"best_label":best_label,
             "best":vals[best_label],"selection":"candidate"}
        rows.append(row)

    # Preserve repeated lyric identity: if one occurrence is materially clearer,
    # allow its candidate realization to seed the weaker repeated occurrence.
    by_text={}
    for row in rows: by_text.setdefault(norm(row["target"]),[]).append(row)

    # Assemble from the globally best median candidate as neutral base.
    med={}
    for label in bank:
        vals=[r["candidates"][label]["cer"] for r in rows]
        med[label]=float(np.median(vals))
    base_label=min(med,key=med.get)
    out=bank[base_label].copy()
    repair_rows=[]
    blend_gains=[0.05,0.08,0.12,0.16,0.22,0.30]

    for row in rows:
        a=max(0,int(row["start"]*sr)); b=min(n,int(row["end"]*sr)); target=row["target"]
        current=score_text(model,out[a:b],sr,target,tmp/f"{row['id']}-current.wav")
        options=[]
        # Direct protect variants.
        for label,y in bank.items():
            s=row["candidates"][label]
            options.append((s["cer"],s["wer"],"candidate",label,y[a:b].copy(),s))
        # Repeated-lyric reuse from a clearer occurrence of the same text.
        group=by_text[norm(target)]
        for other in group:
            if other["id"]==row["id"]: continue
            label=other["best_label"]
            oy=bank[label]
            oa=max(0,int(other["start"]*sr)); ob=min(n,int(other["end"]*sr))
            src=oy[oa:ob].copy()
            if len(src)>1:
                old=np.linspace(0,1,len(src)); new=np.linspace(0,1,b-a)
                src=np.interp(new,old,src).astype(np.float32)
                ss=score_text(model,src,sr,target,tmp/f"{row['id']}-reuse-{other['id']}.wav")
                options.append((ss["cer"],ss["wer"],"repeat",f"{other['id']}:{label}",src,ss))
        # Phrase-local guide blend is allowed only if the guide itself passes.
        if row["guide"]["cer"]<=args.threshold:
            best_direct=min(options,key=lambda x:(x[0],x[1]))
            seed=best_direct[4]; g=guide[a:b].copy()
            if len(g)!=len(seed):
                old=np.linspace(0,1,len(g)); new=np.linspace(0,1,len(seed))
                g=np.interp(new,old,g).astype(np.float32)
            fade=max(1,int(0.045*sr)); env=np.ones(len(seed),dtype=np.float32)
            if len(seed)>=2*fade:
                env[:fade]=np.linspace(0,1,fade,endpoint=False)
                env[-fade:]=np.linspace(1,0,fade,endpoint=False)
            for gain in blend_gains:
                mix=seed+g*(gain*env)
                peak=np.max(np.abs(mix)) if len(mix) else 0
                if peak>.985: mix*=.985/peak
                ss=score_text(model,mix,sr,target,tmp/f"{row['id']}-blend-{gain:.2f}.wav")
                options.append((ss["cer"],ss["wer"],"blend",f"{best_direct[3]}+g{gain:.2f}",mix,ss))

        winner=min(options,key=lambda x:(x[0],x[1],0 if x[2]=="candidate" else 1))
        applied=False
        # Only replace when we improve the current phrase, and never use guide-based
        # repair when the guide itself fails the strict gate.
        if winner[0] < current["cer"]-1e-9:
            crossfade_replace(out,a,b,winner[4],sr); applied=True
        repair_rows.append({
            "id":row["id"],"target":target,"guide":row["guide"],"before":current,
            "winner":{"cer":winner[0],"wer":winner[1],"kind":winner[2],
                      "source":winner[3],"transcript":winner[5]["transcript"]},
            "applied":applied
        })

    # Final actual assembled readback.
    final=[]
    for ph in score["phrases"]:
        target=" ".join(w["text"] for w in ph["words"])
        st,en=phrase_bounds(score,ph,to_sec); a=max(0,int(st*sr)); b=min(n,int(en*sr))
        ss=score_text(model,out[a:b],sr,target,tmp/f"{ph['id']}-final.wav")
        final.append({"id":ph["id"],"target":target,**ss})
    sf.write(args.output,out,sr,subtype="PCM_24")
    guide_bad=[{"id":r["id"],"cer":r["guide"]["cer"],"transcript":r["guide"]["transcript"]}
               for r in rows if r["guide"]["cer"]>args.threshold]
    d_bad=[{"id":r["id"],"cer":r["cer"],"transcript":r["transcript"]}
           for r in final if r["cer"]>args.threshold]
    report={
      "threshold":args.threshold,"base_label":base_label,"candidate_median_cer":med,
      "guide_blockers":guide_bad,"repairs":repair_rows,"final":final,
      "unresolved":d_bad,
      "status":"PASS" if not guide_bad and not d_bad else "REJECT"
    }
    pathlib.Path(args.report).write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report["status"]=="PASS" else 2

if __name__=="__main__":
    raise SystemExit(main())
