# Procedural content

Implementation record, 2 October 2026. The current follow-up is repository work; deployment and live evaluation are recorded separately.

Russian Arcade uses fixed learning objectives and variable practice. A new seed must change the language problem or situation. Shuffling answers, changing a name or replaying a saved question does not establish novelty.

## Current behaviour

| Area | What changes | What stays fixed |
| --- | --- | --- |
| Curriculum practice | All 17 A1 units have rule-generated choice and typed-form practice. New sets vary the subjects, objects, places, dates, durations and grammatical relationships allowed by the unit. | Teaching objectives, marking policy and each issued question. Cosmetic changes do not erase prior answer exposure. |
| Unit reading and listening | Generated messages use the selected A1 unit, its taught language and declared facts. Listening audio is prepared after the text has been generated and checked. | The issued message, answer key, requirement references and prepared audio belong to the saved task. This extends practice, not the exam pilot. |
| Describe the Scene | Spatial relationships, viewpoint, objects, placement, adjective agreement, participant roles and motion scenarios. Motion changes transport, route, directionality, tense and event. | Valid grammatical constructions and physically compatible combinations. Old sessions retain their original scenes. |
| Speaking | All five categories have A1 and A2 situation recipes. Prices, availability, requirements, travel details and conversational objectives vary where appropriate. | The selected preview is frozen at Start. Fluent and Step-through use the same situation; conversation and grading remain separate. |
| Vocabulary games | Text games prepare ten distinct contextual rounds. Picture games reuse at most four pictures through different combinations or routes. | The activity's own interaction, saved answers and normal vocabulary enrichment. |
| Word Jumble | Selection favours words outside the last ten sets. A small collection can introduce one new word rather than repeat the same complete set. | The requested number of words and existing word-definition pipeline. |
| Comprehension, Writing, Translation, radio and native flashcards | Existing AI generation now receives recent material and a proposed situation. Exact recent duplicates are rejected. | Existing schemas, grammatical constraints, budgets and the saved generated instance. |
| Follow the Directions | Existing procedural town and story generation continues. | Saved towns and allocated deliveries remain resumable. |

AI novelty guidance reduces repetition; it cannot prove that two differently worded stories are meaningfully different. The deterministic Scene generator can compare the underlying situation directly. Its identifiers exclude changes that merely rename a character.

## Curriculum grammar

`curriculum_generation.py` realizes checked Russian patterns with a controlled lexicon and morphological inflection. It offers selected patterns from 17 A1 units in choice and typed-form practice. Activities/professions, calendar dates/duration, and conversation topics have focused builders. These extend the taught grammar rather than replace the lexical database.

The sentence, answer, distractors, explanation and requirement reference are produced together. A grammatical distinction must have enough context to be answerable. Motion distinguishes an outward journey from repeated journeys there and back. Aspect states whether the task asks for an unfinished process or a completed result. Inflection does not decide a word's meaning.

New starts should use generated practice where a checked rule exists. Existing authored packs and their saved answers remain readable. The connected location lesson retains its ordered teaching sequence, with generated practice available separately. Starting new work must not replace an unfinished session or regenerate its questions.

A set contains six distinct questions and includes each supported grammar rule before filling the remaining places. Selection considers the learner's last thirty generated sets across both response modes and chooses the least overlapping candidate. The rule space is finite. Exhaustion permits revision; it does not claim an unseen assessment. Exact previously disclosed answers are recorded as assistance, including when a choice question returns as a typed question.

Generator `g1` is part of the content identity. Its rules must remain reproducible. A material rule change requires a new version, retaining the implementation needed to validate old instances. Each set also stores its full payload and criterion contracts. Reading or resuming it never regenerates the question.

These are controlled grammar exercises. They do not establish independent spoken production, a full TORFL requirement or a proficiency level.

The two additional units cover specific A1 gaps:

- **Dates and duration** teaches the genitive month after a day number, then a duration without a preposition. It distinguishes elapsed time from a date, start time or delay. Generation keeps dates valid for every month and accepts both неделю and одну неделю in the one-week construction. It does not assess pronunciation of ordinal dates or the whole Russian time system.
- **Talking about people and interests** teaches о/об + prepositional with familiar nouns. О/об depends on the opening sound; the rule does not substitute об before every written vowel. Pronouns such as обо мне and wider declension classes remain outside this unit.

