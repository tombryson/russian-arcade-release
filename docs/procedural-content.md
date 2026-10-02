# Procedural content

Implementation record, 2 October 2026.

Russian Arcade uses fixed learning objectives and variable practice. A new seed must change the language problem or situation. Shuffling answers, changing a name or replaying a saved question does not establish novelty.

## Current behaviour

| Area | What changes | What stays fixed |
| --- | --- | --- |
| Curriculum practice | New sets compose subjects, objects, places, case relationships, tense, number and communicative context. Choice and typed-form modes use the same grammar rules. | Teaching explanations, the target requirement, marking policy and each issued question. |
| Describe the Scene | Spatial relationships, viewpoint, objects, placement, adjective agreement, participant roles and motion scenarios. Motion changes transport, route, directionality, tense and event. | Valid grammatical constructions and physically compatible combinations. Old sessions retain their original scenes. |
| Speaking | All five categories have A1 and A2 situation recipes. Prices, availability, requirements, travel details and conversational objectives vary where appropriate. | The selected preview is frozen at Start. Fluent and Step-through use the same situation; conversation and grading remain separate. |
| Vocabulary games | Text games prepare ten distinct contextual rounds. Picture games reuse at most four pictures through different combinations or routes. | The activity's own interaction, saved answers and normal vocabulary enrichment. |
| Word Jumble | Selection favours words outside the last ten sets. A small collection can introduce one new word rather than repeat the same complete set. | The requested number of words and existing word-definition pipeline. |
| Comprehension, Writing, Translation, radio and native flashcards | Existing AI generation now receives recent material and a proposed situation. Exact recent duplicates are rejected. | Existing schemas, grammatical constraints, budgets and the saved generated instance. |
| Follow the Directions | Existing procedural town and story generation continues. | Saved towns and allocated deliveries remain resumable. |

AI novelty guidance reduces repetition; it cannot prove that two differently worded stories are meaningfully different. The deterministic Scene generator can compare the underlying situation directly. Its identifiers exclude changes that merely rename a character.

## Curriculum grammar

`curriculum_generation.py` realizes checked Russian patterns with a controlled lexicon and morphological inflection. It offers selected patterns from the existing A1 units in choice and typed-form practice. The added activities/professions unit has its own rule builder.

The sentence, answer, distractors, explanation and requirement reference are produced together. A grammatical distinction must have enough context to be answerable. Motion distinguishes an outward journey from repeated journeys there and back. Aspect states whether the task asks for an unfinished process or a completed result. Inflection does not decide a word's meaning.

The main lesson buttons start or continue the authored lesson practice, preserving its full question coverage. A compact New examples action in each choice or typed-form section offers generated practice of selected grammar patterns. The connected location lesson also offers new examples separately from its authored teaching sequence. Saved attempts continue to work.

A set contains six distinct questions and includes each supported grammar rule before filling the remaining places. Selection considers the learner's last thirty generated sets across both response modes and chooses the least overlapping candidate. The rule space is finite. Exhaustion permits revision; it does not claim an unseen assessment. Exact previously disclosed answers are recorded as assistance, including when a choice question returns as a typed question.

Generator `g1` is part of the content identity. Its rules must remain reproducible. A material rule change requires a new version, retaining the implementation needed to validate old instances. Each set also stores its full payload and criterion contracts. Reading or resuming it never regenerates the question.

These are controlled grammar exercises. They do not establish independent spoken production, a full TORFL requirement or a proficiency level.

## Scene and Speaking composition

Scene generation selects a semantic plan before building the Russian sentence or illustration. Checked noun forms and verb paradigms determine the answer. The illustration uses the same objects and relationships. Variants that require impossible placement or unsuitable transport are excluded. Recent plans are stored in the existing session payloads; old content versions remain readable.

Speaking previews are read-only. Starting a preview materializes its exact variant through the existing scenario table and foreign keys. Recent situation history is shared across Fluent and Step-through. Refreshing should change the communicative situation, not silently change a session already in progress.

