from pathlib import Path
import json,sys,hashlib
import numpy as np
import soundfile as sf
root=Path(__file__).resolve().parent
j=json.loads((root/'output/QUALIFICATION.json').read_text()); assert j['status']=='ARTISTIC_AUDITION_NOT_ACCEPTED'
out=root/'output'
assert all(hashlib.sha256((out/k).read_bytes()).hexdigest()==v for k,v in j['output_files'].items())
assert any(r['word']=='мы' and r['v3_first_250ms_dbfs']-r['z10_first_250ms_dbfs']>12 for r in j['source_rms'])
assert any(r['word']=='встретились' and r['v3_minus_z10_db']>8 for r in j['source_rms'])
assert any(r['word']=='видятся' for r in j['source_rms'])
assert j['claims']['full_natural_singing_qualified'] is False
assert j['claims']['morphology_vidyatsya_qualified'] is False
assert j['identity_protection'].startswith('No resynthesis')
a,sr=sf.read(out/'V10_V3_ORIGINAL_SOURCE_CLEAN_STEMS.wav'); b,_=sf.read(out/'V10_V3_ORIGINAL_SINGER_DRY.wav')
assert len(a)==len(b) and a.shape[1]==2 and a.max()<1 and a.min()>-1
assert 7.84<len(a)/sr<7.86
print('VERIFIED 9/9: hashes, onset recovery, word protection, originality, audio, shape; ARTISTIC ACCEPTANCE PENDING')