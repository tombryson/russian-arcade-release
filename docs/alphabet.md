# Russian alphabet

The Alphabet page (`/#alphabet`, or `/demo/#alphabet`) introduces all 33 letters. It is available without signing in. Activities navigation places it beside Curriculum; the introduction also links to it.

Audio plays only when a learner clicks or taps a letter or word, or activates its button with Enter or Space. Hover and keyboard navigation remain silent.

The Female / Male selector applies to every sound, letter name and example word. The browser remembers the choice. Switching voices stops any current recording; it does not start another one automatically.

## Content and audio

`flask_vocab_app/ui/src/alphabet-data.json` is the shared content source. Each entry has the uppercase and lowercase letter, a pronunciation target, an optional practice syllable, its Russian name, a word with marked stress, an English meaning and a short pronunciation note. IPA targets are authoring data; learners do not need to read phonetic notation.

Clicking a vowel plays its sound. Clicking most consonants plays a complete **practice syllable**, such as **па** for П. The panel labels each practice syllable and identifies its consonant and vowel. Ф instead plays an isolated /f/ sound, labelled “Letter sound”. The large letter replays the same example. Separate controls play the whole example word and the letter name.

Practice syllables use a hard consonant before а where the consonant has a hard/soft pair. Ч and Щ remain soft; Й uses йо, as in йо́гурт. Some syllables, such as ка, coincide with the letter's name. The two controls still identify their roles. Е, ё, ю and я demonstrate stressed word-initial pronunciation. The hard and soft signs have no independent sound: selecting either is silent, with its name, example word and explanation available.

All packaged speech uses ElevenLabs v4 (`eleven_v4`). There are two complete voice sets: TatanaLuke (female) and Felix (male). Each has 33 letter names, 33 example words and 31 pronunciation examples. Playback uses static files and makes no AI request. Original name and word recordings remain unchanged.

Consonant practice syllables are complete provider recordings, copied without cropping, stretching, looping or gain changes. Vowels reuse their original recordings, except О. At the user’s request, **О and Ф retain 110 ms of sound in each voice**, extracted from the original vowel or final frication in эф. These four clips include 60 ms of leading and 100 ms of trailing padding, for 270 ms total playback. No repeats or stretching are applied. All other recordings remain unchanged.

The preparation code requires **160 ms of detected source speech**, with explicit **110 ms exceptions for О and Ф**, measured in 1 ms frames above −45 dBFS. Added silence and container duration do not satisfy this minimum. This is an application quality check, not a rule about how long every Russian consonant must last or proof of correct pronunciation.

Sources and requests are saved in `scripts/audio-sources/alphabet/syllables-v1/`. `scripts/data/alphabet-sound-crops.json` retains its existing filename and selects complete copies for 58 recordings plus the four О/Ф crops. Manifests record source hashes, output hashes and active duration. Sound playback URLs include a version query so browsers do not reuse earlier cropped files. A failed example never silently substitutes its letter name.

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

The first command is a dry run. The second uses the explicitly supplied credential file to prepare the male recordings. A new set requires an explicit configured voice ID; confirm its language and voice description before generation. Reruns preserve verified recordings. Verification checks saved assets without calling a provider. Keep credentials outside version control. The sound preparation script packages the checked-in v4 sources and makes no provider requests. New consonant sources must contain exactly the labelled syllable and match the pinned voice, model and generation settings.

The earlier cropped consonants were not adequately validated for learning. Waveform checks and an inconsistent audio-model screening pass did not establish natural pronunciation. The new complete syllables avoid that cropping process; signal checks still do not establish native-listener approval.

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
