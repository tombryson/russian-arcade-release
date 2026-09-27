# Guided A1 chapters

Status: **retained course release `a1-v1`**. This page documents the earlier course for its existing learners and saved assessments. The current [A1 journey milestones](course-milestones.md) start at home and end with a cumulative received-letter assessment. The earlier content and assessment rules documented here are unchanged.

The guided course has four authored A1 chapters. It uses the existing [curriculum](curriculum.md) and preserves free practice, Lingocoins, game ownership, historical skill ratings and FSRS schedules. These course rules supersede the earlier coin-gated campaign and skill-rating header proposals where they describe the main guided route.

## Chapter sequence

| Chapter | Curriculum topic IDs | Checkpoint task |
| --- | --- | --- |
| 1. The little post office | `greetings`, `numbers`, `family` | Understand introductions, family relationships and a helper’s arrangement. |
| 2. A stop at home | `home`, `daily_activities`, `clothing` | Find clothing and understand where people are and what they are doing. |
| 3. At the market | `food`, `colors` | Collect the right food using requests, colour and size. |
| 4. Your letter arrives | `places`, `weather` | Follow an invitation’s route, understand weather plans and confirm an updated arrangement. |

Each of the ten actual A1 curriculum topic IDs appears once in this sequence. Later chapters reuse earlier language. Short preparation examples teach useful patterns before topic-linked activities. Opening a preparation card does not record a completed practice task.

The first three checkpoints are notes addressed to Barsik by people helping him. The original letter for the learner remains sealed. Chapter 4 delivers that letter: an invitation to meet the friends helping Barsik, with a connected place, plan and reason to reply. The three endings are a park visit, lunch at Nina’s home and tea at Pavel’s home.

## Preparation and advancement

The normal checkpoint becomes ready after **two successful distinct tasks per topic**, each scored at least **70%**, with **at least two activity families across the chapter**. Repeating the same saved task does not create another distinct task. Supported practice can count towards this preparation: it records coverage, not independent mastery. The welcome lesson can contribute one Greetings task when both taught greeting answers are correct; it does not complete the topic or chapter.

A learner may challenge the current chapter early to test out. Chapters still advance in order. A passed checkpoint is a permanent milestone; it does not require coins or a skill rating. The header line shows preparation coverage for the current chapter, independently of Elo. The course view explains remaining topic work and checkpoint status.

A checkpoint passes when all of the following hold:

- At least **80%** of answers are correct: with eight questions, at least seven must be correct.
- Both designated essential message details are correct.
- The separate listening clip has been played.
- No question hints or listening transcript were revealed during that attempt.

Hints and transcripts remain available for learning. A supported attempt gives feedback but cannot unlock the next chapter. The learner must start a new unassisted attempt using another variant for an independent pass. Each chapter has three authored variants. Retries prefer unseen variants; after all three have been used, they rotate without repeating the immediately preceding variant. This finite pilot does not claim that every later attempt contains previously unseen material.

Passing all four chapters unlocks the A2 guided level. The release does **not** claim authored A2 chapter content. Existing practice at higher levels remains accessible. These thresholds are application pilot policy, not CEFR certification or a validated placement examination.

## Checkpoint content

The source is [`course_chapters.json`](../flask_vocab_app/data/course_chapters.json), content version `1`, rubric `a1-checkpoint-v1`. Each chapter includes bilingual objectives, preparation examples and verified topic IDs. Each of its three variants includes:

- A Russian letter, 35–38 words in Chapter 1 and 49–57 words later, with a bilingual title and incidental-word glossary.
- A separate 21–22-word spoken update at `/static/audio/course/<variant-id>.mp3`.
- Five reading questions, two listening questions and one response-selection question, with Russian choices and bilingual prompts, hints and explanations.

The two essential questions are `r1` and `l1`. Listening questions depend on new information in the separate spoken message; the written letter does not supply their answers. Several messages revise an earlier arrangement, and the prompt explicitly asks for the latest spoken detail. Response selection checks a suitable communicative reply; it does not assess spoken production or certify speaking proficiency.

Variant IDs are `<chapter-id>-v1`, `-v2` and `-v3`, using chapter IDs `a1-post-office`, `a1-home`, `a1-market` and `a1-delivery`. Correct-answer keys, explanations before assessment and unrevealed support content remain server-side. Attempts freeze their selected content and rubric. Profile ownership, idempotent submissions and saved support history prevent replays from erasing help or earning another pass.

## Separate systems

Coins continue to reward eligible participation under the existing limits. The game shop retains its permanent purchases and prices. Course chapter readiness and passes neither spend coins nor depend on the wallet. Historical journey receipts remain saved; they do not establish chapter comprehension. FSRS still schedules vocabulary reviews, and provisional skill histories remain separate evidence.

## Release persistence

Migration 045 assigns existing learners and assessments to `a1-v1`. Passes are keyed by profile, release and chapter. Existing A1 completion creates a durable A2 access record, so a later course revision cannot remove that earned access.

The published release registry checks the original content hash. Saved assessment content, answer receipts and rubric versions are preserved. Old requests that did not send a release ID still support retries without creating another attempt or award. New requests include the intended release and reject a stale enrolment.

Assessment responses identify the saved attempt's release separately from the learner's current course. The interface refreshes an old receipt before updating the current journey. Merely viewing Curriculum, Journey or Profile does not enrol a learner in a new release.

Deploy schema 045 with the release-aware application code. Older server code writes the previous pass-table layout and is not compatible with this schema. Rollback should change course routing within a compatible build. Preserve all new learner work before considering a database restore; see the [migration and rollback procedure](journey-milestones-build-plan.md#11-migration-of-existing-learners).

The offline account importer accepts automatic v1 enrolment records from an unused hosted workspace. It retains the local enrolment and archives differences. Conflicting releases, hosted assessments or earned continuation rights still require a separate merge policy; they are never silently discarded or combined.
