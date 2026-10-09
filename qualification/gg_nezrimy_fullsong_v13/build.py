#!/usr/bin/env python3
"""GG / 2026-10-09: six source-level repair AUDITIONS on full accepted-song line.
Input frozen M3 V3 sources and prior v1.2 single word source patch. No publication/acceptance.
"""
from pathlib import Path
import hashlib,json,subprocess
import numpy as np, soundfile as sf
from scipy import signal,ndimage

R=Path('/mnt/data/GG_NORTHSTAR_FULL_SONG_RECOVERY_20261009')
OUT=Path(__file__).resolve().parent
S=48000
LOCK={'VOCAL_REPAIRED_V3.mp3':'1e5c87284d410d6dca090025388a95d75f0cd6dd0cb7211248bdef548c91d82a','D1_CLEAN_GUIDE_FULL.wav':'ea3f0798db4e60927e307467997ea00856bf807d7959a952aa66281182fbc14e','M3_REVIEW_V3.mp3':'da816b1c0f2973cd870f03ad9a499442c259830457cb8d23926d71796ba49290'}
WINDOWS={
 'с тобой':(10.555556,10.833333),
 'в тишине':(25.0,25.277778),
 'люди':(12.232,12.475),
 'две тропы':(30.035,30.445),
 'до разлуки':(108.49,108.915),
 'незабвенным':(162.23,162.498),
}

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p,c):
 q=subprocess.run(['ffmpeg','-nostdin','-loglevel','error','-i',str(p),'-ar',str(S),'-ac',str(c),'-f','f32le','-'],check=True,capture_output=True)
 y=np.frombuffer(q.stdout,dtype='<f4').copy();return y.reshape(-1,c)