Both units supply their verbs and constrain the requested meaning. Their original Writing tasks assess the message, accepting natural paraphrases; they do not turn a communicative success into proof of case mastery. The source allocations retain those limits.

## Scene and Speaking composition

Scene generation selects a semantic plan before building the Russian sentence or illustration. Checked noun forms and verb paradigms determine the answer. The illustration uses the same objects and relationships. Variants that require impossible placement or unsuitable transport are excluded. Recent plans are stored in the existing session payloads; old content versions remain readable.

Speaking previews are read-only. Starting a preview materializes its exact variant through the existing scenario table and foreign keys. Recent situation history is shared across Fluent and Step-through. Refreshing should change the communicative situation, not silently change a session already in progress.

New Speaking diagnostic mappings refer to the requested actions in the frozen situation. They do not use a broad scenario label as evidence of general proficiency. Unclear speech remains unscored, and original-audio evidence retains its existing independence limitations.

## AI generation and vocabulary

The shared `content_variation.py` helper stores at most one hundred recent exposures per owner. Prompts receive the latest twelve excerpts, recent encountered lemmas and a suggested setting and purpose. Internal owner identifiers are removed from provider context. Editorial history is private to the workspace and profile.

Generated activities continue to use mostly familiar vocabulary with some new language. Familiar words can appear in new constructions. Discovering a word does not bypass the lemma/form database or create a universal English translation field. Saving it still uses the existing enrichment, mnemonic and morphology pipeline. Flashcards keep contextual meanings, images and audio.

A duplicate response does not trigger an unbounded paid retry. The learner can explicitly retry preparation. Existing provider allowances and request limits remain in force. Word Jumble also stops immediately on an allowance denial, rather than treating it as malformed model output.

## Generated reading and listening

Each unit offers a new reading or listening situation. The request includes its level, taught constructions, examples, requirement references, familiar lemmas and their stored forms. It also includes recent situations to discourage repetition. A small amount of new vocabulary is allowed; saving a word still uses the normal enrichment pipeline.

The model returns a short message, explicit facts and three questions. Questions must point to source sentences and use an answer stated in that evidence. Checks reject missing facts, unsupported answers, repeated options, recent duplicates and malformed language fields. Unit-specific checks also reject known errors such as a cardinal number used as an ordinal calendar date. These checks constrain generation; they do not prove that every sentence is natural or every distractor is unambiguous.

Accepted text is saved before audio starts. A listening task then selects a voice from the existing configured pool, freezes that choice and creates its recording. An audio retry uses the same text and voice. The player receives the saved task only after publication succeeds. Reading has a separate passage area beside its questions on wide screens and above them on narrow screens.

Preparation shows its current stage and offers an explicit retry after failure. Refreshing or losing a response cannot silently start another paid call. There are at most three attempts per provider stage and six new preparations per profile per hour, in addition to existing hosted AI allowances. Publication retries do not call the provider again. The provider-free preview keeps its saved lesson practice.

## Persistence and rewards

Migration 062 adds bounded editorial exposure history. Migration 063 binds generated-practice start and resume requests to their original session. Migration 064 stores owned situation preparation, immutable requests, accepted text, voice plans, audio descriptors and request receipts. All are additive. They do not migrate personal learning content or change credentials.

Generated sets use the existing learning sessions, attempts and criterion reports. Request replay, active-session resume, ownership checks and frozen originals apply. Different seeds and response modes share one daily reward family per unit. They do not create extra daily coin entitlements or automatic Journey passes.

Ordinary backups retain the workspace. Account import discards editorial exposure history from the output artifact because its private owner scopes are not transferable identities. It preserves both inputs and retains actual learning history. Pending generation is rebound to the verified destination owner before using novelty guidance.

Generated recordings are private media. Playback requires the owned learning session and verifies the exact text and file hashes. Generic static routes cannot expose them. Backups and account imports verify both published recordings and recordings saved before publication, including their manifests. Missing or changed media fails verification rather than silently dropping a learner's recording.

## Deliberately authored content

The five introductory lessons teach a small, ordered foundation. Their examples should remain stable enough to learn from. Spaced flashcard review deliberately returns to saved cards.

