#!/usr/bin/env python3
import json, os, pathlib, shutil, subprocess, sys, time, urllib.request

ROOT=pathlib.Path(os.environ.get("RUNNER_TEMP","/tmp"))/"nd-rife-bench"
ROOT.mkdir(parents=True,exist_ok=True)
a=ROOT/"a.png"; b=ROOT/"b.png"
urls=[
  "https://huggingface.co/datasets/huggingface/documentation-images/resolve/main/diffusers/cat.png",
  "https://huggingface.co/datasets/huggingface/documentation-images/resolve/main/diffusers/cat.png?bench=2"
]
for u,p in zip(urls,[a,b]):
    urllib.request.urlretrieve(u,p)

repo=ROOT/"Practical-RIFE"
if not repo.exists():
    subprocess.check_call(["git","clone","--depth","1","https://github.com/hzwer/Practical-RIFE.git",str(repo)])

model_zip=ROOT/"rife425lite.zip"
if not model_zip.exists():
    subprocess.check_call([sys.executable,"-m","gdown","--fuzzy",
      "https://drive.google.com/file/d/1zlKblGuKNatulJNFf5jdB-emp9AqGK05/view?usp=share_link",
      "-O",str(model_zip)])
unpack=ROOT/"model"
if unpack.exists(): shutil.rmtree(unpack)
unpack.mkdir()
subprocess.check_call(["unzip","-q",str(model_zip),"-d",str(unpack)])
candidates=list(unpack.rglob("flownet.pkl"))
if not candidates:
    raise SystemExit("flownet.pkl not found in downloaded RIFE lite archive")
srcdir=candidates[0].parent
dst=repo/"train_log"
if dst.exists(): shutil.rmtree(dst)
shutil.copytree(srcdir,dst)

# Practical-RIFE's generic image demo hardcodes 448x256, while 4.25.lite
# expects the width path used here to align at 512. Patch only the benchmark checkout.
infer=repo/"inference_img.py"
src=infer.read_text()
src=src.replace("cv2.resize(img0, (448, 256))","cv2.resize(img0, (512, 256))")
src=src.replace("cv2.resize(img1, (448, 256))","cv2.resize(img1, (512, 256))")
infer.write_text(src)

out=repo/"output"
if out.exists(): shutil.rmtree(out)
start=time.perf_counter()
subprocess.check_call([
    sys.executable,"inference_img.py",
    "--img",str(a),str(b),
    "--exp","1",
    "--model",str(dst)
],cwd=repo)
elapsed=time.perf_counter()-start

imgs=sorted(out.glob("img*.png"))
if len(imgs)<3:
    raise SystemExit(f"expected >=3 interpolated frames, got {len(imgs)}")

# Build a tiny proof MP4 from the 3-image interpolation output.
for i,p in enumerate(imgs):
    shutil.copy2(p,ROOT/f"{i:03d}.png")
mp4=pathlib.Path("rife-benchmark.mp4")
subprocess.check_call([
  "ffmpeg","-y","-hide_banner","-loglevel","error",
  "-framerate","12","-i",str(ROOT/"%03d.png"),
  "-c:v","libx264","-pix_fmt","yuv420p","-movflags","+faststart",str(mp4)
])
probe=json.loads(subprocess.check_output([
  "ffprobe","-v","error","-select_streams","v:0",
  "-show_entries","stream=width,height,r_frame_rate,duration",
  "-of","json",str(mp4)
],text=True))
receipt={
  "ok":True,
  "engine":"Practical-RIFE 4.25.lite",
  "device":"cpu",
  "python":sys.version.split()[0],
  "interpolation_exp":1,
  "input_pair_count":1,
  "output_frame_count":len(imgs),
  "inference_seconds":round(elapsed,3),
  "mp4_bytes":mp4.stat().st_size,
  "probe":probe
}
pathlib.Path("rife-benchmark-receipt.json").write_text(json.dumps(receipt,indent=2))
print(json.dumps(receipt))
