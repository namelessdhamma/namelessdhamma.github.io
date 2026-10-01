"""Audition Awata Weak v3: sung Russian excerpt, three separately synthesized colors."""
from pathlib import Path
import json,subprocess,sys,traceback
root=Path('awata/Awata_Weak_DS_v3'); out=Path('gg-vocal-audition');out.mkdir(exist_ok=True)
log=[]
def say(*xs):
 s=' '.join(map(str,xs));print(s,flush=True);log.append(s)
try:
 ph_raw=json.loads((root/'dsmain/phonemes.json').read_text())
 inventory=set(ph_raw if isinstance(ph_raw,list) else ph_raw.keys())
 say('BANK_PHONEMES_RU',[p for p in sorted(inventory) if p.startswith('ru/')]);say('PHONEME_COUNT',len(inventory))
 say('BANK_LANGUAGES',(root/'dsmain/languages.json').read_text()[:1500])
 say('BANK_VOCODER_PRESENT',len(list(root.rglob('*vocoder*.onnx')))>0)
 def ph(*options):
  for p in options:
   if p in inventory:return p
  raise ValueError('Missing phoneme '+str(options))
 groups=[
  [ph('ru/y','ru/j','ru/iy'),ph('ru/a')],
  [ph('ru/g'),ph('ru/ax','ru/a','ru/o')],
  [ph('ru/v'),ph('ru/ax','ru/a','ru/o')],
  [ph('ru/ry','ru/rj','ru/r'),ph('ru/i'),ph('ru/l','ru/ly')],
  [ph('ru/ny','ru/nj','ru/n'),ph('ru/e','ru/ex')],
  [ph('ru/s'),ph('ru/ny','ru/nj','ru/n'),ph('ru/i'),ph('ru/m')],
 ]
 seq=['SP']+[p for g in groups for p in g]+['SP']
 dur=[.375]
 for g in groups:
  dur+=({2:[.10,.65],3:[.12,.53,.10],4:[.12,.08,.45,.10]}[len(g)])
 dur.append(.375)
 assert len(seq)==len(dur)
 ds={'offset':0.0,'text':'SP Я го во рил не с ним SP',
 'ph_seq':' '.join(seq),'ph_dur':' '.join(map(str,dur)),
 'ph_num':'1 2 2 2 3 2 4 1',
 'note_seq':'rest G3 A3 B3 A3 G3 F#3 rest',
 'note_dur':'0.375 0.75 0.75 0.75 0.75 0.75 0.75 0.375',
 'note_slur':'0 0 0 0 0 0 0 0'}
 assert sum(map(int,ds['ph_num'].split()))==len(seq)
 assert len(ds['note_seq'].split())==len(ds['ph_num'].split())
 dspath=out/'vstrecha_ja_govoril_ne_s_nim.ds'
 dspath.write_text(json.dumps([ds],ensure_ascii=False,indent=2))
 for color,sp in [('mature','embeds/5_mature'),('soft','embeds/2_soft'),('dark','embeds/6_dark')]:
  cmd=['dsutau',str(dspath),'--voice-bank',str(root),'--lang','ru',
       '--speaker',sp,'--pitch-steps','5','--variance-steps','5',
       '--acoustic-steps','12','--output',str(out/color)]
  say('SYNTHESIS_START',color)
  proc=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                      text=True,timeout=650)
  (out/f'{color}.log').write_text(proc.stdout[-18000:])
  wavs=list((out/color).rglob('*.wav'))
  say('SYNTHESIS_RESULT',color,'returncode',proc.returncode,'wavs',[(str(f),f.stat().st_size) for f in wavs])
  if proc.returncode or not wavs:
   say('ENGINE_LOG_TAIL',proc.stdout[-7000:]);break
except Exception as e:
 say('BLOCKER',repr(e));say(traceback.format_exc()[-4500:])
finally:
 (out/'render-audit.txt').write_text('\n'.join(log))
