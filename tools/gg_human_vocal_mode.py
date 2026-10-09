#!/usr/bin/env python3
"""True Visual / ND Music Studio HUMAN_VOCAL mode, evidence-first executable controller.

The role is musical orchestration/decision, NOT simulation of a singer.
This controller selects exactly one next operation using provenance and actual phoneme
intelligibility. Native workers are existing OpenUtau/SoulX/Applio/VFS/FFmpeg/ASR.
Every accepting result is bound to inputs + voice identity + specific source revision.
"""
from __future__ import annotations
import argparse, hashlib, json, os, pathlib, subprocess, sys, time
from dataclasses import dataclass
from typing import Any

MODE="TRUE_VISUAL_HUMAN_VOCAL"
REV="0.3.0-golden-song-provenance"
STAGES=("SCORE", "RAW_GUIDE", "DICTATION", "EXPRESSIVE_SOURCE", "TIMBRE", "VFS", "MIX_REVIEW", "AUDIT", "HUMAN_REVIEW")
ALLOWED_WORKERS={"openutau","diffsinger","soulx","applio","asr","vfs","ffmpeg","gg_factory","audio_qa"}

def digest(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()

def jread(p): return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))

def jwrite(p,obj):
    dest=pathlib.Path(p);dest.parent.mkdir(parents=True,exist_ok=True)
    temp=dest.with_name(dest.name+'.tmp')
    temp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding="utf-8")
    temp.replace(dest)

def norm(s):
    import re
    return ' '.join(re.sub(r'[^а-я0-9 ]',' ',s.lower().replace('ё','е')).split())


def asr_decision(source: dict, candidates: list, *, allow_cer_slack=0.025)->dict:
    """Conservative per-phrase lexical gate. Regression cannot be compensated by timbre preference.

    Inputs are exact transcription reports from independently rendered and recognized audio.
    Do not rerun ASR in this module; a pipeline adapter supplies fresh ASR, with source SHA.
    """
    base=source.get('CER')
    if base is None or not isinstance(base,(int,float)) or not 0<=base<=1:
        return {'status':'BLOCKED','reason':'MISSING_SOURCE_ASR','next':'RUN_ORIGINAL_DRY_ASR'}
    if not source.get('sha256'):
        return {'status':'BLOCKED','reason':'SOURCE_SHA_MISSING','next':'BIND_SOURCE_SHA'}
    viable=[]; rejected=[]
    for c in candidates:
        issue=[]; label=c.get('id','anonymous')
        if c.get('CER') is None:issue.append('ASR_ABSENT')
        elif c['CER']>base+allow_cer_slack:issue.append('LEXICAL_REGRESSION')
        if not c.get('sha256'): issue.append('SHA_MISSING')
        if c.get('source_sha256')!=source['sha256']:issue.append('PROVENANCE_MISMATCH')
        if c.get('rvc_passes',0)>1:issue.append('DOUBLE_RVC')
        if c.get('has_overlap'):issue.append('VOCAL_OVERLAP')
        if not issue: viable.append(c)
        else:rejected.append({'id':label,'why':issue,'cer':c.get('CER')})
    if not viable:
        return {'status':'REJECT_ALL','base':source['id'],'preserved_source':source['sha256'],
                'base_CER':base,'rejected':rejected,'next':'RESTORE_EXPRESSIVE_SOURCE_NO_EXTRA_RVC',
                'user_facing':False}
    # Lower CER is a filter only; timbre winner must be listening-qualified.
    viable.sort(key=lambda c:(c['CER'],str(c.get('id'))))
    return {'status':'READY_FOR_ARTISTIC_REVIEW','preserved_source':source['sha256'],
            'eligible':[{k:v for k,v in c.items() if k not in ('private',)} for c in viable],
            'rejected':rejected,'next':'TRUE_VISUAL_A_B_LISTENING','user_facing':False}