New Speaking diagnostic mappings refer to the requested actions in the frozen situation. They do not use a broad scenario label as evidence of general proficiency. Unclear speech remains unscored, and original-audio evidence retains its existing independence limitations.

## AI generation and vocabulary

The shared `content_variation.py` helper stores at most one hundred recent exposures per owner. Prompts receive the latest twelve excerpts, recent encountered lemmas and a suggested setting and purpose. Internal owner identifiers are removed from provider context. Editorial history is private to the workspace and profile.

Generated activities continue to use mostly familiar vocabulary with some new language. Familiar words can appear in new constructions. Discovering a word does not bypass the lemma/form database or create a universal English translation field. Saving it still uses the existing enrichment, mnemonic and morphology pipeline. Flashcards keep contextual meanings, images and audio.

A duplicate response does not trigger an unbounded paid retry. The learner can explicitly retry preparation. Existing provider allowances and request limits remain in force. Word Jumble also stops immediately on an allowance denial, rather than treating it as malformed model output.

## Persistence and rewards

Migration 062 adds bounded editorial exposure history. Migration 063 binds generated-practice start and resume requests to their original session. Both are additive. Neither migrates personal learning content or changes credentials.

Generated sets use the existing learning sessions, attempts and criterion reports. Request replay, active-session resume, ownership checks and frozen originals apply. Different seeds and response modes share one daily reward family per unit. They do not create extra daily coin entitlements or automatic Journey passes.

Ordinary backups retain the workspace. Account import discards editorial exposure history from the output artifact because its private owner scopes are not transferable identities. It preserves both inputs and retains actual learning history. Pending generation is rebound to the verified destination owner before using novelty guidance.

## Deliberately authored content

The five introductory lessons teach a small, ordered foundation. Their examples should remain stable enough to learn from. Spaced flashcard review deliberately returns to saved cards.

The connected lesson's listening recordings, transfer families, Journey checkpoint letters and five-domain diagnostic forms remain authored. Transfer families now rotate by least recent use after both have been encountered, and repeated work remains marked as repeated. These banks need expansion; they are not an unlimited assessment generator.

Uploaded tutor lessons generate material from a particular source revision. Reopening the revision keeps that material. A separate request for new exercises from an unchanged revision is still future work.

## Verification

The full backend run exercised 2,014 tests across 180 modules. It found two regressions: the review exporter test still expected fourteen units, and the standalone Word Jumble selector assumed a game-history table existed. Both were corrected. The affected packet tests passed (9 tests), as did the selector, generation and evidence regressions (70 tests).

After final language and feedback corrections, 42 grammar, learning and evidence tests passed. A separate 21-test run covered the rendered authored/generated lesson actions and their saved content. The full UI suite passed 820 tests across 62 files. TypeScript and the production build passed. The release-source secret scan found no credentials.

Browser checks used an isolated sample workspace with providers disabled. They covered generated six-question practice, a correct saved answer, Scene layouts at desktop and 375px width in English and Russian, Speaking mode changes, refreshed situations and a resumed legacy conversation. These checks verify operation and layout; no natural learner speech or pronunciation review was performed in this pass.

No production deployment or live provider evaluation was performed in this pass.

## Remaining work

1. Extend rule coverage and checked lexical classes where the source inventory still has gaps. Add teaching before requiring new constructions.
2. Prepare recordings for the new instrumental unit. Generate new lesson reading, listening and production situations from declared facts, with frozen audio and independent answer checks. Preserve the original uploaded lesson as source material.
3. Expand assessment forms under a five-domain blueprint. Keep assessment exposure separate from ordinary practice novelty. Do not treat random variation as calibrated exam difficulty.
4. Compare generated Russian and marking against held-out responses and natural learner recordings. Automated morphology and software tests cannot establish pronunciation quality or exam readiness.

The application remains standalone. These are content and product-validation tasks for maintainers, not requirements for learners to find a tutor.
