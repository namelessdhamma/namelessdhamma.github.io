#!/usr/bin/env python3
"""ND Kaggle LTX 2B pure-Diffusers GGUF first/last-frame worker.

Purpose: bypass Wan2GP/MMGP on current Kaggle runtime while preserving
LTX 2B first/last-frame semantics. FREE_ONLY Kaggle T4 route.
"""
from __future__ import annotations

from pathlib import Path
import base64
import hashlib
import json
import math
import os
import subprocess
import sys
import time
import urllib.request

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

WORK = Path("/kaggle/working")
TMP = Path("/tmp/nd-ltx2b-diffusers")
FPS = 28
TRANSFORMER_URL = "https://huggingface.co/calcuis/ltxv-gguf/resolve/main/ltxv-2b-0.9.6-distilled-fp32-q8_0.gguf"
T5_REPO = "calcuis/ltxv-gguf"
T5_GGUF = "t5xxl_fp16-q4_0.gguf"
DECODER_REPO = "callgg/ltxv0.9.6-decoder"
DEFAULT_NEGATIVE = (
    "blurry, mushy, soft focus, cartoon, anime, plastic CGI, texture loss, "
    "over-smoothed surfaces, painterly smear, generic AI repaint, low detail, "
    "warped geometry, duplicate subject, sudden cut, crossfade, slideshow, text, watermark, UI"
)

def _run(cmd: list[str], timeout: int) -> None:
    env = {**os.environ, "PIP_NO_CACHE_DIR": "1"}
    print("ND_LTX2B_DIFF_CMD_START=" + repr(cmd[:6]), flush=True)
    started = time.time()
    p = subprocess.Popen(cmd, env=env)
    next_heartbeat = started + 20.0
    while True:
        rc = p.poll()
        if rc is not None:
            break
        now = time.time()
        if now - started >= timeout:
            p.kill()
            p.wait()
            raise TimeoutError("command timed out: " + repr(cmd))
        if now >= next_heartbeat:
            print(
                "ND_LTX2B_DIFF_CMD_HEARTBEAT elapsed_s="
                + str(int(now - started)),
                flush=True,
            )
            next_heartbeat = now + 20.0
        time.sleep(2.0)
    print(
        "ND_LTX2B_DIFF_CMD_DONE rc="
        + str(rc)
        + " elapsed_s="
        + str(round(time.time() - started, 3)),
        flush=True,
    )
    if rc != 0:
        raise RuntimeError("command failed: " + repr(cmd))

def _install_and_restart(request_path: str) -> bool:
    if os.environ.get("ND_LTX2B_DIFF_RUNTIME_READY") == "1":
        return False
    print("ND_LTX2B_DIFF_STAGE=install_dependencies", flush=True)
    _run(
        [
            sys.executable, "-m", "pip", "install", "--no-cache-dir", "-q",
            "diffusers>=0.37.0",
            "transformers>=4.48.0",
            "accelerate>=1.2.0",
            "gguf>=0.17.1",
            "sentencepiece",
            "protobuf",
            "imageio",
            "imageio-ffmpeg",
            "safetensors",
            "huggingface_hub",
        ],
        900,
    )
    print("ND_LTX2B_DIFF_STAGE=dependencies_ready", flush=True)
    env = dict(os.environ)
    env["ND_LTX2B_DIFF_RUNTIME_READY"] = "1"
    worker_path = Path("/kaggle/working/kaggle_ltx2b_diffusers_worker.py")
    if not worker_path.exists():
        worker_path = Path(sys.argv[0]).resolve()
    print("ND_LTX2B_DIFF_STAGE=clean_child_begin", flush=True)
    child = subprocess.run([sys.executable, str(worker_path), request_path], env=env)
    print("ND_LTX2B_DIFF_STAGE=clean_child_done rc=" + str(child.returncode), flush=True)
    if child.returncode != 0:
        raise RuntimeError("clean child failed rc=" + str(child.returncode))
    return True

