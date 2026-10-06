# GG — «Не с ним» — REBUILD A candidate checkpoint

Date: 2026-10-06
Status: **CLEAN REBUILD COMPLETE / TECHNICAL PASS / HUMAN LISTENING GATE OPEN**

This candidate is not an edit of v0.1/v0.2. It was rebuilt from the clean literary lyrics.

## Clean lyric rule
The Russian phonemizer input contains normal Russian spelling only.
No pseudo-phonetic substitutions.
No capital-letter stress encoding inside lyrics.
Stress is stored separately in the score as a syllable index and influences musical duration/emphasis.

## Form
- 108 BPM
- A minor
- 110 bars
- final duration: 249.444 s
- 10 rebuilt instrumental stems

Long textual lines use three-bar slots.
Chorus lines use two bars.
Verse/bridge/final lines deliberately leave a large response window after the sung phrase.

Static score audit:
- long-line free space after authored phrase: ~1,335–2,850 ticks per 3-bar slot
- no continuous line-slot filling

## Vocal score
Every line was authored with:
- explicit word duration for every word,
- explicit rest-after for every word,
- explicit stress-syllable index,
- grouped OpenUtau extender notes for multisyllabic words,
- section-specific stable song motifs.

Removed:
- vowel-count-derived word duration,
- word-index pitch cycling,
- pseudo-phonetic spelling,
- v0.1/v0.2 score inheritance.

## Timbre
D route only:
- Awata Weak RVC v1.2 / Original
- FCPE
- index_rate 0.50
- pitch 0
- protect 0.5
- no autotune / cleaning / formant shift / decorative RVC FX

## Arrangement
New arrangement built specifically around the new vocal timing:
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

Third bars in long-line sections function as ensemble replies, especially drums + lead guitar.

Arrangement QC:
- 249.444 s
- 48 kHz
- 10 stems
- peak 0.900721
- no clipping

## Workflow
Primary rebuild run:
- 37414332821
- arrangement: SUCCESS
- clean-text guide: SUCCESS
- D North Star: SUCCESS
- original master subjob failed only because ffmpeg was absent on the separate master runner

Master-only recovery:
- run 37415350665
- SUCCESS
- reused preserved arrangement/vocal artifacts; no re-render

Artifacts:
- arrangement: 11390347669
- vocal: 11391007225
- final master: 11390609186

Final master:
- duration 249.444 s
- MP3 SHA256: 2820b6ac32477251bacf39fcc5aff20448309e533170af7095b53f86e0e63d11

Listening package SHA256:
- d6ad14ea4ba95311928d031f0b07ed99e93d4f1f183d28a770e54fcb1a219261

## Objective spacing diagnostic
New isolated D vocal:
- duration 232.5 s
- within active vocal sections, silence ratio ~40%
- whole active span silence ratio ~50%
- median silence run >=150 ms ~2.4 s

For comparison, v0.2 whole active span silence ratio was ~37% and median >=150 ms silence ~0.5 s.
This only verifies structural change; it does not prove musical quality.

## Durable Library
Folder:
`/ND/GG/Songs/Ne-S-Nim/Rebuild-A-2026-10-06/`

Includes:
- NE_S_NIM_REBUILD_A_MASTER.mp3
- D_REBUILD_A_FCPE_IDX050.wav
- 00_GUIDE_REBUILD_A.wav
- NE_S_NIM_REBUILD_A_INSTRUMENTAL.mp3
- NE_S_NIM_REBUILD_A_LISTENING_PACKAGE.zip
- SHA256 manifest

## Gate
Do not canonize until user listening.
If rejected, diagnose this rebuild on musical grounds rather than resuming v0.1/v0.2 incremental edits.
