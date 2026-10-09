#!/usr/bin/env python3
"""GG Vocal Factory: evidence-first orchestration, not another vocal generator.
Only actual isolated stems and explicit gate evidence may reach a user-review mix.
Existing OpenUtau/DiffSinger, SoulX, Applio, VFS and ASR remain external executors.
"""
from __future__ import annotations
import argparse, hashlib, json, os, pathlib, re, shutil, subprocess, sys, time
import numpy as np
import soundfile as sf

VERSION='0.1.1'
STAGES=('score','guide','diction','expression','timbre','vfs','mix','audio_qa','human_review')
REJECTED={'REJECT','FAIL','FAILED','BLOCKED','ERROR','UNVERIFIED'}

def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def readjson(path):
    return json.loads(pathlib.Path(path).read_text(encoding='utf-8'))

def savejson(path,obj):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_name(p.name+'.tmp');tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');tmp.replace(p)

def find_report_status(report):
    x=report.get('status','UNVERIFIED')
    return str(x).upper()

def get_phrases(score):
    assert score['ticks_per_beat']>0 and score['bpm']>0
    assert len(score['phrases'])>0
    ids=set();bounds=[]
    seconds_per_tick=60/(score['bpm']*score['ticks_per_beat'])
    for ph in score['phrases']:
        pid=ph['id']; assert pid not in ids,('duplicate ID',pid);ids.add(pid)
        tick=(ph['bar']*4*score['ticks_per_beat'])+ph['offset']
        length=0;words=[]
        for w in ph['words']:
            assert len(w['durations'])==len(w['pitches']) and len(w['durations'])>0,(pid,w['text'])
            assert all(x>0 for x in w['durations']),(pid,w['text'])
            length+=sum(w['durations'])+w.get('rest',0)
            words.append(w['text'])
        bounds.append({'id':pid,'text':' '.join(words),'start':round(tick*seconds_per_tick,6),
                       'end':round((tick+length)*seconds_per_tick,6)})
    return bounds

def acoustic_report(path,full=False):
    info=sf.info(str(path))
    peak=0.;sq=0.;n=0;maxjump=0.;zeros=0;last=None
    with sf.SoundFile(str(path)) as f:
        while True:
            block=f.read(65536,dtype='float32',always_2d=True)
            if not len(block):break
            mono=block.mean(axis=1);peak=max(peak,float(np.max(np.abs(block))))
            sq+=float(np.dot(mono.astype('float64'),mono.astype('float64')));n+=len(mono)
            maxjump=max(maxjump,float(np.max(np.abs(np.diff(mono))))) if len(mono)>1 else maxjump
            if last is not None:maxjump=max(maxjump,float(abs(mono[0]-last)))
            last=float(mono[-1]);zeros+=int(np.count_nonzero(np.abs(mono)<1e-8))
    duration=info.frames/info.samplerate
    return {'path':str(path),'sha256':sha256(path),'sample_rate':info.samplerate,
            'channels':info.channels,'duration_s':round(duration,5),
            'peak':round(peak,7),'rms':round((sq/max(n,1))**.5,7),
            'max_adjacent_jump':round(maxjump,7),'zero_sample_fraction':round(zeros/max(n,1),6),
            'pcm_clipping_risk':bool(peak>=.999)}

def norm(s):
    return re.sub(r'\s+',' ',re.sub('[^а-я0-9 ]',' ',s.lower().replace('ё','е'))).strip()

def check_declared_lineage(man):
    faults=[]
    if man.get('source_type') not in ('raw_singing','dry_vocal','original_human_recording'):
        faults.append('Source is not an unconverted dry lead. RVC twice/baked-master prohibited.')
    if man.get('rvc_passes',0)>1:faults.append('Repeated RVC destroys consonants; at most one pass.')
    if man.get('contains_baked_vocal'):faults.append('Cannot replace singer inside baked master.')
    if man.get('vocals_on_instrumental'):faults.append('Music stem must contain zero old vocal.')
    if man.get('sample_origin')=='synthetic_assembled_phoneme_chunks' and not man.get('human_approved_articulation'):
        faults.append('Hand-assembled phoneme performance has no articulation approval.')
    return faults

