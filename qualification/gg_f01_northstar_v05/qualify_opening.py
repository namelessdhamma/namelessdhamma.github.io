#!/usr/bin/env python3
import json, pathlib, subprocess, sys, hashlib
import numpy as np
import soundfile as sf
try: import parselmouth
except ImportError: parselmouth=None
R=pathlib.Path(__file__).parent
Q=R/'out'/'OPENING_QUALIFICATION.json'
j=json.loads(Q.read_text())
base={x['variant']:x for x in j['candidates']}
ref=base['golden_z10']
source=(R/'out'/'golden_z10_DRY.wav')
y0,sr=sf.read(source)
out=[]
for item in j['candidates']:
 name=item['variant']; p=R/'out'/(name+'_DRY.wav')
 y,s=sf.read(p)
 ratio=item['first_word_rms']/ref['first_word_rms']
 corr=np.corrcoef(y0,y)[0,1]
 acoustic_gate=bool(item['peak']<0.985 and item['nonfinite']==0 and ratio>=.65 and corr>=.95)
 pitch_info={}
 if parselmouth is not None:
  def contour(sig):
   sound=parselmouth.Sound(sig,48000)
   v=sound.to_pitch(time_step=.02,pitch_floor=130,pitch_ceiling=750).selected_array['frequency']
   return v
  f0,f1=contour(y0),contour(y)
  n=min(len(f0),len(f1)); mask=(f0[:n]>0)&(f1[:n]>0)
  cent=np.abs(1200*np.log2(f1[:n][mask]/f0[:n][mask]))
  pitch_info={'median_abs_pitch_change_cents':round(float(np.median(cent)),2) if len(cent) else None,
              'f0_overlap_frames':int(np.sum(mask))}
 entry={'variant':name,'first_word_rms_fraction_of_original':round(ratio,4),
        'waveform_correlation_to_original':round(float(corr),5),'technically_usable':acoustic_gate,
        'true_whisper_proven':False,'lyrics_asr_new_variant':'PENDING', 'pitch':pitch_info,
        'no_second_singer':True}
 if not acoustic_gate: entry['rejection_reasons']=['first_word_too_quiet_or_waveform_distortion']
 out.append(entry)
res={'north_star':'consistent emotionally expressive sung Russian by one repeatable singer',
     'time_limit_requirement':None,
     'line':'Мы встретились с тобой, как люди видятся во сне',
     'technical_candidates':out,
     'source_lexical_check':'prior independent Whisper-small exact ASR for untouched Z10, source only',
     'dynamic_variant_ASR':'PENDING; no invented pass',
     'human_artistic_selection':'PENDING',
     'actual_whisper':'NOT_PROVEN; no speech-only substitution',
     'song_master_policy':'UNCHANGED',
     'candidate_selected_for_listening':'gentle_emergence' if out[1]['technically_usable'] else 'golden_z10'}
(R/'out'/'QA_DECISION.json').write_text(json.dumps(res,ensure_ascii=False,indent=2))
print(json.dumps(out,ensure_ascii=False))