def evaluate(project:dict,base:pathlib.Path)->dict:
    """One correct highest-value next frontier; no speculative worker invocation."""
    blockers=[]
    for key in ('project','score','raw_voice','instrumental','target_text'):
        if not project.get(key):blockers.append('missing:'+key)
    if blockers:
        return {'mode':MODE,'revision':REV,'status':'BLOCKED','issues':blockers,'next':'RECOVER_REQUIRED_INPUTS'}
    files={};missing=[]
    for key in ('score','raw_voice','instrumental'):
        path=(base/project[key]).resolve();
        if not path.is_file():missing.append(key+':'+str(path))
        else:files[key]={'path':str(path),'sha256':digest(path),'bytes':path.stat().st_size}
    if missing:return {'mode':MODE,'revision':REV,'status':'BLOCKED','issues':missing,'next':'RECOVER_REQUIRED_INPUTS'}
    if project.get('input_voice_rvc_passes',0)>0:
        return {'mode':MODE,'revision':REV,'status':'REJECT','issues':['ALREADY_PROCESSED_VOCAL_SOURCE'],
                'next':'RECOVER_UNCONVERTED_VOCAL','files':files}
    if project.get('instrumental_contains_vocals'):
        return {'mode':MODE,'revision':REV,'status':'REJECT','issues':['BAKED_VOCALS_IN_INSTRUMENTAL'],
                'next':'RECOVER_CLEAN_INSTRUMENTAL','files':files}
    if project.get('score_sha256_expected') and project['score_sha256_expected']!=files['score']['sha256']:
        return {'mode':MODE,'revision':REV,'status':'REJECT','issues':['SCORE_REVISION_CHANGED'],
                'next':'REBASE_SCORE_AND_RESET_STALE_GATES','files':files}
    original=project.get('original_asr')
    if original is None:
        return {'mode':MODE,'revision':REV,'status':'NEEDS_EXECUTION',
                'next':'ASR_RAW_GUIDE','files':files,
                'worker':'asr','why':'Cannot select processed voice until source Russian text is tested'}
    if (original.get('audio_sha256')!=files['raw_voice']['sha256'] or
        norm(original.get('text',''))!=norm(project['target_text']) or
        not original.get('recognized') or not original.get('engine')):
        return {'mode':MODE,'revision':REV,'status':'REJECT','issues':['ASR_NOT_BOUND_TO_EXACT_RAW_OR_LYRICS'],
                'next':'ASR_RAW_GUIDE','files':files}
    if original.get('CER',1)>project.get('max_raw_CER',0.1):
        return {'mode':MODE,'revision':REV,'status':'REJECT','issues':['RAW_RUSSIAN_UNINTELLIGIBLE'],
                'next':'FIX_RUSSIAN_PHONEMES_AND_SCORE_UPSTREAM','files':files}
    candidates=project.get('candidates',[])
    if not candidates:
        return {'mode':MODE,'revision':REV,'status':'NEEDS_EXECUTION','next':'RENDER_EXPRESSIVE_SOURCE',
                'worker':'soulx_or_human_performance','files':files,
                'why':'Original lyric is intelligible; improve expressivity without changing phonemes'}
    for c in candidates:
        # Real generated WAV must exist and match its declared SHA; JSON-only success is forbidden.
        cp=(base/c.get('audio','')).resolve() if c.get('audio') else None
        if cp is None or not cp.is_file() or digest(cp)!=c.get('sha256'):
            return {'mode':MODE,'revision':REV,'status':'REJECT',
                    'issues':['CANDIDATE_AUDIO_MISSING_OR_HASH_MISMATCH'],
                    'next':'RECOVER_OR_REGENERATE_ACTUAL_VOCAL','files':files}
        if c.get('input_sha256')!=files['raw_voice']['sha256']:
            return {'mode':MODE,'revision':REV,'status':'REJECT','issues':['CANDIDATE_SOURCE_REVISION_MISMATCH'],
                    'next':'DISCARD_STALE_CANDIDATE','files':files}
        if c.get('voice_identity')!=project.get('voice_identity'):
            return {'mode':MODE,'revision':REV,'status':'REJECT','issues':['VOICE_IDENTITY_DRIFT'],
                    'next':'RENDER_WITH_QUALIFIED_SINGER','files':files}
    source={'id':'raw_guide','CER':original['CER'],'sha256':files['raw_voice']['sha256']}
    adapted=[]
    for c in candidates:
        adapted.append({'id':c['id'],'CER':c.get('CER'),'sha256':c.get('sha256'),
                        'source_sha256':c['input_sha256'],'rvc_passes':c.get('rvc_passes',0),
                        'has_overlap':c.get('has_overlap',False)})
    decision=asr_decision(source,adapted,allow_cer_slack=project.get('max_regression_CER',0.025))
    out={'mode':MODE,'revision':REV,'status':decision['status'],'next':decision['next'],'files':files,
         'lexical_gate':decision,'released':False}
    if decision['status']=='REJECT_ALL':
        # The whole qualified source chain is exhausted for these exact artifacts.
        # Never silently replay SoulX/RVC when the authentic singing reference has expired.
        if project.get('qualified_expressive_reference_available') is False:
            out['next']='RENDER_NEW_EXPRESSIVE_NATIVE_PHRASE'
            out['instruction']='Existing OpenUtau/DiffSinger with verified Russian phonemizer, whole phrase, dynamics/breath/stress; retain intact guide and compare ASR'
            out['recommended_worker']='openutau'
        return out
    if decision['status']!='READY_FOR_ARTISTIC_REVIEW':return out
    approvals=project.get('qualified_review',{})
    accepted=approvals.get('candidate_id')
    if not accepted:return out
    candidate=next((c for c in candidates if c['id']==accepted),None)
    if (not candidate or candidate.get('sha256')!=approvals.get('candidate_sha256') or
        approvals.get('artistic_verdict')!='ACCEPT' or
        approvals.get('vocal_naturalness')!='PASS' or approvals.get('russian_diction')!='PASS' or
        approvals.get('actual_whisper') not in ('PASS','NOT_REQUIRED')):
        out.update(status='REJECT',next='TRUE_VISUAL_QUALIFY_ACTUAL_PERFORMANCE',issues=['HUMAN_REVIEW_INVALID_OR_INCOMPLETE']);return out
    if project.get('audio_qa_gate')!='PASS':
        out.update(status='REJECT',next='RUN_FULL_MIX_AUDIO_QA',issues=['MIX_AUDIO_QA_NOT_PASSED']);return out
    out.update(status='READY_TO_MIX_REVIEW',next='REPRODUCIBLE_SINGLE_STEM_MIX',winner=accepted,released=False)
    return out


