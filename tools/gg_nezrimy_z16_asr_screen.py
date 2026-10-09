#!/usr/bin/env python3
"""Strict blind lyric ASR screen for Z16 dry vocal variants (not artistic proof)."""
import json,pathlib,re,unicodedata,math,os
from faster_whisper import WhisperModel
from rapidfuzz.distance import Levenshtein
INPUT=pathlib.Path("z16_opening_out")
EXPECTED="мы встретились с тобой как люди видятся во сне"
def norm(s):
 s=unicodedata.normalize("NFKC",s.lower().replace("ё","е"))
 return " ".join(re.sub(r"[^а-я ]+"," ",s).split())
def main():
 model=WhisperModel("small",device="cpu",compute_type="int8",num_workers=2,cpu_threads=4)
 results=[]
 for p in sorted(INPUT.glob("*matched.wav"))+sorted(INPUT.glob("*AUTHENTIC_UNCHANGED.wav")):
  segs,info=model.transcribe(str(p),language="ru",beam_size=4,temperature=0,
       vad_filter=False,condition_on_previous_text=False,word_timestamps=False)
  pieces=list(segs)
  txt=" ".join(x.text for x in pieces)
  clean=norm(txt); exp=norm(EXPECTED)
  cer=Levenshtein.distance(clean,exp)/max(len(exp),1)
  wer=Levenshtein.distance(clean.split(),exp.split())/len(exp.split())
  item={"file":p.name,"recognized":txt,"normalized":clean,"CER":round(cer,4),"WER":round(wer,4),
        "nonempty":bool(clean),"language":info.language,"duration":round(info.duration,3)}
  results.append(item)
  print("Z16_ASR_SCREEN",p.name,repr(txt),round(cer,3),round(wer,3),flush=True)
 (INPUT/"Z16_RUSSIAN_ASR_SCREEN.json").write_text(json.dumps(
    {"expected":EXPECTED,"gate":"advisory: recognition is a reject filter, not human artistic approval","results":results},ensure_ascii=False,indent=2))
if __name__=="__main__":main()
