#!/usr/bin/env python3
"""GG F01 first line non-whisper expressive rehearsal, no extra voices or resynthesis."""
import json, hashlib, pathlib, subprocess
import numpy as np
from scipy import signal
import soundfile as sf
OUT=pathlib.Path(__file__).resolve().parent / 'results'
SRC=pathlib.Path(__file__).resolve().parent / 'sources' / 'NEZRIMY_GOST_Z10_VOCAL_SOURCE.mp3'
INS=pathlib.Path(__file__).resolve().parent / 'sources' / 'INSTRUMENTAL_REAL_V2.mp3'
V3=pathlib.Path(__file__).resolve().parent / 'sources' / 'VOCAL_REPAIRED_V3.mp3'
SCORE=pathlib.Path(__file__).resolve().parent / 'sources' / 'FIRST_LINE_PERFORMANCE_PLAN.json'
ORIG_HASH={'voice':'ee7261383a99f7ea055eb0ac0dcd1ab73472c18882fdf7004df423e65dfc8dfd','music':'9e8636e031ee4d29bbb4258aa9d81a0f6833405ed06d8a5c3ad15401633f1ff7','v3':'1e5c87284d410d6dca090025388a95d75f0cd6dd0cb7211248bdef548c91d82a'}
SR=48000;START=5.8;END=16.45
VOICE_GAIN=1.251832; MUSIC_GAIN=1.056698

