# Curriculum implementation record

Date: 2 October 2026; language-design follow-up updated 3 October. Scope: the [TORFL delivery plan](torfl-assessment-build-plan.md), P0/P1 foundations and ongoing P2 procedural content.

## Procedural follow-up

Practice now composes Russian examples from checked grammar rules. Each set has
six distinct questions, includes the taught contrasts and considers recent work.
There are now 17 A1 teaching units. The two additions cover calendar dates
versus duration, and о/об + a conversation topic. All units have selected
grammar rules for recognition and typed forms. Existing authored exercises and
saved attempts are retained. Generated unit reading/listening and on-demand
audio now use a persistent preparation workflow; preparing another stock
recording bank is not the delivery plan.

Describe the Scene now composes compatible visual situations. Speaking has
variable A1/A2 situation recipes. Text games prepare enough distinct contexts for
their rounds, while picture games keep a four-image ceiling. Ordinary AI activities
share bounded recent-content guidance and reject exact recent duplicates without
an automatic novelty retry. Word Jumble also avoids recently used complete sets.

Saved questions, original responses and marking contracts remain fixed. Repeated
answers retain their support history. Generated sets share the existing daily
reward policy and do not award proficiency. Account import drops private editorial
history and rebuilds pending novelty guidance for the destination account. See
[procedural content](procedural-content.md) for scope and verification.

## Current P2 follow-up

`calendar-and-duration-v1` teaches the month in a date and bare duration phrases. It supplies the date number rather than claiming to assess ordinal date formation. Generation samples valid dates and keeps elapsed time distinct from a starting time or delay. Correct alternatives such as неделю / одну неделю remain accepted.

`talking-about-topics-v1` teaches о/об + prepositional with familiar nouns. The explanation distinguishes sound from spelling and does not generalise об to every vowel letter. Pronoun forms and broader noun classes remain further work. Both units teach the tested forms before practice and link to ordinary Writing and Speaking. Their Writing criteria observe communication, not independent grammatical mastery.

The source allocations now point these three requirements to the new units. They remain partial, unvalidated practice. Adding a unit changes neither Journey passes nor a learner’s level. Sixty retained `g1` packs have unchanged identities and payloads.

New unit reading/listening uses a generated situation tied to the unit’s objectives, vocabulary, stored forms and declared facts. The detailed calendar plan tests written dates in reading and elapsed duration in listening; it does not assume that spoken ordinal dates have been taught. Accepted text is saved before audio preparation; retries retain the text and selected voice. The immutable task and recording then open in the existing player. Preparation, ownership, retries, media integrity, backups and imports have automated coverage. Browser playback completed with an actual generated recording in the earlier implementation pass.

The initial provider check found only one manually acceptable exercise in seven calls. A further eighteen calls tested language-specific plans for location/destination, dates/duration and conversation topics. These plans establish participants, related facts, timelines and full governed answer phrases before the model writes. Comprehension alternatives represent different meanings in grammatical Russian; they do not test case endings through deliberately broken options. Hints and explanations now use checked guidance and exact source quotes.

