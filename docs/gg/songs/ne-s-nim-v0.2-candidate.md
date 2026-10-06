# GG — «Не с ним» — Vocal Prosody Candidate v0.2

Date: 2026-10-06
Status: **TECHNICAL PASS / HUMAN LISTENING GATE OPEN / NOT CANONIZED**

## Why v0.2 exists

v0.1 was rejected by the user despite the near-human D timbre:
- syllables were nearly continuous,
- vocal phrases did not read as musical phrases,
- whole multisyllabic words were effectively forced onto single pitch events,
- blanket pseudo-phonetic spelling sounded unnatural.

## Frozen layers

- backing/arrangement: v0.1, run `37408343048`
- vocal timbre route: D only
- Awata Weak RVC v1.2 / Original
- FCPE
- index_rate = 0.50
- pitch = 0
- protect = 0.5

## v0.2 changes

Pronunciation:
- ordinary Russian spelling,
- only stressed vowel capitalized,
- no blanket о→а / что→што / -тся→-цца rewriting.

Musical prosody:
- explicit phrase rests and breath markers,
- different durations for unstressed/stressed syllables,
- multisyllabic words distributed across multiple notes,
- phrase-final held notes/melismas,
- verse/chorus/bridge/final/coda use different melodic contours,
- chorus/final get register lift,
- coda descends and contracts.

Headless OpenUtau harness was fixed so extender notes are grouped with their leading lexical note before Russian phonemization.

## Technical results

Workflow:
- `GG Ne S Nim Vocal Prosody v0.2`
- run: `37412144215`
- conclusion: SUCCESS

Artifacts:
- guide: `11390290192`
- final D candidate: `11389289927`

Audio:
- guide duration: 186.184 s
- full master duration: 200.556 s
- final master MP3 SHA256: `f91016089d017151f333ef7e407164ab8e60bab8ae06ad5a1f8e0d92c0abe085`
- isolated D vocal SHA256: `4f97830031202bd82825d23764cf24fc5ec30e5b74018a3247089e533c43544f`
- package SHA256: `ab870a2fbb569964ee6a91b8a2bcdf257d982592397c01ac3cae987a775bf118`

## Objective pause comparison vs v0.1 isolated D vocal

50 ms RMS-window diagnostic, -45 dBFS silence threshold, inside the active vocal span:
- v0.1: silence ratio ≈ 27.6%; 31 silence runs >=150 ms; median such run ≈ 0.35 s.
- v0.2: silence ratio ≈ 37.2%; 49 silence runs >=150 ms; median such run ≈ 0.50 s.

This verifies that v0.2 actually introduces materially more breathing space and phrase separation; it does NOT prove musical quality.

## Human gate

Do not canonize v0.2 until listening answers:
1. Is it now perceived as singing rather than syllable sequencing?
2. Are words intelligible?
3. Are phrase entries/exits musical against the frozen backing?
4. Are pauses/breaths believable?
5. Does the chorus lift?
6. Does D retain the near-human timbre?

If rejected, mutate the smallest vocal-score layer responsible. Do not reopen backing or model research without direct evidence.