def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def ffdecode(path,nch):
 cmd=['ffmpeg','-nostdin','-hide_banner','-v','error','-ss',str(START),'-i',str(path),'-t',str(END-START),'-ac',str(nch),'-ar',str(SR),'-f','f32le','-']
 p=subprocess.run(cmd,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 y=np.frombuffer(p.stdout,dtype='<f4').copy()
 return y.reshape((-1,nch))
def smoothstep(x):
 x=np.clip(x,0.0,1.0)
 return x*x*(3.0-2.0*x)
def shape(t,a,b,c,d):
 """1 between b/c, zero outside a/d, smooth endpoints."""
 return smoothstep((t-a)/(b-a))*smoothstep((d-t)/(d-c))
def volume_db(v):return 20*np.log10(max(1e-10,v))
def true_peak(x):
 peak=0
 for c in range(x.shape[1]):
  # lowpass FIR upsample to capture intersample overshoot
  u=signal.resample_poly(x[:,c],4,1)
  peak=max(peak,float(np.max(np.abs(u))))
 return peak

def build():
 for key,path in [('voice',SRC),('music',INS),('v3',V3)]:
  assert sha(path)==ORIG_HASH[key],f'{key} source drift, refuse execution'
 plan=json.loads(SCORE.read_text())
 assert plan['source_version']=='D1_FULL_V3' and len(plan['midi_events'])==15
 assert plan['line']=='мы встретились с тобой как люди видятся во сне'
 assert len({x['midi_pitch'] for x in plan['midi_events']})>=4
 assert plan['source_git_blob_sha']=='2491adff94ae4bfede8399d3f82e06c7db8ec3d6'
 voice=ffdecode(SRC,1)[:,0].astype(np.float64)
 v3=ffdecode(V3,1)[:,0].astype(np.float64)
 music=ffdecode(INS,2).astype(np.float64)
 n=min(len(voice),len(music),len(v3));voice=voice[:n];music=music[:n];v3=v3[:n]
 t=START+np.arange(n)/SR
 # No imaginary whisper. This line is sung from its first word.
 # Keep a single existing F01 performance. Tiny semantic dynamic arcs preserve phonemes and F0.
 spec=[('мы',9.16,9.74,0.70),('встретились',9.73,10.52,0.45),
       ('тобой',10.83,11.65,1.08),('как',11.95,12.22,-0.20),
       ('люди',12.22,12.77,0.34),('видятся',12.78,13.58,0.63),
       ('сне',13.89,14.73,1.10)]
 curve=np.zeros(n,dtype=np.float64)
 for label,a,d,db in spec:
  # active window avoids adjacent word overlap by keeping smooth transitions within each word
  ramp=min((d-a)*0.23,0.13)
  curve+=db*shape(t,a-.015,a+ramp,d-ramp,d+.015)
 # global phrase contour is not an amplitude fade-in; first word stays present.
 curve+=0.22*shape(t,10.42,10.70,14.17,14.75)
 assert np.max(np.abs(curve))<1.8
 voice_new=voice*10.0**(curve/20.0)
 # Backing automation protects consonants without suppressing the GG drum/riff identity.
 duck_db=np.zeros(n)
 for a,d,db in [(9.16,10.58,-0.31),(10.83,11.70,-0.42),(12.16,13.64,-0.28),(13.87,14.74,-0.32)]:
  duck_db+=db*shape(t,a-.07,a+.20,d-.16,d+.09)
 music_new=music*10**(duck_db[:,None]/20)
 # No baked master delta, no two vocals, no fake double harmonics, no hard clipping.
 mix=VOICE_GAIN*voice_new[:,None]+MUSIC_GAIN*music_new
 mix_reference=VOICE_GAIN*voice[:,None]+MUSIC_GAIN*music
 ref_v3=VOICE_GAIN*v3[:,None]+MUSIC_GAIN*music
 tp_pre=true_peak(mix)
 gain=min(1.0,0.875/tp_pre)
 mix*=gain;mix_reference*=gain;ref_v3*=gain
 # fade region edit boundaries, no click
 fade=np.ones(n);edge=int(0.1*SR)
 fade[:edge]=smoothstep(np.arange(edge)/edge)
 fade[-edge:]=smoothstep(np.arange(edge-1,-1,-1)/edge)
 mix*=fade[:,None];mix_reference*=fade[:,None];ref_v3*=fade[:,None]
 # Voice-alone comparisons normalized to same global gain used in mix to avoid misleading loudness
 for name,y,channels in [('CANDIDATE_EXPRESSIVE_F01_DRY.wav',voice_new*gain,1),
      ('CANDIDATE_EXPRESSIVE_F01_WITH_MUSIC.wav',mix,2),
      ('ORIGINAL_Z10_REFERENCE_WITH_MUSIC.wav',mix_reference,2),
      ('USER_ACCEPTED_V3_SOURCE_REFERENCE_WITH_MUSIC.wav',ref_v3,2)]:
  out=OUT/name
  sf.write(out,y,SR,subtype='PCM_24')
  if channels==2:
   subprocess.run(['ffmpeg','-y','-nostdin','-hide_banner','-v','error','-i',str(out),'-c:a','libmp3lame','-b:a','256k',str(out.with_suffix('.mp3'))],check=True)
 result={'status':'TECHNICAL_RENDER_AWAITING_USER_ARTISTIC_QUALIFICATION',
  'requested_whisper_gate':'DEFERRED_BY_USER_NOT_TESTED',
  'source_voice':'Z10 continuous source, immutable','source_voice_sha256':ORIG_HASH['voice'],
  'source_score':'D1_FULL_V3 canonical 15-note actual melody','source_score_git_sha':'2491adff94ae4bfede8399d3f82e06c7db8ec3d6',
  'source_music_sha256':ORIG_HASH['music'],'v3_accepted_reference_sha256':ORIG_HASH['v3'],
  'time_range':[START,END], 'line_time_range':[9.166667,14.722222],
  'vocal_gain_from_reverse_estimate':VOICE_GAIN,'music_gain_from_reverse_estimate':MUSIC_GAIN,
  'mix_gain_for_headroom':gain,'true_peak_after':true_peak(mix),
  'dry_vocal_correlation_with_unchanged_source':float(np.corrcoef(voice,voice_new)[0,1]),
  'dry_vocal_median_pitch_shift_cents':0,
  'max_semantic_voice_gain_delta_db':float(max(abs(curve))),
  'no_new_pitch_synthesis':True,'no_second_singer':True,'no_existing_vocal_baked_master_overlay':True,
  'no_second_rvc_conversion':True,'new_words_generated':False,
  'asr_for_new_exact_export':'PENDING_INDEPENDENT_CHECK','candidate_artistic_pass':'PENDING_USER',
  'cross_song_same_singer':'UNQUALIFIED',
  'note':'This is meaningful native expressive level/mix rephrasing of an existing sung F01 source, NOT a new independent singing synthesis, not actual whisper, not a certified global North Star.'}
 (OUT/'QUALIFICATION.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__': build()