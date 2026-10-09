#!/usr/bin/env python3
"""GG Human Vocal golden-route audit, source-aware and explicitly nonauthoritative.
Audits externally preserved original V3 voice, V2 instrumental, listener PASS M3,
and independent SoulX->Awata C/D new technical render ASR data.
No external jobs, no mutation to masters or user-accepted sound.
"""
import hashlib,io,json,re,subprocess,zipfile
from pathlib import Path
import numpy as np
import soundfile as sf
from scipy.signal import correlate,correlation_lags
ROOT=Path(__file__).parent
ASSETS=ROOT/'golden'
REPLAY=ROOT/'replay'/'GG_NORTHSTAR_SUCCESS_CD_INDEPENDENT_QA_20261009.zip'
OUT=ROOT/'results';OUT.mkdir(exist_ok=True)
TARGET='я говорил не с ним а с тем кто долго стоял у окна и ждал'
EXPECTED=['VOCAL_REPAIRED_V3.mp3','INSTRUMENTAL_REAL_V2.mp3','M3_REVIEW_V3.mp3','NEZRIMY_GOST_Z10_VOCAL_SOURCE.mp3','NEZRIMY_GOST_Z10_M3_SOURCE.mp3']
def normalize(s):
 return re.sub(r'\s+',' ',re.sub(r'[^а-я0-9 ]',' ',s.lower().replace('ё','е'))).strip()
