#!/usr/bin/env python3
"""Z11 bounded vocal surgery. Master M3 frozen; never regenerate backing."""
import os, sys, json, pathlib, subprocess, tempfile, urllib.request, hashlib
import numpy as np
from tools.gg_cloud_music_worker import ensure_applio_runtime, install_rvc_model
ROOT=pathlib.Path(os.getcwd())
OUT=ROOT/"z11_out"; OUT.mkdir(exist_ok=True)
TMP=ROOT/"z11_tmp"; TMP.mkdir(exist_ok=True)
Z10_MASTER="https://cdn.creativeclaw.co/u/3ce53768/audio/973beaaf-5131-472c-b685-92717052a036.mp3"
Z10_VOCAL="https://cdn.creativeclaw.co/u/3ce53768/audio/faaf78a6-b533-4894-8ee4-9c80b0eebdee.mp3"
SR=48000
def run(cmd,timeout=180):
 p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout)
 if p.returncode:raise RuntimeError(str(cmd)+"\n"+p.stdout[-6500:])
 return p.stdout
def dl(u,f):
 with urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"ND-Music-Studio-Z11/1.0"}),timeout=90) as x,open(f,"wb") as y:
  while True:
   b=x.read(1048576)
   if not b:break
   y.write(b)
 if pathlib.Path(f).stat().st_size<100000:raise RuntimeError("missing source "+str(f))
def dec(src,out,channels):
 run(["ffmpeg","-nostdin","-y","-v","error","-i",str(src),"-f","f32le","-ar",str(SR),"-ac",str(channels),str(out)])
 a=np.fromfile(out,dtype="<f4")
 return a.reshape((-1,channels)).astype(np.float64)
def enc(a,path,channels):
 raw=TMP/(path.stem+"_raw.f32")
 np.asarray(a,dtype="<f4").tofile(raw)
 run(["ffmpeg","-nostdin","-y","-v","error","-f","f32le","-ar",str(SR),"-ac",str(channels),"-i",str(raw),"-codec:a","libmp3lame","-b:a","320k",str(path)],timeout=240)
def region(a,b):return slice(int(round(a*SR)),int(round(b*SR)))
def fitlen(x,n):
 if len(x)>=n:return x[:n]
 return np.pad(x,(0,n-len(x)))
