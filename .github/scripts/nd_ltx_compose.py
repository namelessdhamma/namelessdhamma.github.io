import base64
import hashlib
import json
import os
import pathlib
import subprocess
import urllib.request

ROOT = pathlib.Path.cwd()
WORK = ROOT / ".nd-ltx-compose-work"
WORK.mkdir(exist_ok=True)
OUT = ROOT / "ltx-compose-output.mp4"
RECEIPT = ROOT / "ltx-compose-receipt.json"

def run(cmd):
    subprocess.run(cmd, check=True)

def download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "nd-ltx-compose/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)

manifest = json.loads(os.environ.get("ND_LTX_COMPOSE_MANIFEST", "{}"))
if not isinstance(manifest, dict):
    raise SystemExit("manifest must be an object")

width = int(manifest.get("width", 512))
height = int(manifest.get("height", 288))
fps = int(manifest.get("fps", 30))
if (width, height, fps) != (512, 288, 30):
    raise SystemExit("this production route is pinned to 512x288 @ 30fps")

clips = manifest.get("clips") or []
timeline = manifest.get("timeline") or []
if not (1 <= len(clips) <= 12):
    raise SystemExit("clips must contain 1..12 items")
if not (1 <= len(timeline) <= 40):
    raise SystemExit("timeline must contain 1..40 items")

clip_paths = []
for i, clip in enumerate(clips):
    if not isinstance(clip, dict):
        raise SystemExit(f"clip {i} must be an object")
    url = str(clip.get("url", "")).strip()
    if not url.startswith("https://"):
        raise SystemExit(f"clip {i} requires https url")
    dest = WORK / f"clip-{i:02d}.mp4"
    download(url, dest)
    if dest.stat().st_size <= 0:
        raise SystemExit(f"clip {i} is empty")
    clip_paths.append(dest)

segments = []
for i, item in enumerate(timeline):
    if not isinstance(item, dict):
        raise SystemExit(f"timeline item {i} must be an object")
    typ = str(item.get("type", "")).strip()
    seg = WORK / f"seg-{i:02d}.mp4"
    common = [
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p", "-r", str(fps),
        "-g", str(fps * 2), "-keyint_min", str(fps * 2),
        "-sc_threshold", "0", "-an"
    ]
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,"
        f"fps={fps},format=yuv420p"
    )
    if typ == "clip":
        idx = int(item.get("index", -1))
        if idx < 0 or idx >= len(clip_paths):
            raise SystemExit(f"timeline clip index out of range at {i}")
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-i", str(clip_paths[idx]), "-map", "0:v:0", "-vf", vf,
             *common, str(seg)])
    elif typ == "black":
        duration = float(item.get("duration", 0))
        if not (0.05 <= duration <= 20):
            raise SystemExit(f"invalid black duration at {i}")
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-f", "lavfi", "-i",
             f"color=c=black:s={width}x{height}:r={fps}:d={duration}",
             *common, str(seg)])
    elif typ == "image_b64":
        duration = float(item.get("duration", 0))
        rel = str(item.get("path", "")).strip()
        if not (0.05 <= duration <= 5):
            raise SystemExit(f"invalid image duration at {i}")
        if not rel.startswith(".github/assets/blue-sea-intro/") or not rel.endswith(".b64"):
            raise SystemExit(f"invalid image asset path at {i}")
        src = (ROOT / rel).resolve()
        if ROOT.resolve() not in src.parents or not src.exists():
            raise SystemExit(f"image asset missing at {i}")
        jpg = WORK / f"flash-{i:02d}.jpg"
        jpg.write_bytes(base64.b64decode(src.read_text().strip(), validate=True))
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-loop", "1", "-framerate", str(fps), "-t", str(duration),
             "-i", str(jpg), "-vf", vf, *common, str(seg)])
    else:
        raise SystemExit(f"unsupported timeline type at {i}: {typ}")
    if not seg.exists() or seg.stat().st_size <= 0:
        raise SystemExit(f"segment {i} was not produced")
    segments.append(seg)

concat = WORK / "concat.txt"
concat.write_text("".join("file '" + str(p.resolve()).replace("'", "'\\''") + "'\n" for p in segments))
run([
    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
    "-f", "concat", "-safe", "0", "-i", str(concat),
    "-c:v", "libx264", "-preset", "medium", "-crf", "18",
    "-pix_fmt", "yuv420p", "-r", str(fps),
    "-movflags", "+faststart", "-an", str(OUT)
])

probe = subprocess.check_output([
    "ffprobe", "-v", "error", "-show_entries", "format=duration",
    "-of", "default=noprint_wrappers=1:nokey=1", str(OUT)
], text=True).strip()
sha = hashlib.sha256(OUT.read_bytes()).hexdigest()
receipt = {
    "ok": True,
    "renderer": "ffmpeg-ltx-compose-v1",
    "request_id": os.environ.get("ND_REQUEST_ID"),
    "preset": manifest.get("preset"),
    "width": width,
    "height": height,
    "fps": fps,
    "duration_seconds": float(probe),
    "bytes": OUT.stat().st_size,
    "sha256": sha,
    "clip_count": len(clips),
    "timeline_items": len(timeline),
    "source_request_ids": [str(x.get("request_id", "")) for x in clips],
    "audio": "NONE"
}
RECEIPT.write_text(json.dumps(receipt, indent=2, sort_keys=True))
print("ND_LTX_COMPOSE_JSON=" + json.dumps(receipt, separators=(",", ":"), sort_keys=True))
