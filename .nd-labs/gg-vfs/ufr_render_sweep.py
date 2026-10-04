#!/usr/bin/env python3
import json, math, sys, gc
from pathlib import Path
import numpy as np
import soundfile as sf
import yaml
from diffsinger_utau.voice_bank import VoiceBankReader, PredAcoustic, PredVocoder

PACK = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()
OUT.mkdir(parents=True, exist_ok=True)

core = PACK / "0_CORE" / "dsacoustic"
phoneme_json = core / "millefeuille_v001.phonemes.json"
inventory = json.loads(phoneme_json.read_text(encoding="utf-8"))
inv = set(inventory)

def choose(sym):
    if sym in ("SP","AP"):
        for c in (sym, sym.lower()):
            if c in inv:
                return c
        raise KeyError(sym)
    aliases = {
      "j":["j","y","i0"], "a":["a","A"], "g":["g"], "o":["o","O"],
      "v":["v"], "r":["r","r0"], "i":["i","I"], "l":["l","l0"],
      "n":["n"], "e":["e","E"], "s":["s"], "m":["m"]
    }[sym]
    cands=[]
    for a in aliases:
        cands += [f"ru/{a}", f"ru_{a}", f"ru-{a}", f"ru:{a}", a]
    for c in cands:
        if c in inv:
            return c
    # relaxed suffix match, preferring explicit Russian namespace
    for c in inventory:
        cs=str(c)
        if any(cs.endswith("/"+a) or cs.endswith("_"+a) or cs.endswith(":"+a) for a in aliases):
            if "ru" in cs.lower():
                return cs
    raise KeyError(f"{sym}: no candidate; examples={inventory[:120]}")

raw = ["SP","j","a","g","o","v","o","r","i","l","n","e","s","n","i","m","SP"]
ph = [choose(x) for x in raw]
# Fair 5.2 s phrase. Consonants are short; vowels deliberately sustained.
dur = [0.18, .08,.46,.07,.48,.07,.42,.09,.42,.10,.08,.56,.08,.08,.48,.10,.18]
assert len(ph)==len(dur)
# Note targets for each phone; rests at edges. G3-A3-B3-A3-G3-F#3 contour.
hz = {
 "G3":196.00, "A3":220.00, "B3":246.94, "F#3":185.00
}
target = [0,220,220,246.94,246.94,220,220,196,196,196,196,185,185,196,196,196,0]
step=0.005
f0=[]
for idx,(d,base) in enumerate(zip(dur,target)):
    n=max(1,round(d/step))
    if base<=0:
        f0.extend([0.0]*n); continue
    for k in range(n):
        t=k*step
        # restrained vibrato on sustained voiced phones; slight phrase rise/fall
        vib = 1.0 + (0.0035*math.sin(2*math.pi*5.2*t) if d>=0.30 else 0.0)
        phrase = 1.0 + 0.004*math.sin(math.pi*(k/max(1,n-1)))
        f0.append(base*vib*phrase)

section = {
 "offset":0.0,
 "text":"SP Я говорил не с ним SP",
 "ph_seq":" ".join(ph),
 "ph_dur":" ".join(f"{x:.4f}" for x in dur),
 "ph_num":" ".join(["1"]*len(ph)),
 "note_seq":"rest A3 A3 B3 B3 A3 A3 G3 G3 G3 G3 F#3 F#3 G3 G3 G3 rest",
 "note_dur":" ".join(f"{x:.4f}" for x in dur),
 "note_slur":" ".join(["0"]*len(ph)),
 "f0_seq":" ".join(f"{x:.4f}" for x in f0),
 "f0_timestep":str(step)
}

class DS(dict):
    def get_list(self,key):
        if key not in self: return []
        vals=str(self[key]).split()
        if "seq" in key or key=="text": return vals
        if key in ("note_slur","ph_num"): return [int(float(x)) for x in vals]
        return [float(x) for x in vals]
    def has_dur(self): return "ph_dur" in self
    def has_pitch(self): return "f0_seq" in self and "f0_timestep" in self
    def has_breathiness(self): return False
    def has_energy(self): return False
    def has_tension(self): return False
    def has_voicing(self): return False

ds=DS(section)
candidates = [
 ("Kumi", PACK/"UFR_Hitsune Kumi"),
 ("Mimosa", PACK/"Millefeuille_Mimosa"),
 ("Saiun", PACK/"Millefeuille_Saiun"),
]
summary={"phrase":section["text"],"phonemes":ph,"duration":sum(dur),"renders":[],"errors":[]}
for label,root in candidates:
    cfg=yaml.safe_load((root/"dsconfig.yaml").read_text(encoding="utf-8"))
    speakers=cfg.get("speakers") or [None]
    # Keep every declared speaker; these are the model's native controllable colors.
    print(label, "speakers", speakers, flush=True)
    try:
        acoustic=VoiceBankReader.DSAcoustic(root/"dsconfig.yaml", preload_models=True)
        vocoder=VoiceBankReader.DSVocoder(root/"dsvocoder"/"vocoder.yaml", preload_models=True)
        pa=PredAcoustic(dsacoustic=acoustic)
        pv=PredVocoder(vocoder)
        for speaker in speakers:
            spk = speaker
            safe = ("default" if spk is None else str(spk).replace("/","_").replace(" ","_").replace(".","_"))
            name=f"{label}__{safe}.wav"
            try:
                mel=pa.predict(ds, speaker=spk)
                wav=pv.predict(mel, np.asarray(f0,dtype=np.float32))
                wav=np.asarray(wav).squeeze().astype(np.float32)
                peak=float(np.max(np.abs(wav))) if wav.size else 0.0
                if peak>0.97: wav=wav*(0.97/peak)
                sf.write(OUT/name,wav,44100,subtype="PCM_16")
                summary["renders"].append({"voice":label,"speaker":spk,"file":name,"samples":int(wav.size),"peak":peak})
                print("OK",name,wav.shape,peak,flush=True)
            except Exception as e:
                summary["errors"].append({"voice":label,"speaker":spk,"error":repr(e)})
                print("ERR",label,spk,repr(e),flush=True)
        del pa,pv,acoustic,vocoder
        gc.collect()
    except Exception as e:
        summary["errors"].append({"voice":label,"speaker":"__init__","error":repr(e)})
        print("INIT_ERR",label,repr(e),flush=True)

(OUT/"render-summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
(OUT/"test-score.ds").write_text(json.dumps([section],ensure_ascii=False,indent=2),encoding="utf-8")
if not summary["renders"]:
    raise SystemExit("No renders succeeded")
