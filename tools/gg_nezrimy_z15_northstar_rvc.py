#!/usr/bin/env python3
"""Z15 reuse qualified GG North Star: Awata Weak Original/FCPE/protect .5.
RVC original model DOES NOT supply missing phonemes; original phoneme sources are Z14.
Isolated RVC conversion only, do not mix onto an already voiced master.
"""
import pathlib,json,os,subprocess,hashlib
import numpy as np
from tools.gg_cloud_music_worker import ensure_applio_runtime,install_rvc_model
from tools import gg_nezrimy_z11 as z11
ROOT=pathlib.Path(os.getcwd())
OUT=ROOT/"z15_voice_out";OUT.mkdir(exist_ok=True)
IN=ROOT/"z15_voice_source"
SR=48000
SPECS=[
 ("opening_whole_line",IN/"whole/opening_whole_line.wav"),
 ("tishine_whole_line",IN/"whole/tishine_whole_line.wav"),
 ("tropy",IN/"words/tropy.wav"),
 ("pyl",IN/"words/pyl.wav"),
 ("razluki",IN/"words/razluki.wav"),
 ("nezabvennym",IN/"corrected/nezabvennym.wav"),
 ("proshloe_bridge",IN/"corrected/proshloe_bridge.wav"),
 ("proshloe_final",IN/"corrected/proshloe_final.wav"),
]
def info(path):
 q=subprocess.run(["ffprobe","-v","error","-show_entries","stream=duration,sample_rate","-of","json",str(path)],text=True,capture_output=True,check=True)
 return json.loads(q.stdout)
def main():
 missing=[str(p) for _,p in SPECS if not p.exists()]
 if missing:raise RuntimeError("missing original dry independent phoneme source: "+str(missing))
 work=ROOT/"z15_runtime";work.mkdir(exist_ok=True)
 root,vpy,appmeta=ensure_applio_runtime(work)
 model,index,mmeta=install_rvc_model("awata-weak-rvc-v1.2","Original",work)
 manifest={"engine":"Applio", "revision":"GG North-Star pinned", "model":"Awata Weak RVC v1.2 Original",
           "f0_method":"fcpe","protect":.5,"index_rates":[.3,.5],
           "autotune":False,"no_post_fx":True,
           "sources":"Original dry DiffSinger WAV (Z14 full phrase + corrected word), never any mastered audio",
           "user_listening":"PENDING", "source_files":{},"variants":{}}
 for tag,p in SPECS:
  meta=info(p)
  arr=z11.dec(p,z11.TMP/(tag+"_src.f32"),1)[:,0]
  dur=len(arr)/SR
  manifest["source_files"][tag]={"sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"duration":dur,"original_file":str(p)}
  for label,indexrate in [('C',.30),('D',.50)]:
   item=tag+"_"+label
   # Preserve breath onset and rest 70-150 ms; process actual phoneme performance with context.
   # convert emits the pinned original signal after localized voice conversion.
   a=min(.075,max(0,dur*.05));b=max(a+.05,dur-min(.11,dur*.05))
   candidate,q=z11.convert(arr,a,b,indexrate,.50,model,index,root,vpy,item)
   # Note: z11.convert preserves original outside its region, never overlaps another singer.
   dest=OUT/(item+".wav")
   z11.enc(candidate,OUT/(item+"_check.mp3"),1)
   raw=z11.TMP/(item+"_full.f32");candidate.astype('<f4').tofile(raw)
   subprocess.run(["ffmpeg","-nostdin","-y","-v","error","-f","f32le","-ar","48000","-ac","1","-i",str(raw),"-c:a","pcm_f32le",str(dest)],check=True)
   srcmid=arr[int(a*SR):int(b*SR)]
   gotmid=candidate[int(a*SR):int(b*SR)]
   match=float(np.sqrt(np.mean(srcmid**2)+1e-12)/np.sqrt(np.mean(gotmid**2)+1e-12))
   manifest["variants"][item]={"sha256":hashlib.sha256(dest.read_bytes()).hexdigest(),"gain_to_source":match,"source_duration":dur,
                                 "conversion":q,"peak":float(np.max(np.abs(candidate))),"file":dest.name}
   print("GG_Z15_CONVERSION_OK",item,dur,flush=True)
 (OUT/"Z15_RVC_NORTHSTAR_SOURCES.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
 print("Z15_NORTHSTAR_DONE",len(manifest["variants"]),flush=True)
if __name__=="__main__":main()
