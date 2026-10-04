"""A7 Russian vocal candidate sweep using native UFR predictors.
Pipeline: duration -> pitch -> acoustic -> vocoder.
Sweeps available speaker/color embeddings; QC is performed by the workflow.
"""
from pathlib import Path
import json, sys, traceback, gc, re
import numpy as np
from diffsinger_utau.voice_bank.commons.voice_bank_reader import VoiceBankReader
from diffsinger_utau.voice_bank.commons.ds_reader import DSReader
from diffsinger_utau.voice_bank.pred_duration import PredDuration
from diffsinger_utau.voice_bank.pred_pitch import PredPitch
from diffsinger_utau.voice_bank.pred_acoustic import PredAcoustic
from diffsinger_utau.voice_bank.pred_vocoder import PredVocoder
from diffsinger_utau.voice_bank.commons.utils import resample_align_curve

PACK=Path(sys.argv[1]).resolve()
OUT=Path(sys.argv[2]).resolve()
OUT.mkdir(parents=True,exist_ok=True)

def choose(common,*cands):
    for c in cands:
        if c in common:
            return c
    raise KeyError("none of "+repr(cands)+" in common model phoneme inventory")

def make_ds(common):
    # Predictor-compatible Russian proxy sequence. In this UFR model family,
    # /n/ + /i/ is the compatible soft-context realization candidate.
    groups=[
      [choose(common,"SP")],
      [choose(common,"ru/j","ru/y"),choose(common,"ru/a")],
      [choose(common,"ru/g"),choose(common,"ru/ax","ru/a")],
      [choose(common,"ru/v"),choose(common,"ru/ax","ru/a")],
      [choose(common,"ru/ry","ru/r"),choose(common,"ru/i"),choose(common,"ru/l","ru/ly")],
      [choose(common,"ru/n"),choose(common,"ru/i")],
      [choose(common,"ru/s"),choose(common,"ru/n"),choose(common,"ru/i"),choose(common,"ru/m")],
      [choose(common,"SP")],
    ]
    notes=[("rest",.28),("G3",.64),("A3",.64),("B3",.64),("A3",.78),("G3",.62),("F#3",.82),("rest",.30)]
    return DSReader.DSSection({
      "offset":0.0,
      "text":"SP Я го во рил не с ним SP",
      "ph_seq":" ".join(p for g in groups for p in g),
      "ph_num":" ".join(str(len(g)) for g in groups),
      "note_seq":" ".join(n for n,_ in notes),
      "note_dur":" ".join(str(d) for _,d in notes),
      "note_slur":" ".join(["0"]*len(notes)),
    })

def style_key(name):
    # embs/millefeuille_v001.mimosa_core -> mimosa_core
    return name.split("/")[-1].split(".")[-1]

def match_speaker(model, key):
    names=[sp.speaker_name for sp in (getattr(model,"speakers",None) or [])]
    for n in names:
        if style_key(n)==key:
            return n
    for n in names:
        if key in style_key(n):
            return n
    return names[0] if names else None

voices=[
 ("Kumi",PACK/"UFR_Hitsune Kumi"),
 ("Mimosa",PACK/"Millefeuille_Mimosa"),
 ("Saiun",PACK/"Millefeuille_Saiun"),
]
summary={"pipeline":"duration->pitch->acoustic->vocoder","renders":[],"errors":[]}
for bank_label,root in voices:
    try:
        dsdur=VoiceBankReader.DSDur(root/"dsdur"/"dsconfig.yaml",preload_models=True)
        dspitch=VoiceBankReader.DSPitch(root/"dspitch"/"dsconfig.yaml",preload_models=True)
        dsac=VoiceBankReader.DSAcoustic(root/"dsconfig.yaml",preload_models=True)
        dsv=VoiceBankReader.DSVocoder(root/"dsvocoder"/"vocoder.yaml",preload_models=True)
        dur=PredDuration(dsdur); pitch=PredPitch(dspitch); ac=PredAcoustic(dsac); vc=PredVocoder(dsv)

        inventories=[]
        for model in (dsdur,dspitch,dsac):
            ph=getattr(model,"phonemes",None)
            if ph is not None:
                inventories.append(set(ph.content.keys()))
        common=set.intersection(*inventories)
        proxy=make_ds(common)

        dur_speakers=[sp.speaker_name for sp in (dsdur.speakers or [])]
        keys=[]
        for n in dur_speakers:
            k=style_key(n)
            if k not in keys:
                keys.append(k)
        if not keys:
            keys=["default"]

        print("BANK",bank_label,"styles",keys,"common_phonemes",len(common),flush=True)

        for key in keys:
            try:
                sp_d=match_speaker(dsdur,key)
                sp_p=match_speaker(dspitch,key)
                sp_a=match_speaker(dsac,key)
                print("STYLE",bank_label,key,"dur",sp_d,"pitch",sp_p,"acoustic",sp_a,flush=True)

                ph_dur=dur.predict(proxy,lang="ru",speaker=sp_d)
                ds1=DSReader.DSSection(dict(proxy))
                ds1["ph_dur"]=" ".join(f"{x:.6f}" for x in ph_dur.tolist())

                f0=pitch.predict(ds1,lang="ru",speaker=sp_p,key_shift=0,steps=14)
                ds2=DSReader.DSSection(dict(ds1))
                ds2["f0_seq"]=" ".join(f"{x:.4f}" for x in f0.tolist())
                ds2["f0_timestep"]=str(pitch.timestep)

                mel=ac.predict(ds2,lang="ru",speaker=sp_a,steps=20)
                f0a=resample_align_curve(np.asarray(f0,dtype=np.float32),pitch.timestep,vc.timestep,mel.shape[1])
                wav=vc.predict(mel,f0a)

                tag=re.sub(r"[^A-Za-z0-9_-]+","_",key)
                target=OUT/f"{bank_label}__{tag}.wav"
                vc.save_wav(wav,target)
                (OUT/f"{bank_label}__{tag}.ds").write_text(
                    json.dumps([dict(ds2)],ensure_ascii=False,indent=2),encoding="utf8")
                meta={
                  "bank":bank_label,"style":key,
                  "duration_speaker":sp_d,"pitch_speaker":sp_p,"acoustic_speaker":sp_a,
                  "file":target.name,"bytes":target.stat().st_size,
                  "ph_dur":[round(float(x),6) for x in ph_dur.tolist()],
                  "f0_frames":int(len(f0)),
                  "f0_voiced_ratio":round(float((np.asarray(f0)>0).mean()),4),
                }
                summary["renders"].append(meta)
                print("OK",bank_label,key,target.stat().st_size,flush=True)
            except Exception as e:
                summary["errors"].append({"bank":bank_label,"style":key,"error":repr(e)})
                print("ERR",bank_label,key,repr(e),traceback.format_exc()[-5000:],flush=True)

        del dsdur,dspitch,dsac,dsv,dur,pitch,ac,vc
        gc.collect()
    except Exception as e:
        summary["errors"].append({"bank":bank_label,"style":"INIT","error":repr(e)})
        print("INIT_ERR",bank_label,repr(e),traceback.format_exc()[-5000:],flush=True)

(OUT/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf8")
if not summary["renders"]:
    raise SystemExit("No natural renders succeeded")
