# Beginner first steps

## Purpose

These five lessons introduce a small amount of Russian in a clear order. Each new
question uses words or phrases taught earlier. The learner hears an example,
sees its meaning and tries it with support available.

The lessons prepare someone to begin learning. Completing them does not establish
A1 proficiency or show that the learner can speak independently.

## Lesson sequence

| Lesson | Prerequisites | New learning | Practice |
| --- | --- | --- | --- |
| 1. Hello, Barsik! | None | Привет, письмо, Спасибо | Recognise the three words after learning their meanings. |
| 2. Name what you see | The first three words | Это; сумка, дом, карта; reuse письмо | Name four pictured things, then recognise a spoken phrase. |
| 3. Introduce yourself | Greetings; это phrases | Меня зовут… and А тебя? | Recognise the name phrase, identify a name, ask back, listen and choose a reply. |
| 4. Noun gender | Дом, сумка, карта, письмо | Masculine, feminine and neuter noun groups | Classify familiar nouns and compare their endings. |
| 5. Say what is yours | The three noun groups | Мой, моя, моё | Follow a worked example, complete guided phrases, apply the pattern to карта and understand a short exchange. |

Lesson one keeps the approved `first-delivery-v2` content. The four new lessons
are authored in `flask_vocab_app/data/first_steps_v2.json`. Their IDs are `bag`,
`introductions`, `gender` and `ownership`. The chapter and content version are
both `first-steps-v2`.

## Teaching decisions

### Naming comes before agreement

Lesson two explicitly explains это and the absence of a separate word for “is”
in Это письмо. The familiar nouns provide examples for later grammar. Карта is
introduced here and classified in lesson four. Lesson five can therefore ask for
моя карта without introducing an unknown noun at the same time.

### Name phrases are taught as complete phrases

Меня зовут… is introduced as “My name is…”. А тебя? is introduced as the short
follow-up “And yours?” in a name exchange. The lesson does not require the learner
to infer accusative pronoun forms or conjugation.

Dima and Anya are example names. An optional local name field lets the learner
complete Меня зовут… with their own name or another name. This field is ungraded.
It should not upload or store a personal name, produce a grammar score or require
AI generation.

### Noun gender comes before possessive agreement

Lesson four explains grammatical gender as a property of the noun. It uses only
familiar words:

| Noun | Group | Pattern illustrated |
| --- | --- | --- |
| дом | Masculine | Ends in a consonant |
| сумка, карта | Feminine | End in -а |
| письмо | Neuter | Ends in -о |

These are common patterns, not complete rules for every Russian noun. The content
uses “many” and “common” deliberately. Exceptions and soft-sign endings belong in
later lessons after these examples are secure.

Lesson five explains that the form of “my” matches the noun: мой дом, моя сумка,
моё письмо. It does not depend on the speaker’s gender. This is possessive
agreement. Subject–verb agreement is a separate topic and is not tested here.

### Support precedes independent application

The ownership lesson has three stages:

1. A worked example explains why сумка takes моя.
2. Guided questions give the noun’s group while the learner chooses the form.
3. Later questions omit that reminder and transfer the pattern to карта.

Hints and review remain available. Using them records supported practice, not an
independent demonstration of mastery. Gender questions use English category
labels because the learner is classifying grammar. Other answer choices are in
Russian.

The final tasks combine already taught phrases. They do not add formal greetings,
directions or requests inside a supposed recap.

## Audio and reading support

Every teaching card declares `audio_text` and `audio_url`. Three listening
questions declare the same fields plus `transcript`. The authored set requires
18 recordings, plus three for the existing first-word lesson. URLs use
`/static/audio/first-steps-v2/{id}.mp3`.

`audio_text` contains plain Russian without added stress marks. `word_display`
adds stress marks for reading; it does not change the vocabulary source text.
Optional `reading_help` gives an approximate English pronunciation aid. It is
secondary to the recording and is not a transcription standard or pronunciation
assessment.

Teaching cards may include translated `examples`. The introductory name card
uses `name_slot: true`. Questions use `choices_language` to distinguish English
grammar labels from Russian answers.

