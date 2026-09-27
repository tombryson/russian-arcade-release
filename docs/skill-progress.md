# The header progress line

Introduced 15 September 2026; preparation policy updated 23 September 2026. The header now shows guided chapter preparation. Separate provisional practice ratings remain available under [levels and progression](levels-and-progression.md), without reviving the old additive `users.elo_rating`.

## Current chapter preparation

The header line now represents preparation for the current [A1 milestone](course-milestones.md), independently of Elo. For the current release it uses the greater of ordinary activity preparation and focused-target preparation. The activity route requires successful distinct tasks for each chapter topic across two activity families. The focused route counts independent success, or introduction followed by practice. See the [milestone contract](course-milestones.md). Completing preparation opens the checkpoint; passing the checkpoint advances the course. A lower historical skill estimate does not reduce this coverage or remove a pass.

The separate provisional skill histories and their evidence policy remain available. The rating formula and dated verification receipts below describe that separate model; they do not define the header’s fill or destination. Coins and FSRS remain separate.

## Experience

A thin line spans the bottom of the sticky header in both the main app and the older activity pages. A small running Barsik sits at its leading edge. Selecting Barsik or the line opens the **guided course** for the selected learner. The link's accessible name identifies the current chapter and preparation progress.

The header shows checkpoint preparation, not a percentage of proficiency. Reaching 100% recommends the checkpoint; it does not pass it. With no qualifying preparation, Barsik stays at the beginning. Passing a checkpoint advances to the next chapter, whose own coverage determines the new fill. Completing all four chapters shows the completed course. Separate unmeasured skills in the profile still show a dash and **Not started**.

Barsik moves briefly when the same learner’s preparation improves within the current chapter. Reloading, changing learners or advancing to a different chapter must not look like newly earned preparation. He stays still between updates, and reduced-motion preferences disable animation. His feet stay aligned with the line, including at either edge on a narrow screen.

Lingo coins still recognise participation and buy optional games. Historical journey receipts are preserved. A separate skill rating estimates performance within a particular activity; it cannot reduce the course line’s fill or remove a checkpoint pass. Neither system assigns a TORFL qualification or changes FSRS schedules, and ordinary practice stays accessible.

## Separate evidence

The skill families are Reading, Listening, Sentence practice, Word Jumble, Writing, Speaking grammar and Speaking fluency. Speaking keeps its two dimensions separate: a recording can contain enough evidence for one and not the other.

Only new, successfully saved assessments can carry the new versioned rating receipt. Their task difficulty and normalised performance are frozen inside the existing `progression_events.evidence_json` in the same transaction as the activity save. Later edits to a task's difficulty cannot rewrite an earlier result.

The projection excludes old Elo totals, imported balances, earlier unversioned grades, cached reading feedback, lesson completion, journey choices and self-reported flashcard ratings. Existing FSRS review evidence remains useful for memory scheduling, but is not an objective cross-activity language score. Unsupported scores and unknown task difficulties earn no rating observation; their normal participation rules still apply. Reading additionally requires its submitted passage, questions and task settings to match the saved or server-generated task, so an edited easier question cannot inherit the original difficulty.

Within a skill, only the first qualifying assessment of a task counts. The saved attempt history also excludes tasks with recorded feedback before this rollout. Nonzero legacy Sentence practice scores are excluded as evidence of earlier grading, even without a modern attempt row. Speaking can supply fresh speech on later sessions: it counts at most one supported assessment per variation, skill and recorded local study day. Reassessing or rehearsing the same variation repeatedly that day does not multiply its rating observations.

Speaking observations come from the independent audio review, never from live captions or the speaking agent's own conversational response. They require the expected rubric, Russian speech and supporting evidence for a valid score. Short successful exchanges can still earn participation coins without generating a fluency rating. Grammar measures accuracy in the forms actually attempted; a correct simple reply does not prove a broader grammatical range merely because its scenario has an A2 target.

Legacy activities follow their selected profile in personal mode; historical records belong to “Me”. In optional household mode, the shared adult workspace cannot supply a selected child's rating. Learner-owned Speaking evidence follows the saved session owner.

