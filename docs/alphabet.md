# Russian alphabet

The Alphabet page (`/#alphabet`, or `/demo/#alphabet`) introduces all 33 letters. It is available without signing in. Activities navigation places it beside Curriculum; the introduction also links to it.

The main grid contains the 10 vowels and 21 consonants. Ъ (hard sign) and Ь (soft sign) sit below it in a separate **Silent signs** group. Selecting either opens its explanation without playing audio. Their names and example words remain available on click. Tab reaches each group; arrow keys move within it.

Audio plays only when a learner clicks or taps a letter or word, or activates its button with Enter or Space. Hover and keyboard navigation remain silent.

The Female / Male selector applies to every sound, letter name and example word. The browser remembers the choice. Switching voices stops any current recording; it does not start another one automatically.

## Content and audio

`flask_vocab_app/ui/src/alphabet-data.json` is the shared content source. Each entry has the uppercase and lowercase letter, a pronunciation target, an optional practice syllable, its Russian name, a word with marked stress, an English meaning and a short pronunciation note. IPA targets are authoring data; learners do not need to read phonetic notation.

Clicking a vowel plays its sound. Clicking most consonants plays a **practice syllable**, such as **па** for П. The panel labels each practice syllable and identifies its consonant and vowel. В, Ф, Ч, Ц, Щ, Ш, Й and Ж play short sound excerpts, labelled “Letter sound”. Both Й excerpts include the transition into the following vowel; they are not pure isolated /j/. The large letter replays the same example. Separate controls play the whole example word and the letter name.

Practice syllables use a hard consonant before а where the consonant has a hard/soft pair. Ч and Щ remain soft; Й is a brief glide, as in йо́гурт. Some syllables, such as ка, coincide with the letter's name. The two controls still identify their roles. Е, ё, ю and я demonstrate stressed word-initial pronunciation. The hard and soft signs have no independent sound: selecting either is silent, with its name, example word and explanation available.

All packaged speech uses ElevenLabs v4 (`eleven_v4`). There are two complete voice sets: TatanaLuke (female) and Felix (male). Each has 33 letter names, 33 example words and 31 pronunciation examples. Playback uses static files and makes no AI request.

The male Е name and sound were replaced using the pronunciation spelling `йэ.` to elicit the initial /j/. The learner still sees Е. The complete replacement is 640 ms; no speech was cropped. Its source and exact request are retained in `scripts/audio-sources/alphabet/names-v2/`. A blind audio-model check identified [je] in the replacement and no initial glide in the earlier recording. This is model screening, not native-listener certification. The female Е, both Э recordings and all example words remain unchanged.

The female Н example restores the complete 720 ms recording of «на», without trimming, fades or gain changes. Its panel labels it as a practice syllable. The male Н retains the 150 ms sound excerpt. The catalogue’s optional `soundByVoice` field keeps each voice’s label and pronunciation target aligned with its actual recording.

Most practice syllables are complete provider recordings. П uses a shorter excerpt of па and retains that syllable label: it includes the following vowel rather than a sustained isolated /p/. Vowels reuse their letter-name recordings, except О.

The current excerpt durations apply to both voices unless specified:

| Letters | Source window | Playback including padding |
| --- | --- | --- |
| Н (male only), Ц, Й, Ж, В | 150 ms | 310 ms |
| О, Щ, Ч, П | 130 ms | 290 ms |
| Ф | 170 ms | 330 ms |
| Ш | 110 ms | 270 ms |

Each excerpt adds 60 ms of leading and 100 ms of trailing silence. No looping or stretching is applied. Both Й excerpts and the male Ч and Ц excerpts reach the following vowel transition. These short samples do not replace listening to the complete example words.

The default guard requires 160 ms of detected source speech. The table’s letters have explicit duration exceptions. Signal is measured in 1 ms frames above −45 dBFS; Ч, Н and Ц allow respectively five, three and twelve internal quiet milliseconds to preserve the natural signal. Leading and trailing silence do not satisfy the minimum. These are asset checks, not pronunciation certification.

Sources and requests are saved in `scripts/audio-sources/alphabet/` and the name/word manifests. `scripts/data/alphabet-sound-crops.json` selects 41 complete copies and 21 excerpts. Manifests record the source requests, crop bounds, hashes and active duration. Versioned playback URLs prevent browsers from reusing old clips.

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
