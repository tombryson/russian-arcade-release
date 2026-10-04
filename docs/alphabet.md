# Russian alphabet

The Alphabet page (`/#alphabet`, or `/demo/#alphabet`) introduces all 33 letters. It is available without signing in. Activities navigation places it beside Curriculum; the introduction also links to it.

Audio plays only when a learner clicks or taps a letter or word, or activates its button with Enter or Space. Hover and keyboard navigation remain silent.

The Female / Male selector applies to every sound, letter name and example word. The browser remembers the choice. Switching voices stops any current recording; it does not start another one automatically.

## Content and audio

`flask_vocab_app/ui/src/alphabet-data.json` is the shared content source. Each entry has the uppercase and lowercase letter, a sound target, its Russian name, a word with marked stress, an English meaning and a short pronunciation note. IPA targets are authoring data; learners do not need to read phonetic notation.

Clicking a letter plays its **sound**. The large letter in the detail panel replays it. A separate word button plays the **whole example word**. The **letter name** is a secondary control at the bottom of the panel; names remain useful for spelling and discussing letters.

The hard and soft signs have no independent sound. Their grid buttons select the explanation silently, and their example words demonstrate their role. The other 31 letters have recordings in both voices. Paired consonants use their hard sound as a starting point; `ч`, `щ` and `й` remain soft. `е`, `ё`, `ю` and `я` demonstrate stressed word-initial pronunciation and are labelled accordingly. This is an introduction, not a claim that each letter always represents one sound. Examples and notes explain context, softness and vowel reduction.

The audio is prepared with ElevenLabs v4 (`eleven_v4`) and committed under `flask_vocab_app/static/audio/alphabet-v1/`. Playback uses these files directly and makes no AI request. There are two complete sets: TatanaLuke (female) and Felix (male), with 33 letter names and 33 example words each. The original female recordings remain in the root directory; the male set is in `male/`. Each directory has a `manifest.json` recording its voice and generation details. Manifests are maintainer files, not public playback URLs.

Sound recordings are separate assets under `sounds/female/` and `sounds/male/`. Direct isolated-IPA synthesis was tested and rejected: several takes added vowels or spoke more than the intended sound. The consonant clips instead use selected portions of v4 recordings, with separate sustained takes for М and Р. Vowel names already contain the required sound and can be reused. Existing name and word recordings are preserved. A missing consonant sound must never fall back to its letter name.

Each recording plays once. The preparation script rejects repetition and limits amplification to 3 dB. Earlier stop clips were incorrectly looped and over-amplified; those files have been rebuilt. A short isolated release still gives less pronunciation context than the whole word, so removing repeats does not by itself establish pronunciation quality. Hard Л comes from ла́мпа, not the soft ending of эль. Й comes from the beginning of йо́гурт. Crop boundaries, source checksums and processing settings are recorded in `scripts/data/alphabet-sound-crops.json`. The additional М/Р sources and their v4 request metadata are in `scripts/audio-sources/alphabet/`. These files let the sound clips be rebuilt without further synthesis. Sound playback URLs include a version query to invalidate the earlier recordings in browser caches.

## Preparing recordings

From the repository root, use the application's Python environment:

```sh
python scripts/prepare_alphabet_audio.py
python scripts/prepare_alphabet_audio.py --voice male --voice-id sRk0zCqhS2Cmv0bzx5wA --env-file /path/to/private.env --execute
python scripts/prepare_alphabet_audio.py --verify
python scripts/prepare_alphabet_audio.py --voice male --verify
python scripts/prepare_alphabet_sounds.py --voice female --execute
python scripts/prepare_alphabet_sounds.py --voice male --execute
python scripts/prepare_alphabet_sounds.py --voice female --verify
python scripts/prepare_alphabet_sounds.py --voice male --verify
```

The first command is a dry run. The second uses the explicitly supplied credential file to prepare the male recordings. A new set requires an explicit configured voice ID; confirm its language and voice description before generation. Reruns preserve verified recordings. Verification checks saved assets without calling a provider. Keep credentials outside version control. The sound preparation script is separate: it uses the checked-in v4 sources and makes no provider requests.

Waveform and spectrogram checks were used to select consonant boundaries and reject unwanted vowels. An audio-model screening pass was inconsistent on very short clips and is not treated as a pronunciation certificate. These checks do not establish native-listener approval.

A small MAI-Voice-2.1 trial for П, Г, Р and С was also generated on 4 October 2026. Its raw candidates remain outside the application; successful synthesis is not grounds for replacing the current examples.

Before publishing changed content, listen to the affected recordings. Check letter names, word stress, vowel reduction, consonant softness and the treatment of `ё`, `й`, `ъ` and `ь`. Successful synthesis or file decoding alone does not establish pronunciation accuracy. Do not describe all recordings as reviewed unless that listening review has taken place.

## Access and packaging

`services/alphabet_audio.py` derives an exact whitelist of the 194 recording URLs from the content JSON: 132 names and words, plus 62 sound clips. The existing media guard permits these recordings without granting access to other audio files or private learner media. Docker includes the packaged alphabet directory and the shared JSON. Hosted requests support byte ranges without creating a demo workspace just to play a recording.

Relevant checks:

```sh
PYTHONPATH=flask_vocab_app python -m unittest tests.test_alphabet_audio tests.test_alphabet_audio_access tests.test_alphabet_sounds tests.test_navigation_preferences
cd flask_vocab_app/ui
npm test -- ActivitiesMenu.test.tsx ActivitySidebar.test.tsx Alphabet.test.tsx
```

Pronunciation references: the [Russian Academy of Sciences alphabet reference](https://orfo.ruslang.ru/alphabet), [Cornell's Russian letters and sounds](https://russian.cornell.edu/russian.web/courses/305/letters_sounds_1.htm), and [Yanushevskaya and Bunčić's Russian phonetic description](https://doi.org/10.1017/S0025100314000395). See also [ElevenLabs v4 pronunciation guidance](https://elevenlabs.io/docs/overview/capabilities/text-to-speech/best-practices).
