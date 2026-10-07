#!/usr/bin/env python3
import argparse, pathlib, runpy, subprocess, json

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--guide",required=True)
    ap.add_argument("--out-dir",required=True)
    ap.add_argument("--protects",default="0.15,0.20,0.25,0.30,0.35,0.50")
    ap.add_argument("--index-rate",type=float,default=0.50)
    args=ap.parse_args()

    guide=pathlib.Path(args.guide).resolve()
    outdir=pathlib.Path(args.out_dir).resolve(); outdir.mkdir(parents=True,exist_ok=True)
    protects=[float(x) for x in args.protects.split(",") if x.strip()]

    ns=runpy.run_path("tools/gg_cloud_music_worker.py",run_name="gg_d1r5_variants")
    work=pathlib.Path("/tmp/applio-d1r5-variants"); work.mkdir(exist_ok=True)
    root,vpy,rt=ns["ensure_applio_runtime"](work)
    model,index,meta=ns["install_rvc_model"]("awata-weak-rvc-v1.2","Original",work)

    code=(
      "import os,sys; root,source,out,model,index,protect,index_rate=sys.argv[1:8];"
      "os.chdir(root);sys.path.insert(0,root);from core import run_infer_script;"
      "run_infer_script(input_path=source,output_path=out,pth_path=model,index_path=index,"
      "export_format='WAV',embedder_model='contentvec',pitch=0,index_rate=float(index_rate),"
      "volume_envelope=1.0,protect=float(protect),f0_method='fcpe',split_audio=True,"
      "f0_autotune=False,f0_autotune_strength=1.0,proposed_pitch=False,"
      "proposed_pitch_threshold=155.0,clean_audio=False,clean_strength=0.5,"
      "formant_shifting=False,formant_qfrency=1.0,formant_timbre=1.0,"
      "post_process=False,reverb=False,pitch_shift=False,limiter=False,gain=False,"
      "distortion=False,chorus=False,bitcrush=False,clipping=False,compressor=False,delay=False,"
      "reverb_room_size=0.5,reverb_damping=0.5,reverb_wet_gain=0.33,reverb_dry_gain=0.4,"
      "reverb_width=1.0,reverb_freeze_mode=0.0,pitch_shift_semitones=0.0,"
      "limiter_threshold=-6.0,limiter_release_time=0.01,gain_db=0.0,distortion_gain=25.0,"
      "chorus_rate=1.0,chorus_depth=0.25,chorus_center_delay=7.0,chorus_feedback=0.0,"
      "chorus_mix=0.5,bitcrush_bit_depth=8,clipping_threshold=-6.0,"
      "compressor_threshold=0.0,compressor_ratio=1.0,compressor_attack=1.0,"
      "compressor_release=100.0,delay_seconds=0.5,delay_feedback=0.0,delay_mix=0.5,sid=0)"
    )
    manifest=[]
    for protect in protects:
        tag=f"p{int(round(protect*100)):02d}"
        out=outdir/f"D_D1_{tag}.wav"
        p=subprocess.run([str(vpy),"-c",code,str(root),str(guide),str(out),str(model),str(index),
                          f"{protect:.3f}",f"{args.index_rate:.3f}"],
                         cwd=root,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=2400)
        print(f"=== {tag} protect={protect:.2f} ===")
        print(p.stdout[-5000:])
        if p.returncode or not out.exists() or out.stat().st_size==0:
            manifest.append({"label":tag,"protect":protect,"status":"FAILED"})
            continue
        manifest.append({"label":tag,"protect":protect,"status":"RENDERED","path":str(out)})
    (outdir/"rvc-variant-manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    if not any(x["status"]=="RENDERED" for x in manifest):
        raise SystemExit("No RVC variants rendered")
if __name__=="__main__":
    main()
