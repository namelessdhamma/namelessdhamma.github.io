#!/usr/bin/env python3
import argparse,json,pathlib,re,tempfile
import soundfile as sf
from faster_whisper import WhisperModel
from jiwer import wer,cer

def norm(s):
    s=s.lower().replace('ё','е')
    s=re.sub(r'[^а-я0-9 ]+',' ',s)
    return re.sub(r'\s+',' ',s).strip()

def converter(score):
    tpb=score['ticks_per_beat']; BAR=tpb*4
    pts=sorted(score.get('tempo_map') or [{'bar':0,'bpm':score['bpm']}],key=lambda x:int(x['bar']))
    pts=[(int(x['bar'])*BAR,float(x['bpm'])) for x in pts]
    def sec(tick):
        total=0.0; last=0; bpm=pts[0][1]
        for pos,nbpm in pts[1:]:
            if tick<=pos: break
            total+=(pos-last)*60/(bpm*tpb); last=pos; bpm=nbpm
        return total+(tick-last)*60/(bpm*tpb)
    return sec

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--score',required=True); ap.add_argument('--audio',required=True)
    ap.add_argument('--label',required=True); ap.add_argument('--out',required=True)
    ap.add_argument('--model',default='small')
    a=ap.parse_args()
    score=json.loads(pathlib.Path(a.score).read_text()); to_sec=converter(score); tpb=score['ticks_per_beat']; BAR=tpb*4
    y,sr=sf.read(a.audio,always_2d=False)
    if getattr(y,'ndim',1)>1:y=y.mean(axis=1)
    model=WhisperModel(a.model,device='cpu',compute_type='int8')
    td=pathlib.Path(tempfile.mkdtemp(prefix='gg-d1r6-asr-')); rows=[]
    for ph in score['phrases']:
        st=ph['bar']*BAR+ph['offset']; en=st
        for w in ph['words']: en+=sum(w['durations'])+w['rest']
        t0=max(0.0,to_sec(st)-.12); t1=min(len(y)/sr,to_sec(en)+.18)
        seg=y[int(t0*sr):int(t1*sr)]; tmp=td/f'{a.label}-{ph["id"]}.wav'; sf.write(tmp,seg,sr)
        ss,_=model.transcribe(str(tmp),language='ru',beam_size=5,vad_filter=False,
                              condition_on_previous_text=False,temperature=0.0)
        txt=' '.join(x.text.strip() for x in list(ss)).strip()
        target=' '.join(w['text'] for w in ph['words']); nt,nr=norm(target),norm(txt)
        rows.append({'id':ph['id'],'target':target,'transcript':txt,
                     'wer':float(wer(nt,nr)),'cer':float(cer(nt,nr)),
                     'start':t0,'end':t1})
    target=' '.join(x['target'] for x in rows); text=' '.join(x['transcript'] for x in rows)
    nt,nr=norm(target),norm(text)
    result={'label':a.label,'model':a.model,'wer':float(wer(nt,nr)),'cer':float(cer(nt,nr)),
            'mean_phrase_wer':sum(x['wer'] for x in rows)/len(rows),
            'mean_phrase_cer':sum(x['cer'] for x in rows)/len(rows),
            'max_phrase_cer':max(x['cer'] for x in rows),
            'over_020':[x for x in rows if x['cer']>.20],
            'phrases':rows,'transcript':text}
    pathlib.Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
