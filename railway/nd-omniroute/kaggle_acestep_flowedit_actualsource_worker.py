#!/usr/bin/env python3
"""GG-VFS-F01 ACE-Step 1.5 Flow-Edit: lyrics completeness + GG Voice-from-Silence.

Thin wrapper around the official ACE-Step engine. The accepted 8423 vocal is
the source performance. No manual phoneme/vowel timing, guide vocal, or SVC.
"""
from __future__ import annotations
import hashlib, json, os, shutil, subprocess, sys, time, urllib.request
from pathlib import Path

ROOT=Path("/kaggle/working")
REPO=ROOT/"ACE-Step-1.5"
OUT=ROOT/"gg-vfs-flowedit-output"
ACE_COMMIT="ca1e85fe9430179831e6bc6be790c332190a3866"
SOURCE_URL="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/b0525d1/gg-vfs-assets/accepted/GG-VFS-F01_ACE-Step15_RU_8423_1.wav"
SOURCE_SHA="a9052e4b08086a41f97b1c3ff4d2ee5072a56129b8fa6d7ed3260a992fbc5be2"
SEED=8423

SOURCE_CAPTION=("solo female a cappella vocal, warm young adult low-mezzo contralto, "
"intimate and naturally resonant, clear native Russian diction, realistic human singing, "
"expressive legato, varied natural vowel durations, subtle breaths, organic consonant-vowel "
"transitions, dry close studio vocal, no instruments, no harmony, no choir, no reverb, "
"no synthetic buzzing")
SOURCE_LYRICS="[Verse]\nЯ говорила не с ним, а с тем, кто долго стоял у окна и ждал."

TARGET_CAPTION=(SOURCE_CAPTION + ", preserve the same singer identity and melodic contour; "
"GG Voice from Silence: meaning first, restrained warm depth, equanimity without monotony, "
"intimate calm without theatricality; every written Russian word must be audibly complete, "
"including short particles and prepositions; lexical stress must be natural and clear, "
"never exaggerated; keep human vowel-duration variation, subtle breathing and organic transitions")
TARGET_LYRICS="[Verse]\nЯ говори́ла — не с ним,\nа с тем, кто до́лго стоя́л\nу окна́ и ждал."

def run(cmd,cwd=None,timeout=None,env=None):
    print("+"," ".join(map(str,cmd)),flush=True)
    subprocess.run(cmd,cwd=cwd,check=True,timeout=timeout,env=env)

def sha(p:Path)->str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

