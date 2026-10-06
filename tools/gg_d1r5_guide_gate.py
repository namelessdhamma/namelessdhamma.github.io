#!/usr/bin/env python3
import argparse,json,pathlib,re,tempfile
import soundfile as sf
from faster_whisper import WhisperModel
from jiwer import wer,cer

def norm(s):
    s=s.lower().replace("ё","е")
    s=re.sub(r"[^а-я0-9 ]+"," ",s)
    return re.sub(r"\s+"," ",s).strip()

def converter(score):
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

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--score",required=True); ap.add_argument("--guide",required=True)
    ap.add_argument("--out",required=True); ap.add_argument("--threshold",type=float,default=.20)
    a=ap.parse_args()
    score=json.loads(pathlib.Path(a.score).read_text())
    y,sr=sf.read(a.guide,always_2d=False)
    if getattr(y,"ndim",1)>1:y=y.mean(axis=1)
    model=WhisperModel("small",device="cpu",compute_type="int8")
    to_sec=converter(score); tpb=score["ticks_per_beat"]; BAR=tpb*4
    rows=[]; td=pathlib.Path(tempfile.mkdtemp(prefix="gg-guide-gate-"))
    for ph in score["phrases"]:
        st=ph["bar"]*BAR+ph["offset"]; en=st
        for w in ph["words"]: en+=sum(w["durations"])+w["rest"]
        t0=max(0,to_sec(st)-.12); t1=min(len(y)/sr,to_sec(en)+.18)
        seg=y[int(t0*sr):int(t1*sr)]
        p=td/f"{ph['id']}.wav"; sf.write(p,seg,sr)
        ss,_=model.transcribe(str(p),language="ru",beam_size=5,vad_filter=False,
                              condition_on_previous_text=False,temperature=0.0)
        txt=" ".join(x.text.strip() for x in list(ss)).strip()
        target=" ".join(w["text"] for w in ph["words"])
        nt,nr=norm(target),norm(txt)
        rows.append({"id":ph["id"],"target":target,"transcript":txt,
                     "wer":float(wer(nt,nr)),"cer":float(cer(nt,nr)),
                     "start":t0,"end":t1})
    bad=[x for x in rows if x["cer"]>a.threshold]
    result={"status":"PASS" if not bad else "REJECT","threshold":a.threshold,
            "max_phrase_cer":max(x["cer"] for x in rows),"phrases":rows,
            "blockers":[{"id":x["id"],"cer":x["cer"],"transcript":x["transcript"]} for x in bad]}
    pathlib.Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if not bad else 2
if __name__=="__main__": raise SystemExit(main())