def recommend_worker(next_step):
    return {
      'ASR_RAW_GUIDE':('asr','Whisper-small, isolated raw vocal and exact word-level score'),
      'RENDER_EXPRESSIVE_SOURCE':('openutau/soulx','native qualified expressive performance ONCE, not processed/dubbed phonemes'),
      'RESTORE_EXPRESSIVE_SOURCE_NO_EXTRA_RVC':('openutau/soulx','reuse dry source or qualified soulx Human-B prompt; preserve consonants'),
      'FIX_RUSSIAN_PHONEMES_AND_SCORE_UPSTREAM':('openutau/diffsinger','HHSKT Russian phonemizer; entire phrase, contiguous note timing'),
      'TRUE_VISUAL_A_B_LISTENING':('true_visual','A/B lyric, pitch, emotion, breath, identity; inspect actual WAV'),
      'TRUE_VISUAL_QUALIFY_ACTUAL_PERFORMANCE':('true_visual','independent vocal naturalness, actual whisper separately, SHA binding'),
      'RUN_FULL_MIX_AUDIO_QA':('audio_qa','evaluate pitch, riff, masking, groove, sections, no extra vocal'),
      'REPRODUCIBLE_SINGLE_STEM_MIX':('gg_factory','one dry singer and independent music, no baked-master correction')
    }.get(next_step,('recovery','recover exact source/canon or reject unsafe task'))


