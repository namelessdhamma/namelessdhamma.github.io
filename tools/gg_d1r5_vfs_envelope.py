#!/usr/bin/env python3
import argparse,json,pathlib
import numpy as np, soundfile as sf

def converter(score):
    tpb=score["ticks_per_beat"]; bar=tpb*4
    pts=sorted(score.get("tempo_map") or [{"bar":0,"bpm":score["bpm"]}],key=lambda x:x["bar"])
    pts=[(int(p["bar"])*bar,float(p["bpm"])) for p in pts]
    def sec(tick):
        total=0.0; last=0; bpm=pts[0][1]
        for pos,nbpm in pts[1:]:
            if tick<=pos: break
            total+=(pos-last)*60.0/(bpm*tpb); last=pos; bpm=nbpm
        total+=(tick-last)*60.0/(bpm*tpb)
        return total
    return sec

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",required=True); ap.add_argument("--score",required=True)
    ap.add_argument("--output",required=True); ap.add_argument("--report",required=True)
    a=ap.parse_args()
    y,sr=sf.read(a.input,always_2d=False)
    if getattr(y,"ndim",1)>1: y=y.mean(axis=1)
    y=np.asarray(y,dtype=np.float32); score=json.loads(pathlib.Path(a.score).read_text())
    tpb=score["ticks_per_beat"]; bar=tpb*4; to_sec=converter(score)
    section_first={"v1l1","c1l1","v2l1","c2l1","brl1","finl1","codal1"}
    semantic=set(score.get("d1r5",{}).get("semantic_accent_words",[]))
    rows=[]
    for ph in score["phrases"]:
        st_tick=ph["bar"]*bar+ph["offset"]; en_tick=st_tick
        for w in ph["words"]: en_tick+=sum(w["durations"])+w["rest"]
        st=to_sec(st_tick); en=to_sec(en_tick)
        a0=max(0,int(st*sr)); b0=min(len(y),int(en*sr))
        if b0<=a0: continue
        seglen=b0-a0
        env=np.ones(seglen,dtype=np.float32)
        if ph["id"] in section_first:
            # audible emergence: start around -9 dB, relaxed rise to body.
            attack=min(seglen,max(1,int(0.62*sr)))
            env[:attack]=np.linspace(10**(-9/20),1.0,attack,dtype=np.float32)
        else:
            # ordinary phrases keep a smaller natural entrance.
            attack=min(seglen,max(1,int(0.16*sr)))
            env[:attack]=np.linspace(10**(-3.5/20),1.0,attack,dtype=np.float32)
        release=min(seglen,max(1,int(0.20*sr)))
        tail=np.linspace(1.0,10**(-4.5/20),release,dtype=np.float32)
        env[-release:]=np.minimum(env[-release:],tail)

        # Semantic Expression stays separate from Voice Identity: a small,
        # deterministic post-RVC gain emphasis around the stressed syllable.
        # It never shifts lexical stress, pitch or score timing.
        p=st_tick
        accents=[]
        for w in ph["words"]:
            ds=w["durations"]; stress=int(w["stress"])
            stress_tick=p+sum(ds[:stress])
            stress_dur=ds[stress]
            if w["text"] in semantic:
                center=to_sec(stress_tick+stress_dur//2)-st
                ci=int(center*sr)
                radius=max(1,int(0.16*sr))
                lo=max(0,ci-radius); hi=min(seglen,ci+radius+1)
                if hi>lo:
                    x=np.linspace(-1,1,hi-lo,dtype=np.float32)
                    bump=1.0+(10**(1.8/20)-1.0)*np.exp(-3.2*x*x)
                    env[lo:hi]*=bump
                    accents.append({"word":w["text"],"center_s":float(center),"gain_db":1.8})
            p+=sum(ds)+int(w["rest"])
        before=float(np.sqrt(np.mean(y[a0:b0]**2)+1e-12))
        y[a0:b0]*=env
        after=float(np.sqrt(np.mean(y[a0:b0]**2)+1e-12))
        rows.append({"id":ph["id"],"start":st,"end":en,"section_open":ph["id"] in section_first,
                     "semantic_accents":accents,"rms_before":before,"rms_after":after})
    peak=float(np.max(np.abs(y))) if len(y) else 0.0
    if peak>0.985: y*=0.985/peak
    sf.write(a.output,y,sr,subtype="PCM_24")
    pathlib.Path(a.report).write_text(json.dumps({"status":"PASS","rows":rows,"peak":float(np.max(np.abs(y)))},ensure_ascii=False,indent=2))
if __name__=="__main__": main()