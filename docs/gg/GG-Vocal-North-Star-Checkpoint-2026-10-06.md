# GG Vocal North Star Checkpoint — 2026-10-06

Status: **CANONICAL / SERIOUS CHECKPOINT**

This checkpoint preserves the first GG vocal route the user judged to be practically indistinguishable from human singing and very close to the GG Vocal North Star.

## Human qualification

- All four Applio/Awata A/B variants were much better than the prior SoulX source.
- **C and D are co-leaders.**
- Do not silently choose one over the other without later listening evidence.
- User judgment: C and D are already very close to North Star and practically indistinguishable from human vocal.

## Canonical architecture

1. OpenUtau / DiffSinger = Russian score, lyric and phoneme authority.
2. Preserve a dry upstream vocal source.
3. Applio RVC `vocal_mutate` = downstream timbre/articulation/low-register/machine-halo repair layer.
4. Level-matched A/B listening = artistic qualification.

Missing/swallowed words must be repaired upstream. Applio is not the lyric generator.

## Qualified runtime

- Applio repository: `IAHispano/Applio`
- pinned commit: `324f4d89c3e0e8dc0e555a3d53784e3282c16e09`
- production operation: `vocal_mutate`
- relay version: `0.3.0`
- Render live deploy: `dep-db24hfui0phs73d8v4n0`

Production snapshots:
- worker branch: `gg/cloud-music-worker-v1`
- `tools/gg_cloud_music_worker.py` blob: `39a5fdbc602f03f0ffdefea95063ec1e90cb259c`
- `.github/workflows/gg-cloud-music-worker.yml` blob: `8ea9a24a4c76613fbb4b63cd54323c88e2b05e5a`
- studio branch: `gg/cloud-music-studio-v1`
- `render/gg-cloud-music-studio/server.mjs` blob: `e4c92ad38c14e23cf34c8695fc3e0cb475094048`

## Target model

Official Awata Weak RVC v1.2:
- catalog id: `awata-weak-rvc-v1.2`
- canonical variant for this checkpoint: `Original`
- archive also contains and was qualified with Soft, Cute and Whisper.
- all four .pth/.index pairs were accepted by pinned Applio.

## Canonical source

`SoulX_NorthStar_Candidate.wav`
- GitHub Actions run: `37248278728`
- artifact ID: `11320200372`
- artifact name: `gg-soulx-northstar-candidate`

Keep the source unchanged for A/B reference.

## First successful real A/B

- run: `37399761983`
- job: `112064086699`
- result: **SUCCESS**
- artifact ID: `11384609702`
- artifact name: `gg-applio-awata-ab`

Common controls:
- model = Awata Weak RVC v1.2 / Original
- pitch = 0
- protect = 0.5
- volume_envelope = 1.0
- autotune OFF
- cleaning OFF
- formant shift OFF
- post processing OFF
- reverb/chorus/distortion/delay and other decorative FX OFF

Raw Applio output was about 6.4 dB louder than source, so future A/B qualification must be **level-matched**.

## C — North-Star co-leader

`C_FCPE_IDX030`
- `f0_method = fcpe`
- `index_rate = 0.30`
- `protect = 0.5`
- `pitch = 0`
- no decorative post-FX

Listening pair:
`PAIR_SOURCE_vs_C_FCPE_IDX030_LEVEL_MATCHED.wav`

## D — North-Star co-leader

`D_FCPE_IDX050`
- `f0_method = fcpe`
- `index_rate = 0.50`
- `protect = 0.5`
- `pitch = 0`
- no decorative post-FX

Listening pair:
`PAIR_SOURCE_vs_D_FCPE_IDX050_LEVEL_MATCHED.wav`

## Reproduction rule

For a new GG vocal with correct words/phonemes but machine coloration:

1. Fix lyric/pitch/phonemes upstream.
2. Preserve the dry source.
3. Run `vocal_mutate` with `model_id=awata-weak-rvc-v1.2`, `model_variant=Original`, pitch 0, protect 0.5.
4. Render at minimum:
   - C = FCPE + index 0.30
   - D = FCPE + index 0.50
5. Level-match against the dry source.
6. Compare source → silence → candidate.
7. If a defect is local, mutate only a bounded segment with context/crossfade.
8. If lexical content is missing, repair upstream rather than with RVC.

## Current default

**Default next attempt = C and D. Do not reopen broad tool/model research.**

Only reopen broad exploration if C/D fail on a materially different vocal case. The next frontier is local:
- C vs D per phrase/segment,
- bounded segment repair,
- small FCPE index sweep within 0.30–0.50,
- cleaning/formant controls only for a specific remaining defect.

## Durable artifact checkpoint

Persistent Library path:
`/ND/GG/Checkpoints/2026-10-06/`

Contains:
- `GG-Vocal-North-Star-Checkpoint-2026-10-06.md`
- `GG-Applio-Awata-A-B-listening-pack.zip`
- C level-matched pair
- D level-matched pair

Checkpoint file SHA-256:
`8c24af4262432cd3c7ebb4c3ee38ba0e5e4b2c6cd3ea753e90c3928309314838`

Listening pack SHA-256:
`adc65d3a794ade058266567e7863966d12b8c74b85f582e3b763a826f0158be6`

Do not overwrite this checkpoint. Create a successor only after a new result is audibly and reproducibly better.
