"""Render genuine Awata v3 vocals with native acoustic model and vocoder.
Compatibility adapter: the bank has no optional dsvariance; do not load one.
Noncommercial technical audition: upstream PC-NSF-HiFiGAN weights are BY-NC-SA.
"""
from pathlib import Path
import json,math,traceback,numpy as np
from diffsinger_utau.voice_bank.commons.voice_bank_reader import VoiceBankReader
from diffsinger_utau.voice_bank.commons.ds_reader import DSReader
from diffsinger_utau.voice_bank.pred_acoustic import PredAcoustic
from diffsinger_utau.voice_bank.pred_vocoder import PredVocoder
from diffsinger_utau.voice_bank.commons.utils import resample_align_curve

root=Path('awata/Awata_Weak_DS_v3');out=Path('gg-vocal-audition');out.mkdir(exist_ok=True)
logs=[]
def log(*values):
 s=' '.join(map(str,values));print(s,flush=True);logs.append(s)
try:
 inventory=json.loads((root/'dsmain/phonemes.json').read_text())
 def ph(*options):
  return next((p for p in options if p in inventory),None) or (_ for _ in ()).throw(ValueError('Absent phoneme '+str(options)))
 groups=[
  [ph('ru/j','ru/y'),ph('ru/a')],
  [ph('ru/g'),ph('ru/ax','ru/a')],
  [ph('ru/v'),ph('ru/ax','ru/a')],
  [ph('ru/ry','ru/r'),ph('ru/i'),ph('ru/l','ru/ly')],
  [ph('ru/ny','ru/n'),ph('ru/e','ru/ex')],
  [ph('ru/s'),ph('ru/ny','ru/n'),ph('ru/i'),ph('ru/m')],
 ]
 phonemes=['SP']+[p for g in groups for p in g]+['SP']
 phdur=[.375]
 for g in groups:phdur+=({2:[.10,.65],3:[.12,.53,.10],4:[.12,.08,.45,.10]}[len(g)])
 phdur.append(.375)
 notes=[('rest',.375),('G3',.75),('A3',.75),('B3',.75),('A3',.75),('G3',.75),('F#3',.75),('rest',.375)]
 from librosa import note_to_hz
 hop=512/44100
 f0=[]
 for name,duration in notes:
  frames=round(duration/hop)
  if name=='rest':f0.extend([0.0]*frames);continue
  hz=float(note_to_hz(name))
  for frame in range(frames):
   t=frame*hop
   approach=-.09*math.exp(-t/.10)
   vib=.035*math.sin(2*math.pi*4.6*(t-.27))*min(1,max(0,(t-.27)/.20))
   f0.append(hz*2**((approach+vib)/12))
 ds={'offset':0.0,'text':'SP Я го во рил не с ним SP',
  'ph_seq':' '.join(phonemes),'ph_dur':' '.join(f'{d:.5f}' for d in phdur),
  'ph_num':'1 2 2 2 3 2 4 1',
  'note_seq':' '.join(p for p,_ in notes),
  'note_dur':' '.join(str(d) for _,d in notes),
  'note_slur':' '.join(['0']*len(notes)),
  'f0_seq':' '.join(f'{x:.3f}' for x in f0),
  'f0_timestep':str(hop)}
 assert len(phonemes)==sum(map(int,ds['ph_num'].split()))==len(phdur)
 assert abs(sum(phdur)-sum(d for _,d in notes))<1e-5
 (out/'source.ds').write_text(json.dumps([ds],ensure_ascii=False,indent=2))
 acoustic_cfg=root/'dsconfig.yaml';vocoder_cfg=root/'dsvocoder/vocoder.yaml'
 log('ACOUSTIC_CONFIG',acoustic_cfg.exists(),'VOCODER_CONFIG',vocoder_cfg.exists())
 if not vocoder_cfg.exists():raise RuntimeError('VOCODER_NOT_INSTALLED')
 dsacoustic=VoiceBankReader.DSAcoustic(acoustic_cfg,preload_models=True)
 dsvocoder=VoiceBankReader.DSVocoder(vocoder_cfg,preload_models=True)
 ac=PredAcoustic(dsacoustic);vc=PredVocoder(dsvocoder)
 for color,speaker in [('mature','embeds/5_mature'),('soft','embeds/2_soft'),('dark','embeds/6_dark')]:
  log('START',color,speaker)
  mel=ac.predict(DSReader.DSSection(ds),lang='ru',speaker=speaker,steps=12)
  log('MEL',mel.shape)
  f0aligned=resample_align_curve(np.asarray(f0,dtype=np.float32),hop,vc.timestep,mel.shape[1])
  wav=vc.predict(mel,f0aligned)
  target=out/f'vstrecha_female_{color}_REAL_SINGING.wav'
  vc.save_wav(wav,target)
  log('SUCCEEDED',target,target.stat().st_size,'samples',len(wav))
except Exception as e:
 log('FAILED',repr(e),traceback.format_exc()[-6000:])
finally:
 (out/'render-audit.txt').write_text('\n'.join(logs))
