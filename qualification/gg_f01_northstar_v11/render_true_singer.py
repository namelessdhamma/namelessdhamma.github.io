#!/usr/bin/env python3
"""GG F01 new sung first-line source: real note-driven Awata Weak v3 DiffSinger.
NO Mimosa samples, NO TTS, NO post-facto mouth shaping. Music original score v3.
Designed for ephemeral worker: downloaded third-party voice/vocoder weights never exported.
"""
import json, math, os, pathlib, sys, traceback, hashlib
import numpy as np
from diffsinger_utau.voice_bank.commons.voice_bank_reader import VoiceBankReader
from diffsinger_utau.voice_bank.commons.ds_reader import DSReader
from diffsinger_utau.voice_bank.pred_acoustic import PredAcoustic
from diffsinger_utau.voice_bank.pred_vocoder import PredVocoder
from diffsinger_utau.voice_bank.commons.utils import resample_align_curve

ROOT=pathlib.Path(os.environ.get('GG_AWATA_BANK','awata/Awata_Weak_DS_v3'))
OUT=pathlib.Path(os.environ.get('GG_OUT','gg-f01-new-singer'))
OUT.mkdir(parents=True,exist_ok=True)
SCORE=pathlib.Path(__file__).with_name('AUTHENTIC_FIRST_LINE.json')
SRC=json.loads(SCORE.read_text(encoding='utf8'))
assert SRC['authority']['source_git_blob_sha']=='2491adff94ae4bfede8399d3f82e06c7db8ec3d6'
assert SRC['bpm']==108 and SRC['phrase']['id']=='v1l1'
words=SRC['phrase']['words']
assert [w['text'] for w in words]==['мы','встретились','с','тобой','как','люди','видятся','во','сне']
raw_notes=[(int(p),int(d),word['text']) for word in words for p,d in zip(word['pitches'],word['durations'])]
assert len(raw_notes)==15 and set(n for n,_,_ in raw_notes)=={62,64,65,67,69}
# The exact original melodic pitches and ordered syllables; no flattened note fixture.
# Every element is one sung syllable assigned to one score note.
SYLLABLES=[
 ('мы', [['ru/m'],['ru/y','ru/yy','ru/ih','ru/i']]),
 ('встре', [['ru/f','ru/v'],['ru/s'],['ru/t'],['ru/ry','ru/r'],['ru/e','ru/ex']]),
 ('ти', [['ru/ty','ru/t'],['ru/i']]),
 ('лись', [['ru/ly','ru/l'],['ru/i'],['ru/sy','ru/s']]),
 ('с', [['ru/s']]),
 ('то', [['ru/t'],['ru/ax','ru/a']]),
 ('бой', [['ru/b'],['ru/o'],['ru/j']]),
 ('как', [['ru/k'],['ru/a'],['ru/k']]),
 ('лю', [['ru/ly','ru/l'],['ru/u']]),
 ('ди', [['ru/dy','ru/d'],['ru/i']]),
 ('ви', [['ru/vy','ru/v'],['ru/i']]),
 ('дят', [['ru/dy','ru/d'],['ru/a'],['ru/t']]),
 ('ся', [['ru/sy','ru/s'],['ru/a']]),
 ('во', [['ru/v'],['ru/ax','ru/a']]),
 ('сне', [['ru/s'],['ru/ny','ru/n'],['ru/e','ru/ex']]),
]
assert len(SYLLABLES)==15
# Tight onset consonant cluster in 0.278 s was causing robotically clipped "встретились".
# Two performance scores share same speaker, word order and PITCHES.
# 'legato' reallocates 180ms from neighboring long vowels to phonetic complex, preserving total length.
# Fixed deterministic changes, no random pitch jitter or tempo hacks.
REALLOC={1:0.175,0:-0.110,2:0.035,3:0.035,4:-0.060,6:-0.035,7:-0.040}
# sum modification should be zero
assert abs(sum(REALLOC.values()))<1e-8
VOCAB=json.loads((ROOT/'dsmain/phonemes.json').read_text())
missing=[]; selected=[]
for syll,phonealts in SYLLABLES:
 row=[]
 for choices in phonealts:
  avail=next((x for x in choices if x in VOCAB),None)
  if not avail:
   missing.append({'syllable':syll,'wanted':choices})
  else:
   row.append(avail)
 selected.append(row)
if missing:
 (OUT/'FAILED_MISSING_PHONEMES.json').write_text(json.dumps({'missing':missing,'vocab_ru':[x for x in VOCAB if x.startswith('ru/')]},ensure_ascii=False,indent=2))
 raise SystemExit('BANK_MISSING_REQUIRED_PHONEMES; inspect diagnostic')
# phonemes that are essential to audibly distinguish "видятся" from "видится"
assert selected[11][1]=='ru/a' and selected[12][1]=='ru/a'
# No simplistic morphological PASS: human listening still required.

sr=44100
hop=512/sr
steps=int(os.getenv('GG_DIFFUSION_STEPS','12'))
ac=PredAcoustic(VoiceBankReader.DSAcoustic(ROOT/'dsconfig.yaml',preload_models=True))
vc=PredVocoder(VoiceBankReader.DSVocoder(ROOT/'dsvocoder/vocoder.yaml',preload_models=True))