def execute_local_step(spec_path, state_path, *, permit_effect=False):
    """Execute one declared bounded local worker step. No remote polling or chat loops.
    Explicit allowlist of existing executors; output hashing; refuse dangerous nonlocal effects.
    """
    spec=jread(spec_path);name=spec.get('worker')
    if name not in ALLOWED_WORKERS:raise ValueError('Unqualified worker '+str(name))
    if spec.get('kind')!='local_process':raise ValueError('Remote jobs must checkpoint and return WAIT_EXTERNAL')
    src=[pathlib.Path(p) for p in spec.get('inputs',[])]
    if any(not p.is_file() for p in src):raise FileNotFoundError('Declared inputs missing')
    expected=spec.get('input_sha256',{})
    if any(digest(p)!=expected.get(str(p)) for p in src):raise ValueError('Input hash mismatch; do not run stale worker')
    outs=[pathlib.Path(p) for p in spec.get('outputs',[])]
    if not outs:raise ValueError('No declared outputs')
    identity=hashlib.sha256(json.dumps({'worker':name,'input_sha256':expected,'argv':spec.get('argv'),
                                        'outputs':[str(p) for p in outs],'tool_revision':spec.get('tool_revision'),
                                        'config':spec.get('config',{})},sort_keys=True).encode()).hexdigest()
    ledger=jread(state_path) if pathlib.Path(state_path).is_file() else {'operations':{}}
    prev=ledger['operations'].get(identity)
    if prev:
        if prev.get('status')=='SUCCEEDED' and all(p.is_file() and digest(p)==prev.get('output_sha256',{}).get(str(p)) for p in outs):
            return {'status':'REUSED','effect_id':identity,'outputs':prev['output_sha256']}
        # Outcomes possibly corrupted/unknown. No automatic replay; reconcile manually.
        raise RuntimeError('EFFECT_RECONCILIATION_REQUIRED: prior operation or output hash does not match')
    if not permit_effect:
        return {'status':'DRY_RUN','effect_id':identity,'planned':spec['argv'],'expected_outputs':[str(p) for p in outs]}
    if int(spec.get('timeout_s',60))>180 or int(spec.get('timeout_s',60))<=0:
        raise ValueError('Local step timeout must be between 1 and 180s. Remote work is local WAIT_EXTERNAL.')
    if not spec.get('tool_revision'):
        raise ValueError('Worker tool revision required for reproducibility')
    if not all(isinstance(a,str) for a in spec.get('argv',[])):
        raise ValueError('argv must contain only literal strings')
    cmd=spec['argv']
    if not cmd or pathlib.Path(cmd[0]).name not in ('python','python3','ffmpeg'):
        raise ValueError('Local process binary not allowlisted')
    ledger['operations'][identity]={'status':'RUNNING_OR_UNKNOWN','worker':name,'started_utc':int(time.time()),
                                    'input_sha256':expected,'argv':cmd,'outputs':[str(p) for p in outs]}
    jwrite(state_path,ledger)
    try:
        p=subprocess.run(cmd,timeout=int(spec.get('timeout_s',60)),capture_output=True,text=True,check=False)
        if p.returncode or any(not f.is_file() for f in outs):
            raise RuntimeError('Worker rejected/missing output; code='+str(p.returncode)+' stderr='+p.stderr[-1200:])
        result={str(x):digest(x) for x in outs}
        ledger['operations'][identity].update(status='SUCCEEDED',output_sha256=result,exit_code=0)
        jwrite(state_path,ledger)
        return {'status':'SUCCEEDED','effect_id':identity,'outputs':result}
    except Exception as exc:
        # Do not blindly replay an unknown effect, require reconciliation.
        ledger['operations'][identity].update(status='FAILED_NEEDS_RECONCILIATION',error=str(exc)[:1300])
        jwrite(state_path,ledger)
        raise




