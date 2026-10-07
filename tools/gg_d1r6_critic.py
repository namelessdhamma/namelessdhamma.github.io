#!/usr/bin/env python3
import argparse,json,pathlib,sys,re

def tokens(s):
    s=s.lower().replace('ё','е')
    return re.sub(r'[^а-я0-9 ]+',' ',s).split()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--audio',required=True); ap.add_argument('--guide-asr',required=True)
    ap.add_argument('--d-asr',required=True); ap.add_argument('--rvc',required=True)
    ap.add_argument('--vfs',required=True); ap.add_argument('--out',required=True)
    a=ap.parse_args()
    aq=json.loads(pathlib.Path(a.audio).read_text())
    gd=json.loads(pathlib.Path(a.guide_asr).read_text())
    dd=json.loads(pathlib.Path(a.d_asr).read_text())
    rv=json.loads(pathlib.Path(a.rvc).read_text())
    vf=json.loads(pathlib.Path(a.vfs).read_text())
    failures=list(aq.get('failures',[]))
    if gd.get('max_phrase_cer',1)>.20 or gd.get('over_020'): failures.append('guide_phrase_intelligibility')
    if gd.get('cer',1)>.15: failures.append('guide_global_cer')
    if dd.get('max_phrase_cer',1)>.20 or dd.get('over_020'): failures.append('d_phrase_intelligibility')
    if dd.get('cer',1)>.18: failures.append('d_global_cer')
    if rv.get('status')!='PASS': failures.append('rvc_phrase_selector')
    if vf.get('status')!='PASS': failures.append('vfs_selector')
    # The user explicitly reported swallowed negation and chorus words.
    required={
      'c1l1':['не','ним'],'c2l1':['не','ним'],
      'c1l4':['лишь','голос','свой'],'c2l4':['лишь','голос','свой'],
      'finl1':['не'],'finl4':['не'],'codal2':['не']
    }
    by={x['id']:x for x in dd.get('phrases',[])}
    missing={}
    for pid,req in required.items():
        if pid not in by: continue
        ts=tokens(by[pid].get('transcript',''))
        miss=[w for w in req if w not in ts]
        if miss: missing[pid]=miss
    if missing: failures.append('critical_words_missing')
    # Repeated chorus pronunciation should remain comparable.
    def mean(prefix):
        xs=[x['cer'] for x in dd.get('phrases',[]) if x['id'].startswith(prefix)]
        return sum(xs)/len(xs) if xs else 9
    if abs(mean('c1l')-mean('c2l'))>.20: failures.append('d_chorus_consistency')
    result={'status':'PASS' if not failures else 'REJECT','gate_version':'D1R6',
            'failures':list(dict.fromkeys(failures)),'critical_words_missing':missing,
            'audio':aq,'guide_asr':gd,'d_asr':dd,
            'rvc_summary':{'status':rv.get('status'),'base_label':rv.get('base_label'),
                           'unresolved':rv.get('unresolved',[])},
            'vfs_summary':{'status':vf.get('status'),'selected':vf.get('selected')}}
    pathlib.Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['status']=='PASS' else 2
if __name__=='__main__': raise SystemExit(main())
