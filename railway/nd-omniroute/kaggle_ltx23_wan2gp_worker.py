#!/usr/bin/env python3
"""ND Kaggle LTX-2.3 Wan2GP first/last-frame candidate worker.

Candidate recovery route:
- no mounted 86 GiB LTX-13B dataset
- Wan2GP pinned at 2345ae148f82740f66e82c41292dbbdd592e713d
- LTX-2.3 22B distilled quanto-int8 model files staged in /kaggle/tmp
- start + end frame conditioning
- FREE_ONLY provider policy is enforced by the caller
"""
from __future__ import annotations

from pathlib import Path
import gc
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

WORK = Path("/kaggle/working")
TMP = Path("/kaggle/tmp")
ROOT = WORK / "Wan2GP"
MODEL_DIR = ROOT / "models"
TMP_MODELS = TMP / "models"
WAN2GP_COMMIT = "2345ae148f82740f66e82c41292dbbdd592e713d"
MODEL_REPO = "DeepBeepMeep/LTX-2"
FPS = 24.0

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True,garbage_collection_threshold:0.6")
os.environ.setdefault("MALLOC_TRIM_THRESHOLD_", "0")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("PIP_NO_CACHE_DIR", "1")
os.environ.setdefault("HF_HOME", str(TMP / "hf-cache"))


def stage(name: str, **extra) -> None:
    payload = {"stage": name, **extra}
    print("ND_LTX23_STAGE=" + json.dumps(payload, separators=(",", ":"), sort_keys=True), flush=True)


def run(cmd: list[str], timeout: int, cwd: Path | None = None) -> str:
    p = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
        env={**os.environ, "PIP_NO_CACHE_DIR": "1"},
    )
    if p.returncode != 0:
        print("ND_LTX23_CMD_FAIL=" + json.dumps({
            "cmd": cmd,
            "returncode": p.returncode,
            "tail": p.stdout[-12000:],
        }, separators=(",", ":")), flush=True)
        raise RuntimeError("command failed: " + repr(cmd))
    return p.stdout


def download(url: str, path: Path) -> None:
    if not url.startswith(("http://", "https://")):
        raise ValueError("image URL must be http(s)")
    req = urllib.request.Request(url, headers={"User-Agent": "nd-kaggle-ltx23/1.0"})
    with urllib.request.urlopen(req, timeout=180) as src, path.open("wb") as dst:
        shutil.copyfileobj(src, dst, length=1024 * 1024)


def align32(v: int) -> int:
    return max(256, (int(v) // 32) * 32)


def mae(a, b, size) -> float:
    import numpy as np
    aa = np.array(a.resize(size)).astype(np.float32)
    bb = np.array(b.resize(size)).astype(np.float32)
    return float(np.mean(np.abs(aa - bb)))


def ensure_repo_and_dependencies() -> None:
    stage("clone_wan2gp")
    if ROOT.exists():
        shutil.rmtree(ROOT)
    run(["git", "clone", "--filter=blob:none", "https://github.com/DeepBeepMeep/Wan2GP.git", str(ROOT)], 300)
    run(["git", "-C", str(ROOT), "checkout", WAN2GP_COMMIT], 120)
    stage("install_dependencies")
    run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "-q", "--disable-pip-version-check",
         "-r", str(ROOT / "requirements.txt")], 1200)
    run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "-q", "--disable-pip-version-check",
         "mmgp", "gradio"], 600)
    stage("dependencies_ready")


