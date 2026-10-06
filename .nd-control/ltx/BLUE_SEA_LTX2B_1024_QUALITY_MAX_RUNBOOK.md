# A8 / R01 — Kaggle LTX 2B 1024×576 Quality-Max Fast Path

Status: USER-ACCEPTED QUALITY IMPROVEMENT
Date: 2026-10-06
Route: kaggle_ltx2b_direct_f2l
Cost policy: FREE_ONLY

## Purpose

Reproduce the high-detail Blue Sea 2-second LTX shot without repeating the historical recovery/debug cycle.

The accepted improvement was produced by running the existing LTX 2B 0.9.6 Distilled BF16 route at true 1024×576 and enabling tiled VAE decode on Kaggle T4.

## Golden result

- request_id: `k2b-r195f49021100-f1aa-v1`
- effect_id: `ltx2b:195f49021100f1aa1a61ba0260ff158a3862fd715d87455d472777be8e41f046`
- route: `kaggle_ltx2b_direct_f2l`
- model: `multimodalart/ltxv-2b-0.9.6-distilled:transformer/diffusion_pytorch_model.bf16.safetensors`
- precision: BF16
- profile: `VerylowRAM_LowVRAM_DIRECT`
- requested/output size: 1024×576
- frames: 57
- fps: 28
- duration: 2.0357142857142856 s
- seed: 42
- endpoint_order_pass: true
- generation_seconds: 181.703
- MP4 size: 9,683,207 bytes
- MP4 sha256: `0368bb244864af76ff686dffc254af312a9aaa1bb8f8f980a03bc62d7b8b5715`
- Wan2GP commit observed at runtime: `2345ae148f82740f66e82c41292dbbdd592e713d`

User review: substantially better than the previous 768-detail render; preserve this route as the default quality baseline for this shot family.

## Exact input anchors

F01:
`https://cdn.creativeclaw.co/u/3ce53768/images/382ecc95-cb75-4b41-b39c-47a7d53c10d1.jpg`

F09:
`https://cdn.creativeclaw.co/u/3ce53768/images/84110699-a0f7-4529-815f-a954a274541c.jpg`

Use HTTPS CDN anchors. Do NOT restart work on the missing `ND_LTX_INPUT_TOKEN` Drive transport unless CDN anchors cease to work.

## Exact prompt

One continuous ~2-second cinematic sword-fight shot on a storm-soaked pirate deck. Preserve the exact two adult pirate identities, costumes, wet-hair structure, faces, body proportions, blades, ship geometry, lantern lighting and realistic game-cinematic/film-still rendering of the supplied first and last keyframes. The dark-haired swordsman on the left drives a controlled forward attack while the red-haired opponent on the right reacts defensively; arms, legs, hands and blade trajectories evolve continuously and physically. Rain, spray, wet cloth, hair and background crew move independently. Preserve sharp micro-detail in skin, hair strands, wet fabric, leather, metal, wood and water droplets. No style drift, no cut, no camera discontinuity.

## Exact negative prompt

cartoon, anime, illustration, painting, painterly, stylized, plastic, waxy, toy-like, blurry, soft focus, low detail, smeared texture, over-smoothed skin, face morph, identity drift, distorted anatomy, extra limbs, duplicate subjects, fused hands, bent sword, jitter, sudden cut, text, watermark

## Required worker configuration

The working quality-max worker commit is:

`5c1757f83f2580e800cfd1e8c9804bcb23d46b43`

Key differences from the old stable 768 worker:

1. resolution cap increased from approximately 768×448 to 1024×576;
2. H.264 output quality increased from imageio quality 7 to 9;
3. for resolutions above the former 768-class envelope, VAE decode uses:
   - `vae.enable_z_tiling(4)`
   - `vae.enable_hw_tiling()`
   - `vae.set_tiling_params(sample_size=512, overlap_factor=0.25)`
4. expected diagnostic line:
   `ND_LTX2B_VAE_TILING=z4_hw512`

The reserve core was pinned to that worker in commit:

`2b9ace1053b36da2e86fda5741aca4e2fcccd77b`

Before a future submit, verify CURRENT `vercel/nd-kaggle-ltx-reserve/lib/ltx-core.js` still points to a worker containing the same or newer qualified 1024 + tiled-decode behavior. Do not blindly restore an old commit if CURRENT has superseded it.

## Fast execution procedure

1. Fetch CURRENT `.nd-control/ltx/request.json` and its SHA.
2. Verify there is no already-running equivalent effect from A8.
3. Verify worker route has:
   - 1024×576 allowed,
   - VAE z4 + hw512 tiling for high resolution.
4. Copy `.nd-control/ltx/presets/blue-sea-ltx2b-qualitymax-1024.json`.
5. Change only:
   - `nonce`
   - `idempotency_key`
   when a genuinely new effect is wanted.
6. CAS-write the submit request to `.nd-control/ltx/request.json`.
7. Let `.github/workflows/nd-kaggle-ltx-reserve.yml` submit the effect.
8. Do not spam status polls. The accepted run spent ~182 s in generation plus runtime setup/decode. A useful first provider status read is after roughly 2–3 minutes; further reads should respect `next_check_after_seconds`.
9. On COMPLETED, write one `op: result` request and download artifact `nd-kaggle-ltx-reserve-result`.
10. Validate:
   - width 1024
   - height 576
   - frames 57
   - fps 28
   - duration >= 2.0 s
   - endpoint_order_pass = true
   - H.264 MP4 exists
11. Present MP4 to user. Do not run cold reproduction or route research first unless the route has actually changed.

## Known traps — do not repeat

### Trap 1: false 1024 test caused by stale worker pin

Changing the worker on main is NOT sufficient. `ltx-core.js` previously hard-pinned worker commit `2ef1d79f198afc45febb4c42d3ddea7b35898e7c`. A supposed 1024 test therefore silently ran the old worker and returned 768×416.

Preflight must verify the actual pinned worker.

### Trap 2: untiled 1024 VAE decode OOM

True 1024×576 diffusion completed, but untiled final VAE decode failed:
- Kaggle T4 total ~14.56 GiB
- decoder attempted a ~13.53 GiB allocation.

This is not a transformer/LTX resolution failure. The fix is tiled VAE decode, not reducing resolution.

### Trap 3: retry_terminal/idempotency dispatcher edge case

Attempting to retry the same terminal effect produced:
`Kaggle idempotency conflict: existing kernel has no version`

For a changed worker configuration, create a new idempotency key/effect rather than spending time repairing the dispatcher unless dispatcher repair is itself the task.

### Trap 4: split F01→F05 + F05→F09 is not the default quality route

The first half looked sharper, but the second half was softer; the combined two-segment result was not better overall than the single quality render. Do not default to split-segment assembly for quality.

### Trap 5: do not re-research setup

Already closed:
- model import/bootstrap
- MMGP route
- BF16 transformer
- 57@28 duration lattice
- endpoint-order validation
- CDN transport
- GitHub reserve control
- T4 viability.

Start from this runbook and CURRENT state.

## Next quality frontier

This checkpoint is the fast baseline, not necessarily the absolute ceiling. If quality work resumes, the next meaningful experiment is the native `LTXMultiScalePipeline` / `ltxv_0.9.7_spatial_upscaler.safetensors`, not another reconstruction of the base route. Preserve 1024+tiled-decode as the comparison baseline.
