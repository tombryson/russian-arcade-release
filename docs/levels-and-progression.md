# Practice levels, Lingo coins and Barsik’s journey

Progression decision: 15 September 2026. Game-shop update: 17 September 2026. This document records the approved direction and the scope of the first integrated release. It supersedes earlier proposals to turn the legacy Elo total into distance, or to charge coins for access to ordinary practice.

## Current guided-course rules — 23 September 2026

The [four authored A1 milestones](course-milestones.md) now govern the main route. This section supersedes the older coin-unlock and header-rating descriptions below. The current release accepts ordinary activity preparation or focused-target preparation for its normal checkpoint. The activity route uses two successful distinct A1 tasks per topic at 70% or higher across two activity families. Supported practice counts towards preparation; a current-chapter challenge can test out early. See the [TORFL research](curriculum-research.md) and the proposed [curriculum and assessment implementation plan](curriculum-uplift-plan.md).

Current checkpoints require 7/8 for the first three milestones; the final requires 13/16 with separate component minima. Both essential message details, playback of the separate listening clip and no revealed question hints or transcript are also required. Supported attempts provide feedback; a new unassisted attempt using another variant is required to pass. All four passes unlock the A2 guided level, with no authored A2 chapters claimed. Higher-level free practice stays available. These are pilot course rules, not CEFR certification.

The header line shows current-chapter coverage independently of Elo. Historical skill estimates remain separate. Coins, shop ownership and FSRS scheduling retain their existing contracts; they do not gate chapter progression. Earlier journey receipts stay saved.

## Curriculum update

The [full curriculum](curriculum.md) now formalises fifty topics across A1, A2, B1, B2 and C1–C2. Reading, Writing, Translation and Word Jumble use shared topic and task-level guidance. The numeric difficulty estimates for words and forms are unchanged. The Speaking table below describes the existing live scenario catalogue, not the limit of the wider course.

## Product rules

Use A1–C2 as recognisable **practice targets**, accompanied by plain labels. The current live Speaking catalogue uses the A1–B2 subset described below. Avoid “expert”: advanced language ability spans several distinct skills. The application does not award a TORFL qualification or infer a learner’s overall level from one AI conversation score.

| Target | Friendly Speaking label | Intended task demand |
|---|---|---|
| A1 | First conversations | Short, predictable exchanges; one question at a time; choices and repetition available |
| A2 | Everyday conversations | Connected everyday exchanges; preferences, follow-up questions and simple changes of plan |
| B1 | Handling situations | Future authored tasks involving explanation and less predictable situations |
| B2 | Discussing ideas | Future authored tasks involving developed viewpoints and negotiation |

