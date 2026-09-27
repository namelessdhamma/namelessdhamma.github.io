import os
import subprocess
import tempfile
import urllib.request
from pathlib import Path

import modal

LTX_COMMIT = "4b2d053057623ddd4d0a1d3e9cd28890e9ef487f"
LTX_ROOT = Path("/opt/LTX-Video")
PIPELINE_CONFIG = "configs/ltxv-2b-0.9.8-distilled-fp8.yaml"

app = modal.App("nd-ltx2b-first-last")
cache = modal.Volume.from_name("nd-ltx2b-hf-cache", create_if_missing=True)

image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.4.1-devel-ubuntu22.04",
        add_python="3.11",
    )
    .apt_install("git", "ffmpeg", "libgl1", "libglib2.0-0")
    .run_commands(
        f"git clone https://github.com/Lightricks/LTX-Video.git {LTX_ROOT}",
        f"cd {LTX_ROOT} && git checkout {LTX_COMMIT}",
        f"cd {LTX_ROOT} && pip install '.[inference]' fastapi pydantic",
    )
)

with image.imports():
    from fastapi import HTTPException, Response
    from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    start_image_url: str
    end_image_url: str
    prompt: str = "Smooth cinematic transition between keyframes with natural motion and consistent lighting."
    negative_prompt: str = "worst quality, inconsistent motion, blurry, jittery, distorted, sudden cut, duplicate subject, text, watermark"
    duration_seconds: float = Field(default=2.0, ge=1.0, le=6.0)
    width: int = Field(default=512, ge=256, le=1280)
    height: int = Field(default=288, ge=256, le=1280)
    frame_rate: int = Field(default=24, ge=1, le=60)
    seed: int = 42
    start_strength: float = Field(default=1.0, ge=0.0, le=1.0)
    end_strength: float = Field(default=0.9, ge=0.0, le=1.0)


def _num_frames(duration_seconds: float, fps: int) -> int:
    requested = max(9, int(round(duration_seconds * fps)))
    # LTX inference pads to N*8+1. Keep the requested endpoint itself on that grid.
    frames = 1 + 8 * max(1, round((requested - 1) / 8))
    return min(frames, 121)


def _download(url: str, target: Path) -> None:
    if not url.startswith(("https://", "http://")):
        raise ValueError("start/end image URLs must be http(s)")
    req = urllib.request.Request(url, headers={"User-Agent": "nd-modal-ltx/1.0"})
    with urllib.request.urlopen(req, timeout=90) as src, target.open("wb") as dst:
        total = 0
        while True:
            chunk = src.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > 20 * 1024 * 1024:
                raise ValueError("input image exceeds 20 MiB")
            dst.write(chunk)


@app.function(
    image=image,
    gpu="T4",
    timeout=1800,
    scaledown_window=120,
    volumes={"/root/.cache/huggingface": cache},
)
@modal.fastapi_endpoint(method="POST", requires_proxy_auth=True, docs=True)
def generate(req: GenerateRequest):
    frames = _num_frames(req.duration_seconds, req.frame_rate)
    endpoint_frame = frames - 1

    try:
        with tempfile.TemporaryDirectory(prefix="nd-ltx2b-") as td:
            work = Path(td)
            start = work / "start.png"
            end = work / "end.png"
            out = work / "out"
            out.mkdir(parents=True, exist_ok=True)

            _download(req.start_image_url, start)
            _download(req.end_image_url, end)

            cmd = [
                "python", "-m", "ltx_video.inference",
                "--pipeline_config", PIPELINE_CONFIG,
                "--prompt", req.prompt,
                "--negative_prompt", req.negative_prompt,
                "--height", str(req.height),
                "--width", str(req.width),
                "--num_frames", str(frames),
                "--frame_rate", str(req.frame_rate),
                "--seed", str(req.seed),
                "--conditioning_media_paths", str(start), str(end),
                "--conditioning_strengths", str(req.start_strength), str(req.end_strength),
                "--conditioning_start_frames", "0", str(endpoint_frame),
                "--output_path", str(out),
                "--offload_to_cpu",
            ]
            run = subprocess.run(
                cmd,
                cwd=str(LTX_ROOT),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=1700,
            )
            if run.returncode != 0:
                raise RuntimeError("LTX inference failed: " + run.stdout[-6000:])

            outputs = sorted(out.rglob("*.mp4"), key=lambda p: p.stat().st_mtime)
            if not outputs:
                raise RuntimeError("LTX inference returned no MP4")

            video = outputs[-1].read_bytes()
            if not video:
                raise RuntimeError("LTX output MP4 is empty")
            if len(video) > 150 * 1024 * 1024:
                raise RuntimeError("LTX output exceeds 150 MiB")

            try:
                cache.commit()
            except Exception:
                pass

            return Response(
                content=video,
                media_type="video/mp4",
                headers={
                    "X-ND-Route": "modal_ltx2b_distilled_f2l",
                    "X-ND-Frames": str(frames),
                    "X-ND-Seed": str(req.seed),
                    "Cache-Control": "no-store",
                },
            )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)[:7000])


@app.function(image=image)
@modal.fastapi_endpoint(method="GET", requires_proxy_auth=True, docs=False)
def health():
    return {
        "ok": True,
        "route": "modal_ltx2b_distilled_f2l",
        "model": "Lightricks/LTX-Video 2B 0.9.8 distilled FP8",
        "ltx_commit": LTX_COMMIT,
        "gpu": "T4",
        "cost_policy": "FREE_CREDIT_ONLY",
        "first_last": True,
        "max_duration_seconds": 6,
        "max_frames": 121,
    }
