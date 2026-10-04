# Russian alphabet

The Alphabet page (`/#alphabet`, or `/demo/#alphabet`) introduces all 33 letters. It is available without signing in. Activities navigation places it beside Curriculum; the introduction also links to it.

## Content and audio

`flask_vocab_app/ui/src/alphabet-data.json` is the shared content source. Each entry has the uppercase and lowercase letter, its Russian name, a word with marked stress, an English meaning and a short pronunciation note.

The two recordings serve different purposes: one says the **letter's name**; the other says the **whole example word**. A letter name is not necessarily its sound in a word. The hard and soft signs have names but no independent sound. Their examples show them inside words. English sound comparisons are approximate; stress and adjacent letters affect Russian pronunciation.

The audio is prepared with ElevenLabs v4 (`eleven_v4`) and committed under `flask_vocab_app/static/audio/alphabet-v1/`. Playback uses these files directly and makes no AI request. One configured voice is chosen for the set. `manifest.json` records that voice and the generation details. It is a maintainer file, not a public playback URL.

## Preparing recordings

From the repository root, use the application's Python environment:

```sh
python scripts/prepare_alphabet_audio.py
python scripts/prepare_alphabet_audio.py --env-file /path/to/private.env --execute
python scripts/prepare_alphabet_audio.py --verify
```

The first command is a dry run. The second uses the explicitly supplied credential file to prepare recordings. Reruns preserve verified recordings. The verification command checks saved assets without calling a provider. Keep credentials outside version control.

Before publishing changed content, listen to the affected recordings. Check letter names, word stress, vowel reduction, consonant softness and the treatment of `ё`, `й`, `ъ` and `ь`. Successful synthesis or file decoding alone does not establish pronunciation accuracy. Do not describe all recordings as reviewed unless that listening review has taken place.

## Access and packaging

`services/alphabet_audio.py` derives an exact whitelist of the 66 recording URLs from the content JSON. The existing media guard permits these recordings without granting access to other audio files or private learner media. Docker includes the packaged alphabet directory and the shared JSON. Hosted requests support byte ranges without creating a demo workspace just to play a recording.

Relevant checks:

```sh
PYTHONPATH=flask_vocab_app python -m unittest tests.test_alphabet_audio tests.test_alphabet_audio_access tests.test_navigation_preferences
cd flask_vocab_app/ui
npm test -- ActivitiesMenu.test.tsx ActivitySidebar.test.tsx Alphabet.test.tsx
```

Pronunciation references: the [Russian Academy of Sciences alphabet reference](https://orfo.ruslang.ru/alphabet) and [Cornell's Russian letters and sounds](https://russian.cornell.edu/russian.web/courses/305/letters_sounds_1.htm).
