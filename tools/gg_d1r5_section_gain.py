#!/usr/bin/env python3
import argparse,json,pathlib,math
import numpy as np, soundfile as sf

def converter(score):
    tpb=score["ticks_per_beat"]; BAR=tpb*4
    pts=sorted(score.get("tempo_map") or [{"bar":0,"bpm":score["bpm"]}],key=lambda x:int(x["bar"]))
    pts=[(int(p["bar"])*BAR,float(p["bpm"])) for p in pts]
    def sec(tick):
        total=0.0; last=0; bpm=pts[0][1]
        for pos,nbpm in pts[1:]:
            if tick<=pos: break
            total+=(pos-last)*60.0/(bpm*tpb); last=pos; bpm=nbpm
        return total+(tick-last)*60.0/(bpm*tpb)
    return sec

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",required=True);ap.add_argument("--score",required=True)
    ap.add_argument("--output",required=True);ap.add_argument("--section",default="chorus_I")
    ap.add_argument("--gain-db",type=float,default=.45);ap.add_argument("--fade-ms",type=float,default=140)
    a=ap.parse_args()
    y,sr=sf.read(a.input,always_2d=False)
    score=json.loads(pathlib.Path(a.score).read_text())
    form=score["form"][a.section]; start_bar,end_bar=form
    tpb=score["ticks_per_beat"]; BAR=tpb*4; to_sec=converter(score)
    t0=to_sec(start_bar*BAR); t1=to_sec((end_bar+1)*BAR)
    i=max(0,int(t0*sr)); j=min(len(y),int(t1*sr))
    env=np.ones(len(y),dtype=np.float32); gain=10**(a.gain_db/20)
    env[i:j]=gain
    fade=max(1,int(a.fade_ms/1000*sr))
    if i>0:
        lo=max(0,i-fade); env[lo:i]=np.linspace(1,gain,i-lo,endpoint=False)
    if j<len(y):
        hi=min(len(y),j+fade); env[j:hi]=np.linspace(gain,1,hi-j,endpoint=False)
    if getattr(y,"ndim",1)>1: env=env[:,None]
    out=np.asarray(y,dtype=np.float32)*env
    peak=float(np.max(np.abs(out))) if len(out) else 0
    if peak>.985: out*=.985/peak
    sf.write(a.output,out,sr,subtype="PCM_24")
    print(json.dumps({"section":a.section,"start_s":t0,"end_s":t1,"gain_db":a.gain_db,
                      "peak":float(np.max(np.abs(out)))},indent=2))
if __name__=="__main__":main()
