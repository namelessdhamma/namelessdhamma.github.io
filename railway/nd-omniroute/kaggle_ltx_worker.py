#!/usr/bin/env python3
"""ND Kaggle LTX first/last-frame worker.

Designed for Kaggle T4x2 with mounted dataset:
  damnyadav/ltxv13b-distilled-cache

Input: JSON file path as argv[1].
Output:
  /kaggle/working/result.mp4
  /kaggle/working/result.json

No model-weight download is performed.
"""
from __future__ import annotations

from pathlib import Path
import base64
import gc
import hashlib
import inspect
import json
import math
import os
import subprocess
import sys
import time
import urllib.request

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

MODEL = Path("/kaggle/input/datasets/damnyadav/ltxv13b-distilled-cache")
WORK = Path("/kaggle/working")
TMP = Path("/tmp/nd-ltx-f2l")
FPS = 30
DISTILLED_TIMESTEPS = [1000, 993, 987, 981, 975, 909, 725]
DEFAULT_NEGATIVE = (
    "worst quality, inconsistent motion, blurry, jittery, distorted, morphing, "
    "flickering, duplicate subject, sudden cut, text, watermark, logo"
)


def _run(cmd: list[str], timeout: int) -> str:
    env = {**os.environ, "PIP_NO_CACHE_DIR": "1"}
    p = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
        env=env,
    )
    if p.returncode != 0:
        print("ND_LTX_CMD_FAIL " + repr(cmd) + "\n" + p.stdout[-10000:])
        raise RuntimeError("command failed: " + repr(cmd))
    return p.stdout


def _install() -> None:
    _run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-cache-dir",
            "-q",
            "diffusers>=0.37.0",
            "transformers>=4.48.0",
            "accelerate>=1.2.0",
            "bitsandbytes",
            "sentencepiece",
            "protobuf",
            "imageio",
            "imageio-ffmpeg",
            "safetensors",
        ],
        900,
    )


