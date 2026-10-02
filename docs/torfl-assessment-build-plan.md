# TORFL curriculum and assessment delivery plan

**Draft: 2 October 2026. Code baseline: `ba9bee7`.**

This document defines the remaining work needed for Russian Arcade to teach and assess the published requirements of A1–B2 Russian. The supplied *ТРКИ-I* training book provides a concrete B1 example of what learners must eventually do.

It supplements the [curriculum implementation plan](curriculum-uplift-plan.md). It does not replace the existing curriculum, add another progress system or change any learner's access. Everything under “Delivery packages” is proposed work unless explicitly described as implemented.

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

### Vocabulary and morphology

Retain the [lemma-centred database and linked forms](vocabulary-data-model.md). A task needs the word as used, its lemma, relevant grammatical features and its sentence context. Its English explanation belongs to that use; it must not become a supposedly universal translation of the lemma. Preserve ambiguity where homographs or several readings are possible.

Use mostly familiar vocabulary with a deliberate amount of new language. Words saved to the vocabulary store must pass through the existing enrichment pipeline, including the mnemonic and form-generation steps. Assessment text may contain unfamiliar words without automatically adding them to the learner's collection or requiring a database entry for every word.

Keep the normal rarity and participle filters for general card generation. Where a published requirement needs a form those filters exclude, request it explicitly for that requirement and validate it. Do not disable the filters globally or demand every rare form as a completion condition.

## First complete learning sequence

Finish the existing `location-destination-v1` unit first. It already has teaching and playable listening material. Place it after introductory vocabulary and sentence patterns, not immediately after the learner's first three words.

| Step | Learner experience | Evidence |
| --- | --- | --- |
| Explanation | Contrast *Где?* with *Куда?*: *Анна в школе* / *Анна идёт в школу*. Explain the meaning and form change. | Teaching viewed, not mastery. |
| Supported practice | Choose and type forms, with short explanations and optional hints. | The specified distinction, with support recorded. |
| Reading and listening | Understand where someone is and where they are going from a short message and a separate recording. | Comprehension of the stated details. |
| Writing | Write a short meeting message saying where you are and where you are going. | Original message, communicative details and relevant forms. |
| Speaking | Respond to a short spoken exchange and clarify a destination. | Original audio and a limited interaction criterion. |
| Transfer check | Complete a parallel situation with different people, places and information to resolve. | Performance without answer-revealing support on an unseen task. |

Use new information and a different communicative situation, not just swapped nouns. Keep the A1 exchange brief. A later B1 version might require explaining a changed appointment, resolving a misunderstanding and recounting what happened.

**Complete when:** a learner can move through the sequence, leave and resume, receive grounded feedback, retry an uncertain review, and see the results in the existing profile. All five domains must use real saved responses. This proves the workflow for one requirement cluster; it does not prove A1 coverage.

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

## Delivery packages

### P0 — Reconcile requirements and complete pilot recordings

Check the source inventory against the B1 book and the selected published requirements. Record each discrepancy with its source edition. Refresh the generated coverage report and separate drafted content from playable content.

Recheck the media queue. Prepare missing clips through the existing bounded pipeline, preserving verified recordings. Check pronunciation, stress, natural phrasing, level and speaker variation. Verify deployed files and browser playback before marking a pack available.

**Done when:** every existing unit and pilot recording is either verified or explicitly unavailable; the two pilot listening forms can be heard and scored under their declared rules; no stale allowance figure is presented as current. Missing recordings never yield a learner failure.

### P1 — Complete the A1 location/destination sequence

Deliver the sequence above through the existing unit, Comprehension, Writing and Speaking routes. Add the missing original-response criteria and a brief interaction task. Exercise both supported practice and the unfamiliar transfer task.

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

The immediate next work is **P0 followed by P1**. The final assessment blueprint, evaluation sample and pass policy remain decisions to resolve through source review and validation. This draft does not authorise a proficiency claim merely by listing the required work.

## Sources

- Андрюшина Н. П., Макова М. Н., Пращук Н. И. *Тренировочные тесты по русскому языку как иностранному. I сертификационный уровень*. Moscow, 2004. Supplied PDF; not redistributed. Domain instructions: PDF pp. 4, 25, 31, 41–47; self-check examples: pp. 23, 30, 32–33.
- [MSU B1 requirements](https://test.irlc.msu.ru/wp-content/uploads/2024/08/B1_trebovaniya.pdf), edition identified in the repository as 2007 print / 2009 electronic. The upload path is not the publication date.
- [SPbPU testing information](https://www.spbstu.ru/international-cooperation/international-educational-programs/international-programs-of-additional-education/russian-foreign-language/testing-russian-foreign-language/): level mapping, five subtests and the centre's published 66% rule.
- [Herzen testing centre](https://herzen.spb.ru/about/struct-uni/centers/tsentr-testirovaniya/trki/): published subtest timings, including the B1 speaking format.
- [Repository research and source policy](curriculum-research.md), [requirement specifications](curriculum-requirements.md), [implementation status](curriculum-implementation.md), [validation record](curriculum-validation.md) and [current milestone rules](course-milestones.md).

Provider web guidance was checked on 2 October 2026. Reconfirm it when pinning an exam-aligned blueprint. Historical materials remain useful evidence of task demands; they do not override a selected provider's current rules.
