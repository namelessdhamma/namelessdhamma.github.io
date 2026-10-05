#!/usr/bin/env python3
"""GG-VFS-F01 ACE-Step 1.5 local Repaint worker.

Goal: preserve accepted ACE 8423 performance/identity while repairing omitted
Russian words and lexical stress. Uses ACE-Step's native Repaint mode only.
No manual phoneme/vowel duration authoring.
"""
from __future__ import annotations
import hashlib, json, os, shutil, subprocess, sys, time
from pathlib import Path

REQ=Path(sys.argv[1]) if len(sys.argv)>1 else Path("/kaggle/working/gg-vfs-ace-repaint-request.json")
ROOT=Path("/kaggle/working")
REPO=ROOT/"ACE-Step-1.5"
OUT=ROOT/"gg-vfs-ace-repaint-output"
ACE_COMMIT="ca1e85fe9430179831e6bc6be790c332190a3866"

def run(cmd,cwd=None,timeout=None):
    print("+"," ".join(map(str,cmd)),flush=True)
    subprocess.run(cmd,cwd=cwd,check=True,timeout=timeout)

def sha256(p:Path)->str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def fail(stage,exc):
    OUT.mkdir(parents=True,exist_ok=True)
    rec={"ok":False,"stage":stage,"error":repr(exc),"ace_commit":ACE_COMMIT}
    (OUT/"result.json").write_text(json.dumps(rec,ensure_ascii=False,indent=2))
    print(json.dumps(rec,ensure_ascii=False),flush=True)