A1–B2 are CEFR bands used by the Russian testing system. TORFL assesses more than speaking, including listening, reading, writing and language knowledge. These labels describe curriculum intent here; our scenario contracts have not undergone external level validation. Sources: [Council of Europe global scale](https://www.coe.int/en/web/common-european-framework-reference-languages/table-1-cefr-3.3-common-reference-levels-global-scale), [SPbPU Russian testing centre](https://english.spbstu.ru/education/programs/short-term-programs/russian-language-studies/testing-center-russian-as-foreign-language/).

Learners can freely select a practice target. Core activities have no coin requirement, placement lock or new parent/PIN requirement. Optional games are permanent [shop purchases](game-access.md) using Lingocoins: 25 for the first paid game and 50 thereafter. They do not require an Elo score or real-money payment. Personal study remains the default; the existing optional household mode remains optional.

## Three distinct kinds of progress

1. **Lingo coins recognise participation.** Successful saving of meaningful practice earns a bounded reward; high marks are not required. Coins are shared across activities, including native flashcards.
2. **Barsik’s guided route records chapter preparation and passes.** Topic coverage opens the normal checkpoint; an independent pass advances to the next chapter. Early challenges are available. Historical story-stop receipts remain saved separately, and course progression does not spend or require coins.
3. **Learning evidence describes what happened.** Grammar, fluency, task completion and assisted recall remain separate evidence. FSRS controls card scheduling. The profile retains provisional estimates for assessed skills; the header shows current-chapter coverage, and no global proficiency estimate is calibrated. Difficulty recommendations remain future work.

Freeze the legacy additive Elo calculation. Preserve its historical value and receipts, but remove it from prominent statistics and do not use it for access, distance, CEFR placement or coin calculation. A number that rises for adding vocabulary is not an ability measure. The [Russian L2 learner modelling paper](https://aclanthology.org/W19-4451.pdf) supports investigating concept-specific adaptation; it does not validate our old points formula.

## What is implemented

### Speaking

The relationship is activity type → scenario → variation. Café, shop, directions, station and introductions are scenarios, not levels. A variation has its own target band and authored learning contract: communicative objectives, grammar focus, vocabulary focus, agent complexity and support.

There are 30 active situations: three for each of the five settings at A1 and at A2. Each setting and level has its own description and curriculum mapping. A1 tasks cover simple exchanges; A2 tasks add clarification, alternatives or coordinated plans. The saved task requirements guide dialogue generation and feedback. See [Speaking scenarios](speaking-scenarios.md) for the current coverage. The Speaking catalogue shows an **A1 heading and its activities**, followed by an **A2 heading and its activities**. Both groups stay visible; there is no level toggle, dropdown or preference write when browsing them. Available A2 activities use the same active styling as A1. Opening a card selects a task from that card’s band, and a seed from another level cannot be started under it. B1/B2 remain future authored content and are not shown as empty selectors.

The selected variation and contract are copied into the session at creation. Changes to curriculum cannot rewrite an existing conversation’s task or grading context. Historical sessions keep their original snapshots and an unknown target level; they are not retrospectively labelled.

The agent’s language complexity, question load, follow-ups and support follow the contract. Independent audio assessment uses those objectives while accepting valid simpler replies. Its grammar and fluency scores describe the attempt. New eligible first assessments can update separate provisional skill ratings; neither the attempt score nor that estimate assigns a CEFR level. Short valid replies can fulfil a goal even when there is too little speech for a fluency score. Russian errors are preserved for feedback.

### Visible course progress

A thin progress line spans the bottom of both application headers after its introduction, with a miniature running Barsik at its leading edge. Selecting it opens the guided course. Its fill shows preparation for the current chapter and is independent of Elo. Separate profile skill estimates retain their existing evidence policy; the legacy Elo remains frozen. Coins, historical journey receipts and FSRS remain separate. See [the header and rating contract](skill-progress.md).

### Shared rewards

| Activity | Qualifying action | Daily entitlement |
|---|---|---|
| Sentence practice | Save an assessed translation attempt | One per sentence |
| Word Jumble | Save an assessed sentence attempt | One per game |
| Writing | Save an assessed response | One per exercise |
| Reading | Save a checked set of story answers | One per story |
| Lessons | Transition from unfinished to all active practice tasks checked | One per lesson revision/day on a plan completion; rechecking a finished plan does not create another completion |
| Speaking | Save an independent audio review with Russian participation: at least eight Russian words, or a supported completed communication goal | One per scenario variation |
| Existing published choice activities | Finish the activity | One per content definition, across versions |
| Journey scene | Submit a valid scene choice; a correct answer completes the stop | One per stop |
| Native flashcards | Reveal and rate a card Again, Hard, Good or Easy | One per card |

Activity entitlements pay **3 coins**, with a combined **12 activity coins per local study day**. Flashcards pay **1 coin**, with a separate **10 review coins per day**. These are conservative pilot settings, not an educational finding; change them centrally after observing use. Hints and incorrect answers do not reduce participation rewards. Browsing, generation, imports, editing vocabulary, API failures, skipping and reporting cards earn nothing. Unsuccessful Speaking transcription/review does not pretend to provide evidence; a successful later retry can earn its original entitlement. Speaking uses the saved conversation end time for its study day, so delayed feedback cannot shift daily caps. Archiving a profile during review preserves the successful report without awarding coins.

The [first delivery](first-delivery.md) adds a separate **3-coin welcome bonus once per profile** for completing its three recall questions after learning Привет!, письмо and Спасибо!. It remains available after the ordinary activity allowance is used and does not consume that allowance. It counts toward the wallet and eligible journey earnings; story prerequisites still apply. The same completion cannot also collect an ordinary Reading reward. Teaching cards and introduction pages award nothing. Unhinted first recall answers contribute one aggregate Reading observation; hints do not reduce the bonus but exclude supported evidence from Elo. Guest completion is pending until transferred once into a newly created personal profile, never an existing profile selected afterward. Restarting the earlier activity into this revised lesson archives old answers and preserves any existing welcome receipt and rating evidence.

The shop uses the visible wallet balance, including earlier balances and introductory rewards. Learners choose their first paid game for 25 coins and later games for 50 coins each. Purchases are permanent and profile-specific. They do not lower eligible journey earnings or skill estimates. Existing acquired games remain owned; introductory lessons and coin milestones grant no further games automatically. See [game access](game-access.md) for purchase and migration rules.

The review reward does not depend on the selected rating, so there is no incentive to choose Easy dishonestly. Undo appends a negative receipt and releases the card’s daily claim. Re-rating can reclaim the same net entitlement; it cannot accumulate extra coins. Reward writes and their qualifying saves share a SQLite transaction. Request retries and repeated checks cannot exceed the per-content entitlement or shared cap.

Migration 025 assigns saved reading, writing, translation and Word Jumble work to a profile. Their adapters reward the selected profile in personal mode; historical work stays with “Me”. In optional household mode they do **not** attribute work from the shared adult workspace to whichever child happens to be selected. Native review, Speaking, lesson practice and journey rewards also remain profile-scoped. See [local user sessions](user-sessions.md) for the shared-library boundary and browser lifecycle.

### Guided route and historical pilot

The current guided route contains four A1 milestones and three authored checkpoint variants per milestone. The final received letter arranges the journey beyond town; Barsik's original carried letter remains sealed. The [milestone contract](course-milestones.md) defines preparation, independent passes, support and retries. The [earlier chapter contract](course-chapters.md) remains available for the retained v1 release.

The earlier post-office and market-town scenes used eligible-coin thresholds. Their stored unlocks, answers and rewards remain preserved, but they do not establish chapter coverage or a course pass. The main journey view and header link now open the guided course. Updating the coin badge still does not reload an activity or reconnect the microphone, and ordinary practice remains available.

## Data migration and API

Migration 023 adds `progression_preferences`, `progression_events`, an append-only `progression_entries` ledger, daily `progression_claims`, a policy activation timestamp, and journey definitions/progress/answer receipts. The ledger is the balance authority. Events retain source identity and available evidence; they are not a replacement for the full activity attempt records.

The existing user’s coin balance is imported once into `personal-learning`, marked as brought forward. It stays in the wallet but does not count as new campaign earnings or proficiency evidence. Existing native participation receipts are imported with their original profile, amount, policy, date and daily entitlement. Old reward tables, user totals, card schedules and attempts are preserved. No balance is copied to every learner. Existing Speaking calls are not retrospectively rewarded when an old recording is assessed.

Migration 024 adds variation/session target levels and applies the authored contracts to the catalogue. The seed files run only during explicit migration, not on server startup. They are migration inputs; SQLite owns the live catalogue. No translation field is added to lemma records, and no vocabulary/forms, media, Anki schedules or provider credentials are modified.

| API | Purpose |
|---|---|
| `GET /api/v1/progression` | Selected profile’s wallet, preference, policy, receipts, guided course, historical route and provisional skill summaries |
| `POST /api/v1/progression/preferences` | Save A1/A2/B1/B2 preference |
| `GET /api/v1/journey/:world` | Read an unlocked scene without awarding coins |
| `POST /api/v1/journey/:world/answer` | Idempotent answer, reward and completion transaction |
| `GET /api/v1/live-conversations/scenarios` | Full catalogue with level membership, used to render stacked A1/A2 sections; optional `?level=A1` filtering remains available to API callers |
| `GET /api/v1/live-conversations/options?scenario_id=cafe&level=A1` | Preview an exact variation |
| `POST /api/v1/live-conversations` | Start with scenario, seed and target level |

Writes use the existing session/CSRF protections. The server selects the active profile; clients cannot choose a different wallet in a reward request. Provider responses never directly set balances, level access or route completion.

## Verification and remaining work

Regression coverage includes independent profiles, simultaneous duplicate writes, shared daily caps, transaction rollback, local study dates, frozen legacy balances, migration replay, flashcard undo/re-rating with real FSRS, locked-route requests, wrong-answer retries, permanent unlocks and level-aware scenario selection. UI tests cover shared badges, authored level availability and no microphone activation during catalogue browsing.

The original release integrated the participation/progression system and A1/A2 Speaking contracts. The later [curriculum pass](curriculum.md) gives Reading, Writing, Word Jumble and Translation explicit A1–C2 task levels, fifty topic briefs and shared grammar objectives. Their historical records keep their saved values; legacy inputs remain accepted through compatibility mappings. New curriculum labels are not a certification of proficiency.

Still to build: authored A2 and later guided chapters, further live Speaking content, independent curriculum review of band assignments, learner ownership for old shared activities in household mode, and evaluated skill recommendations. The four A1 chapter checkpoints, including the final letter, are implemented. Coins do not solve those curriculum or measurement problems. The later game-shop update adds spending with permanent ownership; it does not introduce a calibrated Elo model. The visible practice rating is explicitly provisional and does not yet choose tasks for the learner.

Operational rollout: back up the configured SQLite store; run `db-upgrade` explicitly; verify foreign keys and preserved historical row counts; build the React bundle; restart the local server against the same configuration. Retain the pre-migration backup. After new work has been saved, roll back through compatible code or release routing while retaining its records and media. Restoring an older database is disaster recovery, not a routine rollback; it must account explicitly for subsequent writes.
