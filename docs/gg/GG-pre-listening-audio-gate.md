# GG pre-listening qualification gate

A render is not user-facing merely because synthesis and mastering succeeded.

Before a song candidate may be sent to the human listening gate, it must pass machine listening against the rendered audio itself.

## Required layers

1. **Shared composition source**
   Vocal melody, harmony, drums and instrumental responses must be generated from one bar-level composition score. Vocal and backing may not be authored independently and merely aligned afterward.

2. **Rendered-audio QA**
   `tools/gg_audio_qa.py` measures:
   - actual vocal pitch support by the rendered accompaniment,
   - vocal attack coupling to drums and eighth-note grid,
   - mid-band masking during sung passages.

3. **Intelligibility QA**
   External ASR comparison against the clean literary lyrics is required before final user-facing qualification when the media bridge is available. Target metric will be CER/WER on isolated D vocal, not on the full master.

4. **Human-like listening gate**
   Machine metrics are rejection filters, not artistic approval. A PASS can still be rejected internally for melody, phrasing, emotion or arrangement.

## Immediate diagnosis: REBUILD A

Local rendered-audio analysis rejected Rebuild A before user-facing qualification:
- vocal pitch in top-3 accompaniment chroma: ~28.6%,
- vocal onset within 150 ms of a drum onset: ~81.3%,
- vocal onset within 100 ms of eighth-note grid: ~69.2%,
- accompaniment louder than vocal in 300–4000 Hz band for ~25.9% of active-vocal frames,
- accompaniment >6 dB louder there for ~17.3%.

Interpretation:
Timing is not the primary failure. Harmony/voice-leading and masking are. The previous architecture created melody and accompaniment separately.

## Next architecture

REBUILD B must be authored from one shared score:
`bar → chord → groove → vocal phrase → stressed-note targets → instrumental answers → dynamics`.

Rules:
- choose a small vocal motif per section and harmonize every stressed/held note explicitly to the current chord or intentional tension/resolution;
- rhythmic stress points are decided with the drum groove, not after it;
- instrumental fills occupy phrase gaps and may answer a melodic fragment from the vocal;
- accompaniment density is reduced under consonant-dense lyric spans;
- no candidate is sent to the user if the rendered-audio gate rejects it.