def _download(url: str, path: Path) -> None:
    if not str(url).startswith(("http://", "https://")):
        raise ValueError("input image must be http(s)")
    req = urllib.request.Request(str(url), headers={"User-Agent": "nd-ltx2b-diffusers/1.0"})
    with urllib.request.urlopen(req, timeout=120) as src, path.open("wb") as dst:
        total = 0
        while True:
            chunk = src.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > 20 * 1024 * 1024:
                raise ValueError("input image exceeds 20 MiB")
            dst.write(chunk)

def _materialize(request: dict, key: str, path: Path) -> None:
    inline = request.get(f"{key}_image_base64")
    if inline:
        raw = base64.b64decode(str(inline))
        if not raw or len(raw) > 20 * 1024 * 1024:
            raise ValueError(f"{key} inline image invalid")
        path.write_bytes(raw)
        return
    _download(str(request.get(f"{key}_image_url") or ""), path)

def _frame_count(seconds: float) -> int:
    raw = max(0.6, min(6.0, float(seconds))) * FPS
    k = max(2, math.ceil((raw - 1) / 8))
    return min(121, 8 * k + 1)

def _align32(v: int) -> int:
    return max(256, int(round(v / 32.0)) * 32)

def _mae(a, b, size) -> float:
    import numpy as np
    aa = np.asarray(a.resize(size), dtype=np.float32)
    bb = np.asarray(b.resize(size), dtype=np.float32)
    return float(np.mean(np.abs(aa - bb)))