def inspect_golden_lineage(registry:dict)->dict:
    """Recovery-first song selection. Review-only variants MUST NOT supersede accepted M3.

    Asset refs are metadata; no fake audio audition or acceptance is inferred from links.
    """
    nodes=registry.get('lineage')
    if not isinstance(nodes,list) or not nodes:
        return {'status':'BLOCKED','reason':'LINEAGE_MISSING'}
    idmap={n.get('id'):n for n in nodes if isinstance(n,dict)}
    if len(idmap)!=len(nodes):return {'status':'BLOCKED','reason':'DUPLICATE_OR_INVALID_NODE'}
    golden=registry.get('golden_reference')
    if golden not in idmap:return {'status':'BLOCKED','reason':'GOLDEN_REFERENCE_MISSING'}
    if registry.get('constraints',{}).get('no_replacement_v3_1_by_unapproved_later_mixes') is not True:
        return {'status':'BLOCKED','reason':'ACCEPTANCE_POLICY_MISSING'}
    admissible={'LISTENER_PASS_GAIN_ONLY','LISTENER_QA_PASS'}
    original=idmap[golden]
    if original.get('status') not in admissible:
        return {'status':'BLOCKED','reason':'GOLDEN_NOT_LISTENER_QUALIFIED'}
    if not original.get('asset_id'):
        return {'status':'BLOCKED','reason':'GOLDEN_ASSET_MISSING'}
    ancestors=set();stack=list(original.get('parents',[]))
    while stack:
        k=stack.pop()
        if k in ancestors:continue
        if k not in idmap:return {'status':'BLOCKED','reason':'GOLDEN_PARENT_MISSING','node':k}
        ancestors.add(k);stack.extend(idmap[k].get('parents',[]))
    if 'V3_M3' not in ancestors or 'V3_VOCAL' not in ancestors or 'INSTRUMENTAL_REAL_V2' not in ancestors:
        return {'status':'BLOCKED','reason':'GOLDEN_SONG_LINEAGE_UNVERIFIED'}
    unsafe=[{'id':n['id'],'status':n['status']} for n in nodes if n['id']!=golden and
             n.get('kind') in ('review_master','vocal') and n.get('status') in
             ('INTERNAL_UNAPPROVED','INTERNAL_LOCAL_REPAIR','PENDING_USER_ARTISTIC_REVIEW',
              'REVIEW_NO_FINAL_ARTISTIC_ACCEPT')]
    return {'status':'GOLDEN_BASELINE_RECOVERED','reference':golden,
            'asset_id':original['asset_id'],'parents':sorted(ancestors),
            'quarantined_candidates':unsafe,'decision':'PRESERVE_GOLDEN_BASELINE',
            'allowed_next':'COMPARE_LATER_CANDIDATES_AT_MATCHED_LEVEL_WITH_LISTENING',
            'released_new_song':False}

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    sub=ap.add_subparsers(dest='action',required=True)
    p=sub.add_parser('plan');p.add_argument('project');p.add_argument('--out')
    g=sub.add_parser('golden');g.add_argument('lineage');g.add_argument('--out')
    v=sub.add_parser('step');v.add_argument('spec');v.add_argument('--state',required=True);v.add_argument('--execute',action='store_true')
    a=ap.parse_args()
    if a.action=='plan':
        project=jread(a.project);answer=evaluate(project,pathlib.Path(a.project).resolve().parent)
        worker,details=recommend_worker(answer['next'])
        answer.update(recommended_worker=worker,instruction=details)
        if a.out:jwrite(a.out,answer)
        print(json.dumps(answer,ensure_ascii=False,indent=2))
        return 0 if answer['status'] in ('READY_TO_MIX_REVIEW','READY_FOR_ARTISTIC_REVIEW') else 2
    if a.action=='golden':
        result=inspect_golden_lineage(jread(a.lineage))
        if a.out:jwrite(a.out,result)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0 if result['status']=='GOLDEN_BASELINE_RECOVERED' else 2
    if a.action=='step':
        x=execute_local_step(a.spec,a.state,permit_effect=a.execute)
        print(json.dumps(x,ensure_ascii=False,indent=2));return 0
if __name__=='__main__':
    try:sys.exit(main())
    except Exception as e:
        print('HUMAN_VOCAL_MODE_FAIL:',e,file=sys.stderr);sys.exit(2)