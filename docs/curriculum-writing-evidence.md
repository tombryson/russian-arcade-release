# Writing task evidence

New A1–B2 Writing activities now save a small assessment focus before the learner responds. The existing Writing task, draft, tutor feedback and check history remain the learner's workflow. A closed **What this response shows** disclosure adds natural-language feedback for each saved criterion. This is diagnostic practice evidence; it does not award curriculum mastery, a chapter pass or a level.

## What is frozen

The generator receives only the selected level's `writing` requirements from the versioned TORFL reference as focus candidates. Its strict output chooses one or two distinct candidate IDs and returns an exact excerpt of each requested demand from both the Russian and English task instructions. The prompt asks for one situation and purpose, with each demand stated once. Focus metadata is extracted from those instructions; it must not become a repeated requirement or rubric in the learner's task. The server checks the IDs, number of criteria, output fields and matching excerpts. Language-use references cannot be relabelled as independent Writing evidence.

The server then builds the contract with `independent_writing` response mode, `reference` evidence scope, the known source locators and a maximum score of two per criterion. The expectation is the explicit English task excerpt. The provider cannot supply its own contract, source references or hash.

The frozen content includes the exact Russian and English instructions, titles, required words and focus excerpts. A selected topic must be the requested canonical topic. For **Any topic**, the generator chooses one canonical task topic; the contract records both that topic and the original `any` request. `writing_exercises.topic` retains the requested value. This does not change vocabulary topic assignments.

Creation saves the activity and its contract in one transaction. It rejects mismatches between the contract and the saved task, vocabulary, level, included display text or requested topic. Saved contracts are immutable. Content and contract hashes detect changes; they are not authentication signatures.

## Checking and failure behavior

Assessment receives the saved contract and the learner's exact response, including whitespace. It keeps the existing tutor score out of ten, strength, next step and short example. Curriculum guidance cannot silently add criteria to a contracted task.

Each criterion report must include the saved contract hash and exactly one judgement for every saved criterion. A judgement has a concise explanation, an outcome and score consistent with its criterion maximum. A scored outcome needs exact quotations from the original response with matching Unicode code-point offsets. **Not enough evidence** is unscored (`null`), not a zero or a pass. Validation rejects unknown or duplicate criteria, invented quotations, mismatched hashes and unsupported fields.

The provider adapter grounds quotation offsets before validation. An already valid span is retained. If an offset is wrong, the server corrects it only when the quoted text occurs exactly once in the original response. An absent quotation or an ambiguous repeated quotation is rejected. No spelling, whitespace, punctuation or Unicode normalization occurs, and the original provider report is left unchanged. Shared contract and repository validators still reject incorrect offsets; they never repair incoming stored or client-supplied evidence.

The repository revalidates the report, task ownership and current draft revision inside the write transaction. Draft, ordinary score, attempt, report and existing Writing rewards succeed together. An invalid report, stale revision or database failure saves no partial check and preserves the previously saved draft and history. No score is manufactured from provider failure. The browser retains the submitted text for retry through the existing error flow.

Reports attach to existing `writing_attempts`; there is no parallel learner-progress system. A later check of the same task records `model_answer` support because earlier feedback already supplied an example. Earlier reports remain unchanged. Criterion feedback exposes labels and explanations, not internal IDs or a proficiency percentage.

## Existing and authored tasks

Previously saved tasks keep their original feedback path and receive no retrospective contract or criterion report. New C1/C2 tasks also keep that path because the current inspected reference covers A1–B2. Their ordinary Writing feedback remains available.

Server-authored tasks may provide a compatible contract at creation. A narrowly elicited grammatical form can use `controlled_text` with a distinct `controlled_production` target and its language-use source reference. This does not become broad independent Writing evidence. Audio criteria are not accepted by the Writing adapter.

## Limits and verification

Structural validation establishes that a report refers to the saved task and quotes the actual response. It does not establish that the model's linguistic judgement is correct, that its chosen task fully operationalises a reference requirement, or that a short answer demonstrates the whole requirement. The generator is instructed to include any source text needed for a source-based activity; semantic adequacy still needs content review. An ambiguous citation or unsupported judgement can still cause otherwise helpful feedback to be rejected rather than partially saved. Structured output constrains the format, not the correctness of its contents. [OpenAI structured-output guidance](https://developers.openai.com/api/docs/guides/structured-outputs)

The existing generation and feedback model, reasoning setting and output budget are unchanged. Focused tests cover all four referenced levels, family A1, contractless law C2, the hosted trial SDK schema, exact task/topic provenance, invalid generation and reports, independent profile ownership, concurrent draft revisions, transactional rollback, repeated checks and the complete generated-task assessment path. They also cover Unicode offset errors, ambiguous repeated quotations and unchanged original responses.

On 23 September 2026, two bounded live calls used the existing local `gpt-5-mini` setting with retries disabled and synthetic data. A1 places-task generation passed validation. The assessment completed at the provider but failed local validation because both quoted spans had incorrect offsets in a response containing a newline and emoji. The exact captured response passes after offline replay through the new grounding adapter. The generated instructions also repeated a requirement, so the generation prompt was tightened. These two calls are a connection and validation check, not a grading-quality evaluation; there was no third paid call to verify the revised prompt.

Implementation: [`writing_service.py`](../flask_vocab_app/services/writing_service.py), [`writing_repository.py`](../flask_vocab_app/repositories/writing_repository.py), [`curriculum.py`](../flask_vocab_app/contracts/curriculum.py), and [`activity_evidence.py`](../flask_vocab_app/services/activity_evidence.py). The shared tables are introduced by migration `049_activity_task_contracts.sql`.