def ensure_models() -> None:
    from huggingface_hub import hf_hub_download

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    TMP_MODELS.mkdir(parents=True, exist_ok=True)

    large_files = [
        "ltx-2.3-22b-distilled_diffusion_model_quanto_int8.safetensors",
        "ltx-2.3-22b-distilled-lora-384.safetensors",
        "ltx-2.3-22b_embeddings_connector.safetensors",
        "ltx-2.3-22b_text_embedding_projection.safetensors",
        "ltx-2.3-22b_vae.safetensors",
    ]
    small_files = [
        "ltx-2.3-22b_audio_vae.safetensors",
        "ltx-2.3-22b_vocoder.safetensors",
        "ltx-2.3-spatial-upscaler-x2-1.1.safetensors",
        "ltx-2.3-temporal-upscaler-x2-1.0.safetensors",
    ]
    gemma_folder = "gemma-3-12b-it-qat-q4_0-unquantized"
    gemma_files = [
        "gemma-3-12b-it-qat-q4_0-unquantized_quanto_bf16_int8.safetensors",
        "added_tokens.json",
        "chat_template.json",
        "config_light.json",
        "generation_config.json",
        "preprocessor_config.json",
        "processor_config.json",
        "special_tokens_map.json",
        "tokenizer.json",
        "tokenizer.model",
        "tokenizer_config.json",
    ]

    stage("download_models_start", large_count=len(large_files), small_count=len(small_files))
    for name in large_files:
        target = MODEL_DIR / name
        actual = TMP_MODELS / name
        if not actual.exists():
            hf_hub_download(repo_id=MODEL_REPO, filename=name, local_dir=str(TMP_MODELS))
        if target.exists() or target.is_symlink():
            target.unlink()
        target.symlink_to(actual)

    for name in small_files:
        target = MODEL_DIR / name
        if not target.exists():
            hf_hub_download(repo_id=MODEL_REPO, filename=name, local_dir=str(MODEL_DIR))

    gemma_tmp = TMP_MODELS / gemma_folder
    gemma_tmp.mkdir(parents=True, exist_ok=True)
    for name in gemma_files:
        actual = gemma_tmp / name
        if not actual.exists():
            hf_hub_download(repo_id=MODEL_REPO, filename=f"{gemma_folder}/{name}", local_dir=str(TMP_MODELS))
    gemma_target = MODEL_DIR / gemma_folder
    if gemma_target.exists() or gemma_target.is_symlink():
        if gemma_target.is_dir() and not gemma_target.is_symlink():
            shutil.rmtree(gemma_target)
        else:
            gemma_target.unlink()
    gemma_target.symlink_to(gemma_tmp)

    for cache in (MODEL_DIR / ".cache", TMP_MODELS / ".cache"):
        if cache.exists():
            shutil.rmtree(cache, ignore_errors=True)

    total = 0
    for p in TMP_MODELS.rglob("*"):
        if p.is_file():
            total += p.stat().st_size
    stage("models_ready", staged_bytes=total, staged_gib=round(total / 2**30, 3))


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: kaggle_ltx23_wan2gp_worker.py request.json")

    request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    prompt = str(request.get("prompt") or "").strip()
    if not prompt:
        prompt = "Smooth cinematic motion between the supplied first and last keyframes."

    width = align32(int(request.get("width") or 512))
    height = align32(int(request.get("height") or 288))
    duration = max(1.0, min(6.0, float(request.get("duration_seconds") or 1.0)))
    frame_num = max(9, int(round(duration * FPS / 8.0)) * 8 + 1)
    seed = int(request.get("seed") or 42)

    start_path = WORK / "nd-ltx23-start.png"
    end_path = WORK / "nd-ltx23-end.png"
    stage("materialize_inputs")
    download(str(request.get("start_image_url") or ""), start_path)
    download(str(request.get("end_image_url") or ""), end_path)

    ensure_repo_and_dependencies()
    ensure_models()

    stage("imports")
    import glob
    import numpy as np
    import torch
    from PIL import Image
    from mmgp import offload
    from shared.utils import files_locator as fl
    from shared.utils.audio_video import save_video

    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)
    torch.backends.cuda.enable_flash_sdp(False)
    torch.backends.cuda.enable_mem_efficient_sdp(True)
    torch.backends.cuda.enable_math_sdp(True)

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable")
    stage("gpu_layout", gpu_count=torch.cuda.device_count(),
          gpus=[torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())])

    fl.set_checkpoints_paths(["models", "ckpts", "."])
    from models.ltx2.ltx2_handler import family_handler

    base_model_type = "ltx2_22B"
    model_def = {"ltx2_pipeline": "distilled"}
    model_def.update(family_handler.query_model_def(base_model_type, model_def))

    gemma_folder = MODEL_DIR / "gemma-3-12b-it-qat-q4_0-unquantized"
    gemma_files = sorted(glob.glob(str(gemma_folder / "*.safetensors")))
    quanto_files = [x for x in gemma_files if "quanto" in x]
    text_encoder_file = quanto_files[0] if quanto_files else (gemma_files[0] if gemma_files else None)
    if not text_encoder_file:
        raise FileNotFoundError("Gemma text encoder not found")

    transformer_path = MODEL_DIR / "ltx-2.3-22b-distilled_diffusion_model_quanto_int8.safetensors"
    stage("load_model")
    ltx2_model, pipe = family_handler.load_model(
        model_filename=str(transformer_path),
        model_type="ltx2_22B_distilled",
        base_model_type=base_model_type,
        model_def=model_def,
        dtype=torch.bfloat16,
        VAE_dtype=torch.float32,
        text_encoder_filename=text_encoder_file,
    )

    stage("offload_profile")
    offload.profile(
        pipe,
        profile_no=4,
        quantizeTransformer=False,
        convertWeightsFloatTo=torch.bfloat16,
        budgets={
            "transformer": 7000,
            "text_encoder": 1500,
            "vae": 2500,
            "spatial_upsampler": 1500,
            "video_encoder": 1500,
            "*": 500,
        },
    )
    offload.shared_state["_attention"] = "sdpa"

    start = Image.open(start_path).convert("RGB")
    end = Image.open(end_path).convert("RGB")
    vram_mb = torch.cuda.get_device_properties(0).total_memory / (1024**2)
    effective_vram = vram_mb / 1.5
    vae_config = 1 if effective_vram >= 24000 else (2 if effective_vram >= 8000 else 3)
    if max(height, width) > 480:
        vae_config += 1
    vae_tile_size = 0 if vae_config <= 1 else (512 if vae_config == 2 else (256 if vae_config == 3 else 128))

    progress_state = {"pass": 1, "step": 0}
    def cb(step, latent, is_start, override_num_inference_steps=None, pass_no=None, **kwargs):
        if is_start:
            if pass_no is not None:
                progress_state["pass"] = int(pass_no)
            progress_state["step"] = 0
        else:
            progress_state["step"] += 1
            if progress_state["step"] <= 20:
                stage("generate_step", pass_no=progress_state["pass"], step=progress_state["step"])

    stage("generate", width=width, height=height, frames=frame_num, seed=seed, vae_tile=vae_tile_size)
    started = time.time()
    with torch.inference_mode():
        result = ltx2_model.generate(
            input_prompt=prompt,
            image_start=start,
            image_end=end,
            height=height,
            width=width,
            frame_num=frame_num,
            fps=FPS,
            seed=seed,
            callback=cb,
            VAE_tile_size=vae_tile_size,
            enhance_prompt=False,
        )
    generation_seconds = time.time() - started

    video_tensor = result.get("x") if isinstance(result, dict) else (result[0] if isinstance(result, tuple) else result)
    if video_tensor is None or not torch.is_tensor(video_tensor):
        raise RuntimeError("Wan2GP returned no video tensor")
    video_tensor = video_tensor.detach().cpu()
    if video_tensor.dim() != 4:
        raise RuntimeError(f"unexpected video tensor shape {tuple(video_tensor.shape)}")

    # Wan2GP currently returns [C,T,H,W] uint8. Normalize defensively if needed.
    if video_tensor.dtype == torch.uint8:
        arr = video_tensor.permute(1, 2, 3, 0).numpy()
        save_tensor = video_tensor.unsqueeze(0).float() / 127.5 - 1.0
    else:
        x = video_tensor.float()
        if float(x.min()) >= -1.01 and float(x.max()) <= 1.01:
            save_tensor = x.unsqueeze(0)
            arr = (((x.permute(1,2,3,0) + 1.0) / 2.0).clamp(0,1) * 255).to(torch.uint8).numpy()
        else:
            x = x.clamp(0, 1)
            save_tensor = x.unsqueeze(0) * 2.0 - 1.0
            arr = (x.permute(1,2,3,0) * 255).to(torch.uint8).numpy()

    result_mp4 = WORK / "result.mp4"
    stage("save_video")
    save_video(
        tensor=save_tensor,
        save_file=str(result_mp4),
        fps=FPS,
        normalize=True,
        value_range=(-1, 1),
    )
    frames = [Image.fromarray(arr[i]) for i in range(arr.shape[0])]
    endpoint = {
        "first_to_start_mae": mae(frames[0], start, (width, height)),
        "first_to_end_mae": mae(frames[0], end, (width, height)),
        "last_to_end_mae": mae(frames[-1], end, (width, height)),
        "last_to_start_mae": mae(frames[-1], start, (width, height)),
    }
    endpoint["endpoint_order_pass"] = (
        endpoint["first_to_start_mae"] < endpoint["first_to_end_mae"]
        and endpoint["last_to_end_mae"] < endpoint["last_to_start_mae"]
    )

    receipt = {
        "ok": True,
        "route": "kaggle_ltx23_wan2gp_runtime_f2l",
        "engine": "Wan2GP",
        "wan2gp_commit": WAN2GP_COMMIT,
        "model_repo": MODEL_REPO,
        "model_type": "ltx2_22B_distilled",
        "width": width,
        "height": height,
        "frames": len(frames),
        "fps": FPS,
        "duration_seconds": len(frames) / FPS,
        "generation_seconds": round(generation_seconds, 3),
        "size_bytes": result_mp4.stat().st_size,
        "sha256": hashlib.sha256(result_mp4.read_bytes()).hexdigest(),
        "seed": seed,
        "gpu_names": [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())],
        **endpoint,
    }
    (WORK / "result.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print("ND_LTX_F2L_JSON=" + json.dumps(receipt, separators=(",", ":"), sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
