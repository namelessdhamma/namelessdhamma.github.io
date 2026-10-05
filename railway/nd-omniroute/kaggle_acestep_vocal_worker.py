#!/usr/bin/env python3
"""GG-VFS-F01 ACE-Step 1.5 Kaggle qualification worker.

Thin wrapper around the official ACE-Step engine. It deliberately does NOT
author phoneme/vowel durations or create a custom singing stack.
"""
from __future__ import annotations
import hashlib, json, os, shutil, subprocess, sys, time
from pathlib import Path

REQ = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/kaggle/working/gg-vfs-ace-request.json")
ROOT = Path("/kaggle/working")
REPO = ROOT / "ACE-Step-1.5"
OUT = ROOT / "gg-vfs-ace-output"
ACE_COMMIT = "ca1e85fe9430179831e6bc6be790c332190a3866"

def run(cmd, cwd=None, timeout=None):
    print("+", " ".join(map(str, cmd)), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True, timeout=timeout)

def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024), b""): h.update(b)
    return h.hexdigest()

def write_failure(stage, exc):
    OUT.mkdir(parents=True, exist_ok=True)
    payload={"ok":False,"stage":stage,"error":repr(exc),"ace_commit":ACE_COMMIT}
    (OUT/"result.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2))
    print(json.dumps(payload,ensure_ascii=False), flush=True)

request=json.loads(REQ.read_text())
OUT.mkdir(parents=True, exist_ok=True)
start=time.time()
try:
    if not REPO.exists():
        run(["git","clone","--filter=blob:none","https://github.com/ACE-Step/ACE-Step-1.5.git",str(REPO)], timeout=300)
    run(["git","fetch","--depth","1","origin",ACE_COMMIT],cwd=REPO,timeout=180)
    run(["git","checkout","--detach",ACE_COMMIT],cwd=REPO,timeout=60)
    got=subprocess.check_output(["git","rev-parse","HEAD"],cwd=REPO,text=True).strip()
    if got != ACE_COMMIT: raise RuntimeError(f"ACE commit mismatch: {got}")

    # Use the project's own locked/runtime declaration rather than reconstructing its stack.
    if shutil.which("uv") is None:
        run(["bash","-lc","curl -LsSf https://astral.sh/uv/install.sh | sh"],timeout=180)
        os.environ["PATH"]=str(Path.home()/".local/bin")+":"+os.environ["PATH"]
    run(["uv","sync","--no-dev"],cwd=REPO,timeout=1200)

    child=ROOT/"gg_vfs_ace_infer.py"
    child.write_text(r'''from __future__ import annotations
import hashlib,json,os,sys,time
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
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()

print("CUDA",torch.cuda.is_available(),torch.cuda.get_device_name(0) if torch.cuda.is_available() else None, flush=True)
gpu=get_gpu_config();set_global_gpu_config(gpu)
print("GPU_CONFIG",gpu,flush=True)
checkpoint_dir=repo/"checkpoints";checkpoint_dir.mkdir(exist_ok=True)
os.environ["ACESTEP_DOWNLOAD_SOURCE"]="huggingface"

# Download official checkpoints through ACE-Step's own downloader.
for name in ["acestep-v15-turbo","vae","acestep-5Hz-lm-0.6B"]:
    print("ENSURE_MODEL",name,flush=True)
    ensure_model_downloaded(name,str(checkpoint_dir))

dit=AceStepHandler()
status,ok=dit.initialize_service(
    project_root=str(repo),config_path="acestep-v15-turbo",device="cuda",
    use_flash_attention=False,compile_model=False,
    offload_to_cpu=True,offload_dit_to_cpu=True,quantization=None,
)
print(status,flush=True)
if not ok: raise RuntimeError("DiT init failed: "+status)

# T4 is pre-Ampere. ACE-Step's own NaN diagnostic recommends float32 when
# float16 overflows. Preserve the official engine/weights and change only
# runtime precision; CPU-offload keeps the FP32 DiT within the T4 envelope.
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

records=[]
for seed in req["seeds"]:
    seed=int(seed)
    seed_out=out/f"seed-{seed}";seed_out.mkdir(parents=True,exist_ok=True)
    params=GenerationParams(
        task_type="text2music",
        caption=req["caption"],
        lyrics=req["lyrics"],
        instrumental=False,
        vocal_language="ru",
        bpm=req.get("bpm"),
        keyscale=req.get("keyscale",""),
        timesignature=req.get("timesignature",""),
        duration=float(req["duration"]),
        inference_steps=8,
        seed=seed,
        guidance_scale=1.0,
        use_adg=False,
        shift=3.0,
        infer_method="ode",
        thinking=True,
        lm_temperature=0.80,
        lm_cfg_scale=2.0,
        lm_top_k=0,
        lm_top_p=0.90,
        use_cot_metas=False,
        use_cot_caption=False,
        use_cot_lyrics=False,
        use_cot_language=False,
        use_constrained_decoding=True,
    )
    cfg=GenerationConfig(
        batch_size=1,allow_lm_batch=False,use_random_seed=False,
        seeds=[seed],lm_batch_chunk_size=1,audio_format="wav"
    )
    t0=time.time()
    res=generate_music(dit,llm,params,cfg,save_dir=str(seed_out))
    if not res.success: raise RuntimeError(f"generation seed {seed} failed: {res.error} / {res.status_message}")
    for j,a in enumerate(res.audios):
        src=Path(a["path"])
        dst=out/f"GG-VFS-F01_ACE-Step15_RU_{seed}_{j+1}.wav"
        if src.resolve()!=dst.resolve():
            import shutil; shutil.copy2(src,dst)
        records.append({
            "seed":seed,"file":dst.name,"sha256":sha(dst),
            "sample_rate":a.get("sample_rate"),"seconds_wall":round(time.time()-t0,3),
            "params":a.get("params",{}),
        })

receipt={
 "ok":True,
 "engine":"ACE-Step 1.5",
 "engine_commit":"ca1e85fe9430179831e6bc6be790c332190a3866",
 "model":"acestep-v15-turbo",
 "lm_model":"acestep-5Hz-lm-0.6B",
 "task_type":"text2music",
 "vocal_language":"ru",
 "caption":req["caption"],
 "lyrics":req["lyrics"],
 "duration":req["duration"],
 "seeds":req["seeds"],
 "manual_phoneme_durations":False,
 "guide_vocal":False,
 "svc":False,
 "performance_timing_owner":"ACE-Step generative model",
 "runtime_precision":"DiT FP32 on pre-Ampere T4; official CPU offload",
 "records":records,
 "artistic_gate":"USER_AUDITORY_REQUIRED",
 "qualification_focus":["background synthetic buzz","natural vowel-duration variation","Russian diction","consonant-vowel transitions","female identity/timbre"],
}
(out/"result.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2,default=str))

# Optional one-shot callback used only to escape provider-output transport limits.
# Webhook receiver gets the candidate WAV plus compact reproduction metadata.
callback_url=req.get("callback_url")
if callback_url:
    import requests
    primary=Path(records[0]["file"]) if records else None
    if primary and not primary.is_absolute():
        primary=out/primary.name if (out/primary.name).exists() else Path(primary)
    if primary and primary.exists():
        payload={
            "engine":"ACE-Step 1.5",
            "engine_commit":receipt["engine_commit"],
            "seed":records[0]["seed"],
            "sha256":records[0]["sha256"],
            "lyrics":req["lyrics"],
            "caption":req["caption"],
            "manual_phoneme_durations":False,
            "guide_vocal":False,
            "svc":False,
        }
        with primary.open("rb") as fh:
            rr=requests.post(
                callback_url,
                data={"metadata":json.dumps(payload,ensure_ascii=False)},
                files={"audio":(primary.name,fh,"audio/wav")},
                timeout=180,
            )
        print("CALLBACK_STATUS",rr.status_code,flush=True)
        if rr.status_code >= 300:
            raise RuntimeError(f"callback upload failed HTTP {rr.status_code}: {rr.text[:500]}")
(out/"REPRODUCTION_RECIPE.md").write_text(f"""# GG-VFS-F01 ACE-Step 1.5 Russian a-cappella probe

Engine: official ACE-Step 1.5 at commit {receipt['engine_commit']}
Model: acestep-v15-turbo
LM: acestep-5Hz-lm-0.6B (PyTorch backend, CPU-offloaded)
Language: ru
Task: text2music
Duration: {req['duration']} s
Seeds: {req['seeds']}
DiT: FP32, 8 steps, shift=3.0, ODE, turbo CFG effectively 1.0; CPU-offloaded on T4
Output: WAV

Caption:
{req['caption']}

Lyrics:
{req['lyrics']}

No guide vocal, no SVC, no manually programmed phoneme or vowel durations.
Reproduce by running this exact worker/request on a CUDA runtime with the pinned
ACE-Step commit and official model downloader. Final artistic acceptance remains auditory.
""")
print(json.dumps(receipt,ensure_ascii=False,default=str),flush=True)
''',encoding="utf-8")

    env=os.environ.copy()
    # Keep Hugging Face caches in /kaggle/working so they survive within the session.
    env["HF_HOME"]=str(ROOT/"hf-cache")
    cmd=["uv","run","python",str(child),str(REPO),str(OUT),str(REQ)]
    print("+"," ".join(cmd),flush=True)
    subprocess.run(cmd,cwd=REPO,env=env,check=True,timeout=3000)
except Exception as exc:
    write_failure("worker",exc)
    raise
finally:
    print("TOTAL_SECONDS",round(time.time()-start,2),flush=True)
