# /// script
# requires-python = ">=3.10"
# dependencies = ["requests>=2.32.0"]
# ///
import argparse, base64, glob, json, os, pathlib, subprocess, sys, tempfile, textwrap

def run(cmd, cwd=None):
    print("+", " ".join(cmd), flush=True)
    subprocess.check_call(cmd, cwd=cwd)

def download(url, path):
    import requests
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(1024 * 1024):
                if chunk:
                    f.write(chunk)

ap = argparse.ArgumentParser()
ap.add_argument("--request-b64", required=True)
args = ap.parse_args()
req = json.loads(base64.urlsafe_b64decode(args.request_b64 + "=" * (-len(args.request_b64) % 4)).decode())

prompt = str(req.get("prompt") or "").strip()
if not prompt:
    raise SystemExit("prompt required")
urls = list(req.get("conditioning_media_urls") or [])
starts = [int(x) for x in (req.get("conditioning_start_frames") or [])]
if urls and len(urls) != len(starts):
    raise SystemExit("conditioning_media_urls and conditioning_start_frames length mismatch")

width = int(req.get("width", 512))
height = int(req.get("height", 768))
frames = int(req.get("num_frames", 49))
seed = int(req.get("seed", 42))
fps = int(req.get("frame_rate", 24))
if width < 256 or height < 256 or width > 1280 or height > 1280:
    raise SystemExit("width/height outside bounded worker range")
if frames < 9 or frames > 121:
    raise SystemExit("num_frames outside bounded worker range")

root = pathlib.Path("/tmp/nd-ltx")
src = root / "LTX-Video"
out = root / "outputs"
media = root / "media"
root.mkdir(parents=True, exist_ok=True)
media.mkdir(parents=True, exist_ok=True)
out.mkdir(parents=True, exist_ok=True)

if not src.exists():
    run(["git", "clone", "--depth", "1", "https://github.com/Lightricks/LTX-Video.git", str(src)])
run([sys.executable, "-m", "pip", "install", "-e", str(src) + "[inference]"])

local_media = []
for i, url in enumerate(urls):
    suffix = pathlib.Path(url.split("?")[0]).suffix or ".png"
    p = media / f"cond_{i}{suffix}"
    download(url, p)
    local_media.append(str(p))

cmd = [
    sys.executable, "inference.py",
    "--prompt", prompt,
    "--pipeline_config", "configs/ltxv-2b-0.9.8-distilled-fp8.yaml",
    "--height", str(height),
    "--width", str(width),
    "--num_frames", str(frames),
    "--seed", str(seed),
    "--frame_rate", str(fps),
    "--output_path", str(out),
    "--offload_to_cpu", "true",
]
if local_media:
    cmd += ["--conditioning_media_paths", *local_media]
    cmd += ["--conditioning_start_frames", *[str(x) for x in starts]]
    strengths = req.get("conditioning_strengths")
    if strengths:
        cmd += ["--conditioning_strengths", *[str(float(x)) for x in strengths]]

env = os.environ.copy()
env.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
print("ND_LTX_WORKER_CONFIG=" + json.dumps({
    "model": "ltxv-2b-0.9.8-distilled-fp8",
    "width": width, "height": height, "num_frames": frames,
    "conditioning_count": len(local_media), "seed": seed, "frame_rate": fps
}), flush=True)
subprocess.check_call(cmd, cwd=src, env=env)

files = sorted(glob.glob(str(out / "**" / "*.mp4"), recursive=True), key=os.path.getmtime)
if not files:
    raise SystemExit("no mp4 output found")
video = files[-1]
size = os.path.getsize(video)
print(f"ND_MP4_SIZE={size}", flush=True)
with open(video, "rb") as f:
    b64 = base64.b64encode(f.read()).decode()
for i in range(0, len(b64), 65536):
    print("ND_MP4_CHUNK=" + b64[i:i+65536], flush=True)
print("ND_LTX_WORKER_DONE=1", flush=True)
