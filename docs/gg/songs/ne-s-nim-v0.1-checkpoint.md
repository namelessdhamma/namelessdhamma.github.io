# GG — «Не с ним» — Full Song Production Checkpoint v0.1

Date: 2026-10-06
Status: **FULL SONG RENDERED / TECHNICAL PASS / HUMAN ARTISTIC GATE OPEN**

This is the first complete song render from the new GG vocal North Star route. It is **not yet canonized as final** until the user listens to the full arrangement and vocal in context.

## Source text and preparation

- Literary master: user's Russian text preserved in `docs/gg/songs/ne-s-nim-production-plan.md`.
- Vocal input: separate bounded phonetic spelling layer with explicit stress notation in the production plan.
- Synthesis implementation uses the OpenUtau DiffSinger Russian phonemizer and the phonetic word forms prepared for this song.

## Composition

- Title: «Не с ним»
- Key: A minor
- Tempo: 108 BPM
- Meter: 4/4
- Core percussion gene: 3+3+2 eighth-note accent cycle
- Form length: 88 bars
- Master duration: 200.556 s (~3:20.6)
- Genre hierarchy: progressive rock ballad → dark folk → restrained doom / psychedelic transformation

Form:
1. 8-bar intro
2. 16-bar verse I
3. 8-bar chorus
4. 4-bar post-chorus
5. 8-bar verse II
6. 8-bar chorus
7. 8-bar bridge
8. 12-bar instrumental development / drum-led solo
9. 8-bar final
10. 4-bar coda
11. 4-bar outro

## Instrumental architecture

10 separately rendered stems:
- drums
- percussion
- bass
- guitar left
- guitar right
- acoustic guitar
- organ
- strings
- lead guitar
- piano

Qualified arrangement:
- workflow run: `37408343048`
- artifact: `11388670253`
- duration: 200.556 s
- sample rate: 48 kHz
- peak: 0.8967
- no clipping
- persistent Library copy: `/ND/GG/Songs/Ne-S-Nim/2026-10-06/gg-ne-s-nim-arrangement.zip`

## Vocal architecture

OpenUtau/DiffSinger Russian guide → Applio RVC North Star.

Guide:
- full song OpenUtau/Awata guide render PASS
- guide source run: `37409292206`
- guide artifact: `11388517371`

Applio:
- pinned commit: `324f4d89c3e0e8dc0e555a3d53784e3282c16e09`
- model: `awata-weak-rvc-v1.2`
- variant: Original
- F0 method: FCPE
- pitch: 0
- protect: 0.5
- autotune: OFF
- cleaning: OFF
- formant shift: OFF
- decorative RVC post-FX: OFF

### C
- index_rate: 0.30
- post-vocal job: PASS
- master job: PASS
- QC: PASS
- artifact: `11388777890`
- final master duration: 200.556 s
- final peak: -1.0 dBFS
- mean level: approximately -16.7 dBFS
- MP3 SHA256: `9f67ea75e260564b1fe5931979339efd527d61a2cbba24ac3ffdc98c0e51eba9`

### D
- index_rate: 0.50
- post-vocal job: PASS
- master job: PASS
- QC: PASS
- artifact: `11389175686`
- final master duration: 200.556 s
- final peak: -1.0 dBFS
- mean level: approximately -16.8 dBFS
- MP3 SHA256: `925afb77e50a74ac067d7ecfbdc8b1481743a5b621c389aa585a7d93dfe7a0ec`

Parallel post-vocal workflow:
- run: `37410166944`
- both matrix jobs SUCCESS.

## Durable listening package

Library folder:
`/ND/GG/Songs/Ne-S-Nim/2026-10-06/`

Files:
- `NE_S_NIM_v0.1_LISTENING_PACKAGE.zip`
- `NE_S_NIM_C_FCPE_IDX030.mp3`
- `NE_S_NIM_D_FCPE_IDX050.mp3`
- `NE_S_NIM_INSTRUMENTAL.mp3`
- SHA256 manifest

Listening package SHA256:
`901eab1a6dd1de11e5c4d5fee02fd8a7a0a7564e8149de3939e16607a03f4e71`

## Recovery rule

Do not restart songwriting, tool research, or vocal qualification from scratch.

The next pass must begin from this v0.1 checkpoint and be driven by **human listening defects**, categorized separately:
1. composition/form,
2. drums/percussion,
3. guitars/bass/instrument colors,
4. vocal melody/prosody,
5. lyric diction/phonetics,
6. C vs D timbre,
7. balance/mix/master.

Only change the smallest layer responsible for an audible defect. Preserve the remaining accepted layers.
