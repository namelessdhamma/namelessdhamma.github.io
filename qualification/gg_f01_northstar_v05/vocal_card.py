#!/usr/bin/env python3
"""Executable decision card for persistent GG singer identity; no provider inference or release promotion."""
from __future__ import annotations
import json, argparse, pathlib
ROOT=pathlib.Path(__file__).parent
PROFILE=ROOT/'SINGER_F01_PROFILE.json'
def decide(event, profile=None):
 p=profile or json.loads(PROFILE.read_text())
 assert p['north_star'] and p['strict_song_duration_target'] is None
 if event.get('selected_identity') not in (None,p['voice_identity']['preferred_singer']):
  return {'status':'REJECT','next':'KEEP_GG_VFS_F01_OR_REQUEST_NEW_ARTISTIC_VOICE_QUALIFICATION','reason':'VOICE_IDENTITY_DRIFT'}
 if not event.get('source_rights_cleared',False):
  return {'status':'BLOCK','next':'VERIFY_SINGER_BANK_RVC_AND_PROMPT_AI_INPUT_LICENSES','reason':'MIMOSA_HISTORICAL_SOURCE_NOT_LICENSED_FOR_AUTOMATIC_SOULX_REUSE'}
 if not event.get('score_and_lyrics_verified'):
  return {'status':'BLOCK','next':'VERIFY_SCORE_RU_PHONEMES_AND_SYLLABLE_TIMING'}
 if not event.get('single_singer_isolated_vocal'):
  return {'status':'BLOCK','next':'RENDER_ONE_CONTINUOUS_PHRASE_FROM_OPENUTAU_DIFFSINGER'}
 if not event.get('source_lexical_pass'):
  return {'status':'REJECT','next':'UPSTREAM_NATIVE_RU_PHONEME_OR_NOTE_TIMING_REPAIR','reason':'DO_NOT_USE_RVC_TO_REPAIR_MISSING_WORD'}
 if not event.get('source_sings_melody'):
  return {'status':'REJECT','next':'RENDER_EXPRESSIVE_NOTED_PERFORMANCE_NOT_TTS'}
 if not event.get('expressive_source_qualified'):
  return {'status':'REVIEW','next':'COMPARE_NATIVE_EXPRESSIVE_SOURCE_TO_FROZEN_V3_REFERENCE'}
 if event.get('post_rvc_passes',0)>0 and event.get('wants_rvc'):
  return {'status':'BLOCK','next':'PRESERVE_ORIGINAL_DO_NOT_DOUBLE_RVC'}
 if event.get('needs_actual_whisper') and not event.get('verified_actual_whisper'):
  return {'status':'REVIEW','next':'REAL_PHYSIOLOGICAL_WHISPER_TO_SINGING_SOURCE_REQUIRED','reason':'GAIN_ENVELOPE_NOT_WHISPER'}
 if event.get('wants_rvc'):
  return {'status':'TRIAL','next':'APPLIO_AWATA_ORIGINAL_C_D_ONE_PASS_LEVEL_MATCHED_AB_TEST'}
 if not event.get('modified_candidate_lexical_pass'):
  return {'status':'REVIEW','next':'INDEPENDENT_RUSSIAN_ASR_ON_ACTUAL_MODIFIED_WAV'}
 if not event.get('passed_perceptual_comparison'):
  return {'status':'REVIEW','next':'LISTEN_PHRASE_FOR_NATURALNESS_EMOTION_BREATH_AND_VOICE_ID'}
 if not event.get('has_independent_backing'):
  return {'status':'BLOCK','next':'RECOVER_UNMIXED_BACKING_NOT_ALREADY_VOICED_MASTER'}
 if not event.get('human_accepted'):
  return {'status':'REVIEW','next':'RENDER_ONE_SINGER_PLUS_BACKING_FOR_HUMAN_ARTISTIC_REVIEW'}
 return {'status':'ARTISTICALLY_APPROVED_BY_HUMAN','next':'PRESERVE_IMMUTABLE_WAV_PLUS_HASH_AND_EXACT_RECIPE'}
def main():
 a=argparse.ArgumentParser();a.add_argument('event');a.add_argument('--out');p=a.parse_args();e=json.loads(pathlib.Path(p.event).read_text());r=decide(e)
 print(json.dumps(r,ensure_ascii=False,indent=2))
 if p.out:pathlib.Path(p.out).write_text(json.dumps(r,ensure_ascii=False,indent=2))
if __name__=='__main__':main()