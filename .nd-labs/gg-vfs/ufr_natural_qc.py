"""A7 natural Russian vocal audition using available native UFR predictors.
Pipeline: duration -> pitch -> acoustic -> vocoder.
Optional variance is intentionally omitted when the singer pack has no dsvariance config.
"""
from pathlib import Path
import json, sys, traceback, gc
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

def make_ds(common, ne_mode):
    # Use only phonemes accepted by duration, pitch AND acoustic models.
    # 8 musical groups: SP | Я | го | во | рил | не | с ним | SP
    ne_vowel = choose(common,"ru/i") if ne_mode=="reduced" else choose(common,"ru/e","ru/ex","ru/i")
    groups=[
      [choose(common,"SP")],
      [choose(common,"ru/j","ru/y"),choose(common,"ru/a")],
      [choose(common,"ru/g"),choose(common,"ru/ax","ru/a")],
      [choose(common,"ru/v"),choose(common,"ru/ax","ru/a")],
      [choose(common,"ru/ry","ru/r"),choose(common,"ru/i"),choose(common,"ru/l","ru/ly")],
      [choose(common,"ru/ny","ru/n"),ne_vowel],
      [choose(common,"ru/s"),choose(common,"ru/ny","ru/n"),choose(common,"ru/i"),choose(common,"ru/m")],
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

def pick_speaker(dsdur):
    names=[sp.speaker_name for sp in (dsdur.speakers or [])]
    if not names:
        return None
    # Prefer neutral/core/natural color when present.
    for needle in ("core","natural","base"):
        for n in names:
            if needle in n.lower():
                return n
    return names[0]

voices=[
 ("Kumi",PACK/"UFR_Hitsune Kumi"),
 ("Mimosa",PACK/"Millefeuille_Mimosa"),
 ("Saiun",PACK/"Millefeuille_Saiun"),
]
summary={"pipeline":"duration->pitch->acoustic->vocoder","renders":[],"errors":[]}
for label,root in voices:
    try:
        dsdur=VoiceBankReader.DSDur(root/"dsdur"/"dsconfig.yaml",preload_models=True)
        dspitch=VoiceBankReader.DSPitch(root/"dspitch"/"dsconfig.yaml",preload_models=True)
        dsac=VoiceBankReader.DSAcoustic(root/"dsconfig.yaml",preload_models=True)
        dsv=VoiceBankReader.DSVocoder(root/"dsvocoder"/"vocoder.yaml",preload_models=True)
        dur=PredDuration(dsdur); pitch=PredPitch(dspitch); ac=PredAcoustic(dsac); vc=PredVocoder(dsv)
        speaker=pick_speaker(dsdur)
        inventories=[]
        for model in (dsdur,dspitch,dsac):
            ph=getattr(model,"phonemes",None)
            if ph is not None:
                inventories.append(set(ph.content.keys()))
        if not inventories:
            raise RuntimeError("No phoneme inventories exposed")
        common=set.intersection(*inventories)
        print("VOICE",label,"speaker",speaker,"common_phonemes",len(common),flush=True)
        for ne_mode,tag in [("reduced","SOFT_NE_HYBRID")]:
            try:
                # Predictor-compatible proxy sequence first.
                base=make_ds(common,ne_mode)
                ph_dur=dur.predict(base,lang="ru",speaker=speaker)
                ds1=DSReader.DSSection(dict(base))
                ds1["ph_dur"]=" ".join(f"{x:.6f}" for x in ph_dur.tolist())

                f0=pitch.predict(ds1,lang="ru",speaker=speaker,key_shift=0,steps=14)

                # Acoustic stage can expose a richer Russian inventory than
                # duration/pitch. Preserve predictor timings/F0, but restore
                # palatalized /nʲ/ for «не» and «ним» when acoustic supports it.
                ds2=DSReader.DSSection(dict(ds1))
                phs=ds2["ph_seq"].split()
                ac_inv=set(dsac.phonemes.content.keys()) if dsac.phonemes is not None else set()
                if "ru/ny" not in ac_inv:
                    raise RuntimeError("Acoustic model has no ru/ny for Russian soft n")
                n_positions=[i for i,p in enumerate(phs) if p=="ru/n"]
                if len(n_positions) < 2:
                    raise RuntimeError("Expected two proxy ru/n positions")
                for i in n_positions[-2:]:
                    phs[i]="ru/ny"
                ds2["ph_seq"]=" ".join(phs)
                ds2["f0_seq"]=" ".join(f"{x:.4f}" for x in f0.tolist())
                ds2["f0_timestep"]=str(pitch.timestep)

                mel=ac.predict(ds2,lang="ru",speaker=speaker,steps=20)
                f0a=resample_align_curve(np.asarray(f0,dtype=np.float32),pitch.timestep,vc.timestep,mel.shape[1])
                wav=vc.predict(mel,f0a)
                target=OUT/f"{label}__{tag}.wav"
                vc.save_wav(wav,target)
                meta={
                  "voice":label,"speaker":speaker,"variant":tag,"file":target.name,
                  "bytes":target.stat().st_size,
                  "ph_dur":[round(float(x),6) for x in ph_dur.tolist()],
                  "f0_frames":int(len(f0)),
                  "f0_voiced_ratio":round(float((np.asarray(f0)>0).mean()),4),
                }
                summary["renders"].append(meta)
                (OUT/f"{label}__{tag}.ds").write_text(json.dumps([dict(ds2)],ensure_ascii=False,indent=2),encoding="utf8")
                print("OK",label,tag,target.stat().st_size,flush=True)
            except Exception as e:
                summary["errors"].append({"voice":label,"variant":tag,"error":repr(e)})
                print("ERR",label,tag,repr(e),traceback.format_exc()[-5000:],flush=True)
        del dsdur,dspitch,dsac,dsv,dur,pitch,ac,vc
        gc.collect()
    except Exception as e:
        summary["errors"].append({"voice":label,"variant":"INIT","error":repr(e)})
        print("INIT_ERR",label,repr(e),traceback.format_exc()[-5000:],flush=True)

(OUT/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf8")
if not summary["renders"]:
    raise SystemExit("No partial-natural renders succeeded")