The last six-call batch passed five structural checks. The Russian forms and answer relationships improved, but some messages still contain filler or an awkward narrative voice. One failed vocabulary annotation was rejected. This is measurable progress, not proof of natural Russian or reliable whole-catalogue generation. The final removal of a sentence-count minimum has regression coverage but no fresh provider evaluation. See the [language-design evaluation](procedural-content.md#language-design-follow-up), including all failed samples. The other fourteen units still need equivalent linguistic plans, and the player still needs normal word lookup and saving for generated passages. This follow-up has not been deployed.

## Delivered in the repository

The Places topic now opens **Where shall we meet?**, a connected edition of the location/destination unit. Existing v1 URLs and saved work remain available.

The lesson teaches current place, destination and a meeting arrangement. Its eight sections cover teaching, contextual choices, typed forms, a short reading, a voice message, original Writing, two recorded replies and a new situation. Two transfer families change the people or the meeting plan. A learner can use the guided route or try the transfer task first. Earlier learning is advice, not an access lock.

The unit uses existing Comprehension, Writing, Speaking and practice stores. It does not create a second collection of learner answers. Each run keeps a frozen manifest and task assets. Reading a page does not allocate tasks or call a provider. Start, retry and navigation writes have request receipts and revision checks.

Typed practice drafts are saved separately from answers. Reading and Writing autosave during lesson tasks. They wait for an acknowledgement before marking text as saved, and finish saving before Check, model-answer help or navigation. Failed saves retain the text and offer retry; conflicting tabs offer a recoverable copy. Stable request receipts make lost acknowledgements safe to retry. Pending feedback prevents a late autosave from replacing its original.

Reading drafts have their own revision, so saving unfinished answers neither requests feedback nor counts as prior assistance. Saved feedback always displays the reviewed answers, even after a new draft is entered. Writing and reading submissions preserve their originals before requesting feedback. Review workers claim a bounded lease; a late worker cannot replace a newer claim. Failed feedback can be retried against the same original. Refreshing a page does not make another paid request.

Text review requests disable the SDK's automatic retries. A single request has a 60-second timeout, below the 180-second review lease. Hosted requests retain the existing allowance checks. A learner explicitly retries unavailable feedback against the saved original.

The Speaking task saves two original recordings against Nina's exact prompts. It can resume after the first reply. Review uses the recordings and their verified canonical waveform, not a corrected transcript. Each criterion is bound to the relevant reply's audio interval. Speech in the first reply cannot establish that the second question was answered. Silence can remain unscored. The exchange ends after the second reply. Permission failures, missing audio and unavailable feedback retain saved work.

## Assessment and support

`curriculum-task-v2` adds scoped grammar observations to original Writing and Speaking. It retains v1 validation and results. Communication and grammar are separate:

- An understandable destination can receive communication credit despite a wrong ending.
- Grammar scores are 0 for incorrect use, 1 for mixed correct and incorrect use, and 2 for correct use.
- A natural alternative outside the elicited construction is unscored for that construction. It is not an invented grammatical error.
- Missing or ambiguous evidence stays unscored, with a recorded reason.

Hints, transcripts, model examples and exact prior feedback affect the saved evidence condition. Ordinary earlier teaching does not mark every later task as assisted. Prior-feedback receipts remain fixed; later work cannot retroactively taint an earlier answer. Newly disclosed answers in another open session are captured before the current answer is committed.

Several listening questions can use one message. Correctness, the answer key and the full transcript stay hidden until those questions are finished, including in Profile. Opening the transcript explicitly marks later questions about that recording as supported. Earlier submitted answers keep their original support condition.

Listening recordings use an owned session endpoint. It serves only current or previously reached questions and verifies the frozen file hash. Browser seeking is supported. Fetching a recording does not mark it as heard. This works through the hosted `/demo` mount without making listening files available to anonymous static requests.

Transfer tasks use `unit-transfer-no-effects-v1`. Their child activities cannot award coins, Elo or Journey passes through legacy submission routes. Ordinary practice retains its existing effects. Recognition retries share the earlier unit's reward family, preventing duplicate rewards from changing editions.

Profile adds **Recent assessed work** with five compact domain rows. It keeps the diagnostic pilot separate from narrow unit observations. A later pending review does not erase earlier results. A multi-question task aggregates the latest reviewed answer to each question. Unsuccessful work links to relevant practice; insufficient evidence links to another situation. Drafts and unfinished feedback take priority. Speaking retains its unverified independence condition and displays known help separately. No new level score or proficiency gate is introduced.

Lesson completion offers one next lesson, **Where from and where to**, with results available in a collapsed section. Repeating practice remains an option. Writing feedback and grounded Speaking corrections can open Phrasebook or flashcard preparation. Nothing is added automatically. Phrasebook uses its existing form; selected words use the existing morphology, mnemonic and enrichment pipeline before opening the native generator. That generator creates new examples, rather than copying the correction into a card without its normal preparation. These actions are absent when the workspace cannot support them.

## Recordings and coverage

All 39 legacy unit recordings and both pilot recordings are now present. Seven existing clips were retained; 34 were generated. The connected sequence adds 19 distinct recordings, shared across 25 playback identities. Each published file has integrity and duration metadata. Random selection from the existing configured voices is retained.

The first sequence recording request failed. Read-only checks confirmed the configuration, and one explicit retry succeeded. The later batch completed without retries. Preparation scripts are bounded, preserve completed files and support a dry run. Missing or changed audio remains unavailable instead of becoming a failed learner score.

The delivery catalogue now allocates all 239 source requirements to candidate units and assessment families. Teaching, recognition, production and assessment are recorded separately. Draft and partial associations remain visible. A content count is not a proficiency percentage.

### A1 present-tense follow-up

The additional **Who is doing what?** unit teaches person and number through читать and говорить, including polite singular вы. It refreshes the subjects and useful words before testing them. Eight contextual choices include two short-message questions; six typed forms observe the taught endings. Its original Writing task measures understandable meaning only. It does not turn an intelligible message into evidence of general conjugation mastery.

Three new listening clips were generated from 244 characters without retries. The repository now has 42 legacy-style unit clips, two pilot clips and 19 connected-sequence recordings. Review fixture v4 adds 25 cases while retaining every v3 case and all earlier fixture files. The new unit appears before Time and daily routines under Daily activities. It adds no access gate and changes no existing unit or saved attempt.

Empty delivery-stage associations now mean **not mapped**, rather than declaring the content missing. The connected-sequence catalogue currently maps seven A1 requirements; the older authored-task inventory includes additional partial content. Both inventories must be considered when choosing further work.

The follow-up passed 78 focused content, review, recording and registry tests. A separate 79-test integration run passed for the sequence, complete walkthroughs, public and hosted demos, release export and ownership boundaries. The review exporter and generated coverage checks also passed. These runs followed the full-suite result below; the full application suite was not repeated for this additive content change.

## Verification

Focused checks cover ownership, CSRF, stale drafts, request replay, frozen content, immutable originals, provider failure, review leases, support receipts, reward boundaries, audio integrity and account imports. Backup copies original Speaking media and retires live review leases. Account import verifies those files; copying them into the destination remains a separate operational step. Unresolvable collisions in frozen references fail explicitly instead of rewriting learner originals. Imported review results must agree with their canonical attempts and criterion reports.

The real Writing provider was checked on four synthetic responses: correct forms, an incorrect destination ending, a natural alternative, and omitted details. An initial run incorrectly gave partial grammar credit for one wrong ending. The finite rubric was clarified; the next run passed all four expectations. The [saved result](validation/location-writing-smoke-2026-10-02.json) records original text, grounded judgements and assessor provenance. The test is reproducible with `scripts/check_curriculum_marking.py`, which defaults to a dry run. This small development check is not independent validation, and the cases are not a held-out evaluation set.

A bounded [original-audio check](validation/location-speaking-smoke-2026-10-02.json) used three synthesized clips and two audio reviews, without retries or a learner transcript supplied to the assessor. Correct destination grammar received 2/2; the intended wrong ending received 0/2 while communication credit was retained. The assessor's transcript retained the wrong ending. `scripts/check_curriculum_audio_marking.py` defaults to a dry run and refuses to overwrite a previous run. Synthetic source audio has not received an independent listening check, so this establishes provider behaviour on these fixtures, not reliable detection of errors in natural learner speech.

Browser checks use an isolated sample database. They cover the unit list, teaching, exact return to the owned run, typed draft save/reload/submission, desktop top navigation, desktop sidebar and 375px/440px mobile layouts. English and Russian UI, the compact Writing map, saved model-example disclosure and the five Profile domains were exercised. Listening playback reached its real `ended` event and unlocked the answers after 7.291 seconds. The tool did not provide audible content for pronunciation review, so this establishes browser playback behaviour, not the quality of the spoken Russian.

An anonymous hosted teaching clip also completed playback (1.625 seconds, HTTP 206). Only validated authored teaching recordings are publicly served; learner recordings and undisclosed listening content remain protected.

After correcting hosted Listening delivery, a fresh browser check used a disposable hosted `/demo` workspace. The owned recording returned HTTP 206, played to its `ended` event at 7.291 seconds, and saved the playback receipt. All three answer controls then became enabled. No answer was submitted and no provider call was made. This used the real hosted dispatcher locally; production playback still needs a deployment check.

API walkthroughs complete both the guided lesson and the challenge-first route using provider stubs and fixture recordings, locally and through the hosted `/demo` mount. They verify retained originals, all five Profile domains, ordinary practice rewards, zero transfer rewards, unattempted skipped practice, completion, and a fresh run selecting the other transfer family. The hosted walkthrough also fetches every required listening recording through its owned URL. Separate hosted checks exercise the real allowance and request limits before provider work. These are software integration checks; the stub marks are not evidence of assessment quality.

The full backend suite passed 1,940 tests across four isolated processes. The full UI suite passed 805 tests across 61 files; TypeScript checks and the production build passed. After the hosted audio correction, nine focused tests passed: four complete local/hosted walkthroughs and five access, range-request and file-integrity checks. A further 67 tests passed for existing listening, learning sessions, deferred feedback, public teaching audio and the provider-free demo. These results describe the local repository, not a deployed release.

## Storage and operations

Additive migrations 056–060 introduce lesson runs/bindings/receipts, draft and disclosure records, immutable pending review submissions, and the two-turn Speaking store. Back up the database and its media directory before deploying. The existing migration runner applies the additions. Do not copy a personal database into a public demo.

The provider-free preview exposes authored practice only and marks production tasks unavailable. Eligible guest and signed-in workspaces retain the existing provider allowance and rate-limit policies. The new endpoints do not increase the demo budget. The legacy unit remains a fallback; disabling a new catalogue entry must not delete saved runs or media.

No production deployment is implied by this record. Deployment and post-deployment playback checks must identify their actual environment and release.

## Remaining work

| Package | Still required |
| --- | --- |
| P0 | Source-edition reconciliation beyond the existing mapping; audible browser/device checks and pronunciation review. Existing recordings are retained. New audio should be created on demand, not through a required stock batch. |
| P1 | Audible review on target devices; a real microphone walkthrough; evaluate marking on natural learner speech, including ASR disagreement; test the full path with learners. The automated local/hosted walkthrough and bounded synthetic-audio check are complete. |
| P2 | Improve generated prose and prerequisite control; measure fresh seeds and add linguistic plans for the remaining fourteen units. Three detailed plans and checked feedback are implemented and evaluated, with quality gaps recorded. Connect passage vocabulary to the existing lookup and enrichment pipeline. Fill remaining A1 teaching, lexical-class and original-production gaps. Partial practice does not establish whole-level coverage. |
| P3 | Define and author a broader assessment blueprint. Compare marking against independent judgements and held-out responses. Validate replay, retakes, task breadth and any proposed pass policy. |
| P4 | Author and evaluate A2, B1 and B2 teaching and five-domain assessments. Their requirement allocations are plans, not delivered courses. |

The application remains usable without a tutor. Independent review and learner trials are product validation work; they do not hold a learner's practice behind an approval screen.
