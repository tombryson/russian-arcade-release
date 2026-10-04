# Curriculum validation

## Current status

Updated 4 October 2026. The current release is `0bcba58`, deployed on 3 October. See the [deployment record](torfl-implementation-2026-10-02.md#deployment-update--3-october-2026) for full CI and live checks, and the [ordered work plan](torfl-assessment-build-plan.md#next-implementation-pass) for remaining language and assessment work. Historical test counts below belong to their stated runs.

The application has 17 authored A1 teaching units and an opt-in diagnostic pilot covering five skills. They work without a tutor. Human review is optional editorial quality assurance for the maintainers, not a prerequisite for using the app or receiving feedback.

The examples and answer keys remain provisional. No independent human review or learner trial is recorded. The pilot does not award a level, unlock activities or claim to be a TORFL examination.

| Unit | Focus | Contextual choices | Typed forms | Listening available |
| --- | --- | ---: | ---: | ---: |
| Where and where to | Location, destination and movement within a place | 4 | 3 | 3 clips |
| Possession and absence | Available items, missing items and ownership | 6 | 4 | 3 clips |
| Objects and recipients | Direct objects, animate objects and recipients | 6 | 4 | 3 clips |
| Time and daily routines | Days, times, conjugation and tense | 6 | 5 | 3 clips |
| Who is doing what? | Present-tense person and number, including polite вы | 8 | 6 | 3 clips |
| Describing clothes and objects | Adjective agreement with nouns | 6 | 4 | 3 clips |
| Referring to people | Personal and possessive pronouns | 6 | 4 | 3 clips |
| Walking and travelling | Walking, transport and repeated journeys | 6 | 4 | 3 clips |
| Numbers and quantities | Numbers and the forms used with quantities | 8 | 5 | 3 clips |
| Greetings and requests | Introductions, greetings and polite requests | 8 | 5 | 3 clips |
| Needs and company | Needs, preferences and activities with another person | 8 | 5 | 3 clips |
| Activities and completed results | The distinction between an activity and its result | 8 | 5 | 3 clips |
| Where from and where to | Origins, destinations and prepositions | 8 | 5 | 3 clips |
| Reasons, questions and connected messages | Short connected accounts and requests for information | 8 | 5 | 3 clips |
| Activities and future professions | Заниматься + activity; буду + profession | 8 | 6 | Prepared on demand |
| Dates and duration | Month names in dates; duration without a preposition | 6 | 6 | Prepared on demand |
| Talking about people and interests | О/об + prepositional for the topic of speech or thought | 6 | 6 | Prepared on demand |

Together the units provide 116 authored contextual choices, 82 typed prompts and 17 Writing briefs. Each unit has classified examples and an original Writing task. Additional generated sets practise selected constructions within each unit; they do not replace the broader authored coverage. Typed tasks test a specified form. They accept selected fuller phrases and ignore outer whitespace, case and final punctuation. They do not claim to accept every paraphrase or measure independent writing.

These units do not cover the whole A1 grammar system. Supplied infinitives in motion tasks test conjugation; separate choices test the distinction between movement types. Unit Speaking links open existing scenarios. They do not transfer a unit criterion automatically. The nine earlier authored Fluent A1 variants retain their original-audio criteria. Generated Speaking variants have separate criteria bound to their exact situations. These observe the named communication task, not every scenario goal or full speaking proficiency.

The earlier 14 authored three-item listening packs are recorded. Both pilot listening forms are also recorded. Instrumental activities/professions, dates/duration and conversation topics have no prerecorded authored packs; eligible workspaces can generate their listening text and audio on demand. All 17 units offer that generated path. Authored recordings retain their scripts and manifests; generated recordings retain the accepted text, selected voice and media hashes. The application checks readiness before offering playback.

### Recording update — 2 October 2026

All 39 clips across the 13 original unit packs and both A1 pilot clips are now prepared. The 34 missing clips were generated from their existing scripts using 4,391 characters. The seven previously prepared recordings were retained. Listening is offered only while every clip in its pack matches the recorded hash; a missing clip does not block the unit's other activities.

The `location-destination-v2` sequence also has 19 distinct recordings: 13 teaching examples, three short listening messages, and shared spoken prompts and a closing. The 25 playback identities reuse identical scripts. This batch used 713 characters. Each file has a text hash, audio hash, duration, model and voice record. Voices were selected from the existing configured list.

The first sequence generation request failed without saving a playable clip. Read-only checks confirmed valid credentials, four accessible voices and sufficient allowance. One explicit retry completed the batch. The remaining unit and pilot batch completed without retries. No published task text or saved learner attempt was replaced.

These checks establish file integrity and playable audio, not an independent judgement of pronunciation or listening-task quality. Browser playback remains a separate acceptance check. The sequence is available as practice; preparing recordings does not validate an assessment or award a level.

A focused run of 112 content, contract, recording, unit, coverage and pilot tests passed on 2 October 2026. These include wrong Russian endings, unobserved grammatical features, binary communication scores, retained original response spans, missing-media fallback and unchanged v1 contracts. This result does not cover the full application suite or browser playback.

```sh
python scripts/prepare_curriculum_sequence_audio.py --dry-run --max-new 0 --max-characters 0
python scripts/render_curriculum_coverage.py --check
```

### Integration update — 2 October 2026

The present-tense unit adds eight contextual questions, six typed forms and three recordings. Two model passes checked person/reference distinctions, taught-before-tested forms and ambiguous present/future wording. They do not count as independent human validation. Its three clips used 244 characters and completed without retries; a later dry run found no missing or changed files.

Review fixture v4 retains all 246 v3 cases and adds 18 controlled-form cases and seven Writing cases: 271 total. Earlier fixture files are unchanged and pinned in regression tests. The new Writing examples include natural alternatives and intelligible grammatical errors. These are communication judgements, not claims about accurate conjugation.

The instrumental activities/professions unit adds eight contextual questions and six typed forms. Its rules vary 33 subject/activity or subject/profession combinations. Both functions cite the A1 standard, §2.2.2, page 13. Examples teach each target before practice; the Writing task observes communication without certifying case control. The unit has no Listening recordings or independent assessment. Two model passes checked the language; this does not count as independent human validation.

Review fixture v5 preserves all 271 v4 cases and adds 19 controlled-form cases and seven Writing cases: 297 total across 15 units. The extra form case accepts the grammatical alternative «музыкою». Earlier fixtures remain unchanged. Authored expectations remain review hypotheses, with no new provider evaluation or learner trial.

The current review fixture, v6, retains those 297 cases and all earlier content hashes. It adds 54 form cases and 14 Writing cases for dates/duration and conversation topics: 365 cases across 17 units. Forms cover wrong endings, valid one-unit alternatives, and date/start-time/delay answers that do not express duration. Each new form also has a correct answer reached with a hint; that help remains visible and cannot count as independent evidence. Writing cases include natural paraphrases, understandable grammatical errors, missing details, unrelated or empty responses and use of a model answer. These are evaluator fixtures, not a bank of repeated learner content. No new provider marking, independent review or learner calibration is claimed.

The connected lesson now saves and resumes across all five domains. Both the guided and challenge-first paths complete in local and hosted `/demo` test workspaces. The walkthroughs use provider stubs and fixture recordings. They verify storage, assistance, review recovery, ordinary rewards and the absence of transfer rewards; they do not validate the generated marks.

The full backend suite passed 1,940 tests in four isolated processes. All 805 UI tests, TypeScript checks and the production build passed. Nine subsequent focused tests passed after fixing hosted Listening delivery: four complete walkthroughs and five ownership, seeking and integrity checks. Undisclosed Listening files remain protected; reached recordings are served through an owned session.

Browser checks covered desktop and mobile layouts, saved Reading/Writing drafts, lesson completion and audio reaching its `ended` event. A real provider check exercised four synthetic written responses and two synthesized spoken exchanges. See the [implementation record](torfl-implementation-2026-10-02.md#verification) for results and limitations. Natural learner speech, audible pronunciation review and a full microphone walkthrough remain unverified. No production deployment is claimed.

## Diagnostic pilot

The pilot is accessible from Curriculum and the profile's course section. A learner can save work, change skill, return later and retry an individual skill. Original writing and speaking recordings are saved before feedback is requested. A failed review can be retried explicitly without resubmitting the response.

| Skill | Sample per form | Interpretation |
| --- | --- | --- |
| Language use | Six contextual choices | Specified forms in these sentences |
| Reading | One passage and three questions | Meaning, reference and sequence in that passage |
| Listening | One recording and three questions | Information heard in that recording |
| Writing | One personal message | Communicative purpose and requested details |
| Speaking | One original recorded reply | Personal information and intelligibility in a short monologue |

Each skill has two authored forms. They have not been calibrated or shown to be equally difficult. Retrying a previously seen form preserves prior feedback as assistance. Hints and transcripts are recorded. Listening playback is a delivery receipt, not proof of attention. The speaking task does not assess dialogue or turn-taking.

Feedback is specific to the saved response. Unclear or unavailable evidence remains unscored. There is no aggregate pass mark. Language use, Reading, Writing and Speaking can run while Listening is unavailable. Learners can continue without a Listening result, or open the transcript for supported practice. Neither path invents a listening score: missing audio remains unmeasured. A check freezes its media availability at creation, and component retries preserve that blueprint. Newly prepared recordings require a new skills check. Earlier results remain saved and accessible.

## Automated checks

Run from the repository root:

```sh
PYTHONPATH=flask_vocab_app python -m unittest \
  tests.test_curriculum_unit_expansion \
  tests.test_curriculum_unit_a1_expansion \
  tests.test_curriculum_unit_everyday_expansion \
  tests.test_curriculum_units_connected_expansion \
  tests.test_speaking_interaction_evidence \
  tests.test_curriculum_writing_evaluation \
  tests.test_curriculum_review_packet \
  tests.test_curriculum_review_ingest \
  tests.test_assessment_pilot_review_packet \
  tests.test_assessment_pilot \
  tests.test_assessment_pilot_integrity
python scripts/prepare_curriculum_review.py --check
python scripts/prepare_assessment_pilot_review.py --check
```

The checks verify content identities, reference IDs, accepted forms, ownership, original response storage and grounded reports. They exercise the application without paid model calls. They test hidden answers, transcript assistance, missing audio, stale forms, duplicate requests and explicit review retries. Passing tests shows that the software follows its declared rules; it does not validate those rules as a proficiency assessment.

The local build on 24 September 2026 passed all 731 frontend tests and the production build. Backend discovery ran 1,744 tests: 1,743 passed and one review-packet assertion still expected the previous seven-unit catalogue. After updating that assertion for the 13-unit fixture, all 19 related review tests passed. The full backend suite was not repeated after this test-only correction. A separate 24-test run passed the final pilot-retry and Writing-evaluator changes. The unit/pilot packet checks, generated coverage check and staged secret scan also passed. These results describe the local branch; this pass was not deployed.

The v3 unit fixture contains 246 authored controlled-form and Writing cases across all 13 units and pins all 13 listening sources. The exporter reports the exact counts for each selected fixture; older review rounds remain reproducible. They include valid alternatives, wrong forms, incomplete messages, empty evaluator input and model-answer use. Empty Writing drafts remain blocked in the live form. The fixture tests the evaluator's treatment of insufficient evidence.

## Optional review packets

Export a separate packet for each review round:

```sh
python scripts/prepare_curriculum_review.py --output-dir /tmp/arcade-units-review
python scripts/prepare_assessment_pilot_review.py --output-dir /tmp/arcade-pilot-review
```

Each directory contains:

- `reviewer.json`: source material, prompts, criteria and blank review fields. Unit sample responses use neutral case IDs.
- `author-key.json`: provisional keys and explanations. Keep this file separate until initial ratings are complete.
- `manifest.json`: source hashes, recording inventory and review limitations.
- `audio/`: available recordings. Missing clips are marked as unprepared in the reviewer file.

The pilot packet includes both forms of all five skills. It contains no real learner recordings or responses. The unit packet includes the listening sources pinned by its fixture, even where recordings are still pending. Neither exporter accesses learner data, credentials or a provider. Exports refuse to overwrite edited reviews or changed recordings.

Source hashes pin the material under review. Corrections to published tasks need a new content version so saved attempts retain their original prompts and keys. Issue a new review fixture when content changes; do not replace hashes merely to silence a check.

## Review submissions and disputed items

A reviewer fills a copy of `reviewer.json`. Record a name or identifier, qualification, ISO date and `kind: "human"`. Internal model work uses `kind: "internal_model"`; it does not count as human review. These are declared identities, not externally verified credentials.

```sh
python scripts/review_curriculum_packet.py \
  --packet-dir /tmp/arcade-units-review \
  --review /path/to/completed-review.json \
  --output /tmp/arcade-review-report.json
```

The importer checks the source pins, original prompts, responses, keys and bundled audio before accepting review fields. One completed human rating is recorded. A second rating is useful for comparing marking; it is not mandatory for every item. Missing ratings, disputed keys, new alternatives and content concerns remain explicit in the report.

For disputed items, collect a second independent rating. The report includes an adjudication template for a separate assessor. An adjudication is bound to the exact packet and submitted reviews; it cannot silently replace different work. Accept, revise and exclude decisions remain separate. Revised or excluded material needs a follow-up content change. The tool never changes learner records, grants a level or blocks a learner.

## Review criteria

A Russian-as-a-foreign-language teacher or assessor can examine:

1. Natural Russian and accurate English explanations.
2. Correct grammatical classification and necessary prerequisites.
3. Enough context for the intended choice, including plausible alternative answers.
4. Reasonable accepted forms and rejected forms.
5. Alignment between the cited requirement and the response the task actually elicits.
6. Brief, useful feedback after an error.
7. Clear, natural recordings and an appropriate listening pace.

For Writing, judge communication separately from grammar. `У меня нет вода` still communicates the missing item, although `воды` is the required form. Keep the learner's original response when recording a correction. Supported work can be correct without becoming independent evidence.

Use `satisfied`, `partial`, `not_satisfied` and `insufficient_evidence` for the stated criterion. Do not infer a whole proficiency level from one choice or short response.

After a reviewed dataset exists, a separate provider evaluation can compare model reports against it. Record model identity, prompt version, task hash, original response, assistance and full report. Count false passes, false failures, unsupported claims and abstentions separately. Keep related task variants out of both the tuning and evaluation sets. The bounded Writing runs below compare authored expectations, not an independently marked or calibrated evaluation set.

## Writing evaluation

The evaluation command uses synthetic authored responses rather than personal learner data. Its default mode makes no provider calls:

```sh
python scripts/evaluate_curriculum_writing.py --output /tmp/arcade-writing-offline
```

This checks controlled-form matching and leaves Writing model cases marked `not_run`. A live run explicitly selects one to eight Writing case IDs. For example:

```sh
python scripts/evaluate_curriculum_writing.py \
  --run-model \
  --case possession-absence-v1-writing-clear \
  --case possession-absence-v1-writing-grammar \
  --case possession-absence-v1-writing-missing-request \
  --env-file /path/to/existing/.env \
  --output /tmp/arcade-writing-live
```

The command reads the existing configuration; it does not edit it. Live calls use the configured model and an isolated ledger backed by the existing spending controls. Each saved case includes the raw response, support, task hash, model, service-code hash and complete validated report. No learner attempt, reward or level result is changed.

An output-directory lock prevents concurrent duplicate provider calls. A matching rerun reuses saved results. Failed or interrupted calls are not automatically repeated, and the run stops after a provider failure. A prompt, model or content change needs a new output directory so comparisons cannot silently mix versions. The report distinguishes agreement with authored expectations, overstated success, missed success, abstentions and rejected input.

The current live work used 22 bounded requests and returned 21 valid reports:

| Run | Requests | Valid reports | Agreement with authored expectations | Finding |
| --- | ---: | ---: | ---: | --- |
| Initial sample | 5 | 5 | 4 | An incomplete but relevant message received too little credit. |
| Partial-credit recheck | 5 | 4 | 4 | One request returned an invalid/unavailable Writing result. |
| Broader sample | 8 | 8 | 7 | A complete message with a wrong counted-noun form was under-graded for communication. |
| Final targeted recheck | 4 | 4 | 4 | Correct communication, missing detail and grammatical errors were distinguished as intended. |

The final prompt explicitly separates communication criteria from the overall grammar grade. Its four-case recheck covers a quantities message with a grammatical error, a quantities message missing detail, an origins message with a grammatical error and a clear social message. The last two unit contexts had not been used in earlier live checks. Explanations were in English, and no overstated success was observed in these samples.

The isolated allowance ledger recorded US$0.077252, including the reservation retained for the failed request. This is ledger accounting, not an independently verified provider invoice. All runs retain their original responses, source identities and reports; failed calls are not counted as agreement or disagreement.

These are small synthetic regression samples with provisional authored labels. They are not an accuracy benchmark, a real-learner trial or independent validation. Cases used to tune the prompt must remain separate from any later held-out evaluation.

## Browser playback checks

The [4 October pass](curriculum-pass-2026-10-04.md) adds a separate text evaluation: 18 first-attempt calls, 17 structurally accepted, 14 judged usable for supported comprehension in assistant review. Its report retains the three weak texts and rejected response. There was no pronunciation review or paid audio generation in that evaluation. Do not combine these results with the earlier Writing-marking agreement figures.

On 24 September 2026, a fresh Codex in-app browser tab played the authored location clip through its native controls to the end: duration 7.476825 seconds, no media error. The receipt unlocked answers. Replay and 0.75× playback worked. Saving and advancing restored the listening requirement for the next question. Explicit transcript use was marked as assistance.

A generated Comprehension test fixture also played a real bundled MP3, unlocked response fields, saved five responses and restored them after reload. Generation and marking were mocked. This checks playback, transport and saved state, not provider accuracy or the linguistic quality of generated content. Keyboard Space operated the native player.

A later local replay check of the possession clip stalled in the in-app browser and is still being investigated. The earlier fresh location playback result stands; it does not establish that every current clip or environment works.

No human pronunciation assessment or microphone trial is claimed by these checks. Speech-error evaluation needs consented original recordings containing known correct forms, mistakes, restarts and ambiguity. Compare the audio, literal transcription and feedback to detect silent autocorrection. Synthetic speech is useful for transport tests but cannot establish recognition accuracy for real learners.

## Future assessment validation

Learner trials should examine task clarity, rejected valid answers, useful corrections, saved work and keyboard/mobile use. A consequential level gate would need reviewed keys, resolved ambiguity, enough independent tasks per requirement and tested marking behaviour. These are future validation criteria, not dependencies for today's standalone practice and diagnostic feedback.
