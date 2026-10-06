#!/usr/bin/env python3
import argparse, json, pathlib, re, tempfile
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

def tempo_converter(score):
    tpb=score["ticks_per_beat"]; bar=tpb*4
    pts=sorted(score.get("tempo_map") or [{"bar":0,"bpm":score["bpm"]}],key=lambda x:int(x["bar"]))
    pts=[(int(p["bar"])*bar,float(p["bpm"])) for p in pts]
    def sec(tick):
        total=0.0; last=0; bpm=pts[0][1]
        for pos,nbpm in pts[1:]:
            if tick<=pos: break
            total+=(pos-last)*60.0/(bpm*tpb); last=pos; bpm=nbpm
        total+=(tick-last)*60.0/(bpm*tpb)
        return total
    return sec

def transcribe(model,y,sr,tmp):
    sf.write(tmp,y,sr)
    segs,_=model.transcribe(str(tmp),language="ru",beam_size=5,vad_filter=False,
                            condition_on_previous_text=False,temperature=0.0)
    return " ".join(x.text.strip() for x in list(segs)).strip()

def phrase_bounds(score,ph,to_sec):
    tpb=score["ticks_per_beat"]; bar=tpb*4
    st=ph["bar"]*bar+ph["offset"]; en=st
    for w in ph["words"]: en+=sum(w["durations"])+w["rest"]
    return max(0,to_sec(st)-0.12),to_sec(en)+0.18

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--score",required=True); ap.add_argument("--guide",required=True)
    ap.add_argument("--raw-d",required=True); ap.add_argument("--out",required=True)
    ap.add_argument("--report",required=True); ap.add_argument("--threshold",type=float,default=0.20)
    args=ap.parse_args()
    score=json.loads(pathlib.Path(args.score).read_text())
    g,srg=load_mono(args.guide); d,srd=load_mono(args.raw_d)
    if srg!=srd:
        from math import gcd
        gg=gcd(srg,srd)
        g=resample_poly(g,srd//gg,srg//gg).astype(np.float32)
        srg=srd
    sr=srd; n=max(len(g),len(d))
    g=np.pad(g,(0,n-len(g))); d=np.pad(d,(0,n-len(d)))
    out=d.copy(); to_sec=tempo_converter(score); model=WhisperModel("small",device="cpu",compute_type="int8")
    rows=[]; tmpdir=pathlib.Path(tempfile.mkdtemp(prefix="gg-d1r5-repair-"))
    gains=[0.05,0.08,0.12,0.16,0.22,0.30]
    # Cache guide phrases so repeated lyrics can reuse the clearer realization.
    guide_cache={}
    for ph in score["phrases"]:
        target=" ".join(w["text"] for w in ph["words"]); nt=norm(target)
        st,en=phrase_bounds(score,ph,to_sec); a=max(0,int(st*sr)); b=min(n,int(en*sr))
        seg=g[a:b].copy()
        txt=transcribe(model,seg,sr,tmpdir/f"{ph['id']}-guide.wav")
        guide_cache[ph["id"]]={"target":target,"audio":seg,"transcript":txt,
                               "wer":float(wer(nt,norm(txt))),"cer":float(cer(nt,norm(txt)))}
    best_guide_by_target={}
    for ph in score["phrases"]:
        z=guide_cache[ph["id"]]; key=norm(z["target"])
        if key not in best_guide_by_target or (z["cer"],z["wer"]) < (best_guide_by_target[key]["cer"],best_guide_by_target[key]["wer"]):
            best_guide_by_target[key]=z
    for ph in score["phrases"]:
        target=" ".join(w["text"] for w in ph["words"]); nt=norm(target)
        st,en=phrase_bounds(score,ph,to_sec); a=max(0,int(st*sr)); b=min(n,int(en*sr))
        base=out[a:b].copy()
        txt=transcribe(model,base,sr,tmpdir/f"{ph['id']}-base.wav")
        baseline={"gain":0.0,"transcript":txt,"wer":float(wer(nt,norm(txt))),"cer":float(cer(nt,norm(txt)))}
        candidates=[baseline]
        if baseline["cer"]>args.threshold:
            guide=g[a:b]
            source_kind="same_phrase"
            alt=best_guide_by_target.get(norm(target))
            if alt is not None and alt["cer"] < guide_cache[ph["id"]]["cer"]:
                src=alt["audio"]
                if len(src)>1 and len(guide)>1 and len(src)!=len(guide):
                    x=np.linspace(0,1,len(src),endpoint=True)
                    xx=np.linspace(0,1,len(guide),endpoint=True)
                    guide=np.interp(xx,x,src).astype(np.float32)
                else:
                    guide=src[:len(guide)]
                source_kind="best_identical_lyric"
            fade=max(1,int(0.045*sr))
            env=np.ones(len(base),dtype=np.float32)
            if len(base)>=2*fade:
                env[:fade]=np.linspace(0,1,fade,endpoint=False)
                env[-fade:]=np.linspace(1,0,fade,endpoint=False)
            for gain in gains:
                mix=base + guide*(gain*env)
                peak=np.max(np.abs(mix)) if len(mix) else 0
                if peak>.985: mix*=.985/peak
                t=transcribe(model,mix,sr,tmpdir/f"{ph['id']}-g{int(gain*100):02d}.wav")
                candidates.append({"gain":gain,"source":source_kind,"transcript":t,
                                   "wer":float(wer(nt,norm(t))),"cer":float(cer(nt,norm(t)))})
        winner=min(candidates,key=lambda x:(x["cer"],x["wer"],x["gain"]))
        applied=False
        if baseline["cer"]>args.threshold and winner["cer"]<=args.threshold and winner["cer"]<baseline["cer"]:
            guide=g[a:b]
            alt=best_guide_by_target.get(norm(target))
            if alt is not None and alt["cer"] < guide_cache[ph["id"]]["cer"]:
                src=alt["audio"]
                if len(src)>1 and len(guide)>1 and len(src)!=len(guide):
                    x=np.linspace(0,1,len(src),endpoint=True); xx=np.linspace(0,1,len(guide),endpoint=True)
                    guide=np.interp(xx,x,src).astype(np.float32)
                else: guide=src[:len(guide)]
            fade=max(1,int(0.045*sr)); env=np.ones(len(base),dtype=np.float32)
            if len(base)>=2*fade:
                env[:fade]=np.linspace(0,1,fade,endpoint=False); env[-fade:]=np.linspace(1,0,fade,endpoint=False)
            repaired=base+guide*(winner["gain"]*env)
            peak=np.max(np.abs(repaired)) if len(repaired) else 0
            if peak>.985: repaired*=.985/peak
            out[a:b]=repaired; applied=True
        rows.append({"id":ph["id"],"target":target,"start":st,"end":en,
                     "baseline":baseline,"winner":winner,"applied":applied,"candidates":candidates})
    # Recheck the actual assembled output phrase by phrase.
    final=[]
    for ph in score["phrases"]:
        target=" ".join(w["text"] for w in ph["words"]); nt=norm(target)
        st,en=phrase_bounds(score,ph,to_sec); a=max(0,int(st*sr)); b=min(n,int(en*sr))
        txt=transcribe(model,out[a:b],sr,tmpdir/f"{ph['id']}-final.wav")
        final.append({"id":ph["id"],"target":target,"transcript":txt,
                      "wer":float(wer(nt,norm(txt))),"cer":float(cer(nt,norm(txt)))})
    sf.write(args.out,out,sr,subtype="PCM_24")
    unresolved=[x for x in final if x["cer"]>args.threshold]
    report={"threshold":args.threshold,
            "guide":[{"id":ph["id"],"target":guide_cache[ph["id"]]["target"],
                      "transcript":guide_cache[ph["id"]]["transcript"],
                      "wer":guide_cache[ph["id"]]["wer"],"cer":guide_cache[ph["id"]]["cer"]} for ph in score["phrases"]],
            "repairs":rows,"final":final,
            "unresolved":[{"id":x["id"],"cer":x["cer"],"transcript":x["transcript"]} for x in unresolved],
            "status":"PASS" if not unresolved else "REJECT"}
    pathlib.Path(args.report).write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if not unresolved else 2

if __name__=="__main__":
    raise SystemExit(main())