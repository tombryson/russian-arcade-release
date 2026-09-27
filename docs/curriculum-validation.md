# Curriculum validation

## Current status

The application has 13 authored A1 teaching units and an opt-in diagnostic pilot covering five skills. They work without a tutor. Human review is optional editorial quality assurance for the maintainers, not a prerequisite for using the app or receiving feedback.

The examples and answer keys remain provisional. No independent human review or learner trial is recorded. The pilot does not award a level, unlock activities or claim to be a TORFL examination.

| Unit | Focus | Contextual choices | Typed forms | Listening available |
| --- | --- | ---: | ---: | ---: |
| Where and where to | Location, destination and movement within a place | 4 | 3 | 3 clips |
| Possession and absence | Available items, missing items and ownership | 6 | 4 | 3 clips |
| Objects and recipients | Direct objects, animate objects and recipients | 6 | 4 | Not yet |
| Time and daily routines | Days, times, conjugation and tense | 6 | 5 | Not yet |
| Describing clothes and objects | Adjective agreement with nouns | 6 | 4 | Not yet |
| Referring to people | Personal and possessive pronouns | 6 | 4 | Not yet |
| Walking and travelling | Walking, transport and repeated journeys | 6 | 4 | Not yet |
| Numbers and quantities | Numbers and the forms used with quantities | 8 | 5 | Not yet |
| Greetings and requests | Introductions, greetings and polite requests | 8 | 5 | Not yet |
| Needs and company | Needs, preferences and activities with another person | 8 | 5 | Not yet |
| Activities and completed results | The distinction between an activity and its result | 8 | 5 | Not yet |
| Where from and where to | Origins, destinations and prepositions | 8 | 5 | Not yet |
| Reasons, questions and connected messages | Short connected accounts and requests for information | 8 | 5 | Not yet |

Together the units provide 88 contextual choices, 58 typed prompts and 13 Writing briefs. Each unit has classified examples, a dedicated reading page and an original Writing task. Typed tasks test a specified form. They accept selected fuller phrases and ignore outer whitespace, case and final punctuation. They do not claim to accept every paraphrase or measure independent writing.

These units do not cover the whole A1 grammar system. Supplied infinitives in motion tasks test conjugation; separate choices test the distinction between movement types. Unit Speaking links open existing scenarios. They do not transfer a unit criterion automatically. Nine authored Fluent A1 variants now have narrow original-audio criteria: three directions questions, three café orders and three name exchanges. These observe the named communication task, not every scenario goal or full speaking proficiency.

There are 13 authored three-item listening packs. Location and possession are fully recorded and available: six clips in total. One objects-and-recipients clip is prepared, but its incomplete pack remains unavailable. The pending queue, including both pilot recordings, is 34 clips and 4,391 transcript characters. Eighteen of those clips were drafted for this pass. No unit listening button appears for an incomplete pack.

The last ElevenLabs allowance check showed 92 characters remaining. This is a preparation constraint, not a broken credential or a learner failure. Existing verified files are reused; the bounded preparation command can resume without regenerating them when allowance is available. No published unit sources or saved attempts are rewritten.

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

On 24 September 2026, a fresh Codex in-app browser tab played the authored location clip through its native controls to the end: duration 7.476825 seconds, no media error. The receipt unlocked answers. Replay and 0.75× playback worked. Saving and advancing restored the listening requirement for the next question. Explicit transcript use was marked as assistance.

A generated Comprehension test fixture also played a real bundled MP3, unlocked response fields, saved five responses and restored them after reload. Generation and marking were mocked. This checks playback, transport and saved state, not provider accuracy or the linguistic quality of generated content. Keyboard Space operated the native player.

A later local replay check of the possession clip stalled in the in-app browser and is still being investigated. The earlier fresh location playback result stands; it does not establish that every current clip or environment works.

No human pronunciation assessment or microphone trial is claimed by these checks. Speech-error evaluation needs consented original recordings containing known correct forms, mistakes, restarts and ambiguity. Compare the audio, literal transcription and feedback to detect silent autocorrection. Synthetic speech is useful for transport tests but cannot establish recognition accuracy for real learners.

## Future assessment validation

Learner trials should examine task clarity, rejected valid answers, useful corrections, saved work and keyboard/mobile use. A consequential level gate would need reviewed keys, resolved ambiguity, enough independent tasks per requirement and tested marking behaviour. These are future validation criteria, not dependencies for today's standalone practice and diagnostic feedback.
