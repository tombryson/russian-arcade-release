# Correcting selected lesson words

The normal flow remains **tap a word → pending cards → create**. An uncertain reading opens **Check this word**, with a crop from the original page, suggested readings and an editable field. Selecting a suggestion saves that reading. Cancel leaves the pending list unchanged. Corrections are remembered for that learner, revision and image region, including after removing and later selecting the word again.

**Select an area** handles missed words and incorrect boundaries. Draw a box or adjust its four corners; corner handles also accept arrow keys (Shift makes larger changes). **Read this area** performs local Russian OCR on a doubled-size colour crop with a white border, using line recognition. It then shows the crop for confirmation. Reading an area alone creates no pending card or generation request. Single-word cards remain the supported output; a wider crop can offer individual word choices.

The original image and raw reading are retained. Existing lesson transcription and annotations supply alternatives; when a crop loses letters, suggestions from the geometrically overlapping whole-page word remain available. Unmatched endings are never silently replaced with a grammatically preferred form. A prior tap alone is not considered confirmation of the spelling. Generated cards retain their existing text and schedules.

## Persistence and recovery

- Migration 018 adds `lesson_word_regions` and links picks to image coordinates. Existing picks are anchored using their original v1 OCR cache, not reassigned using a newly numbered word list. Unavailable legacy coordinates remain unresolved rather than guessed.
- New OCR results match an existing region only when there is a single sufficiently overlapping candidate. The existing anchor stays fixed. Ambiguous matches receive a new region; existing selected regions remain available.
- Migration 019 records explicitly confirmed readings separately from unconfirmed captures.
- Requests, cards and review events retain their original identifiers. Correction after a failed request creates a new selection snapshot; a published card is not rewritten by OCR changes.
- OCR caches use `tesseract-rus-eng-regions-v2`. Mixed Latin/Cyrillic or joined tokens are retained for correction instead of saving only their Cyrillic substring.
- Area endpoints enforce the existing personal/optional-household access rules, CSRF, page membership and bounded coordinates. OCR concurrency and timeout limits are unchanged. Crops use temporary files and do not modify lesson assets.

## Local comparison, 12 September 2026

Six visually checked error examples from **Unusual Professions**, pages 15 and 24: handwritten «УЧЁБА», plus printed «гонорары», «народ», «дети», «деревне» and «племени». Scoring ignores case and optional acute stress marks but **retains the distinction between е and ё**. These are targeted regression examples, not a representative accuracy estimate.

| Crop recognition | Correct readings |
| --- | ---: |
| Current fast Russian model, colour, line mode | 5 / 6 |
| Current fast Russian model, colour, single-word mode | 3 / 6 |
| Current fast Russian model, grayscale/autocontrast, line mode | 5 / 6 |
| Slower `tessdata_best` Russian model, colour, line mode | 3 / 6 |

Colour line recognition recovered all five printed examples. It still lost ё in handwriting; grayscale reduced that handwritten word to a fragment. A manually drawn crop with different margins also produced a fragment, which is why the confirmation view retains the source image and suggestions from both readings. Keep colour line recognition as the crop default; do not adopt the slower model or destructive filters globally from this small comparison.

Reproduction data and the comparison model are ignored local artifacts in `instance/ocr-benchmark/`. The slower model is not a runtime dependency. Refer to the official [quality guidance](https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html) and [model comparison](https://tesseract-ocr.github.io/tessdoc/Data-Files.html).

Checks cover correction persistence, preservation of the original reading, changed OCR order, migration of legacy picks, source context through card generation, bounding-box validation, access/CSRF, pointer geometry, keyboard adjustment, cancellation and failed saves. Browser checks used the actual printed and handwritten words on page 15.

## Remaining limitations

Handwriting can still require typing a correction. Suggestions are alternatives, not certainty scores. Embedded PDF text extraction, a vision-model crop retry, and phrase cards remain future improvements; this change introduces no new provider keys or model settings.
