#!/usr/bin/env python3
"""From true approved GG D1 score to expression-aware one-voice first-line events.

Not a rendered singer. Describes repeatable musical source and semantic emphasis
without flattening the actual note contour or applying arbitrary pitch jitter.
"""
from __future__ import annotations
import json,pathlib
R=pathlib.Path(__file__).parent

def compile_plan(score):
    p=score['phrase'];tpb=int(score['ticks_per_beat']);beat_sec=60/float(score['bpm'])
    tick=p['bar']*4*tpb+p['offset'];segments=[];word_map=[]
    for word in p['words']:
        start=tick
        for i,(pitch,dur) in enumerate(zip(word['pitches'],word['durations'])):
            segments.append({'word':word['text'],'midi_pitch':pitch,
                'start_seconds':round(tick/tpb*beat_sec,6),
                'duration_seconds':round(dur/tpb*beat_sec,6),
                'linguistic_stress_note':i==word['stress']})
            tick+=dur
        word_map.append({'word':word['text'],'start_seconds':round(start/tpb*beat_sec,6),
             'end_seconds':round(tick/tpb*beat_sec,6)})
        tick+=word.get('rest',0)
    return {
       'source_git_blob_sha':score['authority']['source_git_blob_sha'],
       'source_version':score['authority']['revision'],
       'line':' '.join(x['word'] for x in word_map),
       'vocal_identity':'GG-VFS-F01',
       'one_continuous_singer_performance':True,
       'performance_design_status':'AUTHORITATIVE_NOTES_WITH_NONAUTHORITATIVE_ARTISTIC_EXPRESSION_HYPOTHESIS',
       'midi_events':segments,
       'word_map':word_map,
       'semantic_focus':[{'word':'тобой','meaning':'recognition, personal emotional focus','expression_types':['subtle_anticipation','dynamic_support_without_consonant_masking']},
           {'word':'видятся','meaning':'dreamlike unfolding','expression_types':['legato','unforced_connected_vowels']},
           {'word':'сне','meaning':'song identity fully formed','expression_types':['stable_resonance','end_phrase_release']}],
       'note_range':[min(x['midi_pitch'] for x in segments),max(x['midi_pitch'] for x in segments)],
       'requires_real_whisper_onset':True,
       'actual_whisper_source_qualified':False,
       'note_source_is_flattened':len(set(x['midi_pitch'] for x in segments))<3,
       'required_audio_gate':'actual sung F01 voice + same-voice continuity + independent Russian ASR + listening'}

if __name__=='__main__':
 q=json.loads((R/'FIRST_LINE_D1_FULL_V3_AUTHENTIC.json').read_text())
 p=compile_plan(q)
 assert not p['note_source_is_flattened']
 out=R/'FIRST_LINE_PERFORMANCE_PLAN.json';out.write_text(json.dumps(p,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'notes':len(p['midi_events']),'range':p['note_range'],'start':p['word_map'][0]['start_seconds'],'end':p['word_map'][-1]['end_seconds']},ensure_ascii=False))