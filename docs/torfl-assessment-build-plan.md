# TORFL curriculum and assessment delivery plan

**Implementation specification draft: 2 October 2026. Code baseline: `ba9bee7`; initial document: `8fdb608`.**

This document defines the remaining work needed for Russian Arcade to teach and assess the published requirements of A1–B2 Russian. The supplied *ТРКИ-I* training book provides a concrete B1 example of what learners must eventually do.

It supplements the [curriculum implementation plan](curriculum-uplift-plan.md). The current implementation is recorded below. The lesson designs, new routes, schemas and UI behaviour elsewhere in this document are proposed implementation decisions, not shipped functionality. P0 and P1 are specified first; later assessment thresholds remain subject to validation.

Read by purpose:

- [Russian foundations](#russian-language-sequence) and [the first complete lesson](#first-complete-learning-sequence).
- [Screens and navigation](#screens-and-navigation), [save and recovery rules](#save-and-recovery-rules), and [workspace capabilities](#workspace-capabilities).
- [Sequence storage and API](#sequence-storage-and-api), [production marking](#production-marking-contract), and [profile results](#profile-results-and-next-actions).
- [Coverage records](#coverage-records), [delivery packages](#delivery-packages), and [acceptance walkthroughs](#acceptance-walkthroughs).

## Intended outcome

A learner should be able to learn a language feature, practise it with help, then use it independently in a new situation. This must work across vocabulary and grammar, reading, listening, writing and speaking.

The application should report what it has actually assessed. Completing a topic, remembering a flashcard or passing a Journey checkpoint does not establish a TORFL level. A future full-level result should say **“Russian Arcade B1 assessment passed”**, identify the assessment version and show the five domain results. Claiming that this predicts success in an official exam requires separate validation. The app cannot issue a TORFL certificate.

Learners use the application independently. Content review and comparisons with qualified assessors are product-quality work for the maintainers. They never require learners to arrange lessons with a tutor or wait for a human to approve their answers.

## Current implementation

The repository already contains most of the necessary infrastructure. Content coverage and evidence quality are the larger gaps.

| Area | Implemented | Remaining work |
| --- | --- | --- |
| Requirements | 239 source-linked specifications across A1–B2; later levels inherit earlier scope. | Reconcile the inventory against the chosen source editions and assessment blueprints. |
| Teaching | 13 authored A1 units with classified examples, controlled responses and Writing briefs. | Complete A1 coverage and sequence prerequisites; author later levels. |
| Listening | Two complete unit packs, containing six recordings, are exposed as available. | Prepare and verify the remaining unit recordings and both pilot recordings. |
| Activity evidence | Versioned criteria, saved responses and scoped adapters for existing activities. | Complete a connected learning sequence and verify each adapter's limits. |
| Assessment | Resumable A1 diagnostic with two forms per domain. Original responses and assistance are retained. | Broader sampling, spoken interaction, calibration and a separately versioned full-level policy. |
| B1 delivery | 50 B1 requirement entries and generated practice. | The coverage inventory has no allocated, statically authored B1 reference tasks. |
| Progression | Elo, coins and permanent Journey passes have separate purposes. | Introduce any future level gate through a new release, preserving existing progress. |

The current pilot samples six language-use choices, three reading questions, three listening questions, one written message and one recorded introduction. It is too small to establish full-level proficiency. The speaking sample does not test interaction.

The [validation record](curriculum-validation.md) records no independent language review or learner trial. Its last provider allowance is historical, not a current account check. Recheck recording availability and allowance before planning paid generation. The [coverage inventory](curriculum-coverage.md) excludes runtime-generated tasks; an empty authored B1 row does not mean learners have no B1 practice.

## Exam sources and assessment rules

TRKI and TORFL name the same testing system. **ТРКИ-I is B1**, following the elementary A1 and basic A2 levels. The supplied book is a 2004 training publication, not a universal description of every current test administration.

| Domain | What the supplied B1 book demonstrates | Design consequence |
| --- | --- | --- |
| Vocabulary and grammar | 165 items in 60 minutes; contextual vocabulary, word forms, case requirements, aspect, motion and sentence structure. | Assess distinctions in context, including production where the requirement calls for it. |
| Reading | Three texts and 20 questions in 50 minutes. | Include different text purposes and comprehension demands. One short passage is insufficient. |
| Listening | Six texts and 32 items; material is heard once under the stated instructions. | Use varied spoken material and explicit replay rules. A visible transcript changes the evidence. |
| Writing | Two tasks in 60 minutes, including connected retelling with a response and a practical letter. | Require original connected writing that fulfils a communicative purpose. |
| Speaking | Twelve tasks: replying, initiating exchanges, retelling and an extended account. | Include interactive and sustained speech. Choosing a supplied reply cannot substitute for speaking. |

These details come from PDF pages 4, 25, 31, 41–47; references here use PDF page numbers. The book's approximately 75% self-check thresholds differ from the [66% per-subtest rule published by SPbPU](https://www.spbstu.ru/international-cooperation/international-educational-programs/international-programs-of-additional-education/russian-foreign-language/testing-russian-foreign-language/). [Herzen](https://herzen.spb.ru/about/struct-uni/centers/tsentr-testirovaniya/trki/) also publishes a shorter B1 speaking duration than this book. Store provider, source edition, test format and scoring rules together. Select rules for a named format, rather than combining convenient parts of different tests.

Use published requirements to author original tasks. Do not publish the attached book, copy its passages into the application or treat its included scripts as available audio recordings.

### Required blueprint

An assessment blueprint specifies what a test measures and how it runs. Before authoring a full-level test, define:

- Source requirements, inherited prerequisites and excluded scope.
- Task types, text genres, response modes and coverage within each domain.
- Timing, dictionary access, preparation time, replay and assistance rules.
- Marking criteria, domain weights, essential requirements and treatment of missing evidence.
- Retake rules, prior exposure and how alternative forms will be compared.
- The release claim: practice, diagnostic, app assessment or evidence of exam readiness.

The training book informs the B1 blueprint. It does not set the difficulty of introductory A1 lessons. A percentage from a long official test cannot be transplanted onto an eight-question game.

## Teaching and coverage

Keep the existing 50 topics as the curriculum's browsing structure. A topic such as Family can support several levels, depending on the language and communication required. Topic placement and word difficulty remain separate from proficiency assessment.

For every requirement, record teaching, supported recognition, production where relevant, and independent assessment separately. Each needs a content reference, version and status: missing, draft, reviewed or released. Record prerequisites and source locators as well. Prompt instructions that merely mention a feature do not count as coverage.

Use the existing [coverage inventory](curriculum-coverage.md) to expose missing work. Counts describe authored material, not a percentage of the learner's Russian proficiency. Broad requirements such as spoken interaction need several different observations.

### Russian language sequence

Begin with useful expressions and explain the pattern before testing a contrast. For example, teach *мой брат* and *моя сестра* with a short explanation of noun gender before asking the learner to choose a possessive form. Do not expect an English speaker to infer Russian agreement from an unexplained wrong answer.

Teach case through its function: a location, destination, object, recipient, companion or missing item. Connect the function to the verb or preposition and then to the required form. Revisit forms across different nouns and contexts. Case-table recall alone is insufficient.

Treat aspect and motion as distinctions in meaning. Supply enough context to distinguish a journey now from repeated travel, walking from transport, or an activity from its completed result. Avoid questions where several verbs are natural but only one happens to be in the answer key. Introduce prefixes and more complex distinctions according to the source requirement and prerequisites.

At B1, develop connected accounts, practical exchanges, clarification, retelling and explaining a view. At B2, extend interpretation, argument, register and more demanding discourse. Detailed scope remains in the [requirements catalogue](curriculum-requirements.md); this document does not replace it with another topic list.

Use the following order to organise the remaining A1 work. It is a recommended teaching sequence, not a set of access locks or a replacement for the existing introductory lessons.

| Foundation | Learner can do | Existing material to develop |
| --- | --- | --- |
| Sounds, words and familiar expressions | Recognise essential Cyrillic words, hear them and use a greeting or short fixed expression. | First steps; optional sound/letter help when needed. Do not require an alphabet exam to begin. |
| People, things and descriptions | Identify someone or something; understand gender and simple agreement before choosing forms. | Personal reference, noun/adjective agreement, greetings and requests. |
| Having, needing and giving | Say what is available, missing or needed, and who receives something. | Possession/absence, objects/recipients, needs/company. |
| Place, destination and travel | Distinguish where someone is, where they are going and how they travel. | Location/destination first; then origins and basic motion. |
| Time, quantity and actions | Arrange a time, describe a routine and distinguish an activity from its result. | Time/routine, numbers/quantities, action/aspect. |
| Connected communication | Combine familiar patterns into a useful message, explanation or exchange. | Connected messages plus cumulative tasks in Comprehension, Writing and Speaking. |

Each teaching group contains a named function, one short explanation and two or three contrasting examples. Introduce terms such as “accusative” after explaining the job the form does. Word audio belongs inside its word/example control. Full translations and additional grammar stay behind optional help. Keep instruction language consistent with the selected UI language and Russian answers in Russian.

Revisit earlier language in later tasks. A successful answer can lead to a less supported example; a mistake offers the relevant contrast and another attempt. The learner may continue either way. This is task selection within a lesson, not an Elo-driven proficiency claim. A unit should use only activities that serve its objective; testing the five-domain infrastructure does not require forcing five activities into every future lesson.

### Vocabulary and morphology

Retain the [lemma-centred database and linked forms](vocabulary-data-model.md). A task needs the word as used, its lemma, relevant grammatical features and its sentence context. Its English explanation belongs to that use; it must not become a supposedly universal translation of the lemma. Preserve ambiguity where homographs or several readings are possible.

Use mostly familiar vocabulary with a deliberate amount of new language. Words saved to the vocabulary store must pass through the existing enrichment pipeline, including the mnemonic and form-generation steps. Assessment text may contain unfamiliar words without automatically adding them to the learner's collection or requiring a database entry for every word.

Keep the normal rarity and participle filters for general card generation. Where a published requirement needs a form those filters exclude, request it explicitly for that requirement and validate it. Do not disable the filters globally or demand every rare form as a completion condition.

## First complete learning sequence

Build **Where shall we meet?** from the existing `location-destination-v1` unit and verified recordings. Publish changed teaching and tasks as `location-destination-v2`, with `location-destination-sequence-v1` identifying the new sequence. Preserve old URLs, contracts and attempts. Place it after introductory vocabulary and sentence patterns, not immediately after the learner's first three words.

The practical purpose is to help a friend find you. Use a small map with a school, park and library. Position and destination must be visually distinct. Use ordinary reusable artwork or an accessible HTML/SVG diagram; generating several new pictures per attempt is unnecessary. The diagram's text alternative describes the same scene, without supplying an extra grammatical answer.

Before practice, teach *сейчас*, *потом*, *в*, the three place nouns and the required forms of *идти* in the examples. Teach *Встретимся в библиотеке* (“Let's meet at the library”) as a useful whole expression, with audio, before requiring a meeting message. A short optional refresher covers unfamiliar words. This supports beginners without turning prerequisite knowledge into a lock. The existing post-office examples and movement-within-a-place contrast can follow once the first pair is understood.

| Step | Learner experience | Evidence |
| --- | --- | --- |
| Learn | Pair *Анна в школе* with *Анна идёт в школу*. Move the same character from a position marker to a destination arrow. Explain the change in meaning and ending. | Teaching viewed, not mastery. |
| Practise | Four contextual choices and three typed forms. Begin with школа, then transfer the pattern to библиотека and парк. Include *гуляем в парке* after explaining movement within a place. | Separate recognition and controlled-production criteria. |
| Read | A short message gives current location and destination. Three questions distinguish those details and the meeting place. Distractors refer to places in the message, not unrelated pictures. | Reading information, not production of endings. |
| Listen | A separate voice message supplies a different meeting plan. Three questions require hearing its information; the reading task must not reveal the answers. | Listening under recorded support conditions. |
| Write | Choose a starting place and destination from the map. Write a friend a short message saying where you are, where you are going and where to meet. No minimum word count. | Original communication plus separately marked, elicited forms. |
| Speak | Answer *Где ты сейчас?* and *А куда ты идёшь?* in a brief exchange. Use the same chosen places, but provide original speech. | Two original turns, task completion and narrow grammar observations. |
| Try a new situation | Resolve a new meeting arrangement from unfamiliar messages, then provide a short written and spoken reply. Use separate tasks for the domain observations. | Transfer within this scope, not an A1 pass. |

The counts above are P1 content budgets, not exam sampling claims. Russian texts and distractors must receive language checks before publication. A reading question can test meaning without demanding a case name. A grammar task must make its intended distinction clear.

For the spoken exchange, Nina greets the learner and asks their location. After a submitted response, she acknowledges it briefly and asks their destination. She then closes with *Хорошо, до встречи!* The interlocutor must not supply or correct the target form before the learner's relevant turn. Record unexpected help as assistance. If the response is unclear, allow one neutral repeat of the question; do not silently repair the response. Detailed feedback follows the exchange.

Publish two transfer families. One requires tracking two people with different starting places before deciding where to meet. The other contains an initial meeting plan and a later update, requiring the learner to distinguish old information from the final plan. Teach any connective words beforehand. The change is in the information to resolve, not just the names of the places. A later B1 version can add explaining a changed appointment and resolving a misunderstanding; P1 must remain A1.

After feedback, offer **Save sentence** to Phrasebook or **Make a flashcard** for a useful contextual form only when the workspace permits those operations. Reuse the existing flows, including vocabulary enrichment, images and audio. Preserve the original response separately from a corrected study sentence; nothing is added automatically. A corrective practice link can use a game only when its adapter can select the required contrast and the learner owns it; otherwise link to the relevant unit exercise. These optional follow-ups belong below the result, not between every question.

**Complete when:** supported workspaces can run all five domains, save and resume, recover feedback, and show scoped results in Profile. Original live speech remains labelled as practice with unverified independence. The transfer tasks can record absence of in-app help; they cannot establish proctored conditions. This demonstrates the workflow for one requirement cluster, not full A1 coverage.

## Assessment and feedback

### Evidence by domain

| Domain | What to assess | What must not substitute for it |
| --- | --- | --- |
| Vocabulary and grammar | Meaningful word choices, grammatical forms, case requirements and sentence construction within the declared scope. | Word totals, flashcard ratings or grammar that happened to appear in a prompt. |
| Reading | Understanding purpose, detail, reference and relationships in unfamiliar texts at the level. | Remembering a passage already taught or translating isolated words. |
| Listening | Understanding information and intent in recordings under the declared playback conditions. | Reading a transcript or scoring a recording that never played. |
| Writing | Completing a task through original text, with appropriate organisation, language and register. | Selecting, copying or lightly modifying a supplied model answer. |
| Speaking | Original speech, intelligibility, fluency, task completion and interaction where required. | Multiple-choice replies or an automatically corrected transcript. |

Separate communication from accuracy. A wrong ending can lose the relevant grammar credit while the message remains understandable. In reading and listening, a grammatical error in a short answer must not erase clearly demonstrated comprehension. Score any declared grammatical criterion separately.

Accept natural alternatives. If a valid paraphrase avoids the requested grammatical feature, record the feature as unobserved rather than calling the whole answer wrong. Make the intended feature explicit in controlled-form exercises.

### Original speech

Preserve microphone audio before transcription or review. Automatic speech recognition can normalise incorrect declensions and conjugations; a clean transcript cannot establish that the learner spoke correctly. Mark disputed grammar from the audio, with a time reference where possible. Keep recogniser output separate from suggested corrections.

Fluency needs evidence about continuity, pauses, repairs and completion, interpreted for the level. Speed alone is not fluency. Intelligibility should not penalise an accent merely for differing from a native accent.

Test the pipeline with recorded incorrect case and conjugation examples, natural hesitations, acceptable accents, silence and background speech. Compare the original recording with transcription and evaluator findings. Where the system cannot distinguish an error from recognition uncertainty, leave that criterion unscored and explain the limitation briefly.

### Independence and variation

Record hints, translations, transcripts, model answers, prior feedback and replay when they are exposed. An empty support log does not establish independent performance; current live Speaking records independence as unverified. Distinguish “no help recorded” from verified assessment conditions.

Use several authored forms before allowing generated assessment variation. Generated content needs checks for answer ambiguity, actual level, grammatical accuracy, plausible context, audio and rubric compatibility. Freeze the accepted task before the learner starts. Do not let the response model invent the scoring contract afterward.

Retain exposure history. Retries are useful practice, but familiarity must not be mistaken for transfer. Different seeds do not automatically produce equally difficult tests.

### Results and validation

The diagnostic remains available without a pass gate. A future full-level pass requires adequate evidence in all five domains, with each meeting its declared minimum. A high score in one domain cannot compensate for a failed or unmeasured domain. Unavailable audio, failed providers and insufficient responses are distinct from demonstrated incorrect answers.

Before releasing a consequential pass policy, compare the app's marking with qualified independent marking on a representative response set. Include borderline work, valid alternatives and typical learner errors. Use a separate set to evaluate the policy after tuning. Record disagreement, false passes, false failures, unscored cases and reviewer adjudication.

Define the evaluation protocol, sample composition and acceptable error limits before inspecting final results. Reviewer agreement alone does not establish exam prediction; that stronger claim needs evidence against actual exam performance. Until then, report the app result and its scope honestly.

Feedback should start with what the learner communicated, then identify the most useful correction with an example. Keep detailed criteria available on request. Avoid grammar lectures, mixed-language terminology and a page of criticism for a small mistake.

## Profile, Journey and access

Reuse the profile overview. Show each domain's latest result, assessed scope, date and useful next action. “Not assessed” is a valid state. Do not add another readiness percentage or progress bar.

Keep the three existing mechanisms distinct:

- **Lingocoins** reward practice and buy games.
- **Elo** provides provisional skill estimates. It does not currently select difficulty or award a level.
- **Journey passes** advance the published course under that release's rules.

Useful work from any activity can contribute relevant preparation. Learners need not follow Journey to receive credit. Preparation should recommend a checkpoint, not require attendance or a fixed number of pages. Preserve selectable practice levels and early challenges for prior knowledge.

Future full-level assessment belongs alongside these records. Do not reinterpret existing Journey passes as proficiency certificates or remove earned access when requirements expand. Four milestones are course sections, not four mathematically equal quarters of A1.

Keep the curriculum an overview of what can be learned; keep Barsik's story in Journey. Explain checkpoint requirements at the point of entry. Put the task, audio and response controls near the top of the screen, with optional detail below. Preserve the compact profile and activity layouts.

## Implementation approach

Extend the existing services rather than creating another learning or assessment subsystem.

| Responsibility | Existing implementation to extend |
| --- | --- |
| Source requirements and definition links | `data/torfl/*.json`, `services/torfl_requirements.py`, `services/curriculum_requirement_map.py` |
| Teaching and unit media | `data/curriculum_units/`, `services/curriculum_units.py` |
| Task scope and criterion reports | `contracts/curriculum.py`, existing activity adapters and `services/activity_evidence.py` |
| Original speech evidence | `services/speaking_evidence.py` and existing Speaking recording/review services |
| Resumable assessment | `services/assessment_pilot*.py`, `repositories/assessment_pilot_repository.py` |
| Ratings and permanent passes | `services/skill_progress.py`, `services/course_progression.py` |

Paths in this table are relative to `flask_vocab_app/`. Current curriculum contracts accept only `practice` and `diagnostic` purposes. Introduce a named, versioned assessment contract before enabling a consequential gate. Do not weaken the existing validator or silently promote diagnostic results.

Keep authored requirements, blueprints and rubrics in versioned files. Extend relational storage only where attempts and queries require it. Reuse immutable task identities, owned submissions, review retries and idempotency controls.

Each assessment result must remain traceable to its source edition, blueprint, task and rubric versions; original response and media identity; support and exposure history; reviewer/model configuration; criterion findings; and pass-policy version, if applicable. Extend existing records where these fields are missing. Store model configuration identifiers, never credentials.

A corrected task gets a new content version. Preserve earlier prompts, answers, scores and access. Any proposed re-evaluation should be a separate recorded result, never a silent overwrite.

## Screens and navigation

The unit page is the lesson's entry and return point. It shows one outcome, one recommended action and a compact list of activities. The learner can open any available activity. A prerequisite note links to help; it never disables Start. Do not add lesson setup forms that ask again for a level or topic already fixed by the unit.

| Surface | Route and implementation | Required P1 behaviour |
| --- | --- | --- |
| Lesson | New `/curriculum/units/location-destination-v2`; extend `templates/curriculum_unit.html` and `blueprints/curriculum.py`. | **Start lesson**, then **Continue: [activity]**. A `run` query identifies a saved run; validate its owner and unit. Keep v1 readable. |
| Choices, forms, listening | Existing `/#practice/<session>` and `ui/src/Practice.tsx`. | Show the unit backlink and current activity. Reuse answer checking and audio controls; add drafts and sequence-aware continuation. |
| Reading | Existing `/comprehension/load/<id>`. | New authored passage/question adapter; bind immutable questions and support receipts. Do not regenerate a passage when reopening it. |
| Writing | Existing `/writing/load/<id>` and editor. | Load the linked draft, retain checked versions, show the unit return/next action. Scope newly allocated tasks to the run. |
| Speaking | Existing Speaking workspace with a new internal `unit_exchange` task variant. | Two authored spoken prompts, original microphone responses and a natural closing line. Reuse recording/storage/review services; no new advertised activity or mode toggle. |
| Transfer | Same activity players, with a pinned transfer family. | Clearly identify the new situation, preserve help/exposure conditions and show a scoped result. Keep the separate `#assessment` pilot unchanged. |
| Profile | Existing selected-learner profile surface. | Five compact assessed-domain rows using the projection below. Preserve local profile selection and account settings. |

Routes above are canonical app routes, not hard-coded deployment paths. Generate links with the existing workspace-aware helpers so `/demo/` navigation, APIs and media remain in that workspace. A client-supplied return URL cannot override the server's owned task binding.

Use the current activity header and layout components. A representative task should read as follows:

```text
← Where shall we meet?                              Listening

Where is Nina going?
[Listen ↻]                     [Optional hint]

( ) В школу.    ( ) В парк.    ( ) В библиотеку.

[Check answer]
```

This is a layout example for a task with explicit submission, not an answer key or final recording script. Preserve immediate submission where the existing practice choice buttons already use it; do not add a second click throughout that player. Put the question above optional explanation. A small map is useful for teaching and scene-based replies; hide it when it would reveal a listening answer. After checking, show concise feedback and **Continue to Writing**. Do not insert a separate saved-confirmation page.

At 1280×800 and 1440×900, the active prompt and first response control must fit above the fold with the normal app navigation visible. At 390×844, use a single column, with no horizontal overflow or floating controls covering the response. Test top navigation and sidebar layouts. Use one textual activity label; do not add another progress bar. Long reading texts can scroll naturally.

On entry, focus the task heading without unexpected scroll jumps. On checking, announce feedback without moving focus to the page top. Audio buttons need useful accessible names and keyboard operation. Respect reduced motion. Keep English and Russian interface strings paired; grammatical answers and spoken prompts remain Russian.

### Continue and revisit rules

1. **Start lesson** creates or resumes the unfinished run for that exact sequence version. Opening the page alone never creates work or calls a model.
2. **Continue** returns to the most recently opened available, editable unfinished activity. Otherwise select the next available activity in the manifest. Pending/failed reviews have their own open/retry action, rather than blocking every recommendation. Skipped activities remain available in the lesson list.
3. **Back to lesson** flushes the draft, pauses playback and returns to the same run. A failed save keeps the learner on the task with **Retry save** and an explicit **Leave without saving** option. Revisiting teaching never clears answers or support history.
4. A reviewed wrong answer completes that task's interaction. Offer focused practice as a secondary action; do not trap the learner until correct.
5. Reopening completed work shows the submitted response and feedback. **Practise again** explicitly creates a new attempt. Earlier responses remain accessible.
6. **Try a new situation** is available as a secondary challenge from the lesson entry. Prior knowledge does not require visiting every explanation.
7. For a new run, **Start lesson** selects the guided completion path; **Try a new situation** selects the challenge path. Resuming preserves the saved choice. The learner can explicitly switch to the challenge without clearing work. When that path's required responses have been reviewed, show **Lesson finished** and one next-unit recommendation. Skipped practice is not falsely marked completed. Missing or unavailable required work never counts as finished.

## Save and recovery rules

| Boundary | Save rule | Recovery and visible state |
| --- | --- | --- |
| Editable text or an unsubmitted selection | Debounce draft saves by 800 ms; flush before in-app navigation and submission. Preserve immediate-submit behaviour on existing choice tasks. | **Saving…** becomes **Saved** only after acknowledgement. Failed saves retain input and offer retry. |
| Check answer or Send reply | Save an immutable owned response before review; deduplicate by submission ID. | Review failure says **Your reply is saved. Feedback is unavailable.** Retry reviews that same response. |
| Recording | Keep an unsubmitted preview in memory. Explicit Send persists the original audio before the interlocutor continues. | Navigating with unsent audio asks to stay or discard. Never claim it survives refresh; reuse the existing recorder's navigation guard. |
| Mid-exchange exit | Each sent turn is durable and linked to the frozen interlocutor prompt. | Resume at the first unsent turn; do not rerecord earlier turns or regenerate the prompt. |
| Two tabs | Compare expected revisions on draft and run writes. | A stale save cannot overwrite newer work. Preserve the local input and offer reload/copy before replacement. |
| Audio unavailable | Keep answers/drafts, show **Audio unavailable** and retry playback. | A transcript can support practice, but cannot manufacture listening evidence. |
| Microphone denied | Keep the task and offer permission retry or another activity. | Typed text can be practice; it cannot become a speaking result. |
| Provider or budget unavailable | Keep the original; return a retryable availability reason. | No zero score, lost draft, automatic paid retry or fabricated pass. |
| Profile change or demo expiry | Stop writes under the old identity; retain unsent text in the current view where possible. | Explain that the workspace changed or expired. Never attach old work to the new profile automatically. |

Where an existing activity lacks durable drafts, add them to that activity's owned store. For the general practice player, add a proposed `learning_session_drafts` record keyed by session and item, with response JSON, revision and update time. A draft is not an answer, reward or criterion observation. Reuse the Writing and assessment draft mechanisms where present. Browser unload cannot guarantee a final save; the interface must report that accurately.

### Help and transfer conditions

Teaching and supported practice allow word help, translations, hints, examples and normal replay. Transfer starts with help closed; the same support remains available so a learner is never stranded. Persist disclosure before returning answer-revealing content, and retain it in subsequent attempts on that task.

Learning a pattern earlier is not itself assistance on every later task. Track help against the current task and exposure family. Exact prior answers, feedback or a model that supplies the current response affect the evidence condition; ordinary earlier teaching does not make independent use of learned Russian impossible.

P1 diagnostic listening permits replay and records its use. It does not imitate a one-play examination. A transcript or translation marks the relevant result as supported. Text size, keyboard access and focus aids do not. Do not present a listening transcript before the learner chooses it.

Use conditions `unaided_in_app`, `assisted` and `unverified` in the proposed summary contract. The first means no declared answer-supporting disclosure was observed; it does not mean proctored or externally verified. All P1 original speech, including `unit_exchange`, remains `unverified`; retain any observed assistance separately. Show **With help** where relevant, and keep the explanation of conditions in result details rather than exposing these identifiers to the learner.

## Workspace capabilities

Resolve availability on the server for each activity. The unit read response returns capability and reason, so the UI does not infer access from a navigation label or from the presence of a provider key.

| Workspace | P1 scope |
| --- | --- |
| Local selected profile | Owned lesson runs and existing activities; paid feedback follows configured services. Originals survive review failure. |
| Signed-in hosted account | Same sequence in its private workspace; sign-in does not itself grant unlimited AI. |
| `/demo/` guest workspace | Existing temporary lifetime and spending controls. Offer only operations already permitted by its capability policy; preserve the `/demo/` prefix throughout. |
| Provider-free `PUBLIC_DEMO` preview | Authored teaching, choices, forms and available listening. Do not offer an apparently complete five-domain flow whose production steps are disabled. Link to the configured demo/sign-in entry if available. |
| Household learner | The existing legacy Writing path is restricted. Until an owned learner-accessible Writing adapter is delivered and checked, report partial unit availability. Do not introduce a new PIN or approval flow. |

P1's complete-path release check applies to local, signed-in and eligible guest workspaces with the needed services. The guest workspace is distinct from provider-free `PUBLIC_DEMO`: it can already permit the pilot under its configured flag, services and budget. Other modes must report their actual scope. A future household adapter should reuse Writing contracts and owned storage; it must not write into another person's legacy workspace. Signing in must not imply automatic import of temporary demo or local work.

The guest profile link currently leads to its temporary account page. Preserve that behaviour. Show the scoped results in the completed lesson's existing result area for guests, using the same projection as Profile, instead of pretending a permanent personal profile exists.

## Sequence storage and API

Use one small orchestration record to connect existing activities. It controls navigation, not mastery, grades, coins or Journey access. Proposed files are `services/curriculum_sequences.py`, `repositories/curriculum_sequence_repository.py` and a versioned `data/curriculum_sequences/` catalogue. Extend the existing curriculum blueprint.

Example manifest excerpt; each listed content ID is a proposed published asset, not an existing filename:

```json
{
  "schema_version": 1,
  "id": "location-destination-sequence-v1",
  "unit_id": "location-destination-v2",
  "level": "A1",
  "steps": [
    {"id": "learn", "adapter": "teaching", "content_id": "location-teaching-v2"},
    {"id": "choices", "adapter": "unit_practice", "content_id": "location-choices-v2"},
    {"id": "forms", "adapter": "unit_forms", "content_id": "location-forms-v2"},
    {"id": "reading", "adapter": "comprehension", "content_id": "location-reading-v1"},
    {"id": "listening", "adapter": "unit_listening", "content_id": "location-listening-v2"},
    {"id": "writing", "adapter": "writing", "content_id": "location-message-v2"},
    {"id": "speaking", "adapter": "unit_exchange", "content_id": "location-exchange-v1"},
    {"id": "transfer", "adapter": "task_group", "content_id": "location-transfer-v1", "effects_policy": "unit-transfer-no-effects-v1"}
  ],
  "completion_paths": {
    "guided": ["choices", "forms", "reading", "listening", "writing", "speaking", "transfer"],
    "challenge": ["transfer"]
  },
  "completion_policy": "responses-reviewed-v1"
}
```

The full manifest also pins content hashes, requirement/criterion IDs, prerequisite advice, support policy, remediation links and transfer-family definitions. A transfer group names its constituent task IDs and domains; it is not one undifferentiated score. Validate all references before publication. Reuse verified recordings by their existing hash where the new task's script and meaning are unchanged.

Add `curriculum_unit_runs` with an ID, profile owner, sequence ID, frozen manifest/hash, start request ID, activity bindings, selected completion path, navigation state, revision and timestamps. Bindings contain step ID, attempt ordinal and typed references to existing owned tasks/attempts. Do not copy responses, recordings or scores into this record. Derived completion comes from the authoritative activity stores. Teaching views are never required responses.

Enforce one unfinished run per profile and exact sequence version. Starting with the same request ID is idempotent. An explicit repeat after finishing starts another run. New standalone work does not silently replace a bound task; earlier standalone evidence remains available independently. The existing Writing helper's “latest task for this unit” lookup must not reuse an old task across different new runs: use the run/step allocation identity.

Store mutation receipts in proposed `curriculum_unit_requests`, keyed by profile and request ID, with operation, request hash and saved response. The same ID with different input is a conflict; a repeated identical request returns its first result. This follows the pilot's receipt pattern without putting unit requests into pilot tables.

| Proposed operation | Endpoint | Request and result |
| --- | --- | --- |
| Start/resume | `POST /api/v1/curriculum/units/<unit_id>/runs` | `submission_id`, `sequence_id`, initial `completion_path` (default `guided`); returns owned run and lesson URL. An existing run retains its saved path; changing it requires explicit navigation input. |
| Read | `GET /api/v1/curriculum/runs/<run_id>` | Returns step states, availability and next action; no task allocation or paid call. |
| Start/resume step | `POST /api/v1/curriculum/runs/<run_id>/steps/<step_id>/start` | `submission_id`, `expected_revision`; returns typed activity reference and workspace-aware URL. |
| Record navigation | `POST /api/v1/curriculum/runs/<run_id>/navigation` | Revision, request ID and opened/skipped step or explicit completion-path choice; never records mastery. |
| New practice/transfer form | `POST /api/v1/curriculum/runs/<run_id>/steps/<step_id>/retry` | Revision and request ID; creates a new bound attempt, preserving earlier work. |

Answers, drafts, support and review retries continue through their activity endpoints, with additive submission/review operations where an adapter lacks them. Unit Speaking requires a new owned task adapter for the two-turn prompt/recording bundle; reuse existing private audio, provider and budget services. Do not repurpose multiple-choice Step-through submissions as microphone responses. Keep the strict A1 pilot blueprint and its endpoints unchanged.

Current Writing and Comprehension assessed attempts are saved after successful feedback. For their new sequence adapters, add an immutable pending-submission record before calling a provider; a mutable draft is insufficient. A proposed `activity_review_submissions` table stores owner, activity/task identity, submission ID/request hash, original response, task/contract revision, support receipt IDs, review status/lease and final attempt reference. Reuse the pilot's lease/retry pattern without storing these submissions in pilot tables. Existing pilot and Speaking originals remain in their own stores.

Submission returns the saved response identity and review state. Explicit review/retry addresses that identity, not whatever is now in the editor. Do provider work outside the write transaction; revalidate the frozen submission and lease before committing the assessed attempt, applicable effects and receipt exactly once. A crashed or failed review leaves the original retryable. Legacy already-graded attempts are unchanged. Add owned submission/read/review operations under each affected activity API, following its current routing and CSRF conventions; new sequence bindings refer to the pending submission until its final attempt exists.

Allocation and binding must commit together where they share a database. Otherwise use a deterministic child request identity derived from run, step and attempt ordinal, so recovery finds the same task after a crash. A client cannot bind an arbitrary task. The server verifies workspace, profile, content and purpose before attaching it. Add the run envelope and draft records to existing backup/import validation.

Expose separate dimensions rather than combining all conditions into one status:

| Field | Values and meaning |
| --- | --- |
| `work_state` | `not_started`, `draft`, `submitted`, `reviewing`, `reviewed`, `review_unavailable` |
| `outcome` | `demonstrated_in_task`, `practise_and_retry`, `more_evidence_needed`, or null before a valid review |
| `availability` | `available`, `audio_unavailable`, `provider_unavailable`, `account_required`, `unsupported_workspace`, `budget_exhausted` |
| `condition` | `unaided_in_app`, `assisted`, `unverified`; never inferred from a score |

A reviewed incorrect response still completes the activity interaction. An insufficient-evidence report completes review but does not establish the criterion. Provider failure does neither. Keep unsupported activities explicit and offer the next available activity. A complete run means the selected path's required submissions were reviewed; it is not a level pass. Challenge completion does not fabricate practice attempts or awards for skipped activities.

Record transfer exposure when an owned form is first delivered, including abandoned work. Use stable `exposure_family_id` values across cosmetic revisions. Prefer an unseen family; once both families have been seen, label the next attempt **Revisit this situation**. The client cannot reset exposure by changing a seed or starting another run.

## Production marking contract

Introduce `curriculum-task-v2` with explicit validator dispatch. Preserve v1 validation, serialized contracts and issued results. P1 still permits only practice and diagnostic purposes; a new schema version is not permission to award proficiency.

Add `written_language_use` and `spoken_language_use` evidence scopes for a language-use requirement observed in original text or speech. Each needs a distinct application target, a frozen elicitation statement and a finite grammatical feature specification. This extends the currently restricted response-mode combinations rather than weakening their checks.

Example criterion excerpt, completed at publication with existing source references and a versioned rubric:

```json
{
  "id": "destination-form",
  "target_id": "unit.location-message-v2.destination-form",
  "requirement_id": "a1.language.accusative-destination",
  "response_mode": "independent_writing",
  "evidence_scope": "written_language_use",
  "expectation": "Assess the form used for an expressed destination with в or на.",
  "elicitation": "Tell your friend where you are going.",
  "feature": {"function": "destination", "prepositions": ["в", "на"], "case": "accusative"},
  "max_score": 2
}
```

For P1 Writing, use three separate binary communication criteria: current place understandable, destination understandable, and meeting place understandable. Mark location/destination forms separately. The grammar rubric is diagnostic: 2 for correct attributable use, 1 for mixed correct and incorrect use, 0 for clearly incorrect attempted use, null when the feature is not demonstrated or cannot be judged. A single use can demonstrate that task's feature, not mastery of the whole requirement. Do not sum communication and grammar into a supposed A1 percentage.

Add a v2 `reason_code` for null judgements: `feature_not_used`, `valid_alternative`, `insufficient_response` or `unclear_audio`. Require exact original text spans or valid audio intervals for scored observations. Silence and unrecognisable audio are insufficient evidence; a clear response that omits requested information can fail that communication criterion. Provider failure is a review state, not a learner judgement.

For an omitted communicative detail in an otherwise clear message, reference the full submitted message rather than inventing a quote for the missing words. Grammar absent from that message remains unobserved. Ending a spoken exchange after one turn leaves saved work to resume; it cannot complete the two-turn requirement.

| Original response or event | Required interpretation |
| --- | --- |
| *Я в школе. Иду в библиотеку. Встретимся в библиотеке.* | The three details and their relevant forms can receive credit. |
| *Я в школе. Иду в библиотека. Встретимся в библиотеке.* | The destination remains understandable; mark its ending incorrect without deleting communication credit. |
| *Я в школе. Иду к библиотеке. Встретимся у библиотеки.* | Accept the natural outside-meeting arrangement if consistent with the task facts. Destination with в/на is unobserved; do not invent an accusative error. |
| Only *Я в школе.* for the full message task | Current place can receive credit; required destination/meeting details are missing. No attempted destination form to grade. |
| Audio is ambiguous between two endings | Leave that grammatical criterion unscored. A normalised transcript cannot supply the missing evidence. |
| Correct reply copied from a revealed model | Retain the result as supported practice, not independent evidence. |

P1 Speaking uses two saved learner turns bound to the exact heard prompts. Score response relevance and whether the two requested details were communicated; add the scoped forms only where audible. Both turns are needed for the two-turn completion criterion. One fluent sentence cannot establish turn-taking or general fluency. Keep general fluency comments provisional until the broader speech rubric is evaluated.

The unit exchange uses authored prompts and an explicit end condition, not an unlimited conversation whose evaluator decides when enough has happened. It is a task inside Speaking. Existing open Fluent conversations remain available and retain their own grading and independence limits.

For a scoped task summary, derive `practise_and_retry` if any required criterion is partial or not satisfied; otherwise use `more_evidence_needed` if any is unscored; otherwise `demonstrated_in_task`. Show the individual findings in details. This rule is for P1 feedback and never creates a full-level result or compensates one domain with another.

### Rewards and progress effects

The lesson wrapper awards no extra coins, Elo, pass or entitlement. Ordinary unit practice and existing Writing/Speaking tasks retain their current activity reward rules and shared caps. For general unit practice, freeze a reward-family key per learning activity, shared by retries and cosmetic content revisions. Its published alias list includes the retained v1 content IDs representing that activity; check existing daily claims under those aliases before awarding. Never rewrite old reward entries. Writing and Speaking retain their existing adapter eligibility and duplicate rules. A new run or transfer family is not an extra reward source.

New transfer bindings freeze a server-owned `effects_policy: unit-transfer-no-effects-v1` and award no coins, Elo or Journey observations. They also have diagnostic purpose, but **purpose alone must not suppress effects**: existing ordinary Writing and Speaking can use diagnostic contracts while receiving normal rewards. Every transfer adapter checks the bound effects policy server-side before committing. Keep ordinary activity effects unchanged. Run completion and profile summaries are derived displays, never new reward events.

Requirement-definition links do not transfer grades. Existing preparation calculations remain authoritative. P1 scoped reports can recommend practice but cannot silently alter the current Journey bar or checkpoint policy. Any later eligible-observation bridge needs its own reviewed mapping and release tests.

## Profile results and next actions

Add **Recent assessed work** to the existing selected-learner profile, using five compact rows. Each shows domain, short result, scope, date and one action. A row might read **Writing · Include the meeting place · A1: places · 2 Oct · Open feedback**. Put the original response, criteria, assistance and history behind that link. Do not put a second set of ratings or progress bars beside it.

The existing Elo rows are activity estimates and do not map one-to-one to the five TORFL domains. Keep their labels and values intact. Build this projection from owned criterion reports and pilot components, not Elo, viewed pages, coins or Journey passes. Derive the domain from each criterion's requirement: destination endings belong under Language use, even when observed in Writing. One response can support findings in both domains, but must not count as two independent attempts.

Implement one shared projection service for the template and a proposed `GET /api/v1/curriculum/summary?level=A1` response. Resolve the selected profile from the authenticated workspace. Group by level, domain and scope. P1 displays A1; other recorded bands remain available in details without being merged into one result.

Selection rules are deterministic:

1. Within a scope, choose the latest successfully reviewed submission by submission time, then stable attempt ID. Review completion time must not let a delayed old review displace newer work.
2. Keep a newer pending or failed review visible separately. It does not erase the latest reviewed result.
3. A newer insufficient or supported result is shown honestly, with its condition; retain older results in history rather than choosing whichever looks best.
4. Keep broad pilot results and narrow unit observations in separate scope entries. A location exercise must never overwrite a five-domain check or become “A1 passed”. The row names the scope it displays.
5. Across scopes, prefer work in the current unfinished unit as the row's next action, otherwise the most recently submitted scope. A validated level result, when one exists in a later release, has its own preserved course-result entry.

Next-action order is: resume an unfinished draft; retry a saved failed review; resolve unavailable audio/service; offer a new example for insufficient evidence; offer the manifest's focused practice for a partial/incorrect criterion; otherwise continue to the next lesson activity. A user-selected activity always overrides a recommendation. No model chooses URLs or access rights.

The API returns typed result references, scope IDs, submission dates, conditions, a separate pending attempt and a server-built next action. Do not create another score table. An empty domain shows **Not assessed** with a relevant task link. Unavailable review shows **Reply saved; feedback unavailable**. Use “With help” only when support was actually disclosed, not merely because help was offered.

## Coverage records

Add a static, versioned `data/curriculum_coverage/` catalogue consumed by the existing coverage generator. Keep the current source/legacy definition map unchanged. Each requirement record contains separate arrays for teaching, recognition, production and assessment, plus applicability and an explanation for any non-applicable stage.

Every entry carries `content_id`, `content_version`, content hash, relevant criterion IDs, status (`draft`, `reviewed`, `released`), review kind/reference and an owning package. Empty applicable arrays render as missing. Internal model review and qualified external review remain distinguishable; neither label may imply that learners need a tutor.

Media readiness is a separate field derived from the expected recording hash and verified file. A released task with missing audio is released content with unavailable media. It must not disappear from the coverage report or count as playable. Validate references and hashes in CI; generate the Markdown report from this catalogue rather than maintaining another manual spreadsheet.

For P1, allocate these existing references explicitly:

| Reference ID | P1 observation |
| --- | --- |
| `a1.language.prepositional-location` | Location forms in the declared place phrases, through choices, typed forms and scoped original production. |
| `a1.language.accusative-destination` | Destination forms with в/на through the same distinct response modes. |
| `a1.reading.practical-information` | Current place, destination and meeting information in the authored message. |
| `a1.listening.short-message` | Requested information in the separate recording. |
| `a1.writing.personal-message` | A recipient, intelligible purpose and the three requested details in original text. |
| `a1.speaking.ask-and-answer` | Answering related everyday questions only; **partial** coverage. Learner-initiated questions remain future work for this reference. |
| `a1.speaking.intelligibility` | Whether the requested place information is understandable in these recordings; a narrow sample. |

Record `relation: partial` where content exercises only part of the source requirement. A released partial task leaves the remaining coverage gap visible. The publication check rejects missing/incompatible IDs and cannot mark a broad requirement complete just because one task refers to it. Report recognition, controlled production and original production separately.

P2 begins by assigning every inherited A1 requirement to a unit and an assessment family, or recording a visible gap. It does not require one exam question per requirement per learner. P3 samples the declared breadth through its assessment blueprint. Its item counts, score boundaries and retake-validity policy must be specified before authoring and tested before any consequential gate is enabled.

## Delivery packages

### P0 — Reconcile requirements and complete pilot recordings

Check the source inventory against the B1 book and the selected published requirements. Record each discrepancy with its source edition. Refresh the generated coverage report and separate drafted content from playable content.

Recheck the media queue. Prepare missing clips through the existing bounded pipeline, preserving verified recordings. Check pronunciation, stress, natural phrasing, level and speaker variation. Verify deployed files and browser playback before marking a pack available.

**Done when:** every existing unit and pilot recording is either verified or explicitly unavailable; the two pilot listening forms can be heard and scored under their declared rules; no stale allowance figure is presented as current. Missing recordings never yield a learner failure.

### P1 — Complete the A1 location/destination sequence

Deliver the sequence above through the existing unit, Comprehension, Writing and Speaking routes. Add the missing original-response criteria and a brief interaction task. Exercise both supported practice and the unfamiliar transfer task.

Build in this order:

| Work item | Concrete change | Depends on |
| --- | --- | --- |
| P1.1 Content and contracts | Publish v2 unit assets, two transfer families, coverage entries and `curriculum-task-v2` fixtures. Preserve v1 validation. | P0 source/audio inventory |
| P1.2 Owned sequence | Add run/receipt migration, manifest loader and API; implement allocation and navigation rules. | P1.1 |
| P1.3 Activity adapters | Bind authored Comprehension, new Writing tasks and two-turn Speaking; save immutable pending originals before review; enforce transfer effects policy. | P1.2 |
| P1.4 Interface and drafts | Update the unit template, existing players, origin/next actions and durable practice drafts. Verify both navigation layouts. | P1.2–3 |
| P1.5 Profile projection | Add scoped summaries and deterministic next actions using saved reports. | P1.3 |
| P1.6 Release rehearsal | Run the acceptance walkthroughs against copied sample workspaces, including failure and migration cases. | P1.4–5 |

Keep existing unit and pilot routes as the fallback until this sequence passes the complete-path checks. Deploy additive storage first, then enable the sequence catalogue entry. Disable new starts if rollback is needed; retained runs must still read their frozen content and saved responses.

**Done when:** all five domain paths save correct evidence, resume safely and appear in the profile; assistance remains distinguishable from independent work; natural alternatives and uncertain audio behave correctly. A novice can complete it without a tutor or unexplained grammatical jumps.

### P2 — Complete reviewed A1 teaching coverage

Use the inventory to fill gaps in the 13 existing units before adding unrelated activities. Sequence prerequisites and author missing examples, meaningful contrasts, listening and production tasks. Give each released requirement appropriate transfer tasks; broad communication requirements need several situations.

**Done when:** the reviewed A1 scope has teaching, supported practice and suitable assessment material, with verified audio for every released listening task. Every excluded or unsupported requirement is visible in the coverage report. Content checks include misleading distractors, unnatural Russian and answers that require untaught knowledge.

### P3 — Expand and evaluate the A1 assessment

Replace the small pilot's sampling limits through a new diagnostic blueprint. Add multiple reading/listening genres, sufficient language-use coverage, original writing and actual spoken interaction. Select task lengths, counts and scoring rules from the blueprint rather than copying the current pilot.

Run content review, marking comparisons, learner trials and usability checks. Revise disputed tasks and evaluate again on material not used for tuning. Keep assessment attempts diagnostic until evidence supports the proposed pass policy.

**Done when:** a dated validation report explains coverage, marking agreement, remaining uncertainty and the permitted result claim. Only then may a separately versioned app assessment policy and optional course release be enabled. Existing users retain their passes and access.

### P4 — Deliver A2, then B1 and B2

Apply the same process to each level. B1 source mapping and task design can start alongside A1 work, but must not be counted as delivered teaching. Use the supplied B1 book to check that the eventual course prepares learners for connected writing, practical dialogue, clarification, retelling and extended speech.

**Done when, for each level:** requirements and inherited scope are reconciled; teaching and all five domains are delivered; playable audio and varied tasks exist; marking and progression policies have their own validation report. Release each level separately.

## Release checks

For each package, check the changed behaviour at its appropriate level:

- **Language:** accurate Russian, justified level, sufficient context, correct stress and accepted alternatives. Automatic checks support editorial review; they do not prove linguistic quality.
- **Assessment:** support recorded before exposure, hidden answers absent from learner payloads, originals saved before review, uncertain evidence unscored, repeated forms identified and feedback tied to the submitted response.
- **Persistence:** ownership isolation, stale-version rejection, safe retries, duplicate-request protection and preserved historical attempts/access.
- **Audio:** actual playback in a clean browser, including mobile restrictions, pause/replay, unavailable files and microphone recovery. Verify sound, not only successful HTTP responses.
- **Interface:** task visible without excessive scrolling, usable keyboard controls, readable feedback and no duplicate progress indicators. Transcripts remain available for supported learning without becoming listening evidence.
- **Operations:** paid generation and review use the existing server-side spending/rate limits, including the demo's US$1 daily cap. Provider failure cannot lose work or award a pass. Do not send every practice attempt through multiple evaluators by default.

Measure content coverage, completion/abandonment, audio failures, review failures, marking disagreements and performance on unfamiliar tasks. Keep operational metrics separate from claims about learning or exam readiness. Use synthetic or consented responses for evaluation; never publish private learner recordings or tutor documents.

## Acceptance walkthroughs

These are required release cases, not a request for tests that merely repeat implementation details. Use fixture recordings and provider stubs for routine checks, then a small bounded real-provider check and audible browser playback for the paths that need them.

| Case | Expected observable result |
| --- | --- |
| Enter from Curriculum, then return from an activity | Same owned run and task; one recommended next action; no duplicate setup page. |
| Choose the early challenge and finish its reviewed tasks | Lesson can finish through the challenge path. Skipped practice stays unattempted; no extra rewards or proficiency claim. |
| Leave during a typed form or Writing draft | Acknowledged text and revision restore. Unacknowledged input is never labelled saved. |
| Refresh during review, then explicitly retry | One original submission remains; no second paid call from page load; retry attaches feedback to that original. |
| Double-click Start or replay a request after timeout | One run/task and receipt. Different input under the same request ID is rejected. |
| Open two tabs and edit the same draft | Stale write rejected, newer saved response retained, local text available to recover. |
| Submit the wrong-ending and valid-alternative examples above | Communication and grammar results differ exactly as specified; no zero for an unobserved form. |
| Play speech with deliberately wrong endings that ASR corrects | Audio-based review flags an audible error or abstains; corrected text is never accepted as proof of spoken correctness. |
| Complete only one learner turn | First turn is saved; second is resumable; no invented interaction success. |
| Reveal a transcript, then retry the question | Support remains attached. Later correctness does not restore an unaided listening claim. |
| Abandon both transfer forms, then try again | Both families remain exposed; revisit wording appears, without blocking practice. |
| New review pending after an earlier result | Profile retains the earlier reviewed result and shows pending work separately. Newer insufficient evidence stays visible once reviewed. |
| Finish all sequence tasks | One lesson completion display; only existing eligible activity rewards; no additional coins, Elo, Journey pass or level. Ordinary diagnostic Writing/Speaking still earn their existing rewards; transfer tasks do not. |
| Change profile, use another workspace's task URL, or expire a demo | No cross-profile read/write. Saved work remains owned by its original workspace and lifetime policy. |
| Upgrade content while a run is active | Old run resumes its original tasks and media; a new run uses the new manifest. Import/backup preserves both. |
| Missing audio, denied microphone or exhausted AI allowance | Useful recovery/alternative action, retained work and truthful unmeasured status; never a failed language score. |
| Desktop, mobile, English, Russian, top menu and sidebar | Prompt and response appear within the specified viewport; keyboard/focus/audio controls work; no duplicated progress UI. Repeat the complete path in an eligible guest workspace as well as local and signed-in profiles. |

Attach the exercised manifest IDs, fixture IDs, browser/device sizes and check results to the implementation record. Distinguish software verification, language review and learner evaluation. A green automated suite does not establish that an assessment predicts TORFL performance.

The immediate next work is **P0 followed by P1**. The final assessment blueprint, evaluation sample and pass policy remain decisions to resolve through source review and validation. This draft does not authorise a proficiency claim merely by listing the required work.

## Sources

- Андрюшина Н. П., Макова М. Н., Пращук Н. И. *Тренировочные тесты по русскому языку как иностранному. I сертификационный уровень*. Moscow, 2004. Supplied PDF; not redistributed. Domain instructions: PDF pp. 4, 25, 31, 41–47; self-check examples: pp. 23, 30, 32–33.
- [MSU B1 requirements](https://test.irlc.msu.ru/wp-content/uploads/2024/08/B1_trebovaniya.pdf), edition identified in the repository as 2007 print / 2009 electronic. The upload path is not the publication date.
- [SPbPU testing information](https://www.spbstu.ru/international-cooperation/international-educational-programs/international-programs-of-additional-education/russian-foreign-language/testing-russian-foreign-language/): level mapping, five subtests and the centre's published 66% rule.
- [Herzen testing centre](https://herzen.spb.ru/about/struct-uni/centers/tsentr-testirovaniya/trki/): published subtest timings, including the B1 speaking format.
- [Repository research and source policy](curriculum-research.md), [requirement specifications](curriculum-requirements.md), [implementation status](curriculum-implementation.md), [validation record](curriculum-validation.md) and [current milestone rules](course-milestones.md).

Provider web guidance was checked on 2 October 2026. Reconfirm it when pinning an exam-aligned blueprint. Historical materials remain useful evidence of task demands; they do not override a selected provider's current rules.
