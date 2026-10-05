#!/usr/bin/env python3
"""GG-VFS-F01 HQ-SVC zero-shot source gate.

Source is a verified Russian Awata Weak DiffSinger render supplied by the
control workflow. Target reference is the accepted ACE-Step 8423 vocal.
No pitch shift, no auto-F0, no manual phoneme editing inside HQ-SVC.
"""
from __future__ import annotations
import hashlib, json, os, shutil, subprocess, sys, time, urllib.request
from pathlib import Path

ROOT=Path("/kaggle/working")
REPO=ROOT/"HQ-SVC"
ENV=ROOT/"hqsvc-env"
OUT=ROOT/"gg-vfs-hqsvc-output"
SOURCE=ROOT/"awata_mature_source.wav"
TARGET=ROOT/"ace8423_reference.wav"
GITHUB_COMMIT="853a18883f6d380d5e9f9b4bf244d602b6d9d320"
HF_REV="952f1d43e7d9c3af08f5b5842b9fb18d5bd06334"
SOURCE_SHA="e09d5a5330793d8cebf715ea45701f14d4db69841bc527213c20139dcd133a08"
TARGET_SHA="a9052e4b08086a41f97b1c3ff4d2ee5072a56129b8fa6d7ed3260a992fbc5be2"
TARGET_URL="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/b0525d1/gg-vfs-assets/accepted/GG-VFS-F01_ACE-Step15_RU_8423_1.wav"
SEED=8423

def run(cmd,cwd=None,timeout=None,env=None):
    print("+"," ".join(map(str,cmd)),flush=True)
    subprocess.run(cmd,cwd=cwd,check=True,timeout=timeout,env=env)