The [first delivery](first-delivery.md) teaches three Russian words, then asks three recall questions with Russian choices drawn only from those taught words. Its saved unhinted first answers supply one Reading observation using the fraction correct among unhinted answers, with task prior 1000 and the existing update strength. This measures recall after teaching, not broad reading ability. Hinted answers are excluded; wrong unhinted answers remain evidence. Teaching cards stay outside the model. A fully supported completion still earns its participation bonus without manufacturing a measured rating. Replaying or completing the same attempt cannot replace first answers, erase support history or create extra observations. An explicit restart from v1 archives the earlier activity; its already-saved evidence remains unchanged.

## Explicit pilot model

The original policy identifier is `practice-elo-v1`. Historical receipts retain this formula. Each skill has a separate prior `R = 1000`.

```
expected = 1 / (1 + 10 ** ((task_rating - R) / 400))
R_next   = R + 24 * (observed - expected)
```

`observed` is the saved score normalised within that activity's rubric. The model uses conservative fixed updates and fixed task priors; it does not try to learn item difficulty and learner ability from a single household simultaneously.

| Task metadata | Initial task rating |
|---|---|
| Existing beginner / intermediate / advanced choices | 1000 / 1200 / 1400 |
| Sentence practice difficulty 1–5 | 1000 / 1200 / 1400 / 1600 / 1800 |
| Authored Speaking A1 / A2 / B1 / B2 target | 1000 / 1200 / 1400 / 1600 |

These are **uncalibrated task priors**, not equivalent proficiency levels across games. A score of 1200 does not mean A2. Each displayed estimate remains labelled provisional, regardless of observation count. The model needs evaluation against actual learner performance before it recommends difficulty automatically.

New journey-game receipts use `game-evidence-v2` from 16 September 2026. Their task prior is 1000; word difficulty is no longer used as task calibration. Their expected score includes chance performance:

```
expected = chance + (1 - chance) / (1 + 10 ** ((task_rating - R) / 400))
R_next   = R + 24 * (observed - expected)
```

The chance baseline follows each mechanic’s actual scoring rule. It accounts for partial-credit matching and repeated sentence tiles. Hints, transcripts and answers already exposed by earlier feedback are excluded from new evidence. Feedback times are compared across sessions, including sessions opened in a different order. Correction attempts earn no rating observation. Both policy versions remain readable; this change does not recalculate historical receipts.

The visual stages are internal 200-point intervals starting at 1000. At 1200, Stage 2 begins. Ratings below 1000 remain at the beginning of Stage 1, with their real rating and remaining gap available in the skill summary. These visual thresholds are a product setting, not an educational standard.

The API replays qualifying receipts in saved chronological order and ignores reversed events. Reading progress cannot award coins, modify the database or make ratings grow. The initial rating projection required no schema migration or historical grade backfill. Migration 027 adds persistence for the first-delivery activity; it does not backfill historical skill evidence. The old rating is preserved separately.

## Integration and assets

`GET /api/v1/progression` includes a `skill` object with the model version, active skill and independent skill summaries. Each summary contains its status, nullable rating, stage bounds, normalised progress, points to the next stage, observation count and most recent observation time. Existing wallet and journey fields retain their meanings.

The shared header illustration is `flask_vocab_app/static/images/barsik-running-v1.webp`, copied from the established transparent setting-off artwork. Keeping the original pose and character preserves the application's visual identity. The exact public illustration path is available in optional household mode; private uploads and media retain their existing access rules.

## Limits and next work

- Validate the score rubrics, fixed difficulty priors and update strength using real attempts. The current number is an explainable pilot estimate.
- Extend the first delivery's explicit support records to other activities that offer hints or answers before a first assessment. A first saved attempt alone does not prove that work was unaided. Very old Sentence practice records with a zero score cannot distinguish an ungraded task from an old zero-mark attempt because that history was never stored.
- Expand Speaking variations and evaluate repeated exposure. Same-day repetition remains useful even when it no longer supplies another rating observation.
- Introduce evaluated difficulty recommendations only after the evidence supports them. Keep recommendations optional and retain independent card scheduling and journey progression.

## Journey game evidence

Post Office Radio and vocabulary-based A Letter Back add provisional Listening observations from saved playback receipts and first answers without transcript or requested English-hint support. A Letter Back supplies English context and word tiles: this measures supported listening/reconstruction, not independent Writing. Reading the transcript remains a supported practice route with normal participation rewards. Other games supply Reading evidence; matching receives partial credit. Vocabulary difficulty bands are local, uncalibrated task priors, not an A1 label or TORFL placement. Replaying a game with the same saved content identity cannot replace its first completed observation. See [journey games](journey-games.md).