def convert(vocal, start, stop, idx, prot, model, index, root, vpy, tag):
 pad=.27; a=max(0,start-pad);b=min(len(vocal)/SR,stop+pad)
 chunk=vocal[region(a,b)]
 src=TMP/(tag+"_input.wav")
 ff=TMP/(tag+"_src.f32");np.asarray(chunk,dtype="<f4").tofile(ff)
 run(["ffmpeg","-nostdin","-y","-v","error","-f","f32le","-ar",str(SR),"-ac","1","-i",str(ff),"-c:a","pcm_s16le",str(src)])
 output=TMP/(tag+"_rvc.wav")
 cfg={"pitch":0,"index_rate":idx,"volume_envelope":1.0,"protect":prot,
      "f0_method":"fcpe","split_audio":False,"f0_autotune":False,
      "clean_audio":False,"formant_shifting":False,"post_process":False,
      "reverb":False,"chorus":False,"distortion":False,"delay":False}
 config=TMP/(tag+"_cfg.json");config.write_text(json.dumps(cfg))
 runner=TMP/(tag+"_infer.py")
 runner.write_text("""import os,sys,json
root,source,target,model,index,config=sys.argv[1:7]
os.chdir(root);sys.path.insert(0,root)
from core import run_infer_script
run_infer_script(input_path=source,output_path=target,pth_path=model,index_path=index,export_format='WAV',embedder_model='contentvec',**json.load(open(config)))
""")
 run([str(vpy),str(runner),str(root),str(src),str(output),str(model),str(index),str(config)],timeout=900)
 if not output.is_file():raise RuntimeError("RVC no output "+tag)
 out=dec(output,TMP/(tag+"_decoded.f32"),1)[:,0]
 n=len(chunk);out=fitlen(out,n)
 # Conservative local level match. Avoid unintentionally doubling consonant attacks.
 lo=int(.15*SR);hi=min(n,int(.95*n))
 base=np.sqrt(np.mean(chunk[lo:hi]**2)+1e-10)
 got=np.sqrt(np.mean(out[lo:hi]**2)+1e-10)
 out*=np.clip(base/max(got,1e-5),.65,1.55)
 # Preserve only intended word window, never overlap two pronunciations.
 i=max(0,round((start-a)*SR));j=min(n,round((stop-a)*SR))
 patch=np.array(vocal,copy=True)
 before=np.array(patch[round(a*SR):round(a*SR)+n],copy=True)
 candidate=out[i:j]; old=before[i:j]
 fade=min(len(candidate)//4,round(.090*SR))
 env=np.ones(len(candidate),dtype=np.float64)
 if fade:
  env[:fade]=np.sin(np.linspace(0,np.pi/2,fade))**2
  env[-fade:]=np.cos(np.linspace(0,np.pi/2,fade))**2
 patch[round(start*SR):round(start*SR)+len(candidate)]=old*(1-env)+candidate*env
 qc={"tag":tag,"window":[start,stop],"index_rate":idx,"protect":prot,
     "source_rms":float(base),"converted_rms":float(got),
     "edge_diffs":[float(abs(candidate[0]-old[0])),float(abs(candidate[-1]-old[-1]))],
     "change_rms":float(np.sqrt(np.mean((patch-vocal)**2)))}
 return patch,qc
def main():
 for url,name in [(Z10_MASTER,"base_z10_m3.mp3"),(Z10_VOCAL,"base_z10_vocal.mp3")]:dl(url,TMP/name)
 vocal=dec(TMP/"base_z10_vocal.mp3",TMP/"vocal.f32",1)[:,0]
 master=dec(TMP/"base_z10_m3.mp3",TMP/"master.f32",2)
 n=min(len(vocal),len(master));vocal=vocal[:n];master=master[:n]
 work=TMP/"inference";work.mkdir(exist_ok=True)
 root,vpy,meta=ensure_applio_runtime(work)
 model,index,imeta=install_rvc_model("awata-weak-rvc-v1.2","Original",work)
 # Preserve Z10 everywhere except the two disputed phoneme groups.
 # RVC is applied to a single existing voice track, not mixed over it.
 paths=[("tropy_C",29.385,30.63,.30,.27),
        ("tropy_D",29.385,30.63,.50,.27),
        ("nezab_C",160.76,162.53,.30,.22),
        ("nezab_D",160.76,162.53,.50,.30)]
 results={}
 for tag,a,b,idx,prot in paths:
  variant,qa=convert(vocal,a,b,idx,prot,model,index,root,vpy,tag)
  results[tag]=(variant,qa)
  piece=variant[region(a-.25,b+.25)]
  enc(piece,OUT/(tag+"_audition.mp3"),1)
 # Model-index C favors conservative consonant preservation for 'tropy'.
 # Model-index D selected for tonal continuity only if it retains transient energy.
 def transient_ratio(x,a,b):
  s=x[region(a,b)];k=np.diff(s)
  return float(np.sqrt(np.mean(k*k)+1e-12))
 nz_c=transient_ratio(results["nezab_C"][0],160.85,161.95)
 nz_d=transient_ratio(results["nezab_D"][0],160.85,161.95)
 nz_base=transient_ratio(vocal,160.85,161.95)
 nzchoice="nezab_D" if abs(np.log(max(nz_d,1e-8)/max(nz_base,1e-8)))<abs(np.log(max(nz_c,1e-8)/max(nz_base,1e-8))) else "nezab_C"
 # Avoid accepting an unproven change where the acoustic consonant information remains absent.
 # Do not invent /bv/ by another voice. Qualitative review required.
 patched=np.array(vocal,copy=True)
 for tag,a,b in [("tropy_C",29.385,30.63),(nzchoice,160.76,162.53)]:
  patched[region(a,b)]=results[tag][0][region(a,b)]
 delta=patched-vocal
 # W→M3 documented vocal delta: ~0.8767 per channel, 240 sample lag, -1.3dB final.
 # Preserve original Z10 master outside these phrase-local delta windows.
 gain=np.array([.87665715,.8768648])*10**(-1.3/20)
 lag=240
 moved=np.zeros(len(master)); moved[lag:]=delta[:len(master)-lag]
 mixed=master+ moved[:,None]*gain[None,:]
 # Local safety: do not alter outside repair windows to hit arbitrary master loudness.
 peak=float(np.max(np.abs(mixed)))
 if peak>1.02:raise RuntimeError("unexpected peak >1.02; reject")
 enc(mixed,OUT/"NEZRIMY_GOST_Z11_M3_REVIEW.mp3",2)
 enc(patched,OUT/"NEZRIMY_GOST_Z11_VOCAL.mp3",1)
 manifest={"title":"Незримый гость","candidate":"Z11_M3_REVIEW","human_acceptance":"PENDING",
 "basis":"Z10 real listener-PASS M3 master; only bounded single-voice RVC patches",
 "source_urls":{"master":Z10_MASTER,"vocal":Z10_VOCAL},
 "model":"Awata Weak Original RVC v1.2", "strategy":"tropy_C + "+nzchoice,
 "windows_seconds":{"tropy":[29.385,30.63],"nezabvennym":[160.76,162.53]},
 "no_instrumental_regeneration":True,"no_second_voice_overlay":True,
 "preserved_regions":"All outside two bounded word windows (PCM delta 0)",
 "model_metadata":imeta,"runtime":meta,
 "qc":{q:qa for q,(_,qa) in results.items()},
 "peak_linear":peak,
 "limitations":["RVC cannot reconstruct an acoustically absent /bv/ with certainty",
 "Machine similarity is not listening approval","Check precise phoneme timings and splice boundaries by ear"],
 "master_delta_gain":gain.tolist(),"lag_samples":lag}
 (OUT/"Z11_M3_MANIFEST.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
 print(json.dumps({"status":"REVIEW_CANDIDATE","files":[p.name for p in OUT.iterdir()],"strategy":manifest["strategy"],"qc_peak":peak},ensure_ascii=False))
if __name__=="__main__":main()