def phones_duration(n,seconds,i,variant):
 """Allocate phoneme time to vowel nuclei vs consonants; every syllable fully phonated."""
 if n==1: return [seconds]
 vowel=[j for j,p in enumerate(selected[i]) if p.rsplit('/',1)[-1] in ('a','ax','e','ex','i','o','u','y','yy','ih')]
 if not vowel:  # consonant-only preposition 'с'
  return [seconds/n]*n
 nucleus=vowel[-1]
 min_c=0.033 if variant=='score_exact' else 0.040
 cons=[j for j in range(n) if j!=nucleus]
 if seconds-min_c*len(cons)<0.065:
  # prevent clipped vowel: spend more time on vowel and make consonants as short as possible
  min_c=max(0.024,(seconds-0.090)/max(1,len(cons)))
 lengths=[min_c]*n
 lengths[nucleus]=seconds-min_c*len(cons)
 if lengths[nucleus] <.06: raise ValueError(f'vowel too short at {i}: {lengths[nucleus]}')
 return lengths

def make_ds(variant):
 secs=[d/480*60/108 for _,d,_ in raw_notes]
 if variant=='legato':secs=[s+REALLOC.get(i,0.0) for i,s in enumerate(secs)]
 assert abs(sum(secs)-sum(d/480*60/108 for _,d,_ in raw_notes))<0.00001
 assert all(s>.17 for s in secs),secs
 allnotes=[('rest',.100,[])]
 for idx,((note,_,_),seconds) in enumerate(zip(raw_notes,secs)):
  allnotes.append((['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'][note%12]+str(note//12-1),seconds,selected[idx]))
 allnotes.append(('rest',.24,[]))
 phone=['SP']; pdur=[0.100]; count=[1]
 for i,(_,dur,syllphones) in enumerate(allnotes[1:-1]):
  lens=phones_duration(len(syllphones),dur,i,variant)
  phone.extend(syllphones);pdur.extend(lens);count.append(len(syllphones))
 phone.append('SP');pdur.append(.24);count.append(1)
 assert abs(sum(pdur)-sum(d for _,d,_ in allnotes))<1e-5
 # Smooth continuous F0. Original pitches unmodified; time-locked notes; no pseudo-human jitter.
 notes=allnotes;durations=[d for _,d,_ in allnotes]; f0=[]
 t=0
 events=[]
 for k,(label,dur,phones) in enumerate(notes):
  a=round(t/hop);t+=dur;b=round(t/hop)
  if label=='rest':
   f0.extend([0.0]*(b-a));continue
  midi=raw_notes[k-1][0]
  hz=440*2**((midi-69)/12)
  before=raw_notes[k-2][0] if k>1 else midi
  for j in range(b-a):
   x=j*hop
   pitch=float(midi)
   if before!=midi and x<0.060 and variant=='legato':
    # preserve target pitch after onset, smooth through continuous previous note.
    pitch=before+(midi-before)*min(1.0,x/.060)
   # controlled onset and gentle vibrato on true sustained vowels only
   onset=-0.035*math.exp(-x/0.08) if variant=='legato' else 0
   vib=0
   if dur>.45 and x>.26 and x<dur-.05:
    vib=(0.060 if variant=='legato' else 0.025)*math.sin(2*math.pi*4.8*(x-.26))*min(1,(x-.26)/.14)
   f0.append(hz * 2**((pitch-midi+onset+vib)/12))
  events.append({'syllable':SYLLABLES[k-1][0], 'pitch_midi':midi, 'duration_sec':dur,'phonemes':phones})
 ds={'offset':0.0,'text':'Мы встретились с тобой как люди видятся во сне',
  'ph_seq':' '.join(phone),'ph_dur':' '.join(f'{x:.6f}' for x in pdur),
  'ph_num':' '.join(map(str,count)),
  'note_seq':' '.join(n for n,_,_ in allnotes),
  'note_dur':' '.join(f'{x:.6f}' for _,x,_ in allnotes),
  'note_slur':' '.join(['0']*len(allnotes)),
  'f0_seq':' '.join(f'{x:.4f}' for x in f0),
  'f0_timestep':str(hop)}
 assert len(ds['ph_seq'].split())==sum(count)==len(pdur)
 return ds,np.asarray(f0,dtype=np.float32),events

# Only ONE speaker embedding, one voice identity for both variants.
SINGER='embeds/5_mature'
report={'source_score_git_blob':'2491adff94ae4bfede8399d3f82e06c7db8ec3d6',
 'model':'Awata Weak DiffSinger v3','speaker':SINGER,'vocoder':'ezv v2.0',
 'lyrics':'Мы встретились с тобой, как люди видятся во сне',
 'musical_notes':len(raw_notes),'variants':[],'vocabulary':selected,
 'artistic_status':'UNREVIEWED','whisper':'NOT_ATTEMPTED','new_sung_source':True}
for variant in ('score_exact','legato'):
 ds,f0,events=make_ds(variant)
 (OUT/f'F01_{variant}.ds').write_text(json.dumps([ds],ensure_ascii=False,indent=2))
 print('RENDER',variant,'notes',len(events),'phonemes',len(ds['ph_seq'].split()),flush=True)
 mel=ac.predict(DSReader.DSSection(ds),lang='ru',speaker=SINGER,steps=steps)
 f0align=resample_align_curve(f0,hop,vc.timestep,mel.shape[1])
 wav=vc.predict(mel,f0align)
 fname=OUT/f'F01_{variant}_NEW_SINGING.wav'
 vc.save_wav(wav,fname)
 data=np.asarray(wav,dtype=np.float32)
 score={'variant':variant,'file':fname.name,'sha256':hashlib.sha256(fname.read_bytes()).hexdigest(),
        'seconds':len(data)/sr,'peak':float(np.max(np.abs(data))),'rms':float(np.sqrt(np.mean(data**2))),
        'phonemes':ds['ph_seq'].split(),'note_events':events}
 report['variants'].append(score)
 print('SUCCEEDED',fname,score['sha256'],'peak',score['peak'],flush=True)
(OUT/'NEW_SINGER_RENDER_MANIFEST.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))