The retained connected-lesson recordings, transfer families, Journey checkpoint letters and five-domain diagnostic forms remain authored. New generated unit listening does not replace those saved assets. Transfer families now rotate by least recent use after both have been encountered, and repeated work remains marked as repeated. These banks need expansion; they are not an unlimited assessment generator.

Uploaded tutor lessons generate material from a particular source revision. Reopening the revision keeps that material. A separate request for new exercises from an unchanged revision is still future work.

## Verification

The two new unit builders passed morphology, source-reference and answer-boundary checks. Tests cover all 12 month forms, five single-unit durations and eight topic nouns. They check valid one-unit alternatives, reject start-time/delay answers to duration questions, and keep prior exposure attached when only a date or subject changes. Sixty existing `g1` packs were compared with the prior implementation and remain unchanged. These checks establish the specified grammar behaviour; they are not independent language review or learner calibration.

### Earlier procedural pass

The following results belong to the previous implementation pass.

The full backend run exercised 2,014 tests across 180 modules. It found two regressions: the review exporter test still expected fourteen units, and the standalone Word Jumble selector assumed a game-history table existed. Both were corrected. The affected packet tests passed (9 tests), as did the selector, generation and evidence regressions (70 tests).

After final language and feedback corrections, 42 grammar, learning and evidence tests passed. A separate 21-test run covered the rendered authored/generated lesson actions and their saved content. The full UI suite passed 820 tests across 62 files. TypeScript and the production build passed. The release-source secret scan found no credentials.

Browser checks used an isolated sample workspace with providers disabled. They covered generated six-question practice, a correct saved answer, Scene layouts at desktop and 375px width in English and Russian, Speaking mode changes, refreshed situations and a resumed legacy conversation. These checks verify operation and layout; no natural learner speech or pronunciation review was performed in this pass.

### Current reading and listening follow-up

The backend regression run exercised 388 tests. It found one outdated review-fixture expectation after adding the two units. Fixture v6 now preserves all earlier cases and adds their coverage; 23 focused packet, ingestion and unit tests passed after that correction. The final focused backend run passed 159 tests. A further 43-test run covered the shared-recording playback correction. The final full UI suite passed 833 tests across 63 files. TypeScript and the production build passed; the source scan found no credentials.

Seven bounded text-provider calls tested the evolving generation contract with the configured model. One produced a manually acceptable exercise. Other responses were rejected for grounding, length or language-field errors; one structurally accepted response used the wrong Russian date form and led to an additional validator. This is a development finding, not an acceptable production success-rate claim. The final date guard and more explicit input facts still need a fresh measured provider evaluation.

The acceptable listening message produced a valid 26.053-second recording through the existing speech provider. In an isolated browser workspace, that file played to its real `ended` event and all three answers were saved through completion. A playback bug found during that check was fixed: listening once covers later questions about the identical recording and transcript in the same session, without counting as help. Different recordings and sessions retain their own playback requirement. Reading was checked at desktop and narrow widths, including passage layout and answer progression. These checks establish playback and UI behaviour, not an audible pronunciation review. Test captures and temporary workspaces are outside the repository; no personal or production data was changed.

No production deployment was performed in this follow-up.

## Remaining work

1. Extend rule coverage and checked lexical classes where the source inventory still has gaps. Calendar dates, duration and simple о/об topics now have partial teaching and generated practice; they do not close the whole A1 inventory. Add teaching before requiring new constructions.
2. Improve and measure generated reading/listening reliability across the unit catalogue. The preparation, persistence, private audio and player path is implemented; the small provider sample exposed unacceptable rejection frequency and language-quality gaps. Supply checked grammatical facts, test question ambiguity and record acceptance before rollout. A stock-recording batch is not a release requirement. Preserve existing authored recordings and uploaded lesson revisions.
3. Extend original production and connected sequences beyond the current location lesson. Generating another controlled question does not substitute for original writing or speech.
4. Expand assessment forms under a five-domain blueprint. Keep assessment exposure separate from ordinary practice novelty. Do not treat random variation as calibrated exam difficulty.
5. Compare generated Russian and marking against held-out responses and natural learner recordings. Automated morphology and software tests cannot establish pronunciation quality or exam readiness.

The application remains standalone. These are content and product-validation tasks for maintainers, not requirements for learners to find a tutor.
