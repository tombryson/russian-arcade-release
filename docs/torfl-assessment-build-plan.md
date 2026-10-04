# TORFL curriculum and assessment delivery plan

**Implementation specification, updated 4 October 2026. Deployed baseline: `7e493e6`. Original code baseline: `ba9bee7`; initial document: `8fdb608`.**

This document defines the remaining work needed for Russian Arcade to teach and assess the published requirements of A1–B2 Russian. The supplied *ТРКИ-I* training book provides a concrete B1 example of what learners must eventually do.

It supplements the [curriculum implementation plan](curriculum-uplift-plan.md). The current implementation is recorded below and in the [implementation record](torfl-implementation-2026-10-02.md). The connected A1 sequence, storage, activity adapters and profile projection are now implemented in the repository. This does not mean that every later delivery package is finished or deployed. Full-level assessment thresholds remain subject to validation.

The latest generated reading/listening and passage-support work was deployed to Fly on 4 October, including the `/demo/` workspace. CI passed 2,221 backend tests and 843 frontend tests. Live checks verified page and asset delivery, source identity, Fly health and the demo home page. These checks establish deployment, not the naturalness of generated Russian or a fresh production playback result. See [the next implementation pass](#next-implementation-pass) before starting further work; the P0/P1 construction steps later in this document are retained design specifications, not a request to rebuild completed infrastructure.

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
| Teaching | 17 A1 teaching units, including present-tense person/number, instrumental activities/professions, dates/duration and о/об topics; generated choice and typed practice; a connected location/destination edition with two transfer situations. | Complete the source-level breadth of A1 and its prerequisites; author later levels. |
| Listening | The earlier 14 unit packs and both pilot forms retain 44 verified clips. The connected sequence retains 19 reusable recordings across 25 playback identities. Generated unit listening now saves accepted text before preparing private audio on demand; browser playback has been checked. | Improve and measure generated language quality, review pronunciation, and check target devices. Preserve each issued text, voice and recording. |
| Activity evidence | V1 retained; v2 separates communication from forms in original writing and speech. Immutable submissions survive unavailable feedback. | Broader original-production coverage and validation on learner responses. |
| Lesson state | Owned, frozen runs; idempotent activity allocation; durable typed drafts; review recovery; per-task support and transfer exposure. | Wider real-user and device trials; extend the proven sequence pattern to the remaining units. |
| Profile | Five compact domain rows, scoped activity/pilot results, pending work and deterministic next actions. | Validate recommendations with learners; add later-level results only under an explicit assessed scope. |
| Assessment | Resumable A1 diagnostic with two forms per domain. Original responses and assistance are retained. | Broader sampling, spoken interaction, calibration and a separately versioned full-level policy. |
| B1 delivery | 50 B1 requirement entries and generated practice. | The coverage inventory has no allocated, statically authored B1 reference tasks. |
| Progression | Elo, coins and permanent Journey passes have separate purposes. | Introduce any future level gate through a new release, preserving existing progress. |

The current pilot still samples six language-use choices, three reading questions, three listening questions, one written message and one recorded introduction. It is too small to establish full-level proficiency. Its Speaking sample does not test interaction. The new lesson has a separate two-turn recorded exchange; this does not silently expand the pilot's scope.

The [validation record](curriculum-validation.md) records no independent language review or learner trial. All 239 requirements now have a proposed unit and assessment family, with explicit remaining gaps. The [coverage inventory](curriculum-coverage.md) excludes runtime-generated tasks; an empty authored B1 row does not mean learners have no B1 practice.

## Procedural practice follow-up

The [procedural implementation record](procedural-content.md) documents the new generators and their limits. Curriculum grammar now produces owned, frozen sets; Scene and Speaking compose situations from explicit facts; ordinary AI activities receive bounded recent-content history. Teaching and assessment objectives stay versioned. Changing an answer order or character name is not evidence of new content.

P2 content work extends these rules and their teaching, rather than adding isolated banks of complete questions. The new date/duration and о/об units cover three named source requirements partially. New reading and listening now have a persistent generation path using unit objectives, taught language and explicit facts, with source-grounded questions and answers. Audio is prepared from the accepted text on demand; no stock recording batch is required for each content variant. The deployed generators still need better prose and measured language quality before their scope expands. The diagnostic pilot and Journey letters remain authored. Broader P3 forms still require a declared sampling blueprint, ambiguity checks, audio and validated marking. This pass does not convert practice scores into a full-level pass.

The language-design pass now starts with the Russian: the communicative purpose, prerequisite constructions, natural answer phrases and credible alternatives. The initial three unit plans froze related facts before generation and supplied checked hints and source-based feedback. All seventeen units now use this approach, with two situation families each. A comprehension question must distinguish meanings; it must not rely on an obviously wrong ending to identify the answer. Written-date teaching does not establish spoken-date comprehension. Short messages should carry useful information without padding to meet a universal length target. The [linguistic design](procedural-content.md#linguistic-design) and [eighteen-call evaluation](procedural-content.md#language-design-follow-up) record the implementation and remaining quality limits.

## Next implementation pass

The immediate priorities are language quality, useful variation and connecting new vocabulary to the rest of the app. More services, progress bars or stock recordings are not required. Keep the existing learning player, vocabulary pipeline, saved tasks and provider limits.

**Deployed progress, 4 October:** all seventeen A1 units now have two reading/listening situation families, with checked constructions, participants and answer relationships. Optional “Words and phrases” help sits beside existing word lookup and saving. Opening help records assistance; listening retains its transcript boundary. Saved tasks keep their original contracts. The [deployment record](torfl-implementation-2026-10-02.md#deployment-update--4-october-2026) records the release checks and their limits.

The [earlier report](curriculum-pass-2026-10-04.md) records the initial three-unit evaluation. The [extension report](curriculum-expansion-2026-10-04.md) covers the other fourteen plans, whole-passage vocabulary checks and the new evaluation. Generated text still needs language review beyond structural acceptance. Matched-input vocabulary adaptation, complete examples for original-sentence flashcards, and wider Writing/Speaking remain unfinished. The table below gives completion criteria, not a claim that all content-quality goals are met.

| Order | Deliverable | Completion evidence |
| --- | --- | --- |
| 1 | Improve the three detailed reading/listening plans and evaluate the current prose prompt. | Fresh samples have a coherent speaker, addressee and purpose; correct Russian; answerable questions; and appropriate supporting language. Report rejected and weak samples as well as successes. |
| 2 | Add word lookup and saving to generated passages. | A selected form retains its sentence context and uses the existing lemma, mnemonic and enrichment pipeline. Saving is optional. Listening transcripts and answer-related help retain their support rules. |
| 3 | Extend linguistic plans to the remaining 14 units, in small groups. | Each group teaches its tested contrasts and has distinct situation families checked in reading and listening. A broad A1 prompt does not count as a completed plan. |
| 4 | Add fresh Writing briefs and unit-specific Speaking beyond the connected location lesson. | Every unit already has an original Writing brief. New situations retain earlier work and elicit original messages and replies. Reports distinguish understandable meaning, correct use of an elicited construction and insufficient evidence. |
| 5 | Expand the diagnostic and later-level courses. | A versioned five-domain blueprint, broader task sampling and evaluation against responses not used for tuning. Existing pilot scores remain diagnostic. |

### 1. Natural Russian and meaningful variation

Start with a person who needs to tell, ask or find out something. Decide what the addressee must understand or do, then choose the Russian constructions that express it. The writer should realise that situation without adding filler to satisfy a length target. Keep the speaker, viewpoint, register and timeline consistent.

The earlier source-v4 batch passed five of six structural checks. Assistant review judged three usable for supported comprehension and none fully polished. A message addressing Анна ended by narrating what Анна knew; another added «Это была поездка Лены» without useful information. The new source-v5 batches check the shorter-message policy and revise address, viewpoint and cohesion guidance. Their results remain a small development sample, not a production success-rate estimate.

The baseline plans repeated the same information pattern under different recipe names. Location always asked about two current places and one destination. Calendar tasks always used a completed stay. Topic tasks paired two speakers with their subjects and a location. Plan v4 adds shared-place/diverging-destination, reading-duration, and stated-thought versus conversation families. These change the information relationship, but two families per unit remain a limited starting range.

The [baseline plan audit](validation/russian-content-audit-2026-10-04.json) found one fact-role structure per unit/mode. The [follow-up audit](validation/curriculum-situations-2026-10-04.json) checks the same 600 seeds and reaches both families in every combination. These audits concern the three detailed reading/listening plans, not every generator in the application. Family coverage does not prove natural prose.

Two distinct families are now implemented for each of the seventeen units. Further families must change what the learner needs to resolve: for example, locating a friend versus acting on a changed meeting plan, or understanding the length of a visit versus time spent on an activity. Use only taught language or explicitly supported new language. Different names, dates and nouns alone do not establish a different family.

Choose the situation family using recent semantic exposure before selecting its words. Recent text excerpts and exact-duplicate rejection alone cannot prevent the same problem returning with different names.

For every family, specify:

- Who is speaking, to whom, why, and through which medium: note, message, announcement or brief exchange.
- The facts and relationships needed to answer. Preserve natural alternative answers where the task allows them.
- The target construction, permitted supporting grammar, familiar vocabulary and a small amount of supported new vocabulary.
- The question's purpose and plausible alternatives. A reading question distinguishes meanings; a form exercise may explicitly test an ending.
- What the seed changes, which combinations are implausible, and which changes should count as a previously encountered task.

Sentence count should follow the message's purpose. The current generation contract requires exactly three assessed facts, each bound to one question. Keep that contract and the three-question player until a deliberate versioned change is made. If a proposed situation cannot support three useful questions, redesign its information or give it a different declared task shape. Do not pad the prose.

The previously unreachable calendar reading-duration context is now selected and tested. It distinguishes time spent reading from finishing a book. Listening uses duration, venue and another reader; it does not introduce untaught spoken ordinal dates.

The three planned batches of six text calls are recorded in the pass report. Each used a dry run, a fresh seed and a synthetic vocabulary profile; there were no automatic retries or private learner inputs. The evaluation command now supports explicit vocabulary fixtures. Because profiles and seeds changed together, these runs do not establish vocabulary adaptation. Use the same seed with different profiles for that separate comparison.

Review grammatical correctness, communicative purpose, supporting difficulty, referents, distractors, naturalness and meaningful variation separately. A schema pass is not a language pass. Record cost, latency, first-attempt acceptance and all rejections. Check for every known defect, then evaluate corrected work with new seeds. This is a release check for the sampled scope, not catalogue-wide validation or an exam-readiness estimate.

Review unfamiliar language across the complete passage. Source-v6 limits new vocabulary to three lemmas, with separate contextual annotations where their occurrences differ and at most eight word/phrase support entries. The earlier three-annotation limit could not safely describe repeated words or homographs. A familiar lemma still does not establish knowledge of its case forms or governing construction. Allow useful supported expressions, such as an invitation, deliberately. Do not label idiomatic Russian incorrect simply because it is outside the target construction. Keep annotation errors separate from errors in the Russian itself.

Review analyser disagreements as a separate validation task. The rejected «тоже» annotation does not make its sentence ungrammatical. Normalise justified annotation differences against the existing morphology pipeline without accepting wrong surface forms or inventing a lexical sense. An analyser's preferred parse alone cannot settle every contextual interpretation.

Prepare audio only after accepting its text. Retain randomized voice selection and save the chosen voice with the task. Check pronunciation and prosody audibly, including Russian stress and the intended readings of numbers. Successful playback alone does not establish good Russian speech. Do not add an extra model judge to every learner request by default; any proposed quality pass must have a measured benefit, cost and failure policy.

Implementation starts in `curriculum_situation_plans.py`, `curriculum_situation_content.py` and `scripts/check_curriculum_situations.py`. Publish material prompt or plan changes as new versions. Preserve old adapters, issued questions and saved answers.

### 2. Vocabulary integration

Generated passages now use `ui/src/PassageWords.tsx` within the existing player. The server verifies the selected word and its exact position in the saved passage. Lookup and saving reuse the existing morphology, mnemonic and enrichment services. A contextual annotation applies only when it identifies one occurrence; repeated homographs retain alternatives. Unannotated words may have no established contextual English meaning. No universal translation field is added.

Reading can offer word help on demand. Listening must keep its transcript hidden until requested; opening it or receiving answer-related help must retain the existing support record. Saving a word must be idempotent and include the existing mnemonic and morphology work. New passage vocabulary should then be available to the normal flashcard generator with contextual clozes, images and audio.

Captures retain the original sentence, selected reading, offsets and passage hash in owned command receipts. The saved-word read endpoint retrieves them after completion without another provider call. Complete card examples require more than this provenance: prepare the sentence translation and contextual target before inserting them into the example cache. That original-sentence reuse remains future work.

### 3. Extend the language plans

Work through coherent groups: personal reference and agreement; actions and routines; possession, objects and recipients; motion, origins and aspect; quantities, needs and social exchanges; then connected messages and instrumental activities/professions. Check actual prerequisites before choosing each group. These are work groups, not new access locks.

A plan must describe the Russian relationship being learned, not just a topic or case label. Distinguish recipient from companion, absence from possession, location from destination, and process from result. Separate each unit's taught lexical classes from its remaining coverage. Add explanation before testing a new contrast. Broader original writing, speech and full A1 coverage remain separate work after a generator exists.

Concrete teaching gaps include adjective forms outside nominative descriptions, the allocated departure/arrival motion requirement, and spoken ordinal dates. The existing units deliberately cover narrower uses. Do not infer complete coverage from their titles or from a zero in the separate sequence-mapping inventory. Identify the missing construction, teach it, then extend its generation and evidence contract.

### 4. Production and assessment

Reuse the existing original-response stores and two-turn exchange. Add new purposes such as making a request, explaining what is missing or arranging a time. Let learners answer in natural Russian; do not require them to reproduce the model's sentence. Retain the original audio so transcription cannot silently erase grammatical mistakes.

Ordinary unit Writing currently reopens one saved brief and observes one communication criterion. Add an explicit new-situation action while preserving resume, drafts and feedback for the old brief. Add grammatical criteria only when the new task actually elicits those forms. The connected location/destination sequence already has more detailed evidence; reuse that design without forcing every unit through the same activity list.

Expand assessment variation under its blueprint, with fresh tasks held back from practice and tuning. Keep known help and repeated exposure attached to results. Test natural learner recordings and disputed alternatives before strengthening grading or level gates. This is maintainer validation; the learner still uses a standalone application without needing a tutor.

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
| Speak | Answer *Где ты сейчас?* and *А куда ты идёшь?* in a brief exchange. Choose from the same familiar places and provide original speech. | Two original turns, task completion and narrow grammar observations. |
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

1. Within a scope, choose the latest successfully reviewed submission by submission time, then its persisted submission identity. Historical stores record seconds, so their original insertion order breaks same-second ties before the report ID. Imports preserve that order. Review completion time must not let a delayed old review displace newer work. For a multi-question reading task, first choose the newest reviewed answer to each question, then aggregate those answers.
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

Use the inventory to fill gaps across the 17 A1 units before adding unrelated activities. Sequence prerequisites and author missing examples, meaningful contrasts, listening and production tasks. Give each released requirement appropriate transfer tasks; broad communication requirements need several situations.

The first P2 addition is now `present-actions-v1`: читать/говорить person and number, with eight contextual questions, six controlled forms, three recordings and a short original Writing task. Existing content is retained. Its coverage is partial; the Writing criterion measures meaning, not general conjugation control.

The next addition, `instrumental-activities-professions-v1`, teaches заниматься + an activity and the future-profession pattern буду врачом. It includes contextual choices, typed forms, a short Writing task and generated practice. It has no authored Listening bank; it uses the new generated unit listening path with on-demand audio. These are bounded uses, not complete instrumental-case coverage.

`calendar-and-duration-v1` now distinguishes calendar dates from duration (`a1.language.genitive-calendar-month` and `a1.language.accusative-duration`). It teaches those functions separately before combining them in an arrangement. `talking-about-topics-v1` adds о/об + a topic (`a1.language.prepositional-topic`). Both have taught examples, generated recognition, controlled forms and a communicative Writing task. Their forms and lexical classes remain bounded; they do not establish full case mastery.

Next, improve and measure the language quality and acceptance rate of generated reading/listening, then use the source inventory to prioritise the remaining language functions and original-production coverage. The persistent text/audio workflow is implemented, with browser playback checked. Preserve older units and First steps; an unmapped sequence reference is not proof of absent teaching. Each generated task must keep its accepted text, facts, answer key, support history and source scope. A refreshed situation must not rewrite an issued task or create another coin entitlement.

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

The repository contains the P1 foundations, the retained P0 recordings, the current P2 grammar additions and generated unit reading/listening with private on-demand audio. The implementation record distinguishes automated checks, browser checks and remaining evaluation. Next, finish the outstanding P1 acceptance cases and improve and measure generated-content quality, then use the coverage allocations to fill further P2 gaps. P3's expanded assessment blueprint, evaluation sample and pass policy remain explicit work; P4 teaching has not been authored. This specification does not authorise a proficiency claim merely by listing the required work.

## Sources

- Андрюшина Н. П., Макова М. Н., Пращук Н. И. *Тренировочные тесты по русскому языку как иностранному. I сертификационный уровень*. Moscow, 2004. Supplied PDF; not redistributed. Domain instructions: PDF pp. 4, 25, 31, 41–47; self-check examples: pp. 23, 30, 32–33.
- [MSU B1 requirements](https://test.irlc.msu.ru/wp-content/uploads/2024/08/B1_trebovaniya.pdf), edition identified in the repository as 2007 print / 2009 electronic. The upload path is not the publication date.
- [SPbPU testing information](https://www.spbstu.ru/international-cooperation/international-educational-programs/international-programs-of-additional-education/russian-foreign-language/testing-russian-foreign-language/): level mapping, five subtests and the centre's published 66% rule.
- [Herzen testing centre](https://herzen.spb.ru/about/struct-uni/centers/tsentr-testirovaniya/trki/): published subtest timings, including the B1 speaking format.
- [Repository research and source policy](curriculum-research.md), [requirement specifications](curriculum-requirements.md), [implementation status](curriculum-implementation.md), [validation record](curriculum-validation.md) and [current milestone rules](course-milestones.md).

Provider web guidance was checked on 2 October 2026. Reconfirm it when pinning an exam-aligned blueprint. Historical materials remain useful evidence of task demands; they do not override a selected provider's current rules.