def lev(a,b):
 prev=list(range(len(b)+1))
 for i,ca in enumerate(a,1):
  curr=[i]+[0]*len(b)
  for j,cb in enumerate(b,1):curr[j]=min(curr[j-1]+1,prev[j]+1,prev[j-1]+(ca!=cb))
  prev=curr
 return prev[-1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def to_float(path,rate=12000,max_s=None):
 cmd=['ffmpeg','-nostdin','-v','error','-i',str(path)]
 if max_s is not None:cmd+=['-t',str(max_s)]
 cmd+=['-ac','1','-ar',str(rate),'-f','f32le','-']
 return np.frombuffer(subprocess.run(cmd,capture_output=True,check=True).stdout,dtype='<f4').copy()
def aligned(y,x,k,start,stop):
 # master waveform delayed k samples wrt directly decoded sources
 a=x[start:stop]; b=y[start+k:stop+k];n=min(len(a),len(b));return a[:n],b[:n]
def find_lag(master,inst,rate):
 lo,hi=12*rate,23*rate
 a=master[lo:hi][::3];b=inst[lo:hi][::3]
 c=correlate(a,b,mode='full',method='fft')
 l=correlation_lags(len(a),len(b),mode='full')
 selection=np.abs(l)<=80
 lag0=int(l[selection][np.argmax(c[selection])])*3
 return lag0

def regression(x,z,y,lag,lo,hi,rate=12000):
 a=x[int(lo*rate):int(hi*rate)]; b=z[int(lo*rate):int(hi*rate)]
 c=y[int(lo*rate)+lag:int(hi*rate)+lag]
 n=min(len(a),len(b),len(c))
 if n<100:raise ValueError('short fit region')
 X=np.stack([a[:n:11],b[:n:11]],axis=1).astype('float64');Y=c[:n:11].astype('float64')
 beta=np.linalg.lstsq(X,Y,rcond=None)[0]
 p=X@beta
 r2=float(1-np.mean((Y-p)**2)/(np.var(Y)+1e-15))
 rms_db=float(20*np.log10(np.sqrt(np.mean((Y-p)**2)+1e-18)/np.sqrt(np.mean(Y**2)+1e-18)))
 return {'start_s':lo,'end_s':hi,'gain_vocal':float(beta[0]),'gain_music':float(beta[1]),'r2':r2,'residual_relative_db':rms_db}

def enforce_pins(actual,expected):
 for name,h in expected.items():
  if name not in actual or actual[name]['sha256']!=h:
   raise ValueError('GOLDEN_SOURCE_VERSION_DRIFT: '+name)
 return True

def safe_source_report():
 missing=[n for n in EXPECTED if not (ASSETS/n).is_file()]
 if missing:raise FileNotFoundError(missing)
 files={n:{'bytes':(ASSETS/n).stat().st_size,'sha256':sha(ASSETS/n)} for n in EXPECTED}
 lock=json.loads((ROOT/'GOLDEN_LOCK.json').read_text())
 enforce_pins(files,lock['files'])
 if sha(REPLAY)!=lock['replay_sha256']:raise ValueError('GOLDEN_REPLAY_VERSION_DRIFT')
 with zipfile.ZipFile(REPLAY) as z:
  qa=json.loads(z.read('independent_russian_asr.json'))
  rows=[]
  for t in qa['transcripts']:
   txt=normalize(t['text']);rows.append({'file':t['file'],'transcript':txt,'CER':round(lev(TARGET,txt)/len(TARGET),6),'exact':txt==TARGET})
  replay={'new_replay_files':{n:hashlib.sha256(z.read(n)).hexdigest() for n in ['C_FCPE_IDX030.wav','D_FCPE_IDX050.wav']},'independent_transcript':rows}
 with zipfile.ZipFile(ROOT/'replay'/'GG-applio-awata-success-AB-reference.zip') as old,zipfile.ZipFile(REPLAY) as new:
  variance={}
  for name in ['C_FCPE_IDX030.wav','D_FCPE_IDX050.wav']:
   a,_=sf.read(io.BytesIO(old.read(name)));b,_=sf.read(io.BytesIO(new.read(name)))
   variance[name]={'sample_exact':bool(np.array_equal(a,b)),'pearson_correlation':float(np.corrcoef(a,b)[0,1]),'rms_difference':float(np.sqrt(np.mean((a-b)**2)))}
  replay['old_new_audio_comparison']=variance
 return files,replay

def main():
 files,replay=safe_source_report()
 x=to_float(ASSETS/'VOCAL_REPAIRED_V3.mp3');i=to_float(ASSETS/'INSTRUMENTAL_REAL_V2.mp3');m=to_float(ASSETS/'M3_REVIEW_V3.mp3')
 r=12000; approx=find_lag(m,i,r)
 opts=[]
 for lag in range(max(-150,approx-10),min(151,approx+10)):
  z=regression(x,i,m,lag,12,55)
  opts.append((z['r2'],lag,z))
 best=max(opts);lag=best[1];t=best[2]
 sections=[(12,45),(45,80),(80,120),(120,160),(160,200),(200,238)]
 snapshots=[regression(x,i,m,lag,a,b) for a,b in sections]
 report={'status':'TECHNICAL_GOLDEN_ROUTE_AUDIT_NO_NEW_ARTISTIC_ACCEPTANCE','baseline':'V3 vocal and REAL_V2 instrumental -> listener-PASS M3 master','source_artifacts':files,'song_stem_alignment':{'sample_rate_hz':r,'lag_samples':lag,'lag_seconds':lag/r,'fitted_gains_training_only':t,'validation_windows':snapshots,'note':'Estimated from decoded MP3 waveforms, not proof of original mixer settings. May include EQ, dynamics, bus compression and lossy encoding.'},'replayed_cd_audition':replay,'candidate_decision':{'source':'SoulX full lyric preserved as text gate','C':'eligible technical candidate (exact transcript)','D':'rejected as lexical-regressed on the new replay (стоя/стоял); historic C/D remain historic co-leaders, independent future audition needed'},'governance':{'user_accepted_music_immutable':True,'v3_m3_reference_preserved':True,'later_w_z10_are_review_only':True,'real_whisper_unverified':True,'60_minute_new_song_northstar_unqualified':True}}
 (OUT/'GOLDEN_TECHNICAL_AUDIT.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
 # render 11 seconds of a reconstructed fit, then the frozen original, identical loudness match.
 targetrate=48000
 vocal=to_float(ASSETS/'VOCAL_REPAIRED_V3.mp3',rate=targetrate,max_s=52)
 instrumental=to_float(ASSETS/'INSTRUMENTAL_REAL_V2.mp3',rate=targetrate,max_s=52)
 master=to_float(ASSETS/'M3_REVIEW_V3.mp3',rate=targetrate,max_s=52)
 fs=targetrate
 pos0=35*fs; pos1=46*fs
 align=int(round(lag/r*fs)); 
 # reconstructed was delayed align samples relative to source; master time [pos0:pos1]
 idx=np.arange(pos0,pos1,dtype=np.int64)-align
 reconstruct=t['gain_vocal']*vocal[idx]+t['gain_music']*instrumental[idx]
 reference=master[pos0:pos1]
 # preserve absolute relative audio levels rather than misleading loudness boost.
 pad=np.zeros(int(.6*fs),dtype='float32')
 audio=np.concatenate([reference.astype('float32'),pad,reconstruct.astype('float32')])
 if np.max(np.abs(audio))>=1:audio*=.95/np.max(np.abs(audio))
 sf.write(OUT/'M3_GOLDEN_vs_ESTIMATED_RECONSTRUCTION.wav',audio,fs,subtype='PCM_24')
 subprocess.run(['ffmpeg','-nostdin','-y','-v','error','-i',str(OUT/'M3_GOLDEN_vs_ESTIMATED_RECONSTRUCTION.wav'),'-c:a','libmp3lame','-b:a','224k',str(OUT/'M3_GOLDEN_vs_ESTIMATED_RECONSTRUCTION.mp3')],check=True)
 print(json.dumps({'lag_samples_12000':lag,'fit':t,'windows':snapshots,'replay':replay,'audition':str(OUT/'M3_GOLDEN_vs_ESTIMATED_RECONSTRUCTION.mp3')},indent=2,ensure_ascii=False))
if __name__=='__main__':main()