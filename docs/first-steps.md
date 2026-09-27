# First steps with Barsik

This optional five-lesson opening gets Barsik ready to leave the post office with the learner’s letter. The learner meets useful Russian, then uses it to name what he carries, follow directions and ask the clerk for help. Completing it establishes the post-office checkpoint; the letter is still on its way to the learner.

First steps is available to every learner, including existing profiles, and ordinary activities remain direct alternatives. Home shows the learner’s actual next lesson and resumes saved work. Post-office links, including the older journey route, open this chapter rather than a separate introductory quiz.

First steps teaches the opening words and actions; it does not unlock games. After the introduction, Reading, Writing, Sentence practice, Word Jumble, Lessons, Speaking and Flashcards provide the main practice routes. Learners can spend Lingocoins in [the shop](game-access.md) to choose permanent game unlocks. Introductory rewards remain spendable, but lessons do not grant games automatically. Games use their full content pipelines, rather than only the words in these five lessons.

The authored source is `flask_vocab_app/data/first_steps.json`, version `first-steps-v1`. Lesson one reuses the saved `first-delivery-v2` activity rather than creating a second greeting attempt. Its `first_lesson` vocabulary mirrors the immutable v2 practice descriptor, checked by a content test so edits cannot silently change historical greeting cards. The `lessons` array contains lessons two through five.

## The five lessons

| Lesson | Language and action | Resolution |
|---|---|---|
| 1. Hello, Barsik! | Learn Привет!, письмо and Спасибо!, then choose the Russian words. | Meet Barsik and receive the one-time welcome reward. |
| 2. What’s in the bag? | Name Это письмо., Это сумка. and Это карта. with simple object pictures. | The letter, bag and map are ready. |
| 3. Which way? | Use прямо, налево and направо with map arrows. | Practise the three directions needed for the route. |
| 4. Ask for help | Learn Здравствуйте!, рынок, Где рынок? and Покажите, пожалуйста.; reuse Спасибо!. | Ask the clerk for the market’s location and thank them. |
| 5. Ready to set off | Reuse the greeting, letter and directions; add потом and там in a short clue. | Leave the post office with directions toward the market. |

Each new lesson has three or four tiny teaching cards followed by three or four questions. Every Russian answer choice uses language introduced by that point, including distractors. Teaching cards disappear during recall. Object pictures and map arrows use code graphics with stable visual keys; they do not reveal Russian answer labels. The final reading questions retain their short passage because understanding the clue is the task.

The clerk’s final clue is **«Рынок там. Прямо, потом налево.»** — “The market is there. Straight ahead, then left.” The learner has met every word before using it. The greeting distinguishes informal **Привет!** with Barsik from polite **Здравствуйте!** with the clerk. No chapter completion claims that the learner has independently mastered Russian or that the final letter has been delivered.

## Saved practice and rewards

Lessons unlock in order. All teaching cards must be acknowledged before answering, and each first answer is frozen before feedback. Hints remain available and are recorded before the answer. Incorrect answers still lead to feedback and allow the lesson to be completed. Refreshes and request retries resume the saved teaching card, question or feedback without adding a second completion.

Lesson one keeps its separate lifetime welcome bonus of 3 coins. The four later lessons use ordinary participation rewards: up to 3 coins each, within the shared 12-coin daily activity allowance. Hints and mistakes do not reduce participation rewards. A completed lesson cannot be replayed on another day to claim another grant. Coin amounts reflect committed receipts, including zero when the allowance is already used.

Each saved lesson can supply one provisional Reading observation from its unhinted first answers. Hinted answers are excluded, and an entirely hinted lesson adds no independent rating evidence. This is recall or short reading after teaching; its completion is participation, not a claim of broad mastery. Repeat requests cannot replace those first answers or create more observations.

The last lesson establishes the existing post-office checkpoint after its questions and feedback are finished. It preserves older journey answers and checkpoint timestamps. The market still requires the existing coin threshold as well as the post-office prerequisite. The introductory series does not mark the market scene complete or create a final-letter result.

Migration 029 adds `first_steps_attempts`, with one owned attempt per chapter lesson. Each attempt freezes the authored lesson JSON, including teaching, questions, feedback, contextual vocabulary and version. Later edits to the source cannot rewrite old answers or change their meaning. No existing first-delivery attempt, reward, schedule or journey answer is migrated into a fabricated lesson completion.

Guests can save temporary chapter work with their first-delivery session. Only creating a new personal profile can claim that work and its eligible rewards; selecting an existing profile keeps that learner’s own history. Ordinary activities remain directly available outside the chapter.

## Words for later practice

Each lesson supplies three contextual native-card candidates with `lemma`, `form`, OpenCorpora `pos`, sentence, whole-sentence translation, target meaning and grammatical tags. Repeated contexts are deduplicated across the chapter. The target occurs once and leaves useful context when hidden. For example, **карта** means “a map” in **«Это карта.»**, while **Покажите** is the polite imperative of **показать** in **«Покажите, пожалуйста.»**. These meanings belong to these contexts; they do not overwrite every use of the dictionary lemma.

Nouns specify case and number to disambiguate forms. Direction cards retain **«Барсик, прямо!»**, **«Барсик, налево!»** and **«Барсик, направо!»** so a cloze does not hide the whole utterance. Image and audio creation use the existing native-card workflow when the learner chooses to add the words. Completing a lesson by itself does not create media, change card schedules or prove long-term retention.

The flashcard action creates native Russian clozes from the authored sentences and contextual meanings, then uses the existing pipeline for an image, word audio and sentence audio. These cards become study-ready only when all three media are attached. The study link filters the normal library to **First steps**; it does not introduce another card store or scheduler.

Lesson and chapter requests reuse the same selected native items. If an earlier request is unfinished, the later request includes those items and can finish or retry their cards and media. It never advances unrelated cards from the earlier batch. Repeated clicks preserve card identity and review dates, and a retired card stays removed.

After the chapter, the practice actions also open an ordinary saved Word Jumble using **это, письмо, сумка**, or open Speaking with the **directions** scenario selected. The jumble is reused on repeat clicks; opening Speaking does not start or complete a conversation automatically.

## Validation

`tests/test_first_steps_content.py` checks the complete series shape, Russian-only choices, prior teaching coverage for every answer and reading clue, the post-office destination, useful cloze context and unambiguous morphology for every vocabulary candidate. The four content checks pass with `../.venv/bin/python -m unittest tests.test_first_steps_content -v` from `flask_vocab_app`; they use no provider or learner database.