def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: kaggle_ltx2b_diffusers_worker.py request.json")
    request_path = str(sys.argv[1])
    request = json.loads(Path(request_path).read_text(encoding="utf-8"))

    TMP.mkdir(parents=True, exist_ok=True)
    start_path = TMP / "start.png"
    end_path = TMP / "end.png"

    if os.environ.get("ND_LTX2B_DIFF_INPUTS_READY") != "1":
        print("ND_LTX2B_DIFF_STAGE=materialize_inputs", flush=True)
        _materialize(request, "start", start_path)
        _materialize(request, "end", end_path)
        print(
            "ND_LTX2B_DIFF_STAGE=materialize_inputs_done start_bytes="
            + str(start_path.stat().st_size)
            + " end_bytes="
            + str(end_path.stat().st_size),
            flush=True,
        )
        os.environ["ND_LTX2B_DIFF_INPUTS_READY"] = "1"

    if _install_and_restart(request_path):
        return

    print("ND_LTX2B_DIFF_STAGE=clean_child_runtime_ready", flush=True)

    import torch
    from PIL import Image, ImageOps
    from diffusers import GGUFQuantizationConfig, LTXVideoTransformer3DModel
    from diffusers.pipelines.ltx.pipeline_ltx_condition import (
        LTXConditionPipeline,
        LTXVideoCondition,
    )
    from diffusers.utils import export_to_video
    from transformers import T5EncoderModel

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU required")
    print(
        "ND_LTX2B_DIFF_GPU="
        + json.dumps(
            {
                "count": torch.cuda.device_count(),
                "names": [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())],
            },
            separators=(",", ":"),
        ),
        flush=True,
    )

    width = _align32(int(request.get("width") or 736))
    height = _align32(int(request.get("height") or 416))
    if width * height > 736 * 416:
        scale = math.sqrt((736 * 416) / float(width * height))
        width = _align32(max(256, int(width * scale)))
        height = _align32(max(256, int(height * scale)))
    frames = _frame_count(float(request.get("duration_seconds") or 2.0))
    seed = int(request.get("seed") or 42)
    prompt = str(request.get("prompt") or "").strip() or "A continuous cinematic motion shot."
    negative = str(request.get("negative_prompt") or DEFAULT_NEGATIVE)

    print(
        "ND_LTX2B_DIFF_STAGE=load_transformer "
        + json.dumps({"width": width, "height": height, "frames": frames, "fps": FPS}),
        flush=True,
    )
    transformer = LTXVideoTransformer3DModel.from_single_file(
        TRANSFORMER_URL,
        quantization_config=GGUFQuantizationConfig(compute_dtype=torch.bfloat16),
        torch_dtype=torch.bfloat16,
    )
    print("ND_LTX2B_DIFF_STAGE=load_t5", flush=True)
    text_encoder = T5EncoderModel.from_pretrained(
        T5_REPO,
        gguf_file=T5_GGUF,
        torch_dtype=torch.bfloat16,
    )
    print("ND_LTX2B_DIFF_STAGE=load_pipeline", flush=True)
    pipe = LTXConditionPipeline.from_pretrained(
        DECODER_REPO,
        transformer=transformer,
        text_encoder=text_encoder,
        torch_dtype=torch.bfloat16,
    )
    try:
        pipe.vae.enable_tiling()
    except Exception:
        pass
    try:
        pipe.enable_model_cpu_offload()
        offload_mode = "model_cpu_offload"
    except Exception:
        pipe = pipe.to("cuda")
        offload_mode = "cuda"
    print("ND_LTX2B_DIFF_STAGE=pipeline_ready mode=" + offload_mode, flush=True)

    start = Image.open(start_path).convert("RGB")
    end = Image.open(end_path).convert("RGB")
    start = ImageOps.fit(start, (width, height), method=Image.Resampling.LANCZOS)
    end = ImageOps.fit(end, (width, height), method=Image.Resampling.LANCZOS)

    conditions = [
        LTXVideoCondition(image=start, frame_index=0),
        LTXVideoCondition(image=end, frame_index=frames - 1),
    ]
    generator = torch.Generator(device="cuda").manual_seed(seed)
    timesteps = [1000, 993, 987, 981, 975, 909, 725]

    print("ND_LTX2B_DIFF_STAGE=generate", flush=True)
    started = time.time()
    out = pipe(
        conditions=conditions,
        prompt=prompt,
        negative_prompt=negative,
        width=width,
        height=height,
        num_frames=frames,
        frame_rate=FPS,
        timesteps=timesteps,
        guidance_scale=1.0,
        image_cond_noise_scale=0.025,
        decode_timestep=0.05,
        decode_noise_scale=0.025,
        generator=generator,
        output_type="pil",
    )
    generation_seconds = time.time() - started
    video_frames = out.frames[0]
    if not video_frames:
        raise RuntimeError("pipeline returned no frames")

    result_mp4 = WORK / "result.mp4"
    export_to_video(video_frames, str(result_mp4), fps=FPS)

    endpoint = {
        "first_to_start_mae": _mae(video_frames[0], start, (width, height)),
        "first_to_end_mae": _mae(video_frames[0], end, (width, height)),
        "last_to_end_mae": _mae(video_frames[-1], end, (width, height)),
        "last_to_start_mae": _mae(video_frames[-1], start, (width, height)),
    }
    endpoint["endpoint_order_pass"] = (
        endpoint["first_to_start_mae"] < endpoint["first_to_end_mae"]
        and endpoint["last_to_end_mae"] < endpoint["last_to_start_mae"]
    )

    receipt = {
        "ok": True,
        "route": "kaggle_ltx2b_diffusers_gguf_f2l",
        "pipeline": "LTXConditionPipeline",
        "transformer": "calcuis/ltxv-gguf:q8_0",
        "text_encoder": "calcuis/ltxv-gguf:t5xxl_q4_0",
        "decoder": DECODER_REPO,
        "width": width,
        "height": height,
        "frames": len(video_frames),
        "fps": FPS,
        "duration_seconds": len(video_frames) / FPS,
        "generation_seconds": round(generation_seconds, 3),
        "size_bytes": result_mp4.stat().st_size,
        "sha256": hashlib.sha256(result_mp4.read_bytes()).hexdigest(),
        "seed": seed,
        "offload_mode": offload_mode,
        "gpu_names": [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())],
        **endpoint,
    }
    (WORK / "result.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(
        "ND_LTX2B_RECEIPT_JSON="
        + json.dumps(receipt, separators=(",", ":"), sort_keys=True),
        flush=True,
    )

if __name__ == "__main__":
    main()
