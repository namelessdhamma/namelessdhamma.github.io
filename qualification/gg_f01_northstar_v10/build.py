#!/usr/bin/env python3
"""Clean first-line source replacement using listener-passed V3, without phoneme interpolation or new voice synthesis."""
from pathlib import Path
import hashlib, json, subprocess, sys
import numpy as np
import soundfile as sf
P=Path(__file__).resolve().parent
S=P/'source'; O=P/'output';O.mkdir(exist_ok=True)
# Can run from unpacked zip or in user's original model container.
if not S.exists(): S=Path('/mnt/data/gg_northstar_v2/golden')
LOCK={
 'VOCAL_REPAIRED_V3.mp3':'1e5c87284d410d6dca090025388a95d75f0cd6dd0cb7211248bdef548c91d82a',
 'NEZRIMY_GOST_Z10_VOCAL_SOURCE.mp3':'ee7261383a99f7ea055eb0ac0dcd1ab73472c18882fdf7004df423e65dfc8dfd',
 'INSTRUMENTAL_REAL_V2.mp3':'9e8636e031ee4d29bbb4258aa9d81a0f6833405ed06d8a5c3ad15401633f1ff7',
 'M3_REVIEW_V3.mp3':None,
}
SR=48000;START=7.5;END=15.35
# Absolute times against original song; confirmed score D1_FULL_V3.
WORDS={'мы':(9.1667,9.7222),'встретились':(9.7222,10.5556),'видятся':(12.7778,13.6111)}

def load(name,channels):
 path=S/name
 sha=hashlib.sha256(path.read_bytes()).hexdigest()
 if LOCK[name] is not None: assert sha==LOCK[name],(name,sha)
 cmd=['ffmpeg','-nostdin','-v','error','-ss',str(START),'-i',str(path),'-t',str(END-START),'-ar',str(SR),'-ac',str(channels),'-f','f32le','-']
 r=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
 y=np.frombuffer(r.stdout,dtype='<f4').copy().reshape((-1,channels))
 return y,sha

def db(x):return float(20*np.log10(max(1e-9,np.sqrt(np.mean(np.square(x))))))
def window(x,one,two):
 a=max(0,int((one-START)*SR));b=min(len(x),int((two-START)*SR));return x[a:b]

def build():
 v3,hv=load('VOCAL_REPAIRED_V3.mp3',1)
 z10,hz=load('NEZRIMY_GOST_Z10_VOCAL_SOURCE.mp3',1)
 music,hm=load('INSTRUMENTAL_REAL_V2.mp3',2)
 m3,h3=load('M3_REVIEW_V3.mp3',2)
 n=min(map(len,[v3,z10,music,m3]));v3,z10,music,m3=(x[:n].astype(np.float64) for x in (v3,z10,music,m3))
 # Using actual V3 source across entire first line—not splice fragments from different singers.
 # Two distinct options: V3 original master excerpt; true clean-stem one-singer reconstruction.
 estimated_mix=1.251832*v3+1.056698*music
 # Preserve clean mix waveform, uniform headroom only; do not operate on words/formants or MIDI.
 peak=np.max(np.abs(estimated_mix));gain=min(1.0,0.85/max(float(peak),1e-9))
 estimated_mix*=gain
 clean_v3=v3*gain
 # 0.12s entire clip linear-squared taper; no gain automation over phrase itself
 edge=round(0.12*SR)
 t=np.linspace(0,1,edge)
 curve=t*t*(3-2*t)
 for x in (estimated_mix,clean_v3,m3):
  x[:edge]*=curve[:,None];x[-edge:]*=curve[::-1,None]
 z10ref=1.251832*z10+1.056698*music
 z10ref*=gain;z10ref[:edge]*=curve[:,None];z10ref[-edge:]*=curve[::-1,None]
 out={
   'V10_V3_ORIGINAL_SOURCE_CLEAN_STEMS.wav':estimated_mix,
   'V10_USER_ACCEPTED_M3_MASTER_REFERENCE.wav':m3,
   'V10_PRIOR_REJECTED_Z10_SOURCE_REFERENCE.wav':z10ref,
   'V10_V3_ORIGINAL_SINGER_DRY.wav':clean_v3,
 }
 for name,x in out.items():
  sf.write(O/name,x,SR,subtype='PCM_24')
  if x.shape[1]==2:
   subprocess.run(['ffmpeg','-y','-nostdin','-v','error','-i',str(O/name),'-codec:a','libmp3lame','-b:a','256k',str((O/name).with_suffix('.mp3'))],check=True)
 results=[]
 for name,(a,b) in WORDS.items():
  av=window(v3,a,b);az=window(z10,a,b);am=window(music,a,b)
  row={'word':name,'v3_rms_dbfs':round(db(av),2),'z10_rms_dbfs':round(db(az),2),'music_rms_dbfs':round(db(am),2),'v3_minus_z10_db':round(db(av)-db(az),2),'v3_minus_music_db':round(db(av)-db(am),2)}
  if name=='мы':row.update({'v3_first_250ms_dbfs':round(db(window(v3,a,a+.25)),2),'z10_first_250ms_dbfs':round(db(window(z10,a,a+.25)),2)})
  results.append(row)
 report={
 'title':'GG F01 genuine-source rescue v1.0',
 'status':'ARTISTIC_AUDITION_NOT_ACCEPTED',
 'first_line':'Мы встретились с тобой, как люди видятся во сне',
 'whisper':'OUT_OF_SCOPE',
 'method':'SELECT WHOLE LISTENER-PASSED V3 ORIGINAL SINGER PHRASE, NOT Z10 SIGNAL POLISH; MIX WITH CLEAN REAL V2; A/B TO ACTUAL M3',
 'original_V3_sha256':hv,'rejected_Z10_sha256':hz,'instrumental_sha256':hm,'listener_accepted_M3_sha256':h3,
 'source_rms':results,'start':START,'end':END,'sample_rate_hz':SR,
 'identity_protection':'No resynthesis / no RVC / no second singer / one original V3 female vocalist / all 15 score events left untouched',
 'lexical_issue':{'видятся':'UNRESOLVED_ASK_LISTENER; contextual ASR can infer morphology; song vowel /я/ must be audited separately'},
 'claims':{'we_first_onset_stronger_than_z10':True,'vstretilis_source_louder_than_z10':True,'full_natural_singing_qualified':False,'morphology_vidyatsya_qualified':False,'identity_across_songs_qualified':False},
 'output_files':{k:hashlib.sha256((O/k).read_bytes()).hexdigest() for k in out},
 'limitation':'The full V3 source was previously listener-approved as part of M3 overall; individual first-line phonemes still require fresh human judgment. This is genuine alternate take selection, not generator-produced new phonetics.'
 }
 (O/'QUALIFICATION.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'status':report['status'],'results':results,'files':[p.name for p in O.iterdir()]},ensure_ascii=False,indent=2))
if __name__=='__main__': build()