OUT.mkdir(parents=True,exist_ok=True)
start=time.time()
try:
    src=ROOT/"ACE8423_SOURCE_EXACT.wav"
    if not src.exists():
        req=urllib.request.Request(SOURCE_URL,headers={"User-Agent":"nd-gg-vfs-flowedit/1.0"})
        src.write_bytes(urllib.request.urlopen(req,timeout=120).read())
    if sha(src)!=SOURCE_SHA: raise RuntimeError("source SHA mismatch")

    if not REPO.exists():
        run(["git","clone","--filter=blob:none","https://github.com/ACE-Step/ACE-Step-1.5.git",str(REPO)],timeout=300)
    run(["git","fetch","--depth","1","origin",ACE_COMMIT],cwd=REPO,timeout=180)
    run(["git","checkout","--detach",ACE_COMMIT],cwd=REPO,timeout=60)
    if subprocess.check_output(["git","rev-parse","HEAD"],cwd=REPO,text=True).strip()!=ACE_COMMIT:
        raise RuntimeError("ACE commit mismatch")

    if shutil.which("uv") is None:
        run(["bash","-lc","curl -LsSf https://astral.sh/uv/install.sh | sh"],timeout=180)
        os.environ["PATH"]=str(Path.home()/".local/bin")+":"+os.environ["PATH"]
    run(["uv","sync","--no-dev"],cwd=REPO,timeout=1200)

    child=ROOT/"gg_vfs_flowedit_infer.py"
    child.write_text(r'''from __future__ import annotations
import hashlib,json,os,sys,time,shutil
from pathlib import Path
import torch
repo=Path(sys.argv[1]); src=Path(sys.argv[2]); out=Path(sys.argv[3])
sys.path.insert(0,str(repo))
from acestep.handler import AceStepHandler
from acestep.llm_inference import LLMHandler
from acestep.inference import GenerationParams,GenerationConfig,generate_music
from acestep.api.model_download import ensure_model_downloaded
from acestep.gpu_config import get_gpu_config,set_global_gpu_config

ACE_COMMIT="ca1e85fe9430179831e6bc6be790c332190a3866"
SOURCE_CAPTION=os.environ["SOURCE_CAPTION"]; SOURCE_LYRICS=os.environ["SOURCE_LYRICS"]
TARGET_CAPTION=os.environ["TARGET_CAPTION"]; TARGET_LYRICS=os.environ["TARGET_LYRICS"]
SEED=int(os.environ["FLOW_SEED"])

def sha(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()

print("CUDA",torch.cuda.is_available(),torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,flush=True)
gpu=get_gpu_config();set_global_gpu_config(gpu);print("GPU_CONFIG",gpu,flush=True)
checkpoint_dir=repo/"checkpoints";checkpoint_dir.mkdir(exist_ok=True)
os.environ["ACESTEP_DOWNLOAD_SOURCE"]="huggingface"
for name in ["acestep-v15-turbo","vae","acestep-5Hz-lm-0.6B"]:
    print("ENSURE_MODEL",name,flush=True);ensure_model_downloaded(name,str(checkpoint_dir))

dit=AceStepHandler()
status,ok=dit.initialize_service(
    project_root=str(repo),config_path="acestep-v15-turbo",device="cuda",
    use_flash_attention=False,compile_model=False,
    offload_to_cpu=True,offload_dit_to_cpu=True,quantization=None)
print(status,flush=True)
if not ok:raise RuntimeError("DiT init failed: "+status)
dit.dtype=torch.float32
dit.model=dit.model.to("cpu").to(torch.float32)
if getattr(dit,"silence_latent",None) is not None:
    dit.silence_latent=dit.silence_latent.to("cpu").to(torch.float32)
print("DIT_RUNTIME_DTYPE",dit.dtype,flush=True)

llm=LLMHandler()
lstatus,lok=llm.initialize(
    checkpoint_dir=str(checkpoint_dir),lm_model_path="acestep-5Hz-lm-0.6B",
    backend="pt",device="cuda",offload_to_cpu=True,dtype=None)
print(lstatus,flush=True)
if not lok:raise RuntimeError("LM init failed: "+lstatus)

params=GenerationParams(
    task_type="text2music",
    src_audio=str(src),
    flow_edit_morph=True,
    flow_edit_source_caption=SOURCE_CAPTION,
    flow_edit_source_lyrics=SOURCE_LYRICS,
    flow_edit_n_min=0.0,
    flow_edit_n_max=1.0,
    flow_edit_n_avg=1,
    caption=TARGET_CAPTION,
    lyrics=TARGET_LYRICS,
    instrumental=False,
    vocal_language="ru",
    duration=15.0,
    inference_steps=8,
    seed=SEED,
    guidance_scale=1.0,
    use_adg=False,
    shift=3.0,
    infer_method="ode",
    thinking=False,
    use_cot_metas=False,use_cot_caption=False,use_cot_lyrics=False,use_cot_language=False,
    use_constrained_decoding=True,
)
cfg=GenerationConfig(batch_size=1,allow_lm_batch=False,use_random_seed=False,seeds=[SEED],audio_format="wav")
t0=time.time()
res=generate_music(dit,llm,params,cfg,save_dir=str(out/"raw"))
if not res.success:raise RuntimeError(f"FlowEdit failed: {res.error} / {res.status_message}")
if len(res.audios)!=1:raise RuntimeError(f"expected one audio, got {len(res.audios)}")
a=res.audios[0]; p=Path(a["path"])
dst=out/"GG-VFS-F01_ACE8423_FLOWEDIT_ACTUALSOURCE_GG_002.wav";shutil.copy2(p,dst)
shutil.copy2(src,out/"BASELINE_8423_EXACT.wav")
receipt={
 "ok":True,"engine":"ACE-Step 1.5","engine_commit":ACE_COMMIT,
 "model":"acestep-v15-turbo","lm_model":"acestep-5Hz-lm-0.6B",
 "runtime_precision":"DiT FP32 + official CPU offload on T4",
 "task_type":"text2music+flow_edit","source_sha256":sha(src),"candidate_sha256":sha(dst),
 "seed":SEED,"flow_edit":{"n_min":0.0,"n_max":1.0,"n_avg":1},
 "source_caption":SOURCE_CAPTION,"source_lyrics":SOURCE_LYRICS,
 "target_caption":TARGET_CAPTION,"target_lyrics":TARGET_LYRICS,
 "manual_phoneme_durations":False,"manual_vowel_durations":False,"guide_vocal":False,"svc":False,
 "performance_timing_owner":"ACE-Step generative Flow-Edit over accepted 8423 source",
 "wall_seconds":round(time.time()-t0,3),
}
(out/"result.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
(out/"REPRODUCTION_RECIPE.md").write_text(f"""# GG-VFS-F01 ACE8423 Flow-Edit ACTUALSOURCE GG-002

Engine: ACE-Step 1.5 @ {ACE_COMMIT}
Model: acestep-v15-turbo
LM: acestep-5Hz-lm-0.6B
Runtime: Kaggle T4; DiT FP32 + official CPU offload
Source SHA-256: {sha(src)}
Candidate SHA-256: {sha(dst)}
Seed: {SEED}
Task: text2music + Flow-Edit overlay
Flow-Edit schedule: n_min=0.0, n_max=1.0, n_avg=1
Inference: 8 steps, shift=3.0, ODE, guidance=1.0
Language: ru
Duration: 15 s

SOURCE CAPTION:
{SOURCE_CAPTION}

SOURCE LYRICS:
{SOURCE_LYRICS}

TARGET CAPTION:
{TARGET_CAPTION}

TARGET LYRICS:
{TARGET_LYRICS}

No guide vocal, SVC, manual phoneme durations or manual vowel durations.
The accepted 8423 audio is the performance source. Source lyrics are the independently observed stronger-ASR transcript of that audio, so V_src describes what is actually audible rather than the original requested text. ACE-Step owns the edit and timing.
""")
print(json.dumps(receipt,ensure_ascii=False),flush=True)
''',encoding="utf-8")

    env=os.environ.copy();env["HF_HOME"]=str(ROOT/"hf-cache")
    env["SOURCE_CAPTION"]=SOURCE_CAPTION;env["SOURCE_LYRICS"]=SOURCE_LYRICS
    env["TARGET_CAPTION"]=TARGET_CAPTION;env["TARGET_LYRICS"]=TARGET_LYRICS
    env["FLOW_SEED"]=str(SEED)
    log=OUT/"child.log"
    with log.open("w") as fh:
        p=subprocess.run(["uv","run","python",str(child),str(REPO),str(src),str(OUT)],
                         cwd=REPO,env=env,stdout=fh,stderr=subprocess.STDOUT,timeout=3000)
    if p.returncode!=0:
        raise RuntimeError(f"child failed rc={p.returncode}; tail={log.read_text(errors='replace')[-5000:]}")
except Exception as e:
    (OUT/"result.json").write_text(json.dumps({"ok":False,"error":repr(e),"ace_commit":ACE_COMMIT},ensure_ascii=False,indent=2))
    raise
finally:
    print("TOTAL_SECONDS",round(time.time()-start,2),flush=True)
