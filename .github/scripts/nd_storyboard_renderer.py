#!/usr/bin/env python3
import json, os, pathlib, subprocess, sys, urllib.request

ROOT = pathlib.Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "nd-storyboard-render"
FRAMES = ROOT / "frames"
CLIPS = ROOT / "clips"
OUT = pathlib.Path("storyboard-output.mp4")
ROOT.mkdir(parents=True, exist_ok=True)
FRAMES.mkdir(parents=True, exist_ok=True)
CLIPS.mkdir(parents=True, exist_ok=True)

def run(cmd):
    print("+", " ".join(map(str, cmd)), flush=True)
    subprocess.check_call([str(x) for x in cmd])

def ffprobe(path):
    out = subprocess.check_output([
        "ffprobe","-v","error","-select_streams","v:0",
        "-show_entries","stream=width,height,r_frame_rate,duration",
        "-of","json",str(path)
    ], text=True)
    return json.loads(out)

manifest = json.loads(os.environ.get("ND_STORYBOARD_MANIFEST", "{}"))
frames = manifest.get("frames") or []
if len(frames) < 2:
    raise SystemExit("at least two frames are required")

width = int(manifest.get("width", 640))
height = int(manifest.get("height", 360))
fps = int(manifest.get("fps", 24))
default_duration = float(manifest.get("default_duration", 1.4))
transition_duration = float(manifest.get("transition_duration", 0.30))

if not (256 <= width <= 1920 and 256 <= height <= 1920):
    raise SystemExit("width/height outside bounded range")
if not (12 <= fps <= 60):
    raise SystemExit("fps outside bounded range")
if not (0.05 <= transition_duration <= 1.0):
    raise SystemExit("transition_duration outside bounded range")

downloaded = []
for i, frame in enumerate(frames):
    url = str(frame.get("url") or "").strip()
    if not url.startswith(("https://","http://")):
        raise SystemExit(f"frame {i} requires http(s) url")
    ext = pathlib.Path(url.split("?")[0]).suffix.lower()
    if ext not in {".png",".jpg",".jpeg",".webp"}:
        ext = ".img"
    target = FRAMES / f"{i:03d}{ext}"
    print(f"download frame {i}: {url}", flush=True)
    urllib.request.urlretrieve(url, target)
    downloaded.append(target)

clip_paths = []
durations = []
for i, (frame, src) in enumerate(zip(frames, downloaded)):
    duration = float(frame.get("duration", default_duration))
    if not (0.20 <= duration <= 20.0):
        raise SystemExit(f"frame {i} duration outside bounded range")
    motion = str(frame.get("motion") or "slow_push_in")
    clip = CLIPS / f"{i:03d}.mp4"

    base = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
    if motion == "static":
        vf = f"{base},fps={fps},format=yuv420p"
    elif motion == "slow_pull_out":
        vf = (
            f"{base},zoompan="
            f"z='if(eq(on,0),1.08,max(1.0,zoom-0.0008))':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d=1:s={width}x{height}:fps={fps},format=yuv420p"
        )
    elif motion == "pan_left":
        vf = (
            f"scale={int(width*1.12)}:{int(height*1.12)}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height}:x='(in_w-out_w)*(1-t/{duration})':y='(in_h-out_h)/2',"
            f"fps={fps},format=yuv420p"
        )
    elif motion == "pan_right":
        vf = (
            f"scale={int(width*1.12)}:{int(height*1.12)}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height}:x='(in_w-out_w)*(t/{duration})':y='(in_h-out_h)/2',"
            f"fps={fps},format=yuv420p"
        )
    else:
        vf = (
            f"{base},zoompan="
            f"z='min(1.08,1+on*0.0008)':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d=1:s={width}x{height}:fps={fps},format=yuv420p"
        )

    run([
        "ffmpeg","-y","-hide_banner","-loglevel","error",
        "-loop","1","-i",src,
        "-t",f"{duration:.3f}",
        "-vf",vf,
        "-an","-c:v","libx264","-preset","veryfast","-crf","20",
        "-pix_fmt","yuv420p","-movflags","+faststart",clip
    ])
    clip_paths.append(clip)
    durations.append(duration)

# Chain xfade transitions. A hard cut is represented by a very short fade.
inputs = []
for p in clip_paths:
    inputs += ["-i", str(p)]

filters = []
prev = "[0:v]"
elapsed = durations[0]
for i in range(1, len(clip_paths)):
    trans = str(frames[i].get("transition") or "fade")
    if trans == "cut":
        trans_name = "fade"
        td = 0.05
    else:
        trans_name = {
            "fade":"fade",
            "wipeleft":"wipeleft",
            "wiperight":"wiperight",
            "fadeblack":"fadeblack",
            "slideleft":"slideleft",
            "slideright":"slideright",
        }.get(trans, "fade")
        td = transition_duration
    offset = max(0.0, elapsed - td)
    outlabel = f"[v{i}]"
    filters.append(f"{prev}[{i}:v]xfade=transition={trans_name}:duration={td:.3f}:offset={offset:.3f}{outlabel}")
    prev = outlabel
    elapsed = elapsed + durations[i] - td

filter_complex = ";".join(filters)
run([
    "ffmpeg","-y","-hide_banner","-loglevel","error",
    *inputs,
    "-filter_complex",filter_complex,
    "-map",prev,
    "-an","-r",str(fps),
    "-c:v","libx264","-preset","veryfast","-crf","20",
    "-pix_fmt","yuv420p","-movflags","+faststart",
    OUT
])

probe = ffprobe(OUT)
receipt = {
    "ok": True,
    "engine": "ffmpeg-storyboard-v1",
    "frames": len(frames),
    "width": width,
    "height": height,
    "fps": fps,
    "output": str(OUT),
    "bytes": OUT.stat().st_size,
    "probe": probe,
    "rife": "NOT_YET_QUALIFIED"
}
pathlib.Path("storyboard-receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
print(json.dumps(receipt), flush=True)
