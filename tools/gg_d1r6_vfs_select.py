#!/usr/bin/env python3
import argparse,json,pathlib,re,tempfile
import numpy as np
import soundfile as sf
from faster_whisper import WhisperModel
from jiwer import cer

PROFILES=[
    ('full',   -9.0,0.62,-3.5,0.16,-4.5,0.20),
    ('medium', -7.0,0.50,-3.0,0.14,-4.0,0.18),
    ('gentle', -5.0,0.38,-2.5,0.12,-3.5,0.16),
]
SECTION_FIRST={'v1l1','c1l1','v2l1','c2l1','brl1','finl1','codal1'}

def norm(s):
    s=s.lower().replace('ё','е')
    s=re.sub(r'[^а-я0-9 ]+',' ',s)
    return re.sub(r'\s+',' ',s).strip()

def converter(score):
    tpb=score['ticks_per_beat']; BAR=tpb*4; bpm=float(score['bpm'])
    return lambda tick: tick*60.0/(bpm*tpb)

def rms(x):
    return float(np.sqrt(np.mean(np.asarray(x,dtype=np.float64)**2)+1e-12)) if len(x) else 0.0

def apply_profile(y,sr,score,profile):
    name,deep_db,deep_s,ordinary_db,ordinary_s,release_db,release_s=profile
    out=y.copy(); to_sec=converter(score); tpb=score['ticks_per_beat']; BAR=tpb*4
    for ph in score['phrases']:
        st=ph['bar']*BAR+ph['offset']; en=st
        for w in ph['words']: en+=sum(w['durations'])+w['rest']
        a=max(0,int(to_sec(st)*sr)); b=min(len(out),int(to_sec(en)*sr))
        if b<=a: continue
        n=b-a; env=np.ones(n,dtype=np.float32)
        if ph['id'] in SECTION_FIRST:
            db,dur=deep_db,deep_s
        else:
            db,dur=ordinary_db,ordinary_s
        attack=min(n,max(1,int(dur*sr)))
        env[:attack]=np.linspace(10**(db/20),1.0,attack,dtype=np.float32)
        release=min(n,max(1,int(release_s*sr)))
        tail=np.linspace(1.0,10**(release_db/20),release,dtype=np.float32)
        env[-release:]=np.minimum(env[-release:],tail)
        out[a:b]*=env
    peak=float(np.max(np.abs(out))) if len(out) else 0.0
    if peak>.985: out*=.985/peak
    return out

def phrase_bounds(score,ph):
    tpb=score['ticks_per_beat']; BAR=tpb*4; bpm=float(score['bpm']); ts=60/(bpm*tpb)
    st=ph['bar']*BAR+ph['offset']; en=st
    for w in ph['words']: en+=sum(w['durations'])+w['rest']
    return max(0,st*ts-.12),en*ts+.18

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--input',required=True); ap.add_argument('--score',required=True)
    ap.add_argument('--output',required=True); ap.add_argument('--report',required=True)
    ap.add_argument('--threshold',type=float,default=.20)
    a=ap.parse_args()
    y,sr=sf.read(a.input,always_2d=False)
    if getattr(y,'ndim',1)>1:y=y.mean(axis=1)
    y=np.asarray(y,dtype=np.float32)
    score=json.loads(pathlib.Path(a.score).read_text())
    model=WhisperModel('small',device='cpu',compute_type='int8')
    td=pathlib.Path(tempfile.mkdtemp(prefix='gg-d1r6-vfs-'))
    rows=[]; rendered={}
    for rank,p in enumerate(PROFILES):
        name=p[0]; z=apply_profile(y,sr,score,p); rendered[name]=z
        phrase_rows=[]
        for ph in score['phrases']:
            if ph['id'] not in SECTION_FIRST: continue
            st,en=phrase_bounds(score,ph); aa=max(0,int(st*sr)); bb=min(len(z),int(en*sr))
            seg=z[aa:bb]; tmp=td/f'{name}-{ph["id"]}.wav'; sf.write(tmp,seg,sr)
            ss,_=model.transcribe(str(tmp),language='ru',beam_size=5,vad_filter=False,
                                  condition_on_previous_text=False,temperature=0.0)
            txt=' '.join(x.text.strip() for x in list(ss)).strip()
            target=' '.join(w['text'] for w in ph['words'])
            # acoustic VFS readback measured at exact note onset, not pre-roll.
            onset=(ph['bar']*score['ticks_per_beat']*4+ph['offset'])*60/(score['bpm']*score['ticks_per_beat'])
            oa=max(0,int(onset*sr))
            x1=z[oa:min(len(z),oa+int(.15*sr))]
            x2=z[min(len(z),oa+int(.20*sr)):min(len(z),oa+int(.70*sr))]
            adb=20*np.log10((rms(x1)+1e-9)/(rms(x2)+1e-9))
            phrase_rows.append({'id':ph['id'],'target':target,'transcript':txt,
                                'cer':float(cer(norm(target),norm(txt))),
                                'attack_vs_body_db':float(adb)})
        maxcer=max(x['cer'] for x in phrase_rows)
        median_attack=float(np.median([x['attack_vs_body_db'] for x in phrase_rows]))
        passes=maxcer<=a.threshold and median_attack<=-2.0
        rows.append({'profile':name,'rank':rank,'max_section_start_cer':maxcer,
                     'median_attack_vs_body_db':median_attack,'passes':passes,
                     'phrases':phrase_rows})
    eligible=[x for x in rows if x['passes']]
    if eligible:
        winner=min(eligible,key=lambda x:x['rank'])  # strongest qualified VFS
        status='PASS'
    else:
        winner=min(rows,key=lambda x:(x['max_section_start_cer'],x['median_attack_vs_body_db']))
        status='REJECT'
    sf.write(a.output,rendered[winner['profile']],sr,subtype='PCM_24')
    report={'status':status,'selected':winner['profile'],'threshold':a.threshold,
            'profiles':rows,'selector_version':'D1R6_VFS_1'}
    pathlib.Path(a.report).write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if status=='PASS' else 2
if __name__=='__main__': raise SystemExit(main())
