"""A7 natural-phonetics audition: full DiffSinger pipeline + Russian pronunciation variants."""
from pathlib import Path
import json, sys, traceback
from diffsinger_utau.voice_bank import PredAll
from diffsinger_utau.voice_bank.commons.ds_reader import DSReader

PACK=Path(sys.argv[1]).resolve()
OUT=Path(sys.argv[2]).resolve()
OUT.mkdir(parents=True,exist_ok=True)

def make_ds(ne_vowel="ru/i"):
    # 8 note/syllable groups: SP | Я | го | во | рил | не | с ним | SP
    groups=[
      ["SP"],
      ["ru/j","ru/a"],
      ["ru/g","ru/ax"],
      ["ru/v","ru/ax"],
      ["ru/ry","ru/i","ru/l"],
      ["ru/ny",ne_vowel],
      ["ru/s","ru/ny","ru/i","ru/m"],
      ["SP"],
    ]
    ph=[p for g in groups for p in g]
    d={
      "offset":0.0,
      "text":"SP Я го во рил не с ним SP",
      "ph_seq":" ".join(ph),
      "ph_num":" ".join(str(len(g)) for g in groups),
      "note_seq":"rest G3 A3 B3 A3 G3 F#3 rest",
      "note_dur":"0.20 0.55 0.40 0.40 0.75 0.45 0.70 0.25",
      "note_slur":"0 0 0 0 0 0 0 0",
    }
    return DSReader.DSSection(d)

voices=[
 ("Kumi",PACK/"UFR_Hitsune Kumi"),
 ("Mimosa",PACK/"Millefeuille_Mimosa"),
 ("Saiun",PACK/"Millefeuille_Saiun"),
]
summary={"renders":[],"errors":[]}
for label,root in voices:
    try:
        pred=PredAll(root)
        speakers=list(getattr(pred,"available_speakers",[]) or [])
        core=next((s for s in speakers if "core" in str(s).lower()), speakers[0] if speakers else None)
        for ne_vowel,tag in [("ru/i","NE_REDUCED_I"),("ru/e","NE_E")]:
            ds=make_ds(ne_vowel)
            sub=OUT/f"{label}_{tag}"
            sub.mkdir(exist_ok=True)
            try:
                result=pred.predict_full_pipeline(
                    ds=ds,
                    lang="ru",
                    speaker=core,
                    key_shift=0,
                    pitch_steps=10,
                    variance_steps=10,
                    acoustic_steps=18,
                    gender=0.0,
                    output_dir=str(sub),
                    save_intermediate=True,
                )
                audio=Path(result["audio_path"])
                target=OUT/f"{label}__{tag}.wav"
                target.write_bytes(audio.read_bytes())
                summary["renders"].append({"voice":label,"speaker":core,"variant":tag,"file":target.name,"bytes":target.stat().st_size})
                print("OK",label,core,tag,target.stat().st_size,flush=True)
            except Exception as e:
                summary["errors"].append({"voice":label,"speaker":core,"variant":tag,"error":repr(e)})
                print("ERR",label,tag,repr(e),traceback.format_exc()[-3000:],flush=True)
    except Exception as e:
        summary["errors"].append({"voice":label,"variant":"INIT","error":repr(e)})
        print("INIT_ERR",label,repr(e),flush=True)
(OUT/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf8")
if not summary["renders"]:
    raise SystemExit("No natural-pipeline renders succeeded")
