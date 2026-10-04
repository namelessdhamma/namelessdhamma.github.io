"""Render a fair Russian female-voice sweep from the ready-made UFR DiffSinger pack."""
from pathlib import Path
import json, math, sys, gc, traceback
import numpy as np, yaml
from diffsinger_utau.voice_bank.commons.voice_bank_reader import VoiceBankReader
from diffsinger_utau.voice_bank.commons.ds_reader import DSReader
from diffsinger_utau.voice_bank.pred_acoustic import PredAcoustic
from diffsinger_utau.voice_bank.pred_vocoder import PredVocoder
from diffsinger_utau.voice_bank.commons.utils import resample_align_curve
from librosa import note_to_hz

PACK=Path(sys.argv[1]).resolve(); OUT=Path(sys.argv[2]).resolve(); OUT.mkdir(parents=True,exist_ok=True)
logs=[]
def log(*x):
 s=" ".join(map(str,x)); print(s,flush=True); logs.append(s)

inventory=json.loads((PACK/"0_CORE/dsacoustic/millefeuille_v001.phonemes.json").read_text(encoding="utf8"))
def ph(*options):
 for p in options:
  if p in inventory:return p
 raise ValueError("Absent phoneme "+str(options))

groups=[
 [ph("ru/j","ru/y"),ph("ru/a")],
 [ph("ru/g"),ph("ru/ax","ru/a")],
 [ph("ru/v"),ph("ru/ax","ru/a")],
 [ph("ru/ry","ru/r"),ph("ru/i"),ph("ru/l","ru/ly")],
 [ph("ru/ny","ru/n"),ph("ru/e","ru/ex")],
 [ph("ru/s"),ph("ru/ny","ru/n"),ph("ru/i"),ph("ru/m")],
]
phonemes=["SP"]+[p for g in groups for p in g]+["SP"]
phdur=[.375]
for g in groups:
 phdur += {2:[.10,.65],3:[.12,.53,.10],4:[.12,.08,.45,.10]}[len(g)]
phdur.append(.375)
notes=[("rest",.375),("G3",.75),("A3",.75),("B3",.75),("A3",.75),("G3",.75),("F#3",.75),("rest",.375)]
hop=512/44100
f0=[]
for name,duration in notes:
 frames=round(duration/hop)
 if name=="rest":
  f0.extend([0.0]*frames); continue
 hz=float(note_to_hz(name))
 for frame in range(frames):
  t=frame*hop
  approach=-.06*math.exp(-t/.10)
  vib=.026*math.sin(2*math.pi*4.8*(t-.30))*min(1,max(0,(t-.30)/.22))
  f0.append(hz*2**((approach+vib)/12))
ds={"offset":0.0,"text":"SP Я го во рил не с ним SP",
 "ph_seq":" ".join(phonemes),"ph_dur":" ".join(f"{d:.5f}" for d in phdur),
 "ph_num":"1 2 2 2 3 2 4 1",
 "note_seq":" ".join(p for p,_ in notes),
 "note_dur":" ".join(str(d) for _,d in notes),
 "note_slur":" ".join(["0"]*len(notes)),
 "f0_seq":" ".join(f"{x:.3f}" for x in f0),"f0_timestep":str(hop)}
assert len(phonemes)==sum(map(int,ds["ph_num"].split()))==len(phdur)
assert abs(sum(phdur)-sum(d for _,d in notes))<1e-5
(OUT/"test-score.ds").write_text(json.dumps([ds],ensure_ascii=False,indent=2),encoding="utf8")

candidates=[
 ("Kumi",PACK/"UFR_Hitsune Kumi"),
 ("Mimosa",PACK/"Millefeuille_Mimosa"),
 ("Saiun",PACK/"Millefeuille_Saiun"),
]
summary={"phrase":ds["text"],"phonemes":phonemes,"duration":sum(phdur),"renders":[],"errors":[]}
for label,root in candidates:
 try:
  cfg=yaml.safe_load((root/"dsconfig.yaml").read_text(encoding="utf8"))
  speakers=cfg.get("speakers") or [None]
  log("VOICE",label,"SPEAKERS",speakers)
  dsa=VoiceBankReader.DSAcoustic(root/"dsconfig.yaml",preload_models=True)
  dsv=VoiceBankReader.DSVocoder(root/"dsvocoder/vocoder.yaml",preload_models=True)
  ac=PredAcoustic(dsa); vc=PredVocoder(dsv)
  for spk in speakers:
   safe=("default" if spk is None else str(spk).replace("/","_").replace(" ","_").replace(".","_"))
   target=OUT/f"{label}__{safe}.wav"
   try:
    mel=ac.predict(DSReader.DSSection(ds),lang="ru",speaker=spk,steps=12)
    f0a=resample_align_curve(np.asarray(f0,dtype=np.float32),hop,vc.timestep,mel.shape[1])
    wav=vc.predict(mel,f0a)
    vc.save_wav(wav,target)
    summary["renders"].append({"voice":label,"speaker":spk,"file":target.name,"bytes":target.stat().st_size})
    log("OK",target.name,target.stat().st_size)
   except Exception as e:
    summary["errors"].append({"voice":label,"speaker":spk,"error":repr(e)})
    log("ERR",label,spk,repr(e))
  del ac,vc,dsa,dsv; gc.collect()
 except Exception as e:
  summary["errors"].append({"voice":label,"speaker":"__init__","error":repr(e)})
  log("INIT_ERR",label,repr(e),traceback.format_exc()[-2000:])
(OUT/"render-summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf8")
(OUT/"render-audit.txt").write_text("\n".join(logs),encoding="utf8")
if not summary["renders"]: raise SystemExit("No renders succeeded")