req=json.loads(REQ.read_text())
OUT.mkdir(parents=True,exist_ok=True)
start=time.time()
try:
    if not REPO.exists():
        run(["git","clone","--filter=blob:none","https://github.com/ACE-Step/ACE-Step-1.5.git",str(REPO)],timeout=300)
    run(["git","fetch","--depth","1","origin",ACE_COMMIT],cwd=REPO,timeout=180)
    run(["git","checkout","--detach",ACE_COMMIT],cwd=REPO,timeout=60)
    got=subprocess.check_output(["git","rev-parse","HEAD"],cwd=REPO,text=True).strip()
    if got!=ACE_COMMIT: raise RuntimeError(f"ACE commit mismatch: {got}")

    if shutil.which("uv") is None:
        run(["bash","-lc","curl -LsSf https://astral.sh/uv/install.sh | sh"],timeout=180)
        os.environ["PATH"]=str(Path.home()/".local/bin")+":"+os.environ["PATH"]
    run(["uv","sync","--no-dev"],cwd=REPO,timeout=1200)

    child=ROOT/"gg_vfs_ace_repaint_infer.py"
    child.write_text(r'''from __future__ import annotations
import hashlib,json,os,sys,time,shutil
from pathlib import Path
import torch
repo=Path(sys.argv[1]); out=Path(sys.argv[2]); req=json.loads(Path(sys.argv[3]).read_text())
sys.path.insert(0,str(repo))
from acestep.handler import AceStepHandler
from acestep.llm_inference import LLMHandler
from acestep.inference import GenerationParams, GenerationConfig, generate_music
from acestep.api.model_download import ensure_model_downloaded
from acestep.gpu_config import get_gpu_config,set_global_gpu_config

def sha(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

checkpoint_dir=repo/"checkpoints";checkpoint_dir.mkdir(exist_ok=True)
os.environ["ACESTEP_DOWNLOAD_SOURCE"]="huggingface"
for name in ["acestep-v15-turbo","vae","acestep-5Hz-lm-0.6B"]:
    ensure_model_downloaded(name,str(checkpoint_dir))

gpu=get_gpu_config();set_global_gpu_config(gpu)
print("CUDA",torch.cuda.is_available(),torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,flush=True)
print("GPU_CONFIG",gpu,flush=True)

dit=AceStepHandler()
status,ok=dit.initialize_service(
    project_root=str(repo),config_path="acestep-v15-turbo",device="cuda",
    use_flash_attention=False,compile_model=False,
    offload_to_cpu=True,offload_dit_to_cpu=True,quantization=None,
)
print(status,flush=True)
if not ok: raise RuntimeError("DiT init failed: "+status)
dit.dtype=torch.float32
dit.model=dit.model.to("cpu").to(torch.float32)
if getattr(dit,"silence_latent",None) is not None:
    dit.silence_latent=dit.silence_latent.to("cpu").to(torch.float32)
print("DIT_RUNTIME_DTYPE",dit.dtype,"OFFLOAD_DIT",dit.offload_dit_to_cpu,flush=True)

llm=LLMHandler()
lstatus,lok=llm.initialize(
    checkpoint_dir=str(checkpoint_dir),lm_model_path="acestep-5Hz-lm-0.6B",
    backend="pt",device="cuda",offload_to_cpu=True,dtype=None
)
print(lstatus,flush=True)
if not lok: raise RuntimeError("LM init failed: "+lstatus)

# 1) Exact replay of accepted source seed. This keeps source transport out of Kaggle
# and simultaneously tests reproducibility before editing.
base=req["baseline"]
params=GenerationParams(
    task_type="text2music",caption=base["caption"],lyrics=base["lyrics"],
    instrumental=False,vocal_language="ru",duration=float(base["duration"]),
    inference_steps=8,seed=int(base["seed"]),guidance_scale=1.0,use_adg=False,
    shift=3.0,infer_method="ode",thinking=True,lm_temperature=0.80,
    lm_cfg_scale=2.0,lm_top_k=0,lm_top_p=0.90,
    use_cot_metas=False,use_cot_caption=False,use_cot_lyrics=False,
    use_cot_language=False,use_constrained_decoding=True,
)
cfg=GenerationConfig(batch_size=1,allow_lm_batch=False,use_random_seed=False,seeds=[int(base["seed"])],lm_batch_chunk_size=1,audio_format="wav")
bres=generate_music(dit,llm,params,cfg,save_dir=str(out/"baseline-replay"))
if not bres.success: raise RuntimeError("baseline replay failed: "+str(bres.error))
bsrc=Path(bres.audios[0]["path"])
baseline=out/"BASELINE_8423_REPLAY.wav"; shutil.copy2(bsrc,baseline)
baseline_sha=sha(baseline)
expected=base["expected_sha256"]
print("BASELINE_REPLAY_SHA",baseline_sha,"MATCH",baseline_sha==expected,flush=True)
if baseline_sha != expected:
    raise RuntimeError(f"accepted 8423 baseline replay drift: expected {expected}, got {baseline_sha}")

# 2) Native Repaint candidates. Only repaint strength changes between variants.
rp=req["repaint"]
records=[]
for strength in rp["strengths"]:
    strength=float(strength)
    tag=str(strength).replace(".","p")
    p=GenerationParams(
        task_type="repaint",src_audio=str(baseline),
        repainting_start=float(rp["start"]),repainting_end=float(rp["end"]),
        chunk_mask_mode="explicit",repaint_mode="balanced",repaint_strength=strength,
        caption=rp["caption"],lyrics=rp["lyrics"],instrumental=False,
        vocal_language="ru",duration=float(base["duration"]),
        inference_steps=8,seed=int(rp["seed"]),guidance_scale=1.0,use_adg=False,
        shift=3.0,infer_method="ode",thinking=True,lm_temperature=0.80,
        lm_cfg_scale=2.0,lm_top_k=0,lm_top_p=0.90,
        use_cot_metas=False,use_cot_caption=False,use_cot_lyrics=False,
        use_cot_language=False,use_constrained_decoding=True,
    )
    c=GenerationConfig(batch_size=1,allow_lm_batch=False,use_random_seed=False,seeds=[int(rp["seed"])],lm_batch_chunk_size=1,audio_format="wav")
    t0=time.time(); rr=generate_music(dit,llm,p,c,save_dir=str(out/f"repaint-{tag}"))
    if not rr.success: raise RuntimeError(f"repaint strength {strength} failed: {rr.error}")
    src=Path(rr.audios[0]["path"])
    dst=out/f"GG-VFS-F01_ACE8423_REPAINT_{tag}.wav"; shutil.copy2(src,dst)
    records.append({"strength":strength,"file":dst.name,"sha256":sha(dst),"wall_seconds":round(time.time()-t0,3)})

receipt={
    "ok":True,
    "engine":"ACE-Step 1.5","engine_commit":"ca1e85fe9430179831e6bc6be790c332190a3866",
    "model":"acestep-v15-turbo","lm_model":"acestep-5Hz-lm-0.6B",
    "runtime_precision":"DiT FP32 + official CPU offload on T4",
    "baseline_replay_sha256":baseline_sha,"baseline_expected_sha256":expected,
    "baseline_bit_identical":baseline_sha==expected,
    "task_type":"repaint","source":"accepted seed8423 replay",
    "repaint_start":rp["start"],"repaint_end":rp["end"],"repaint_mode":"balanced",
    "target_lyrics":rp["lyrics"],"target_caption":rp["caption"],
    "seed":rp["seed"],"records":records,
    "manual_phoneme_durations":False,"manual_vowel_durations":False,
    "guide_vocal":False,"svc":False,
    "purpose":"restore omitted words and lexical stress while preserving accepted vocal/performance outside bounded interval",
}
(out/"result.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
(out/"REPRODUCTION_RECIPE.md").write_text(f"""# GG-VFS-F01 ACE8423 native Repaint

Engine: ACE-Step 1.5 @ {receipt['engine_commit']}
Model: acestep-v15-turbo
LM: acestep-5Hz-lm-0.6B
Runtime: Kaggle T4, DiT FP32 + CPU offload
Source generation: exact seed {base['seed']} text2music replay
Expected source SHA: {expected}
Observed source SHA: {baseline_sha}
Source bit-identical: {baseline_sha==expected}

Repaint interval: {rp['start']}–{rp['end']} s
Mode: balanced
Strengths: {rp['strengths']}
Repaint seed: {rp['seed']}
Chunk mask: explicit
DiT: 8 steps, shift=3.0, ODE, turbo CFG=1.0

Target caption:
{rp['caption']}

Target lyrics:
{rp['lyrics']}

No guide vocal, no SVC, no manually programmed phoneme/vowel durations.
""")
print(json.dumps(receipt,ensure_ascii=False,indent=2),flush=True)
''',encoding="utf-8")

    env=os.environ.copy(); env["HF_HOME"]=str(ROOT/"hf-cache")
    run(["uv","run","python",str(child),str(REPO),str(OUT),str(REQ)],cwd=REPO,timeout=3300)
except Exception as exc:
    fail("worker",exc); raise
finally:
    print("TOTAL_SECONDS",round(time.time()-start,2),flush=True)
