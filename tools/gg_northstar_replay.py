#!/usr/bin/env python3
"""Replay genuine historically accepted source on the proven pinned Applio/Awata route.

Produces auditable output WAVs and no automatic claim of human acceptance.
Input: the exact 2026-10-06 GitHub Actions source artifact; output: new C/D render.
"""
import hashlib, json, os, pathlib, runpy, shutil, subprocess, sys, tempfile

def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def main():
    from tools.gg_cloud_music_worker import ensure_applio_runtime, install_rvc_model
    work=pathlib.Path.cwd()/"gg_northstar_replay_work"
    inp=work/"reference"; out=work/"render"; inp.mkdir(parents=True,exist_ok=True);out.mkdir(parents=True,exist_ok=True)
    source=next(inp.rglob("00_SOURCE_SoulX_NorthStar_Candidate.wav"),None)
    if not source:raise FileNotFoundError("Original qualified SoulX source is missing: do not fabricate substitute")
    # This SHA is pinned in the permanent test fixture, not gleaned from the filename.
    verified_sha=os.getenv("GG_APPROVED_SOURCE_SHA256")
    if not verified_sha or sha(source)!=verified_sha:raise RuntimeError("The historical source WAV does not match the canonical SHA256")
    root,vpy,_=ensure_applio_runtime(work/"runtime")
    model,index,meta=install_rvc_model("awata-weak-rvc-v1.2","Original",work/"runtime")
    script=work/"infer_once.py"
    script.write_text('''import json,os,sys
root,source,target,model,index,rate=sys.argv[1:7]
os.chdir(root);sys.path.insert(0,root)
from core import run_infer_script
run_infer_script(input_path=source,output_path=target,pth_path=model,index_path=index,
    export_format="WAV",embedder_model="contentvec",pitch=0,index_rate=float(rate),
    volume_envelope=1.0,protect=0.5,f0_method="fcpe",split_audio=False,
    f0_autotune=False,f0_autotune_strength=1.0,proposed_pitch=False,
    proposed_pitch_threshold=155.0,clean_strength=0.5,clean_audio=False,
    formant_shifting=False,post_process=False,reverb=False,chorus=False,
    distortion=False,delay=False)
''')
    candidates=[]
    for name,rate in [('C_FCPE_IDX030',0.30),('D_FCPE_IDX050',0.50)]:
        target=out/(name+".wav")
        cmd=[str(vpy),str(script),str(root),str(source),str(target),str(model),str(index),str(rate)]
        p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=1100,check=False)
        if p.returncode or not target.exists() or target.stat().st_size<200000:raise RuntimeError(name+" FAIL: "+p.stdout[-3000:])
        candidates.append({'name':name,'sha256':sha(target),'bytes':target.stat().st_size,'f0':'fcpe','index_rate':rate,'protect':0.5,'model':'awata-weak-rvc-v1.2/Original','source_sha256':verified_sha})
        print('RENDERED',name,target.stat().st_size)
    obj={'status':'RENDERED_NOT_AUTOMATICALLY_ACCEPTED','historical_source_sha256':verified_sha,
         'historical_source_name':source.name,'applio_commit':'324f4d89c3e0e8dc0e555a3d53784e3282c16e09',
         'candidates':candidates,'lyrics_evaluation':'RUN_INDEPENDENT_ASR_AND_LISTENING_ON_RENDERED_AUDIO'}
    shutil.copy2(source,out/source.name)
    (out/'replay_provenance.json').write_text(json.dumps(obj,ensure_ascii=False,indent=2))
    print(json.dumps(obj,ensure_ascii=False))
if __name__=='__main__':main()