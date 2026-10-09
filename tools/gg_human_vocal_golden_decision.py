#!/usr/bin/env python3
"""Evidence-scoped vocal production decision map. This is not a generator.
Distinguishes earlier Awata C/D audition from later listener accepted V3/M3 song.
"""
import argparse,json,pathlib,re
ROOT=pathlib.Path(__file__).parent
RELEASE_STATES={'LISTENER_QA_PASS','LISTENER_PASS_GAIN_ONLY'}
LOCKED={'V3_M3':'b407aae9-c54e-4d40-84b8-10954314d794','V3_1':'bdc8326b-2b01-4961-bf6d-4411edf91bd5'}
def clean(text):return ' '.join(re.sub(r'[^а-я0-9 ]',' ',text.lower().replace('ё','е')).split())

def choose_technically(transcripts, target, require_exact=True):
    rows=[r for r in transcripts if r['file'] in {'C_FCPE_IDX030.wav','D_FCPE_IDX050.wav'}]
    target_clean=clean(target)
    if not target_clean:raise ValueError('A nonempty explicit canonical lyric is required')
    elig=[r for r in rows if (clean(r.get('transcript',''))==target_clean if require_exact else r.get('CER',1)<=0.02)]
    if not elig:return {'status':'NO_LEXICALLY_VALID_RVC','next':'REPAIR_EXPRESSIVE_SOURCE','eligible':[]}
    first=next((r for r in elig if r['file'].startswith('C_')),elig[0])
    return {'status':'TECHNICAL_TEXT_GATE_ONLY','selected_for_listening':first['file'],'eligible':[r['file'] for r in elig], 'needs_listener_verdict':True, 'must_not_premix':True}

def preserve_master(lineage,choice_id):
    items={x['id']:x for x in lineage}
    if choice_id not in items:raise ValueError('Unknown candidate')
    chosen=items[choice_id]
    accepted=(choice_id in LOCKED and chosen.get('status') in RELEASE_STATES
              and chosen.get('asset_id')==LOCKED.get(choice_id)
              and (choice_id=='V3_M3' or chosen.get('parents')==['V3_M3']))
    return {'selected':choice_id,'historical_status':chosen.get('status'),'golden_reference':'V3_1','preserve_original':True,'release_eligible_by_existing_listener_evidence':accepted,'may_modify_canonical_song':False,'next':'HUMAN_COMPARATIVE_LISTENING' if not accepted else 'PRESERVE_GOLDEN_MASTER'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--song-selection',default='V3_1');p.add_argument('--out',default=str(ROOT/'results'/'GOLDEN_ROUTE_DECISION.json'));args=p.parse_args()
    report=json.loads((ROOT/'results'/'GOLDEN_TECHNICAL_AUDIT.json').read_text())
    lineage=json.loads((ROOT/'accepted_route'/'GOLDEN_LINEAGE.json').read_text())
    cd=choose_technically(report['replayed_cd_audition']['independent_transcript'], 'я говорил не с ним а с тем кто долго стоял у окна и ждал')
    master=preserve_master(lineage['lineage'],args.song_selection)
    out={'route':'GG Human Vocal v0.4','original_cd_dry_audition':cd,'song_master':master,'priority':'recover expressive source and exact V3 surgical edits before any fresh song claim','future_true_sound_contract':{'input':'lyric, score, emotion arc, dry stems, permitted voice profile','output':'audition candidates with exact provenance and review status','must_not':'use baked master as music-only bed; double RVC; rewrite accepted phrases; auto-call technical PASS artistic PASS'},'outcome':'GOLDEN_REFERENCE_REPRODUCTION_PARTIAL_NOT_NEW_SONG_NORTHSTAR'}
    pathlib.Path(args.out).write_text(json.dumps(out,ensure_ascii=False,indent=2))
    print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__':main()