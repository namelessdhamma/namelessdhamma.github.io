#!/usr/bin/env python3
"""Z17 restore user-qualified human base, not Z14/Z15 hand-programmed phonemes.
Processes one contiguous 8.6-15.35s opening context from recovered authentic Z10/W-era lead.
Six alternate RVC conversions, saved isolated for direct audition; no mastering/music.
"""
import os,json,pathlib,subprocess,hashlib,math,urllib.request
import numpy as np
from tools.gg_cloud_music_worker import ensure_applio_runtime,install_rvc_model
R=pathlib.Path.cwd(); OUT=R/"z17_opening_out"; OUT.mkdir(exist_ok=True)
TEMP=R/"z16_opening_runtime"; TEMP.mkdir(exist_ok=True)
SR=48000
BASES={"GUIDE":"file:z17_clean_guide/vocal/00_GUIDE_D1.wav"}
START,STOP=8.58,15.35
def ff(*args):
 q=subprocess.run(["ffmpeg","-nostdin","-y","-v","error",*map(str,args)],capture_output=True)
 if q.returncode:raise RuntimeError(q.stderr.decode()[-1600:])
def restore(k,u):
 if not u.startswith("file:"):raise RuntimeError("Direct clean guide file required; reject remote substitute")
 p=R/u[5:]
 if not p.is_file() or p.stat().st_size<1000000:raise RuntimeError("missing recovered clean guide "+str(p))
 wav=TEMP/(k+"_context.wav")
 ff("-ss",START,"-t",STOP-START,"-i",p,"-ar",SR,"-ac",1,"-c:a","pcm_s16le",wav)
 return wav
def wav_array(p):
 raw=TEMP/(p.stem+".f32")
 ff("-i",p,"-ar",SR,"-ac",1,"-f","f32le",raw)
 return np.fromfile(raw,dtype='<f4')
def normalize(x,y):
 n=min(len(x),len(y));x=x[:n];y=y[:n]
 # Loudness match converted vs original on ONLY phrase, not silent context.
 lo=int((9.24-START)*SR); hi=int((14.47-START)*SR)
 xb=np.sqrt(np.mean(x[lo:hi].astype('float64')**2)+1e-12)
 yb=np.sqrt(np.mean(y[lo:hi].astype('float64')**2)+1e-12)
 gain=float(np.clip(xb/yb,.4,1.9))
 return y*gain,dict(src_rms=float(xb),dest_rms=float(yb),match_gain=gain)
def inference(root,vpy,model,index,source,k,label,indexrate):
 target=OUT/(k+"_"+label+".wav")
 cfg={"pitch":0,"index_rate":indexrate,"volume_envelope":1.0,"protect":.5,
      "f0_method":"fcpe","split_audio":False,"f0_autotune":False,"f0_autotune_strength":1.0,
      "proposed_pitch":False,"proposed_pitch_threshold":155.0,"clean_strength":0.5,
      "clean_audio":False,"formant_shifting":False,"post_process":False,
      "reverb":False,"chorus":False,"distortion":False,"delay":False}
 p=TEMP/(k+"_"+label+"_cfg.json");p.write_text(json.dumps(cfg))
 s=TEMP/"rvc_single.py"
 s.write_text("""import os,sys,json
root,source,target,model,index,config=sys.argv[1:7]
os.chdir(root);sys.path.insert(0,root)
from core import run_infer_script
run_infer_script(input_path=source,output_path=target,pth_path=model,index_path=index,export_format='WAV',embedder_model='contentvec',**json.load(open(config)))
""")
 q=subprocess.run([str(vpy),str(s),str(root),str(source),str(target),str(model),str(index),str(p)],
   capture_output=True,text=True,timeout=900)
 if q.returncode or not target.exists():raise RuntimeError("RVC failed "+k+" "+label+" "+q.stdout[-2500:]+q.stderr[-2500:])
 return target
def main():
 sources={k:restore(k,u) for k,u in BASES.items()}
 rt,vpy,_=ensure_applio_runtime(TEMP/"app")
 manifest={"objective":"restore clean human-expressive original 00_GUIDE_D1.wav and convert exactly once, no stacked RVC chain","context":[START,STOP],"samplerate":SR,"models":{},"results":[]}
 for variant in ("Original","Whisper"):
  model,index,_=install_rvc_model("awata-weak-rvc-v1.2",variant,TEMP/"app")
  manifest["models"][variant]={"pth":model.name,"index":index.name}
  work=[("GUIDE","C",.30),("GUIDE","D",.50)]
  for k,label,rate in work:
   out=inference(rt,vpy,model,index,sources[k],k,variant+"_"+label,rate)
   src=wav_array(sources[k]);got=wav_array(out)
   a,match=normalize(src,got)
   # No reverb / multitrack; output level-matched raw RVC
   pcm=OUT/(k+"_"+variant+"_"+label+"_matched.f32");a.astype('<f4').tofile(pcm)
   wav=OUT/(k+"_"+variant+"_"+label+"_matched.wav")
   ff("-f","f32le","-ar",SR,"-ac",1,"-i",pcm,"-c:a","pcm_s24le",wav)
   entry={"source":k,"model":variant,"index_rate":rate,"file":wav.name,"source_file":sources[k].name,
          "sha256":hashlib.sha256(wav.read_bytes()).hexdigest(),"matching":match,"seconds":len(a)/SR}
   manifest["results"].append(entry)
   print("Z17_SINGING_PERFORMANCE_RESTORED",k,variant,label,round(len(a)/SR,3),flush=True)
 for k,src in sources.items():
  dst=OUT/(k+"_AUTHENTIC_UNCHANGED.wav");dst.write_bytes(src.read_bytes())
 (OUT/"Z16_OPENING_SOURCE_COMPARISON.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
 print("Z16_QUALIFICATION_SOURCES_READY",len(manifest["results"]),flush=True)
if __name__=="__main__":main()
