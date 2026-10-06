# «Не с ним» — Vocal Prosody v0.2

Status: active experiment after v0.1 human rejection.

## Frozen layers

- Instrumental arrangement v0.1 is frozen.
- Timbre route is frozen to D: Awata Weak RVC v1.2 / Original, FCPE, index_rate 0.50, pitch 0, protect 0.5.
- No new model search.
- No C render.

## Pronunciation rule

Use ordinary Russian spelling.
Only the stressed vowel is capitalized for the synthesis preparation layer.
Do not blanket-rewrite unstressed vowels or consonants.

Examples:
- тобОй, not табОй
- говорИл, not гаварИл
- собОй, not сабОй
- котОрый, not катОрый
- что, not што
- прикоснУться, not прикаснуцца

Ё is used when it is the actual stressed vowel: стЁрлась, тЁмный.

## Musical-prosody rule

The atomic unit is a sung phrase, not a word.

- Multisyllabic words span multiple musical notes.
- First note carries the word; following syllables use OpenUtau `+` extender notes.
- Phrase-final melismas use `+~`.
- Explicit breath markers create rests inside phrases.
- Verses use mostly shorter syllables with longer stressed syllables and a substantial phrase-end rest.
- Choruses have larger gaps, longer terminal holds and a higher melodic contour.
- Bridge has longer internal breaths around syntactic pivots.
- Final rises to the highest tessitura of the song.
- Coda narrows and descends.

## Timing

Backing: 108 BPM, 4/4, 88 bars.

Each text line still owns a 2-bar slot, but v0.2 does NOT fill that slot continuously:
- verse active phrase ≈ 3180 ticks plus pickup/breaths/rest,
- chorus active phrase ≈ 2880 ticks, leaving more silence after each line,
- bridge ≈ 3300 ticks with explicit internal breaths,
- final ≈ 3240 ticks,
- coda ≈ 2760 ticks.

Within words there is legato continuity.
Between words there are short gaps.
At | there is a clear breath.
At || there is a larger rhetorical pause.

## Melody

Section-specific phrase contours replace the v0.1 word-index pitch cycling:
- verse: restrained A-minor stepwise arc,
- chorus: register lift and stressed-note emphasis,
- bridge: widening arc,
- final: climax up to the top register,
- coda: descending contraction.

## Qualification

Human gate asks only:
1. Does it sound like singing rather than sequential syllables?
2. Are words intelligible?
3. Are phrases locked to the instrumental form?
4. Are rests/breaths believable?
5. Does the chorus lift?
6. Does D retain the near-human timbre after the new score?

If v0.2 fails, change vocal score/prosody only unless the failure clearly belongs to another layer.