def _align32(v: int) -> int:
    return max(256, (int(v) // 32) * 32)


def _frame_count(seconds: float) -> int:
    raw = max(1.0, min(6.0, float(seconds))) * FPS
    k = max(1, round((raw - 1) / 8))
    return 8 * k + 1


def _download(url: str, path: Path) -> None:
    if not url.startswith(("http://", "https://")):
        raise ValueError("start/end image must be an http(s) URL")
    req = urllib.request.Request(url, headers={"User-Agent": "nd-kaggle-ltx/1.0"})
    with urllib.request.urlopen(req, timeout=120) as src, path.open("wb") as dst:
        while True:
            chunk = src.read(1024 * 1024)
            if not chunk:
                break
            dst.write(chunk)


def _materialize_image(request: dict, key: str, path: Path) -> None:
    inline = request.get(f"{key}_image_base64")
    if inline:
        raw = base64.b64decode(str(inline))
        if not raw or len(raw) > 20 * 1024 * 1024:
            raise ValueError(f"{key} inline image is empty or too large")
        path.write_bytes(raw)
        return
    _download(str(request.get(f"{key}_image_url") or ""), path)


def _mae(a, b, size):
    import numpy as np

    aa = np.array(a.resize(size)).astype(np.float32)
    bb = np.array(b.resize(size)).astype(np.float32)
    return float(np.mean(np.abs(aa - bb)))


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: kaggle_ltx_worker.py request.json")

    request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    prompt = str(request.get("prompt") or "").strip()
    if not prompt:
        prompt = (
            "Smooth coherent motion from the first keyframe to the final keyframe, "
            "continuous camera, physically plausible movement, no cuts."
        )

    negative = str(request.get("negative_prompt") or DEFAULT_NEGATIVE)
    width = _align32(int(request.get("width") or 864))
    height = _align32(int(request.get("height") or 480))
    if width * height > 864 * 480:
        scale = math.sqrt((864 * 480) / float(width * height))
        width = _align32(max(256, int(width * scale)))
        height = _align32(max(256, int(height * scale)))

    num_frames = _frame_count(float(request.get("duration_seconds") or 2.0))
    seed = int(request.get("seed") or 42)

    TMP.mkdir(parents=True, exist_ok=True)
    start_path = TMP / "start"
    end_path = TMP / "end"
    _materialize_image(request, "start", start_path)
    _materialize_image(request, "end", end_path)

    _install()

    import imageio.v2 as imageio
    import numpy as np
    import torch
    import torch.nn as nn
    from PIL import Image
    from diffusers import (
        AutoencoderKLLTXVideo,
        BitsAndBytesConfig as DiffusersBnBConfig,
        LTXConditionPipeline,
        LTXVideoTransformer3DModel,
    )
    from diffusers.pipelines.ltx.pipeline_ltx_condition import LTXVideoCondition
    from diffusers.schedulers import FlowMatchEulerDiscreteScheduler
    from transformers import (
        BitsAndBytesConfig as TransformersBnBConfig,
        T5EncoderModel,
        T5TokenizerFast,
    )

    if not torch.cuda.is_available() or torch.cuda.device_count() < 2:
        raise RuntimeError("ND Kaggle LTX requires T4x2 or equivalent two-GPU runtime")

    dtype = torch.float16
    max_transformer = {0: "14GiB", 1: "1GiB", "cpu": "8GiB"}
    max_t5 = {0: "1GiB", 1: "14GiB", "cpu": "8GiB"}

    nf4_diff = DiffusersBnBConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=dtype,
    )
    nf4_t5 = TransformersBnBConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=dtype,
    )

    if not getattr(LTXVideoTransformer3DModel, "_no_split_modules", None):
        LTXVideoTransformer3DModel._no_split_modules = []

    print("ND_LTX_STAGE=load_transformer")
    transformer = LTXVideoTransformer3DModel.from_pretrained(
        str(MODEL),
        subfolder="transformer",
        quantization_config=nf4_diff,
        torch_dtype=dtype,
        device_map="auto",
        max_memory=max_transformer,
        local_files_only=True,
    )

    class ChunkedFF(nn.Module):
        def __init__(self, ff, chunk=512):
            super().__init__()
            self.ff = ff
            self.chunk = chunk

        def forward(self, x, *args, **kwargs):
            if x.shape[1] <= self.chunk:
                return self.ff(x, *args, **kwargs)
            out = torch.empty_like(x)
            for start in range(0, x.shape[1], self.chunk):
                end = min(start + self.chunk, x.shape[1])
                out[:, start:end] = self.ff(x[:, start:end], *args, **kwargs)
            return out

    for block in transformer.transformer_blocks:
        if hasattr(block, "ff"):
            block.ff = ChunkedFF(block.ff, 512)

    print("ND_LTX_STAGE=load_t5")
    text_encoder = T5EncoderModel.from_pretrained(
        str(MODEL),
        subfolder="text_encoder",
        quantization_config=nf4_t5,
        torch_dtype=dtype,
        device_map="auto",
        max_memory=max_t5,
        local_files_only=True,
    )
    tokenizer = T5TokenizerFast.from_pretrained(
        str(MODEL), subfolder="tokenizer", local_files_only=True
    )

    print("ND_LTX_STAGE=load_vae")
    vae = AutoencoderKLLTXVideo.from_pretrained(
        str(MODEL), subfolder="vae", torch_dtype=dtype, local_files_only=True
    ).to("cuda:0")
    scheduler = FlowMatchEulerDiscreteScheduler.from_pretrained(
        str(MODEL), subfolder="scheduler", local_files_only=True
    )

    pipe = LTXConditionPipeline(
        transformer=transformer,
        text_encoder=text_encoder,
        tokenizer=tokenizer,
        vae=vae,
        scheduler=scheduler,
    )

    start = Image.open(start_path).convert("RGB").resize((width, height), Image.LANCZOS)
    end = Image.open(end_path).convert("RGB").resize((width, height), Image.LANCZOS)
    conditions = [
        LTXVideoCondition(image=start, frame_index=0),
        LTXVideoCondition(image=end, frame_index=num_frames - 1),
    ]

    kwargs = dict(
        prompt=prompt,
        negative_prompt=negative,
        width=width,
        height=height,
        num_frames=num_frames,
        guidance_scale=1.0,
        decode_timestep=0.05,
        decode_noise_scale=0.025,
        image_cond_noise_scale=0.025,
        generator=torch.Generator(device="cuda:0").manual_seed(seed),
        output_type="latent",
        conditions=conditions,
    )
    params = set(inspect.signature(pipe.__call__).parameters.keys())
    if "timesteps" in params:
        kwargs["timesteps"] = DISTILLED_TIMESTEPS
    else:
        kwargs["num_inference_steps"] = 7
    if "tone_map_compression_ratio" in params:
        kwargs["tone_map_compression_ratio"] = 0.6

    gc.collect()
    torch.cuda.empty_cache()

    print("ND_LTX_STAGE=generate")
    started = time.time()
    latents = pipe(**kwargs).frames
    generation_seconds = time.time() - started

    mean = pipe.vae.latents_mean.view(1, -1, 1, 1, 1).to(
        latents.device, latents.dtype
    )
    std = pipe.vae.latents_std.view(1, -1, 1, 1, 1).to(
        latents.device, latents.dtype
    )
    latents = latents * std + mean

    pipe.vae.to("cuda:1")
    latents = latents.to("cuda:1", pipe.vae.dtype)
    timestep = torch.tensor([0.05], device="cuda:1", dtype=pipe.vae.dtype)

    print("ND_LTX_STAGE=decode")
    with torch.no_grad():
        decoded = pipe.vae.decode(latents, timestep, return_dict=False)[0]

    decoded = decoded.squeeze(0).permute(1, 2, 3, 0)
    decoded = ((decoded.float() + 1.0) / 2.0).clamp(0, 1)
    arr = (decoded * 255).to(torch.uint8).cpu().numpy()
    frames = [Image.fromarray(arr[i]) for i in range(arr.shape[0])]

    result_mp4 = WORK / "result.mp4"
    imageio.mimsave(
        str(result_mp4),
        [np.array(frame) for frame in frames],
        fps=FPS,
        codec="libx264",
        quality=7,
    )

    endpoint = {
        "first_to_start_mae": _mae(frames[0], start, (width, height)),
        "first_to_end_mae": _mae(frames[0], end, (width, height)),
        "last_to_end_mae": _mae(frames[-1], end, (width, height)),
        "last_to_start_mae": _mae(frames[-1], start, (width, height)),
    }
    endpoint["endpoint_order_pass"] = (
        endpoint["first_to_start_mae"] < endpoint["first_to_end_mae"]
        and endpoint["last_to_end_mae"] < endpoint["last_to_start_mae"]
    )

    receipt = {
        "ok": True,
        "route": "kaggle_ltx13b_mounted_cache_f2l",
        "pipeline": "LTXConditionPipeline",
        "dataset_source": "damnyadav/ltxv13b-distilled-cache",
        "width": width,
        "height": height,
        "frames": len(frames),
        "fps": FPS,
        "duration_seconds": len(frames) / FPS,
        "generation_seconds": round(generation_seconds, 3),
        "size_bytes": result_mp4.stat().st_size,
        "sha256": hashlib.sha256(result_mp4.read_bytes()).hexdigest(),
        "seed": seed,
        "gpu_names": [
            torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())
        ],
        **endpoint,
    }
    (WORK / "result.json").write_text(
        json.dumps(receipt, indent=2), encoding="utf-8"
    )
    print("ND_LTX_F2L_JSON=" + json.dumps(receipt, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()