def smooth(x):return x*x*(3-2*x)
def short_preposition(voice,start,end,duration=.058):
 """Reposition a compressed short /s/ or /v/ adjacent to its host word.
     Change ONLY the source consonant's score slot, not any other words."""
 aa=round(start*S);bb=round(end*S)
 orig=voice[aa:bb].astype(float)
 # Historically successful D1R5P uses 45 ticks (~52ms) instead of 240.
 # Preserve actual consonant articulation by compressing the first voiced/noisy ~160ms.
 n=round(duration*S)
 # Phonetically conservative: select original ~55ms articulation and move it.
 # NO speed-up, no pitch shift, unlike the rejected triple-speed consonant.
 src=orig[round(.045*S):round(.045*S)+n]
 y=src.copy()
 rms=lambda a:float(np.sqrt(np.mean(a*a)))
 target=rms(orig[round(.040*S):round(.160*S)])
 y=y*min(2.0,max(.55,target/max(rms(y),1.e-7)))
 # Retain original score slot, move /s/ or /v/ to its last 58ms.
 updated=np.zeros_like(orig)
 # 5ms silence before the next word may be shortened to 1ms in source
 off=len(orig)-n-round(.003*S)
 if off<0:raise ValueError('unexpected score window')
 updated[off:off+n]=y
 # 6ms taper at onset/end prevents clicks, does not insert second voice
 f=min(round(.006*S),n//4)
 updated[off:off+f]*=smooth(np.linspace(0,1,f))
 updated[off+n-f:off+n]*=smooth(np.linspace(1,0,f))
 # A 9ms end notch is quieter consonant decay; original next word starts untouched.
 voice[aa:bb]=updated
 return {'slot_s':[start,end],'original_ticks':240,'new_sound_ms':round(duration*1000),'consonant_anchored_before_next_word_s':float((bb-(off+n+aa))/S),'source_rms':rms(orig),'output_rms':rms(updated)}

def voice_preserving_donor(voice,guide,start,end,weight=.80):
 """Replace acoustically wrong phoneme using SAME score's existing clean sung source,
     frequency-envelope-adjusted, with source signal (NOT unrelated speech or a second voice)."""
 a=max(0,round((start-.28)*S));b=min(len(voice),round((end+.28)*S))
 v=np.asarray(voice[a:b],dtype=np.float64);g=np.asarray(guide[a:b],dtype=np.float64)
 # Use smooth broadband timbre transfer; do not force pitch, words or reverb.
 nper=2048;hop=256;ov=nper-hop
 f,tt,V=signal.stft(v,fs=S,nperseg=nper,noverlap=ov)
 _,_,G=signal.stft(g,fs=S,nperseg=nper,noverlap=ov)
 center=(tt+(a/S)>(start+.045))&(tt+(a/S)<(end-.045))
 if center.sum()<5:raise ValueError('phonetic window too small')
 vm=np.median(np.abs(V[:,center]),axis=1); gm=np.median(np.abs(G[:,center]),axis=1)
 factor=np.exp(np.clip(ndimage.gaussian_filter1d(np.log(np.maximum(vm,1e-7))-np.log(np.maximum(gm,1e-7)),sigma=13)*.30,-.42,.42))
 G*=factor[:,None]
 _,syn=signal.istft(G,fs=S,nperseg=nper,noverlap=ov)
 syn=syn[:len(v)]
 # Refine microphase only (±1.6ms), keeps phoneme in time.
 mid=round(((start+end)/2)*S)-a
 half=min(round(.028*S),int(.25*(end-start)*S));x=v[mid-half:mid+half]
 scores=[]
 for shift in range(-70,71,7):
  ix0=mid-half-shift;ix1=mid+half-shift
  if ix0<0 or ix1>len(syn): continue
  t=syn[ix0:ix1]
  corr=float(np.dot(x,t)/(np.linalg.norm(x)*np.linalg.norm(t)+1e-10))
  scores.append((corr,shift))
 correlation,shift=max(scores)
 if shift>0:syn=np.r_[np.zeros(shift),syn[:-shift]]
 elif shift<0:syn=np.r_[syn[-shift:],np.zeros(-shift)]
 aa=round(start*S)-a;bb=round(end*S)-a
 vr=float(np.sqrt(np.mean(v[aa:bb]**2)));dr=float(np.sqrt(np.mean(syn[aa:bb]**2)))
 gain=np.clip(vr/max(dr,1e-8),.55,2.3)
 syn*=gain
 fade=min(.064,(end-start)*.27)
 t=np.arange(len(v))/S+a/S
 mask=np.clip((t-start)/fade,0,1)*np.clip((end-t)/fade,0,1)
 mask=weight*smooth(mask)
 updated=v*(1-mask)+syn*mask
 voice[a:b]=updated.astype(np.float32)
 return {'window':[start,end],'max_source_donor_weight':weight,'alignment_samples':shift,'phase_corr':correlation,'donor_rms_gain':float(gain),'changed_rms':float(np.sqrt(np.mean((updated-v)**2)))}

def main():
 for f,d in LOCK.items(): assert sha(R/f)==d, ('sha mismatch',f)
 baseline=R/'review/GG_NEZRIMY_FULL_M3_REAL_DYA_SOURCE_DONOR_D_REVIEW.wav'
 assert baseline.exists()
 mix,sr=sf.read(baseline,dtype='float32',always_2d=True);assert sr==S and len(mix)>S*270
 v3=load(R/'VOCAL_REPAIRED_V3.mp3',1)[:,0]
 guide=load(R/'D1_CLEAN_GUIDE_FULL.wav',1)[:,0]
 assert len(guide)>S*200
 n=min(len(v3),len(guide),len(mix));v=v3.copy()[:n];guide=guide[:n]
 modifications={}
 for word in ['с тобой','в тишине']:
  modifications[word]=short_preposition(v,*WINDOWS[word],duration=.054 if word=='с тобой' else .064)
 for word,w in [('люди',.90),('две тропы',.86),('до разлуки',.90),('незабвенным',.88)]:
  modifications[word]=voice_preserving_donor(v,guide,*WINDOWS[word],weight=w)
 # Protect every previously accepted/unchanged sample and the v1.2 vidyatsya repair.
 changes=np.zeros(n,dtype=np.float32)
 allowed=np.zeros(n,dtype=bool)
 limiter_scales={}
 for word,(a,b) in WINDOWS.items():
  i0=round(a*S);i1=round(b*S)
  allowed[i0:i1+1]=True
  local_change=(v-v3)[i0:i1].astype(np.float32)
  # Original M3 remains unaltered in source coordinates; avoid suppressing
  # actual phonetic repairs merely to satisfy a target MP3 peak.
  changes[i0:i1]=local_change
  limiter_scales[word]=1.0

 assert (changes[~allowed]==0).all()
 assert np.max(np.abs(changes))>.02
 new=mix.copy()
 assert len(new)>=n
 new[:n,0]+=np.float32(1.252)*changes
 new[:n,1]+=np.float32(1.252)*changes
 assert np.array_equal(new[round(13.055*S):round(13.325*S)],mix[round(13.055*S):round(13.325*S)]), 'v1.2 vidyatsya must remain unchanged'
 diff=np.any(new!=mix,axis=1)
 allow_whole=np.zeros(len(mix),dtype=bool);allow_whole[:n]=allowed
 assert not np.any(diff & ~allow_whole), 'out-of-scope changes'
 # Transparent, strictly word-local peak management (not entire master gain).
 # Prevent output clipping on narrow consonant grafts by ducking only the
 # tiny replaced waveform window, leaving ALL other decoded PCM unchanged.
 local_controls={}
 for word,(ra,rb) in WINDOWS.items():
  ia=round(ra*S);ib=round(rb*S)
  old_peak=float(np.max(np.abs(mix[ia:ib])))
  input_peak=float(np.max(np.abs(new[ia:ib])))
  if input_peak<=.985:
   local_controls[word]={'old_peak':old_peak,'input_peak':input_peak,'gain_min':1.}
   continue
  x=new[ia:ib].copy()
  local_level=np.max(np.abs(x),axis=1)
  worst=ndimage.maximum_filter1d(local_level,size=2*round(.006*S)+1)
  gain=np.minimum(1.,.975/np.maximum(worst,1.e-6))
  # smooth local gain; faster attack than release, suppress alias modulation
  gain=ndimage.gaussian_filter1d(gain,sigma=round(.003*S))
  # Keep max peak at/below unchanged baseline if baseline already near fullscale
  ceiling=max(.985,old_peak+1e-5)
  need=np.minimum(1.,ceiling/np.maximum(local_level*gain,1e-6))
  gain*=need
  # Edits remain inside only this phrase slot. Tiny fades keep smooth boundaries.
  fades=round(.004*S)
  fade=np.ones(len(gain));fade[:fades]=smooth(np.linspace(0,1,fades));fade[-fades:]=smooth(np.linspace(1,0,fades))
  gain=1-(1-gain)*fade
  reduced=x*gain[:,None]
  if float(np.max(np.abs(reduced)))>ceiling+1e-4:
   # Final bounded exact safeguard in rare boundary transients.
   corrected=np.minimum(1.,ceiling/np.maximum(np.max(np.abs(reduced),axis=1),1e-7))
   reduced*=corrected[:,None]
  new[ia:ib]=reduced
  local_controls[word]={'old_peak':old_peak,'input_peak':input_peak,'output_peak':float(np.max(np.abs(reduced))),'gain_min':float(gain.min())}
 raw_peak=float(np.max(np.abs(new)))
 listening_gain=1.0
 export=new
 assert float(np.max(np.abs(export)))<=max(1.01,float(np.max(np.abs(mix)))+1e-5)
 # Original accepted master untouched, all changes in exactly six phonetic slots.
 outwav=OUT/'NEZRIMY_GOST_V13_SIX_ISSUES_REVIEW.wav'
 sf.write(outwav,export,S,subtype='FLOAT')
 outmp3=OUT/'NEZRIMY_GOST_V13_SIX_ISSUES_REVIEW.mp3'
 subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-i',str(outwav),'-codec:a','libmp3lame','-b:a','320k',str(outmp3)],check=True)
 # Show before/after comparisons with sufficient context, not surgically severed phonemes.
 clips=[('01_STOBOY',9.4,12.15),('02_V_TISHINE',23.6,27.0),('03_LYUDI',11.85,13.78),('04_DVE_TROPY',28.85,31.1),('05_DO_RAZLUKI',106.7,109.8),('06_NEZABVENNYM',159.9,163.1)]
 ab=[];silence=np.zeros((round(.55*S),2),dtype=np.float32)
 for name,a,b in clips:
  old=mix[round(a*S):round(b*S)]
  current=export[round(a*S):round(b*S)]
  # Same exact mastering level as baseline, no full-track attenuation
  ab.extend([old,silence,current,np.zeros((round(.88*S),2),dtype=np.float32)])
  wav=OUT/f'{name}_BEFORE_AFTER.wav';sf.write(wav,np.concatenate([old,silence,current]),S,subtype='PCM_24')
  subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-i',str(wav),'-b:a','256k',str(wav.with_suffix('.mp3'))],check=True)
 abfile=OUT/'SIX_ISSUES_BEFORE_AFTER.mp3'
 abwav=OUT/'SIX_ISSUES_BEFORE_AFTER.wav'
 sf.write(abwav,np.concatenate(ab),S,subtype='PCM_24')
 subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-i',str(abwav),'-b:a','256k',str(abfile)],check=True)
 details={'status':'ARTISTIC_REVIEW_ONLY','base':'full-song v1.2 single vowel D donor, not golden master','base_sha256':sha(baseline),'new_song_sha256':sha(outmp3),'new_pcm_wav_sha256':sha(outwav),'no_whisper':True,'no_second_voice':True,'source_v3_sha256':sha(R/'VOCAL_REPAIRED_V3.mp3'),'guide_sha256':sha(R/'D1_CLEAN_GUIDE_FULL.wav'),'regions':{name:{'interval':[float(a),float(b)],'technique':'shortened and moved consonant toward following word' if name in ('с тобой','в тишине') else 'local replacement from authentic D1 sung guide with timbre match/crossfade','qa':modifications[name]} for name,(a,b) in WINDOWS.items()},'local_peak_controls':local_controls,'global_uniform_listening_gain':listening_gain,'raw_float_peak':raw_peak,'changed_frames':int(diff.sum()),'changed_ratio':float(diff.mean()),'patch_scaling_for_peak_safety':limiter_scales,'max_peak':float(np.max(np.abs(new))),'unchanged_excluding_six_windows':True,'preserved_prior_v12_phenome_window':True,'limitations':'Source guide phonetic fidelity and artistic naturalness not independently hearing accepted. Pitched fragment edits can introduce timbral seams. Do not promote automatically.'}
 (OUT/'MANIFEST.json').write_text(json.dumps(details,ensure_ascii=False,indent=2))
 print(json.dumps({k:details[k] for k in ['status','changed_frames','max_peak','unchanged_excluding_six_windows','preserved_prior_v12_phenome_window','new_song_sha256']},ensure_ascii=False))
 for k,vv in modifications.items(): print('EDIT',k,vv)
if __name__=='__main__':main()