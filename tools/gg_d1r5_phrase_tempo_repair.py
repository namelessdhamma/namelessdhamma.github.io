#!/usr/bin/env python3
import argparse,json,pathlib,re,tempfile,subprocess
import numpy as np
import soundfile as sf
from faster_whisper import WhisperModel
from jiwer import wer,cer

def norm(s):
    s=s.lower().replace("ё","е")
    s=re.sub(r"[^а-я0-9 ]+"," ",s)
    return re.sub(r"\s+"," ",s).strip()

def converter(score):
    tpb=score["ticks_per_beat"]; BAR=tpb*4
    pts=sorted(score.get("tempo_map") or [{"bar":0,"bpm":score["bpm"]}],key=lambda x:x["bar"])
    pts=[(int(p["bar"])*BAR,float(p["bpm"])) for p in pts]
    def sec(tick):
        total=0.0; last=0; bpm=pts[0][1]
        for pos,nbpm in pts[1:]:
            if tick<=pos: break
            total+=(pos-last)*60.0/(bpm*tpb); last=pos; bpm=nbpm
        return total+(tick-last)*60.0/(bpm*tpb)
    return sec

def phrase_ticks(score,ph):
    tpb=score["ticks_per_beat"]; BAR=tpb*4
    st=ph["bar"]*BAR+ph["offset"]; en=st
    for w in ph["words"]: en+=sum(w["durations"])+w["rest"]
    return st,en

def tx(model,x,sr,path,target):
    sf.write(path,x,sr)
    segs,_=model.transcribe(str(path),language="ru",beam_size=5,vad_filter=False,
                            condition_on_previous_text=False,temperature=0.0)
    text=" ".join(s.text.strip() for s in list(segs)).strip()
    nt,nr=norm(target),norm(text)
    return {"transcript":text,"wer":float(wer(nt,nr)),"cer":float(cer(nt,nr))}

def atempo(x,sr,speed,tmp):
    # ffmpeg atempo preserves pitch. speed<1 = slower/longer.
    inp=tmp/"in.wav"; out=tmp/f"out-{speed:.2f}.wav"
    sf.write(inp,x,sr)
    subprocess.run(["ffmpeg","-y","-v","error","-i",str(inp),"-af",f"atempo={speed:.4f}",
                    "-ar",str(sr),"-ac","1",str(out)],check=True)
    y,ysr=sf.read(out,always_2d=False)
    if getattr(y,"ndim",1)>1:y=y.mean(axis=1)
    return np.asarray(y,dtype=np.float32)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--score",required=True);ap.add_argument("--input",required=True)
    ap.add_argument("--output",required=True);ap.add_argument("--report",required=True)
    ap.add_argument("--threshold",type=float,default=.20)
    ap.add_argument("--speeds",default="0.97,0.94,0.91,0.88,0.85")
    a=ap.parse_args()
    score=json.loads(pathlib.Path(a.score).read_text())
    y,sr=sf.read(a.input,always_2d=False)
    if getattr(y,"ndim",1)>1:y=y.mean(axis=1)
    y=np.asarray(y,dtype=np.float32);out=y.copy();to_sec=converter(score)
    model=WhisperModel("small",device="cpu",compute_type="int8")
    td=pathlib.Path(tempfile.mkdtemp(prefix="gg-tempo-repair-"))
    speeds=[float(x) for x in a.speeds.split(",") if x.strip()]
    rows=[]
    for idx,ph in enumerate(score["phrases"]):
        target=" ".join(w["text"] for w in ph["words"])
        st_tick,en_tick=phrase_ticks(score,ph); st=to_sec(st_tick); en=to_sec(en_tick)
        next_st=(to_sec(phrase_ticks(score,score["phrases"][idx+1])[0])
                 if idx+1<len(score["phrases"]) else len(y)/sr)
        # leave 120 ms safety before the next lexical phrase
        max_end=max(en,next_st-.12)
        i=max(0,int(st*sr)); j=min(len(out),int(en*sr))
        base=out[i:j].copy()
        pre=tx(model,base,sr,td/f"{ph['id']}-pre.wav",target)
        options=[{"speed":1.0,"audio":base,"end":en,**pre}]
        if pre["cer"]>a.threshold:
            for speed in speeds:
                cand=atempo(base,sr,speed,td/f"{ph['id']}-{speed:.2f}")
                cand_end=st+len(cand)/sr
                if cand_end>max_end: continue
                sc=tx(model,cand,sr,td/f"{ph['id']}-{speed:.2f}-asr.wav",target)
                options.append({"speed":speed,"audio":cand,"end":cand_end,**sc})
        winner=min(options,key=lambda z:(z["cer"],z["wer"],abs(1-z["speed"])))
        applied=False
        if pre["cer"]>a.threshold and winner["cer"]<=a.threshold and winner["cer"]<pre["cer"]:
            k=min(len(out),i+len(winner["audio"]))
            src=winner["audio"][:k-i]
            fade=min(max(1,int(.055*sr)),max(1,len(src)//4))
            env=np.ones(len(src),dtype=np.float32)
            if len(src)>=2*fade:
                env[:fade]=np.linspace(0,1,fade,endpoint=False)
                env[-fade:]=np.linspace(1,0,fade,endpoint=False)
            # Clear original tail / free phrase gap before writing extended phrase.
            out[i:k]*=(1-env)
            out[i:k]+=src*env
            applied=True
        rows.append({"id":ph["id"],"target":target,"pre":pre,
                     "winner":{k:v for k,v in winner.items() if k!="audio"},
                     "applied":applied,
                     "tested":[{k:v for k,v in z.items() if k!="audio"} for z in options]})
    sf.write(a.output,out,sr,subtype="PCM_24")
    pathlib.Path(a.report).write_text(json.dumps({"repairs":rows},ensure_ascii=False,indent=2))
    print(json.dumps({"applied":[{"id":r["id"],**r["winner"]} for r in rows if r["applied"]]},ensure_ascii=False,indent=2))
if __name__=="__main__":main()
