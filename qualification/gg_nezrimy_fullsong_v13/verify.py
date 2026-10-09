"""Independent guards for GG phonetic reconstruction v1.3; artistic approval excluded."""
import json,hashlib
from pathlib import Path
import numpy as np,soundfile as sf
from build import WINDOWS,S
P=Path(__file__).resolve().parent
R=Path('/mnt/data/GG_NORTHSTAR_FULL_SONG_RECOVERY_20261009')
q=json.loads((P/'MANIFEST.json').read_text())
b,s=sf.read(R/'review/GG_NEZRIMY_FULL_M3_REAL_DYA_SOURCE_DONOR_D_REVIEW.wav',dtype='float32',always_2d=True)
y,ss=sf.read(P/'NEZRIMY_GOST_V13_SIX_ISSUES_REVIEW.wav',dtype='float32',always_2d=True)
assert s==ss==S and b.shape==y.shape and b.shape[1]==2
assert 271<len(y)/S<273
print('PASS — entire existing song retained (~272s, stereo 48kHz)')
mask=np.zeros(len(y),dtype=bool)
for word,(a,b_) in WINDOWS.items():
 aa=round(a*S);bb=round(b_*S)
 mask[aa:bb]=True
 diff=np.abs(y[aa:bb]-b[aa:bb])
 assert np.count_nonzero(diff>1e-6)>100,('missing actual audio edit',word)
 peak_y=float(np.max(np.abs(y[aa:bb])));peak_b=float(np.max(np.abs(b[aa:bb])))
 assert peak_y<=max(.985,peak_b)+.002,(word,peak_y,peak_b)
 print('PASS — real changed audio, local peak safe:',word,round(peak_b,3),'→',round(peak_y,3))
assert np.array_equal(y[~mask],b[~mask]);print('PASS — decoded PCM exactly unchanged OUTSIDE six intended windows')
assert np.array_equal(y[round(13.055*S):round(13.325*S)],b[round(13.055*S):round(13.325*S)]);print('PASS — previous v1.2 «видятся» repair preserved')
assert q['source_v3_sha256']=='1e5c87284d410d6dca090025388a95d75f0cd6dd0cb7211248bdef548c91d82a';print('PASS — singer source pinned')
for word,ms in [('с тобой',54),('в тишине',64)]:
 assert q['regions'][word]['qa']['new_sound_ms']==ms
 assert q['regions'][word]['qa']['consonant_anchored_before_next_word_s']<=.0031
 print('PASS — linked consonant without exaggerated preposition separation:',word)
assert q['status']=='ARTISTIC_REVIEW_ONLY' and q['no_second_voice'] and q['no_whisper'];print('PASS — no artistic false-PASS, no extra vocal track, no whisper hypothesis')
assert all((P/x).is_file() and (P/x).stat().st_size>8000 for x in ['SIX_ISSUES_BEFORE_AFTER.mp3','NEZRIMY_GOST_V13_SIX_ISSUES_REVIEW.mp3']+[f'{i:02}_{n}_BEFORE_AFTER.mp3' for i,n in enumerate(['STOBOY','V_TISHINE','LYUDI','DVE_TROPY','DO_RAZLUKI','NEZABVENNYM'],1)]);print('PASS — full MP3 and six playable paired A/B excerpts exist')
assert hashlib.sha256((P/'NEZRIMY_GOST_V13_SIX_ISSUES_REVIEW.mp3').read_bytes()).hexdigest()==q['new_song_sha256'];print('PASS — exact current review MP3 SHA256 match')
print('RESULT — technical regression checks PASS; correct phonemes and artistic acceptance STILL require actual human listening')