def sha(path:Path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()

OUT.mkdir(parents=True,exist_ok=True)
t0=time.time()
try:
    if not SOURCE.exists() or sha(SOURCE)!=SOURCE_SHA:
        raise RuntimeError("verified Awata source missing or SHA mismatch")

    if not TARGET.exists():
        req=urllib.request.Request(TARGET_URL,headers={"User-Agent":"nd-vfs-hqsvc/1.0"})
        TARGET.write_bytes(urllib.request.urlopen(req,timeout=180).read())
    if sha(TARGET)!=TARGET_SHA:
        raise RuntimeError("ACE8423 target reference SHA mismatch")

    if not REPO.exists():
        run(["git","clone","--filter=blob:none","https://github.com/ShawnPi233/HQ-SVC.git",str(REPO)],timeout=300)
    run(["git","fetch","--depth","1","origin",GITHUB_COMMIT],cwd=REPO,timeout=180)
    run(["git","checkout","--detach",GITHUB_COMMIT],cwd=REPO,timeout=60)
    got=subprocess.check_output(["git","rev-parse","HEAD"],cwd=REPO,text=True).strip()
    if got!=GITHUB_COMMIT: raise RuntimeError("HQ-SVC Git commit mismatch")

    # Official authors distribute a frozen Linux CUDA 11.8 environment.
    # Stream-extract to avoid holding the 4.7GB tarball on Kaggle disk.
    if not (ENV/"bin/python").exists():
        ENV.mkdir(parents=True,exist_ok=True)
        url=f"https://huggingface.co/shawnpi/HQ-SVC/resolve/{HF_REV}/environment.tar.gz"
        run(["bash","-lc",f"set -euo pipefail; curl -fL --retry 3 --connect-timeout 30 '{url}' | tar -xz -C '{ENV}'"],timeout=1500)

    # Download ONLY runtime weights used by official gradio_app.py.
    files=[
      "utils/pretrain/250000_step_val_loss_0.50.pth",
      "utils/pretrain/ns3_facodec_decoder_v2.bin",
      "utils/pretrain/ns3_facodec_encoder_v2.bin",
      "utils/pretrain/nsf_hifigan/config.json",
      "utils/pretrain/nsf_hifigan/model",
      "utils/pretrain/rmvpe/model.pt",
    ]
    for rel in files:
        dst=REPO/rel
        if dst.exists() and dst.stat().st_size>0: continue
        dst.parent.mkdir(parents=True,exist_ok=True)
        url=f"https://huggingface.co/shawnpi/HQ-SVC/resolve/{HF_REV}/{rel}"
        run(["curl","-fL","--retry","3","--connect-timeout","30","-o",str(dst),url],timeout=900)

    infer=ROOT/"hqsvc_gate_infer.py"
    infer.write_text(r'''from __future__ import annotations
import hashlib,json,os,sys,time
from pathlib import Path
import numpy as np
import soundfile as sf
import torch

repo=Path(sys.argv[1]);source=Path(sys.argv[2]);target=Path(sys.argv[3]);out=Path(sys.argv[4])
sys.path.insert(0,str(repo))
os.chdir(repo)

from logger.utils import load_config
from utils.models.models_v2_beta import load_hq_svc
from utils.vocoder import Vocoder
from utils.data_preprocessing import load_facodec,load_f0_extractor,load_volume_extractor,get_processed_file

SEED=8423
torch.manual_seed(SEED);np.random.seed(SEED)
if torch.cuda.is_available(): torch.cuda.manual_seed_all(SEED)

args=load_config("configs/hq_svc_infer.yaml")
args.config="configs/hq_svc_infer.yaml"
device=args.device
print("DEVICE",device,"CUDA",torch.cuda.is_available(),torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,flush=True)

vocoder=Vocoder(vocoder_type="nsf-hifigan",vocoder_ckpt="utils/pretrain/nsf_hifigan/model",device=device)
net=load_hq_svc(mode="infer",device=device,model_path=args.model_path,args=args)
net.eval()
fa_encoder,fa_decoder=load_facodec(device)
pre={
 "fa_encoder":fa_encoder,"fa_decoder":fa_decoder,
 "f0_extractor":load_f0_extractor(args),
 "volume_extractor":load_volume_extractor(args),
}

with torch.no_grad():
    td=get_processed_file(str(target),args.sample_rate,args.encoder_sr,vocoder,pre["volume_extractor"],pre["f0_extractor"],
                          pre["fa_encoder"],pre["fa_decoder"],None,None,device=device)
    if td is None: raise RuntimeError("target reference preprocessing failed")
    spk=td["spk"].squeeze().to(device)

    sd=get_processed_file(str(source),args.sample_rate,args.encoder_sr,vocoder,pre["volume_extractor"],pre["f0_extractor"],
                          pre["fa_encoder"],pre["fa_decoder"],None,None,device=device)
    if sd is None: raise RuntimeError("source preprocessing failed")
    f0=sd["f0"].unsqueeze(0).to(device)   # exact source pitch; no auto target shift
    mel=net(sd["vq_post"].unsqueeze(0).to(device),f0,sd["vol"].unsqueeze(0).to(device),spk,
            gt_spec=None,infer=True,infer_speedup=args.infer_speedup,method=args.infer_method,vocoder=vocoder)
    wav=vocoder.infer(mel,f0) if args.vocoder=="nsf-hifigan" else vocoder.infer(mel)

dst=out/"GG-VFS-F01_HQSVC_AWATA_MATURE_to_ACE8423.wav"
sf.write(dst,wav.squeeze().detach().cpu().numpy(),44100,subtype="PCM_16")

def sha(p):
 h=hashlib.sha256()
 with open(p,"rb") as f:
  for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
 return h.hexdigest()
receipt={
 "ok":True,
 "engine":"HQ-SVC",
 "engine_git_commit":"853a18883f6d380d5e9f9b4bf244d602b6d9d320",
 "model_hf_revision":"952f1d43e7d9c3af08f5b5842b9fb18d5bd06334",
 "source_sha256":"e09d5a5330793d8cebf715ea45701f14d4db69841bc527213c20139dcd133a08",
 "target_reference_sha256":"a9052e4b08086a41f97b1c3ff4d2ee5072a56129b8fa6d7ed3260a992fbc5be2",
 "output_sha256":sha(dst),
 "seed":SEED,
 "pitch_shift_semitones":0,
 "auto_target_f0":False,
 "sample_rate":44100,
 "infer_speedup":args.infer_speedup,
 "infer_method":args.infer_method,
 "identity_source":"ACE-Step 8423 generated vocal reference",
 "content_melody_source":"Awata Weak v3 mature Russian score render",
}
(out/"result.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
(out/"REPRODUCTION_RECIPE.md").write_text(f"""# GG-VFS-F01 HQ-SVC source gate

HQ-SVC git: {receipt['engine_git_commit']}
HQ-SVC model revision: {receipt['model_hf_revision']}
Source SHA: {receipt['source_sha256']}
Target reference SHA: {receipt['target_reference_sha256']}
Output SHA: {receipt['output_sha256']}
Seed: {SEED}
Pitch shift: 0 semitones
Auto target-F0: OFF
HQ-SVC infer speedup: {args.infer_speedup}
HQ-SVC solver: {args.infer_method}
Output: PCM16 44.1kHz mono

Source owns Russian lyrics + melody. ACE8423 reference supplies zero-shot speaker identity.
No phoneme editing, SVC tuning, post-pitch correction, denoise, EQ, or mastering after conversion.
""")
print(json.dumps(receipt,ensure_ascii=False),flush=True)
''',encoding="utf-8")

    child_env=os.environ.copy()
    # Keep Kaggle's host NVIDIA driver path. HQ-SVC README says to unset
    # LD_LIBRARY_PATH only as an optional workaround for a specific segfault;
    # unsetting it on Kaggle hides libcuda from the official CUDA env.
    cmd=[str(ENV/"bin/python"),str(infer),str(REPO),str(SOURCE),str(TARGET),str(OUT)]
    log=OUT/"child.log"
    with log.open("w") as fh:
        p=subprocess.run(cmd,cwd=REPO,env=child_env,stdout=fh,stderr=subprocess.STDOUT,timeout=1800)
    if p.returncode!=0:
        raise RuntimeError(f"HQ-SVC child rc={p.returncode}; tail={log.read_text(errors='replace')[-7000:]}")
except Exception as exc:
    (OUT/"result.json").write_text(json.dumps({"ok":False,"error":repr(exc),"git_commit":GITHUB_COMMIT,"hf_revision":HF_REV},ensure_ascii=False,indent=2))
    raise
finally:
    print("TOTAL_SECONDS",round(time.time()-t0,2),flush=True)
