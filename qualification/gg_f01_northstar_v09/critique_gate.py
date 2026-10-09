#!/usr/bin/env python3
"""Human Vocal F01 adversarial review: acoustics + human phonetic feedback.

This is a *rejection gate*, never an automated aesthetic acceptance decision.
It does not modify a master or hallucinate acoustic improvement from ASR success.
"""
import argparse, hashlib, json, os, pathlib, subprocess
import numpy as np

EXPECTED={
 'z10':'ee7261383a99f7ea055eb0ac0dcd1ab73472c18882fdf7004df423e65dfc8dfd',
 'v3':'1e5c87284d410d6dca090025388a95d75f0cd6dd0cb7211248bdef548c91d82a',
 'music':'9e8636e031ee4d29bbb4258aa9d81a0f6833405ed06d8a5c3ad15401633f1ff7',
}
ROOT=pathlib.Path(os.getenv('GG_GOLDEN_ROOT', '/mnt/data/gg_northstar_v2/golden'))
PATHS={'z10':ROOT/'NEZRIMY_GOST_Z10_VOCAL_SOURCE.mp3','v3':ROOT/'VOCAL_REPAIRED_V3.mp3','music':ROOT/'INSTRUMENTAL_REAL_V2.mp3'}
START, END, SR=8.8,15.25,24000
WORD_TIMES=[('мы',9.1667,9.7222),('встретились',9.7222,10.5556),('с',10.5556,10.8333),('тобой',10.8333,11.6667),('как',11.9444,12.2222),('люди',12.2222,12.7778),('видятся',12.7778,13.6111),('во',13.6111,13.8889),('сне',13.8889,14.7222)]
OBSERVED_USER_FEEDBACK={
 'мы': {'present':False,'finding':'FIRST_WORD_NEAR_INAUDIBLE'},
 'встретились': {'sung':False,'finding':'BROKEN_MECHANICAL_SPOKEN_INSTEAD_OF_SUNG'},
 'видятся': {'phonetic_accept':False,'heard_as':'видится','finding':'LEXICAL_FORM_MISHEARD'},
}

def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

def read_audio(path):
 cmd=['ffmpeg','-nostdin','-v','error','-ss',str(START),'-i',str(path),'-t',str(END-START),'-ac','1','-ar',str(SR),'-f','f32le','-']
 p=subprocess.run(cmd,capture_output=True,check=True)
 return np.frombuffer(p.stdout,dtype='<f4').copy()

def db(y):return float(20*np.log10(max(1e-10,float(np.sqrt(np.mean(np.square(y.astype(np.float64))))))))

def crop(y,a,b):
 i=max(0,round((a-START)*SR));j=min(len(y),round((b-START)*SR));return y[i:j]

def inspect_signal(paths=PATHS, verify=True):
 if verify:
  for key,p in paths.items():
   if sha(p)!=EXPECTED[key]:raise ValueError(f'PINNED_SOURCE_DRIFT:{key}')
 s={k:read_audio(p) for k,p in paths.items()}
 out=[]
 for word,a,b in WORD_TIMES:
  levels={k:round(db(crop(s[k],a,b)),2) for k in s}
  out.append({'word':word,'score_interval_seconds':[a,b],
    'levels_dbfs':levels,
    'source_vocal_minus_music_db':round(levels['z10']-levels['music'],2),
    'source_vocal_minus_v3_db':round(levels['z10']-levels['v3'],2)})
 first=next(r for r in out if r['word']=='мы')
 a,b=WORD_TIMES[0][1:]
 early=db(crop(s['z10'],a,a+.25));late=db(crop(s['z10'],b-.25,b))
 first['early_250ms_dbfs']=round(early,2)
 first['late_250ms_dbfs']=round(late,2)
 first['early_minus_late_db']=round(early-late,2)
 return out

def decide(rows, feedback=OBSERVED_USER_FEEDBACK, asr_result='EXACT'):
 """No number of automated PASS values can override an explicit human phonetic FAIL."""
 failures=[]; by={row['word']:row for row in rows}
 if by['мы']['early_minus_late_db'] < -9:
  failures.append({'word':'мы','code':'INAUDIBLE_OPENING_ONSET','detail':'Early part is substantially weaker than later vowel; word-boundary score may be out of alignment'})
 if by['встретились']['source_vocal_minus_music_db'] < -4:
  failures.append({'word':'встретились','code':'WORD_MASKED_BY_INSTRUMENTAL','detail':'Word source weaker than accompanying music by >4dB; observational threshold, not a universal masking model'})
 if by['встретились']['source_vocal_minus_v3_db'] < -6:
  failures.append({'word':'встретились','code':'SOURCE_WEAKER_THAN_ACCEPTED_V3','detail':'Large level regression from previous preserved sung take'})
 for word,issue in feedback.items():
  if issue.get('present') is False:failures.append({'word':word,'code':'HUMAN_INAUDIBLE_WORD','detail':issue['finding']})
  if issue.get('sung') is False:failures.append({'word':word,'code':'HUMAN_NOT_SUNG','detail':issue['finding']})
  if issue.get('phonetic_accept') is False:failures.append({'word':word,'code':'HUMAN_PHONETIC_REJECT','detail':issue['finding']+'; heard as '+issue.get('heard_as','')})
 return {'status':'REJECT' if failures else 'ARTISTIC_REVIEW_REQUIRED',
   'asr_pass_no_override':asr_result,
   'asr_is_only_a_screen':True,
   'singer_naturalness_machine_certification':False,
   'user_rejection_is_binding':bool(feedback),
   'whisper_module':'DEFERRED',
   'original_accepted_master_unchanged':True,
   'failures':failures,
   'next_action':'SOURCE_PERFORMANCE_REPAIR_REQUIRED_BEFORE_ANY_MIX_OR_GAIN_CHANGES' if failures else 'HUMAN_LISTENING',
   'notes':'Word windows are SCORE-derived, not forced alignment. For precise localization, independently align acoustic onsets and evaluate with focused A/B. Orthographic ASR can normalize or linguistically infer a word from its context; lexical naturalness needs direct scrutiny.'}

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument('--golden-root',type=pathlib.Path,default=ROOT,help='Directory holding immutable source Z10, V3 and REAL V2 MP3s')
 ap.add_argument('--out',default='GG_F01_V08_REJECT_SIGNAL_EVIDENCE.json')
 a=ap.parse_args()
 paths={k:a.golden_root/v.name for k,v in PATHS.items()}
 rows=inspect_signal(paths);report=decide(rows);report['per_word_acoustics']=rows
 p=pathlib.Path(a.out);p.parent.mkdir(exist_ok=True,parents=True);p.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps({'status':report['status'],'failures':report['failures']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()