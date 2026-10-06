#!/usr/bin/env python3
import argparse,json,pathlib,re,tempfile
import numpy as np, soundfile as sf
from faster_whisper import WhisperModel
from jiwer import wer,cer

def norm(s):
    s=s.lower().replace("ё","е")
    s=re.sub(r"[^а-я0-9 ]+"," ",s)
    return re.sub(r"\s+"," ",s).strip()

def converter(score):
    tpb=score["ticks_per_beat"]; bar=tpb*4
    pts=sorted(score.get("tempo_map") or [{"bar":0,"bpm":score["bpm"]}],key=lambda x:x["bar"])
    pts=[(int(p["bar"])*bar,float(p["bpm"])) for p in pts]
    def sec(tick):
        total=0.0; last=0; bpm=pts[0][1]
        for pos,nbpm in pts[1:]:
            if tick<=pos: break
            total+=(pos-last)*60.0/(bpm*tpb); last=pos; bpm=nbpm
        return total+(tick-last)*60.0/(bpm*tpb)
    return sec

def bounds(score,ph,to_sec):
    tpb=score["ticks_per_beat"]; bar=tpb*4
    st=ph["bar"]*bar+ph["offset"]; en=st
    for w in ph["words"]: en+=sum(w["durations"])+w["rest"]
    return max(0,to_sec(st)-0.12),to_sec(en)+0.18

def tx(model,y,sr,path):
    sf.write(path,y,sr)
    segs,_=model.transcribe(str(path),language="ru",beam_size=5,vad_filter=False,
                            condition_on_previous_text=False,temperature=0.0)
    return " ".join(x.text.strip() for x in list(segs)).strip()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--score",required=True); ap.add_argument("--input",required=True)
    ap.add_argument("--output",required=True); ap.add_argument("--report",required=True)
    a=ap.parse_args()
    score=json.loads(pathlib.Path(a.score).read_text())
    y,sr=sf.read(a.input,always_2d=False)
    if getattr(y,"ndim",1)>1:y=y.mean(axis=1)
    y=np.asarray(y,dtype=np.float32); out=y.copy(); to_sec=converter(score)
    model=WhisperModel("small",device="cpu",compute_type="int8")
    td=pathlib.Path(tempfile.mkdtemp(prefix="gg-guide-id-"))
    rows=[]
    for ph in score["phrases"]:
        target=" ".join(w["text"] for w in ph["words"]); nt=norm(target)
        st,en=bounds(score,ph,to_sec); i=max(0,int(st*sr)); j=min(len(y),int(en*sr))
        txt=tx(model,y[i:j],sr,td/f"{ph['id']}-pre.wav")
        rows.append({"id":ph["id"],"target":target,"start":st,"end":en,"i":i,"j":j,
                     "transcript":txt,"wer":float(wer(nt,norm(txt))),"cer":float(cer(nt,norm(txt)))})
    groups={}
    for r in rows: groups.setdefault(norm(r["target"]),[]).append(r)
    repairs=[]
    for key,grp in groups.items():
        if len(grp)<2: continue
        best=min(grp,key=lambda x:(x["cer"],x["wer"]))
        if best["cer"]>0.20: continue
        src=y[best["i"]:best["j"]].copy()
        for dst in grp:
            if dst["id"]==best["id"] or dst["cer"]<=0.20: continue
            n=dst["j"]-dst["i"]
            if len(src)<2 or n<2: continue
            xx=np.linspace(0,1,len(src)); yy=np.linspace(0,1,n)
            rep=np.interp(yy,xx,src).astype(np.float32)
            fade=max(1,int(0.060*sr))
            fade=min(fade,n//3)
            w=np.ones(n,dtype=np.float32)
            if fade>1:
                w[:fade]=np.linspace(0,1,fade,endpoint=False)
                w[-fade:]=np.linspace(1,0,fade,endpoint=False)
            out[dst["i"]:dst["j"]]=out[dst["i"]:dst["j"]]*(1-w)+rep*w
            repairs.append({"target":dst["target"],"source_id":best["id"],"target_id":dst["id"],
                            "source_cer":best["cer"],"target_pre_cer":dst["cer"]})
    post=[]
    for ph in score["phrases"]:
        target=" ".join(w["text"] for w in ph["words"]); nt=norm(target)
        st,en=bounds(score,ph,to_sec); i=max(0,int(st*sr)); j=min(len(out),int(en*sr))
        txt=tx(model,out[i:j],sr,td/f"{ph['id']}-post.wav")
        post.append({"id":ph["id"],"target":target,"transcript":txt,
                     "wer":float(wer(nt,norm(txt))),"cer":float(cer(nt,norm(txt)))})
    sf.write(a.output,out,sr,subtype="PCM_24")
    pathlib.Path(a.report).write_text(json.dumps({"repairs":repairs,"pre":rows,"post":post},ensure_ascii=False,indent=2))
    print(json.dumps({"repairs":repairs,"post_max_cer":max(x["cer"] for x in post)},ensure_ascii=False,indent=2))

if __name__=="__main__": main()