def collect(recipe):
    p=readjson(recipe);source=pathlib.Path(recipe).resolve().parent
    sc=(source/p['score']).resolve();score=readjson(sc);bounds=get_phrases(score)
    files={}; missing=[]
    for key,rel in p.get('stems',{}).items():
        f=(source/rel).resolve()
        if not f.is_file():missing.append(key+':'+str(f))
        elif f.suffix.lower() in ('.wav','.flac','.ogg'):files[key]=acoustic_report(f)
        else:files[key]={'path':str(f),'sha256':sha256(f),'bytes':f.stat().st_size}
    report_files={};reports={};
    for key,rel in p.get('gate_reports',{}).items():
        f=(source/rel).resolve()
        if not f.is_file():missing.append('gate:'+key+':'+str(f))
        else:
            reports[key]=readjson(f)
            report_files[key]={'path':str(f),'sha256':sha256(f),'status':find_report_status(reports[key])}
    defects=check_declared_lineage(p.get('lineage',{}))
    if p.get('score_version_expected') and score.get('version')!=p['score_version_expected']:
        defects.append('Score source mismatch: expected '+str(p['score_version_expected'])+' but found '+str(score.get('version'))+'; stale QA reports cannot approve a different score.')
    source_duration=files.get('guide',{}).get('duration_s',0)
    if source_duration and bounds[-1]['end']>source_duration+2:
        defects.append('Score final phrase extends beyond guide audio.')
    qa_fails=[]
    # Do not trust a global PASS if individual phrases are known to fail.
    for key in ('guide','rvc_selection','post_vfs_asr','audio','qualification'):
        if key in reports:
            a=reports[key]
            if find_report_status(a)!='PASS':qa_fails.append(f'{key}:{find_report_status(a)}')
            if a.get('failures'):qa_fails.extend(f'{key}:{x}' for x in a['failures'])
            if a.get('blockers'):qa_fails.append(f'{key}:{len(a["blockers"])} blocked phrases')
            if a.get('unresolved'):qa_fails.append(f'{key}:{len(a["unresolved"])} unresolved phrases')
    for key in ('guide','selected_vocal','vfs_vocal'):
        if key in files and files[key].get('pcm_clipping_risk'):qa_fails.append(key+':possible clipping')
    ready=(not missing and not defects and not qa_fails and
           all(k in reports for k in ('guide','rvc_selection','post_vfs_asr','audio','qualification')))
    evidence_payload={'score_sha256':sha256(sc),
        'files':{k:v['sha256'] for k,v in sorted(files.items())},
        'reports':{k:v['sha256'] for k,v in sorted(report_files.items())}}
    evidence_sha256=hashlib.sha256(json.dumps(evidence_payload,sort_keys=True).encode()).hexdigest()
    return {'factory_version':VERSION,'recipe':str(recipe),'song':p['song'],'stage_ids':STAGES,
            'score':{'file':str(sc),'sha256':sha256(sc),'bpm':score['bpm'],'phrases':bounds},
            'evidence_sha256':evidence_sha256,
            'files':files,'reports':report_files,'missing':missing,'lineage_blockers':defects,
            'qa_blockers':qa_fails,'machine_gate':'PASS' if ready else 'REJECT',
            'artistic_status':'UNREVIEWED — machine-pass never equals artistic acceptance'}

def guarded_mix(recipe,out,review):
    result=collect(recipe);p=readjson(recipe);base=pathlib.Path(recipe).resolve().parent
    if not pathlib.Path(review).is_file():
        raise RuntimeError("Human artistic acceptance file missing; no publication.")
    human=readjson(review)
    if result['machine_gate']!='PASS':raise RuntimeError('MACHINE_GATE_REJECT: '+str(result['qa_blockers']+result['missing']+result['lineage_blockers']))
    if human.get('verdict')!='ACCEPT' or human.get('song')!=p['song'] or not human.get('reviewer'):
        raise RuntimeError('Human artistic acceptance tied to this song is mandatory; no publication.')
    if human.get('recipe_sha256')!=sha256(recipe):raise RuntimeError('Review belongs to another recipe revision.')
    voice=base/p['stems']['vfs_vocal'];music=base/p['stems']['instrumental']
    if human.get('evidence_sha256')!=result['evidence_sha256']:
        raise RuntimeError('Human review does not match current machine evidence bundle.')
    if human.get('vocal_sha256')!=sha256(voice) or human.get('instrumental_sha256')!=sha256(music):
        raise RuntimeError('Human review input-audio SHA256 does not match current stems.')
    dst=pathlib.Path(out);dst.parent.mkdir(parents=True,exist_ok=True)
    # Only standalone music + single standalone dry vocal; never an already voiced master.
    cmd=['ffmpeg','-hide_banner','-nostdin','-y','-loglevel','error','-i',str(music),'-i',str(voice),
         '-filter_complex','[0:a][1:a]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.94[out]',
         '-map','[out]','-ar','48000','-c:a','libmp3lame','-b:a','320k',str(dst)]
    subprocess.run(cmd,check=True,timeout=300)
    savejson(dst.with_suffix('.manifest.json'),{'source_recipe_hash':sha256(recipe),'human_review_hash':sha256(review),
             'mix_sha256':sha256(dst),'music_sha256':sha256(music),'vocal_sha256':sha256(voice),
             'FFmpeg':cmd,'not_an_artistic_guarantee':True})
    return dst