Listening prompts do not show the transcript or an illustration that gives away
the answer. A transcript may be requested as support or shown with feedback.
Replay must remain available. Missing audio must be handled as unavailable audio,
not treated as an incorrect learner answer.

## Data and saved progress

The original `first_steps.json` remains unchanged. Saved attempts must retain the
content and answers with which they began. The new chapter is a separate content
edition; changing the preferred route must not relabel old results as new lessons.

Vocabulary records keep lemmas separate from their observed forms. For example,
мой, моя and моё use the lemma мой with different grammatical tags. The name
phrases carry their real morphological tags internally, although the beginner
lesson teaches the phrase as a whole.

These authored vocabulary entries are inputs to the existing vocabulary and card
pipeline. They do not justify direct inserts that skip enrichment, mnemonics or
normal validation. English meanings describe the example context; they are not
proposed as one permanent translation per lemma.

## Lesson presentation

All five lessons use `IntroLessonCard` for teaching, questions, feedback and
completion. The title, counter and actions keep the same spacing. Reading help
sits at the top right and starts closed for each teaching card. Normal and slow
playback stay beside the Russian word or phrase.

Translated examples sit together below the explanation. Longer dialogues wrap;
noun comparisons can use columns on wider screens. Illustrations appear only
when the content defines one. The name exercise remains local and ungraded.

Questions put hints and example review in one action row. Opening examples still
records support before displaying them. Listening transcripts stay hidden until
the backend permits them. Audio controls never submit an answer.

Completion keeps the next lesson as the main action. Rewards and optional word
review remain inside the same card; further practice is a small row below it.
The site footer is omitted while a lesson is open.

## Evidence and limits

The questions check recognition, understanding and supported selection. They do
not check pronunciation, spontaneous conversation or independent written Russian.
The scoring system must preserve that distinction. Completing these lessons must
not silently pass an A1 milestone or unlock games as if a level assessment had
been passed.

Authored content and automated validation are not a learner trial. Release checks
must cover recordings, transcript concealment, replay, mobile layout, hints,
answer saving, resume behaviour and the transition between lessons.

## Subsequent work

### Release checks

The production UI build, 89 focused UI tests and 150 focused backend tests pass.
An additional 33 audio, hosted-demo and release-packaging tests pass. The teaching
layout and normal/slow audio playback have been checked in the local browser.

All 21 recordings are packaged with the application. They were generated from
291 authored Russian characters using `gpt-4o-mini-tts`, with variation between
the `marin` and `cedar` voices. ElevenLabs lacked sufficient capacity for this
set; its application configuration remains unchanged. These are AI-generated
voices; their provenance is recorded in the audio manifest. See the
[speech API reference](https://developers.openai.com/api/docs/guides/text-to-speech).

`scripts/prepare_first_steps_audio.py --provider openai --dry-run` verifies the
manifest without generating recordings. A normal run preserves verified audio,
limits new requests and stops on the first failure. Text changes require a new
recording URL. Tests check file hashes, decoding, audible signal and public
byte-range playback. Generated clips must pass the signal check before they are
published. This rejects silent files even when their duration and format are valid.

The first-word письмо recording uses a revised URL after its original generated
file was found to be silent. Its replacement uses `marin`; a Russian transcription
check returned «Письмо.». The new URL avoids reusing a cached silent recording.
Automated playback checks do not constitute a human pronunciation review.

### Later teaching

The next lessons need their own teaching sequence. Directions, formal greetings
at the post office, requests, family words and location phrases remain useful
subjects. They should introduce one new distinction at a time and reuse these
first nouns and phrases.

The existing Leaving home practice and later milestones require a prerequisite
review. A target being labelled A1 does not make it suitable immediately after
these five lessons. New course routes should lead to the appropriate next lesson,
with optional review available, rather than assuming that a short introduction
establishes all the knowledge needed for a milestone.

Future coverage should add recognition of grammatical exceptions, more listening
examples and genuinely independent production. These are separate deliverables;
the five-lesson revision does not claim to complete the A1 curriculum.
