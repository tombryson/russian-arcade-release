# Russian alphabet

The Alphabet page (`/#alphabet`, or `/demo/#alphabet`) introduces all 33 letters. It is available without signing in. Activities navigation places it beside Curriculum; the introduction also links to it.

Audio plays only when a learner clicks or taps a letter or word, or activates its button with Enter or Space. Hover and keyboard navigation remain silent.

The Female / Male selector applies to every letter name and example word. The browser remembers the choice. Switching voices stops any current recording; it does not start another one automatically.

## Content and audio

`flask_vocab_app/ui/src/alphabet-data.json` is the shared content source. Each entry has the uppercase and lowercase letter, its Russian name, a word with marked stress, an English meaning and a short pronunciation note.

The two recordings serve different purposes: one says the **letter's name**; the other says the **whole example word**. A letter name is not necessarily its sound in a word. The hard and soft signs have names but no independent sound. Their examples show them inside words. English sound comparisons are approximate; stress and adjacent letters affect Russian pronunciation.

The audio is prepared with ElevenLabs v4 (`eleven_v4`) and committed under `flask_vocab_app/static/audio/alphabet-v1/`. Playback uses these files directly and makes no AI request. There are two complete sets: TatanaLuke (female) and Felix (male), with 33 letter names and 33 example words each. The original female recordings remain in the root directory; the male set is in `male/`. Each directory has a `manifest.json` recording its voice and generation details. Manifests are maintainer files, not public playback URLs.

## Preparing recordings

From the repository root, use the application's Python environment:

```sh
python scripts/prepare_alphabet_audio.py
python scripts/prepare_alphabet_audio.py --voice male --voice-id sRk0zCqhS2Cmv0bzx5wA --env-file /path/to/private.env --execute
python scripts/prepare_alphabet_audio.py --verify
python scripts/prepare_alphabet_audio.py --voice male --verify
```

The first command is a dry run. The second uses the explicitly supplied credential file to prepare the male recordings. A new set requires an explicit configured voice ID; confirm its language and voice description before generation. Reruns preserve verified recordings. Verification checks saved assets without calling a provider. Keep credentials outside version control.

Before publishing changed content, listen to the affected recordings. Check letter names, word stress, vowel reduction, consonant softness and the treatment of `ё`, `й`, `ъ` and `ь`. Successful synthesis or file decoding alone does not establish pronunciation accuracy. Do not describe all recordings as reviewed unless that listening review has taken place.

## Access and packaging

`services/alphabet_audio.py` derives an exact whitelist of the 132 recording URLs from the content JSON. The existing media guard permits these recordings without granting access to other audio files or private learner media. Docker includes the packaged alphabet directory and the shared JSON. Hosted requests support byte ranges without creating a demo workspace just to play a recording.

Relevant checks:

```sh
PYTHONPATH=flask_vocab_app python -m unittest tests.test_alphabet_audio tests.test_alphabet_audio_access tests.test_navigation_preferences
cd flask_vocab_app/ui
npm test -- ActivitiesMenu.test.tsx ActivitySidebar.test.tsx Alphabet.test.tsx
```

Pronunciation references: the [Russian Academy of Sciences alphabet reference](https://orfo.ruslang.ru/alphabet) and [Cornell's Russian letters and sounds](https://russian.cornell.edu/russian.web/courses/305/letters_sounds_1.htm).
