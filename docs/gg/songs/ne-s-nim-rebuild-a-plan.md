# «Не с ним» — REBUILD A

This is a clean rebuild, not an edit of v0.1/v0.2.

## Immutable input rule
Lyrics passed to the Russian phonemizer use normal Russian spelling only.
No capital-letter stress encoding and no pseudo-phonetic spelling.
Stress is a separate score attribute used only for rhythm, duration and musical emphasis.

## New form
Tempo: 108 BPM
Meter: 4/4
Target form: 110 bars (~4:04)

- intro: 8 bars
- verse I: 8 lines × 3 bars = 24 bars
- chorus I: 4 lines × 2 bars = 8 bars
- instrumental response: 4 bars
- verse II: 4 lines × 3 bars = 12 bars
- chorus II: 8 bars
- bridge: 4 lines × 3 bars = 12 bars
- instrumental/drum development: 12 bars
- final: 4 lines × 3 bars = 12 bars
- coda: 2 lines × 3 bars = 6 bars
- outro: 4 bars

## Vocal design
- Each word has an explicit total duration.
- Each word has an explicit rest-after value.
- Every multisyllabic word is grouped across OpenUtau extender notes.
- Stress syllable is specified separately for every multisyllabic word.
- Phrase start/pickup is explicit.
- Verse lines intentionally leave roughly one bar of response space.
- Chorus uses repeatable melody rather than a new contour per line.
- Bridge has rhetorical mid-line pauses.
- Final has the highest tessitura.
- Coda descends and thins.

No algorithm may infer word duration from vowel count.
No algorithm may continuously fill a line slot.
No word-index pitch cycling is allowed.

## Arrangement design
The backing is rebuilt around these vocal phrase windows.
Drums and lead guitar answer the singer in the deliberately empty space.
Percussion retains the 3+3+2 identity but reduces under dense lyric passages.
