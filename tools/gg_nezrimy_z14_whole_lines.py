#!/usr/bin/env python3
"""Z13: actual phoneme-source replacement, not filtering/RVC/envelope cosmetics.
Target melody anchored to accepted C3R1 D1 score. Render only rejected words.
This script does not claim human intelligibility approval.
"""
import os, pathlib, urllib.request, zipfile, json, math, hashlib, subprocess, sys, shutil
import numpy as np
from tools.gg_cloud_music_worker import install_vocal_stack, install_awata_ezv, normalize_character_yaml

ROOT=pathlib.Path(os.getcwd())
OUT=ROOT/"z14_whole_lines_out";OUT.mkdir(exist_ok=True)
CACHE=ROOT/".gg-awata-ds-cache";CACHE.mkdir(exist_ok=True)
URL="https://github.com/hhskt/Awata_Weak/releases/download/diffsinger_v3.0/Awata_Weak_DS_v3.zip"
SR=48000
def target(tag,text,start,notes,ticks,groups,stressed=None):
 assert len(notes)==len(ticks)==len(groups)
 assert all(isinstance(g,list) and g for g in groups)
 return dict(tag=tag,text=text,start=round(start,6),notes=notes,ticks=ticks,groups=groups,stressed=stressed)
T=[
 target("opening_whole_line","Мы встретились с тобой, как люди видятся во сне",9.1666667,
    [64,64,64,62,64,67,69,0,67,67,65,64,64,62,62,64],
    [480,240,240,240,45,240,675,240,240,240,240,240,240,240,240,720],
    [["m","y"],["v","s","t","ry","e"],["ty","i"],["ly","i","sy"],["s"],
     ["t","a"],["b","o","j"],["SP"],["k","a","k"],["ly","u"],["dy","i"],
     ["vy","i"],["dy","a"],["t","sy","a"],["v","o"],["s","ny","e"]],14),
 target("tishine_whole_line","Два голоса блуждали в тишине",22.5,
    [62,62,62,65,65,64,64,64,64,64,68],
    [240,240,240,480,240,480,240,240,240,240,720],
    [["d","v","a"],["g","o"],["l","o"],["s","a"],["b","l","u","zh"],
     ["d","a"],["ly","i"],["v"],["ty","i"],["sh","i"],["ny","e"]],10),
]
CONSONANTS={"b","j","v","vy","t","ty","s","sy","z","zh","sh","ch","k","g","d","dy","p","r","ry","l","ly","m","my","n","ny","f"}
def nname(midi):
 names=["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
 return "rest" if midi == 0 else names[midi%12]+str(midi//12-1)
def build_score(t):
 # Rebuild the phonemes themselves: an entirely new sound source with the exact source melody.
 # Distinct variants of видятся explicitly increase the perceptual /дя/ vowel.
 before=.070;after=.150
 dur=[before]+[int(k)/480*60/108 for k in t["ticks"]]+[after]
 notes=["rest"]+[nname(x) for x in t["notes"]]+["rest"]
 groups=[["SP"]]+[["SP" if p=="SP" else "ru/"+p for p in gp] for gp in t["groups"]]+[["SP"]]
 phdur=[]
 for idx,(g,d) in enumerate(zip(groups,dur)):
  if idx in (0,len(groups)-1):
   phdur.append([d]);continue
  c=len(g)
  if c==1:phdur.append([d]);continue
  vowel_indexes=[i for i,p in enumerate(g) if p.split("/")[-1] in ("a","e","i","o","u","y")]
  # Consonants get actual reserved acoustic duration; vowels are NOT crossfaded in.
  weights=[]
  for j,p in enumerate(g):
   label=p.split("/")[-1]
   if label in ("b","vy") and t["tag"]=="nezabvennym": w=.075
   elif label in ("t","s","sy","p") and t["tag"] in ("vidyatsya_A","vidyatsya_B","tropy","pyl"):w=.060
   elif label in CONSONANTS:w=.047
   else:w=0
   weights.append(w)
  free=max(.07,d-sum(weights))
  if sum(weights)>d-.07:
   scale=(d-.07)/sum(weights); weights=[v*scale for v in weights]; free=.07
  if not vowel_indexes:
   weights=[d/c for _ in g]
  else:
   for j in vowel_indexes: weights[j]+=free/len(vowel_indexes)
  # Numerical exactness: adjust one vowel or final phone.
  weights[-1]+=d-sum(weights)
  if any(q<=0 for q in weights): raise ValueError((t["tag"],g,weights))
  phdur.append(weights)
 ph_seq=[z for g in groups for z in g]
 ph_num=[len(g) for g in groups]
 ph_dur=[v for g in phdur for v in g]
 assert len(ph_seq)==sum(ph_num)==len(ph_dur)
 assert abs(sum(ph_dur)-sum(dur))<1e-7
 # 10ms F0 ticks over 48kHz. Fixed notes, subtle note-local vibrato only.
 dt=.01; total=sum(dur);f0=[]
 for k in range(math.ceil(total/dt)):
  sec=k*dt
  ni=0;acc=0
  for i,d in enumerate(dur):
   if sec<acc+d:ni=i;local=sec-acc;break
   acc+=d
  else: ni=len(dur)-1;local=0
  if ni in (0,len(dur)-1) or t["notes"][ni-1]==0:f0.append(0.0);continue
  f=440*2**((t["notes"][ni-1]-69)/12)
  progress=local/max(dur[ni],.0001)
  vibrato=(.0015*math.sin(2*math.pi*5.4*local))*(math.sin(math.pi*progress)**2)
  f0.append(round(f*(1+vibrato),4))
 return dict(offset=0.0,text=t["text"],ph_seq=" ".join(ph_seq),
             ph_num=" ".join(map(str,ph_num)),
             ph_dur=" ".join(f"{v:.7f}" for v in ph_dur),
             note_seq=" ".join(notes),note_dur=" ".join(f"{v:.7f}" for v in dur),
             note_slur=" ".join("0" for _ in notes),
             f0_seq=" ".join(f"{v:.4f}" for v in f0),
             f0_timestep=str(dt))
def download_source():
 vb=CACHE/"voicebank"
 if list(vb.rglob("dsconfig.yaml")):return vb
 arc=CACHE/"Awata_Weak_DS_v3.zip"
 if not arc.exists():
  print("AWATA_DOWNLOAD_BEGIN",flush=True)
  urllib.request.urlretrieve(URL,arc)
  if arc.stat().st_size<1000000:raise ValueError("unexpected tiny bank")
  print("AWATA_DOWNLOAD_BYTES",arc.stat().st_size,flush=True)
 vb.mkdir(exist_ok=True)
 with zipfile.ZipFile(arc) as z:
  z.extractall(vb)
 if not list(vb.rglob("dsconfig.yaml")):raise RuntimeError("voicebank no dsconfig.yaml")
 return vb
def main():
 scores={}
 for t in T:
  sc=build_score(t);scores[t["tag"]]=sc
  assert len(sc["ph_seq"].split())==len(sc["ph_dur"].split())
 (OUT/"Z14_WHOLE_LINES.ds").write_text(json.dumps(list(scores.values()),ensure_ascii=False,indent=2))
 print("SCORE_GATES_PASS",[(t["tag"],len(scores[t["tag"]]["ph_seq"].split())) for t in T],flush=True)
 vbroot=download_source()
 dsconfig=next(vbroot.rglob("dsconfig.yaml"))
 vb=dsconfig.parent
 print("VOICEBANK_FOUND",str(vb),flush=True)
 normalize_character_yaml(vb.parent)
 install_vocal_stack()
 ezv=install_awata_ezv(vb,ROOT/"z13_vocoder_work")
 print("VOCODER_READY",str(ezv),flush=True)
 from diffsinger_utau.voice_bank.commons.voice_bank_reader import VoiceBankReader
 from diffsinger_utau.voice_bank.commons.ds_reader import DSReader
 from diffsinger_utau.voice_bank.pred_acoustic import PredAcoustic
 from diffsinger_utau.voice_bank.pred_vocoder import PredVocoder
 from diffsinger_utau.voice_bank.commons.utils import resample_align_curve
 ac=PredAcoustic(VoiceBankReader.DSAcoustic(dsconfig,preload_models=True))
 vc=PredVocoder(VoiceBankReader.DSVocoder(vb/"dsvocoder/vocoder.yaml",preload_models=True))
 out=[]
 for t in T:
  tag=t["tag"];sc=scores[tag]
  print("RENDER_BEGIN",tag,flush=True)
  mel=ac.predict(DSReader.DSSection(sc),lang="ru",speaker=None,steps=18,gender=0.0)
  f0=resample_align_curve(np.asarray([float(x) for x in sc["f0_seq"].split()],dtype=np.float32),
                          float(sc["f0_timestep"]),vc.timestep,mel.shape[1])
  voice=vc.predict(mel,f0)
  file=OUT/(tag+".wav")
  vc.save_wav(voice,file)
  size=file.stat().st_size
  if size<10000:raise RuntimeError("empty rendered clip "+tag)
  out.append(dict(tag=tag,text=t["text"],start_s=t["start"],
                 duration_s=round(sum(x/480*60/108 for x in t["ticks"]),6),
                 leading_rest_s=.070,trailing_rest_s=.150,
                 file=file.name,bytes=size,
                 sha256=hashlib.sha256(file.read_bytes()).hexdigest(),
                 note_midi=t["notes"],note_ticks=t["ticks"],
                 phones=sc["ph_seq"],phoneme_duration=sc["ph_dur"]))
  print("RENDER_PASS",tag,size,flush=True)
 (OUT/"Z14_WHOLE_LINES_MANIFEST.json").write_text(json.dumps(dict(candidate="Z14_ENTIRE_LINE_SINGLE_SOURCE",
      human_approval="PENDING",method="DiffSinger from scratch using explicit ru/ phonemes; NO RVC, NO TTS overwrite, NO spectral donor repair",
      source_score="D1_FULL_V4_PHONETIC_REPAIR_A, C3R1 108 BPM, original exact timings",
      source_voice="Awata_Weak_DS_v3",
      cannot_assert_listener_intelligibility=True,clips=out),ensure_ascii=False,indent=2))
 print("Z14_DONE",len(out),flush=True)
if __name__=="__main__": main()