def audition(recipe,out,phrase_id,before=.3,after=.4):
    r=collect(recipe);p=readjson(recipe);root=pathlib.Path(recipe).resolve().parent
    ph=next((x for x in r['score']['phrases'] if x['id']==phrase_id),None)
    if not ph:raise ValueError('No phrase '+phrase_id)
    sources=[k for k in ('guide','selected_vocal','vfs_vocal') if k in r['files']]
    if not sources:raise ValueError('No available vocal source')
    clips=[];sr=48000
    from math import gcd
    for srcname in sources:
        y,rate=sf.read(root/p['stems'][srcname],dtype='float32',always_2d=True)
        y=y.mean(axis=1)
        if rate!=sr:
            from scipy.signal import resample_poly
            g=gcd(rate,sr);y=resample_poly(y,sr//g,rate//g)
        a=max(0,int((ph['start']-before)*sr));b=min(len(y),int((ph['end']+after)*sr))
        clips += [y[a:b],np.zeros(int(.65*sr),dtype=np.float32)]
    dest=pathlib.Path(out);dest.parent.mkdir(parents=True,exist_ok=True)
    sf.write(dest,np.concatenate(clips),sr,subtype='PCM_24')
    savejson(dest.with_suffix('.json'),{'song':p['song'],'phrase':ph,'sources':sources,'sha256':sha256(dest),
            'status':'REFERENCE_ONLY / NOT ARTISTICALLY APPROVED'})
    return dest

def main():
    ap=argparse.ArgumentParser(description=__doc__);s=ap.add_subparsers(dest='command',required=True)
    a=s.add_parser('audit');a.add_argument('recipe');a.add_argument('--out')
    b=s.add_parser('audition');b.add_argument('recipe');b.add_argument('phrase_id');b.add_argument('--out',required=True)
    c=s.add_parser('mix');c.add_argument('recipe');c.add_argument('--review',required=True);c.add_argument('--out',required=True)
    d=s.add_parser('commands');d.add_argument('recipe')
    q=ap.parse_args()
    if q.command=='audit':
        obj=collect(q.recipe)
        if q.out:savejson(q.out,obj)
        print(json.dumps({'machine_gate':obj['machine_gate'],'missing':obj['missing'],
             'lineage_blockers':obj['lineage_blockers'],'qa_blockers':obj['qa_blockers'],
             'phrases':len(obj['score']['phrases'])},ensure_ascii=False,indent=2))
        return 0 if obj['machine_gate']=='PASS' else 2
    if q.command=='audition':print(audition(q.recipe,q.out,q.phrase_id));return 0
    if q.command=='mix':print(guarded_mix(q.recipe,q.out,q.review));return 0
    if q.command=='commands':
        print('EXISTING PRODUCTION TOOLS (not reinventions):')
        for cmd in [
          'python tools/gg_ne_s_nim_d1_full_arrange.py SCORE.json ARRANGEMENT_DIR',
          'python tools/gg_d1r5_guide_gate.py --score SCORE.json --guide RAW_GUIDE.wav --out qa-guide.json --threshold .20',
          'Applio vocal_mutate (Awata Original / FCPE .30 and .50 / protect 0.5 / NO FX) — one pass only',
          'python tools/gg_d1r5_rvc_variant_select.py --score SCORE.json --guide RAW_GUIDE.wav --candidate p030=C.wav --candidate p050=D.wav --output SELECTED.wav --report rvc-qa.json --threshold .20',
          'python tools/gg_d1r5_vfs_envelope.py --input SELECTED.wav --score SCORE.json --output VFS.wav --report vfs-qa.json',
          'python tools/gg_audio_qa.py --vocal VFS.wav --instrumental MUSIC.wav --drums DRUMS.wav --riff RIFF.wav --master MASTER.wav --score SCORE.json --bpm 108 --out audio-qa.json']:
            print('  '+cmd)
        return 0
if __name__=='__main__':
    try:sys.exit(main())
    except Exception as e:print('GG_FACTORY_ERROR:',e,file=sys.stderr);sys.exit(2)