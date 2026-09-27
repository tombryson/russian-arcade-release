# A1 journey milestones

The current course release is `a1-journey-v2`. It starts at home, visits the post office and market, and ends with an invitation beyond town. Barsik receives a separate letter at each stop. The original letter in his bag remains sealed.

## Course structure

| Milestone | Main topics | Assessment |
| --- | --- | --- |
| Home | Greetings, Family, Home | Identify people, objects and an updated arrangement. |
| Post office | Numbers, Daily activities | Understand routines, times and who is doing what. |
| Market | Food, Colours, Clothing | Follow requests and distinguish descriptions. |
| Leaving town | Places, Weather; earlier topics return | Combine the route, people, supplies and meeting arrangements. |

Each milestone has three authored variants. The first three contain eight questions each; the final contains sixteen. Retries prefer an unseen variant, then rotate through the finite set. All answer choices are Russian. Interface prompts and explanations are available in English and Russian.

Journey shows future milestones as grey cards with blurred content shapes. Only each milestone's number remains clear. The shapes contain no future story text or links. Names, descriptions and assessment links appear when the previous milestone is passed. Completed milestones remain accessible.

Curriculum remains a complete overview of the 50 topics, grouped by teaching band, with vocabulary, grammar, objectives and activity links. It does not show story cards, milestone artwork or personal progress. Profile holds the personal progress summary. The journey references the same topic IDs without changing the catalogue or hiding topics.

The final assessment samples all ten A1 topics: six reading decisions, four listening decisions, four contextual language decisions and two replies. Passing requires 13/16 overall, at least 4/6 reading, 3/4 listening, 2/4 language and 1/2 replies. Both essential decisions must also be correct. Earlier milestones require 7/8 and both essential decisions.

The listening update supplies new information. A passing attempt requires listening to the recording; replay is allowed. Hints and transcripts are optional and mark an attempt as supported. The transcript also allows practice when audio cannot play. Supported attempts keep their answers and feedback but do not earn a milestone. A fresh independent attempt can earn it.

If a recording fails, the learner can retry it or open the transcript. If saving a completed listen fails, they can retry that save without replaying the recording. Playback errors and retries do not grant listening credit. The server must acknowledge the completed listen before an independent assessment can be submitted.

## Preparation and evidence

Topic reference examples live in `flask_vocab_app/data/course_reference_notes.json`. Each preparation item has named language categories, such as Greetings, with labelled examples such as Formal and Informal. Titles and labels are bilingual; every Russian example has an English translation. Use short examples that isolate the named distinction. Do not replace these categories with an explanatory paragraph or infer them from sentence text.

The file uses schema version 1 and maps release IDs to the preparation IDs in that release. Each entry has `groups`; each group has a distinct `id`, `title`, `title_ru` and `items`. Items contain `label`, `label_ru`, `ru` and `en`. Validation checks complete preparation coverage, known IDs and bounded, nonempty content.

Reference notes are presentation data. The API joins them to unlocked preparation when returning course state, including saved receipt responses. Future milestones remain hidden. Editing these notes does not change published course files, assessment questions, grades or stored attempts.

For the current release, normal readiness uses the greater of ordinary activity preparation and focused-target preparation. The activity route uses two successful distinct tasks per topic, at least 70%, across two activity families in the section. Reading, Writing, Speaking, Translation and Word Jumble remain the main practice routes. Daily coin limits do not stop their saved practice from contributing.

The alternative focused route covers 32 comprehension and form-selection targets across the course. A target is prepared when it has been independently demonstrated, or introduced and attempted. Correct independent evidence does not require another teaching click. Short preparation items fill gaps without extra coins. Their completion recommends a checkpoint; it does not establish full proficiency.

The preparation policy is `activity-or-target-practice-v1`. Earlier course releases retain their original policy. The [A1–B2 research review](curriculum-research.md) documents the distinction between preparation, milestone passes and full-level assessment. No existing grade or pass is rewritten.

Evidence records the individual decision and any support used. Selected-response practice is not labelled spoken or written production. Existing aggregate activity scores remain topic evidence. They do not prove every objective in that topic. New guided-speaking and introductory answers contribute only where their saved question contract supports the target.

Learners can attempt the current milestone early. Higher-level standalone practice remains available. Completing this application's A1 course preserves access to A2 practice; a guided A2 region is not yet authored. This is an application course, not a TORFL certificate.

## Shared practice tools

After checking a letter, a learner can keep a word through the existing lemma/form resolver and topic/mnemonic enrichment pipeline. Ambiguous lexical readings require a choice. English meanings remain attached to context.

Authored sentences can become ordinary native cloze cards, with contextual meanings, inflected forms, pictures, word audio and sentence audio. The normal generation queue, deduplication and FSRS schedules are reused. Reopening a letter does not create another deck or reset existing reviews.

An optional written reply opens a saved task in Writing. It uses the same draft storage and assessment service as other writing tasks. Repeating the action returns the existing task. Neither follow-up is required to pass the letter.

Anonymous demo visitors can use the authored preparation and letters without AI calls. Collection-saving follow-ups are offered in local installations and signed-in workspaces, where the existing provider budgets apply.

## Persistence and migration

Schema 045 identifies course releases and preserves earned A2 access. Schema 046 adds target observations and resumable preparation. Schema 047 adds assessment drafts, explicit release switches and follow-up references.

Schema 048 makes preparation's release, target catalogue and content identities explicit. New links include the release; old attempt links and command receipts remain valid. Schema 049 adds diagnostic task contracts and criterion reports for the [curriculum implementation](curriculum-implementation.md). Those reports do not change this course's pass policy.

New learners use the current release. Existing enrolments remain pinned to their earlier course until the learner accepts the switch preview. Earlier milestones, active letters, answers, media and continuation rights remain available. Old passes are not presented as newly assessed targets. The earlier final letter keeps its historical wording.

Assessment drafts use revision checks. A second tab cannot silently overwrite a newer draft. Profiles own their attempts, practice and follow-ups. Start and answer commands retain their original request receipts; replayed receipts hide future milestone details under the current presentation rules.

Coins reward participation. Skill estimates describe performance. FSRS schedules vocabulary reviews. Milestones record course progression. None substitutes for another.

## Release checks

The source catalogue, its content hash and audio are versioned. Published text is not edited in place. Editorial review checks the Russian, answer evidence, distractors and target mappings. Automated checks cover all variants, media decoding, scoring, support, retries, ownership and migration.

The content has been reviewed by the implementation agents. A human learner pilot has not been run. The current thresholds and distractor difficulty remain subject to that pilot; no claim of validated proficiency measurement is made.

Run a read-only inventory and optional rehearsal before a database upgrade:

```sh
python scripts/audit_course_migration.py --db /path/to/vocab.db --rehearse
```

The rehearsal upgrades a temporary SQLite backup and checks retained course rows and foreign keys. It leaves the source unchanged. Normal application migrations also create pre-migration backups.

`COURSE_DEFAULT_RELEASE=a1-v1` changes the default for learners without an enrolment. It does not rewrite existing enrolments or delete new work. Keep a build that understands both releases when rolling back routing. Do not restore an old database over completed learner work.

Generate missing authored audio only in an explicit maintenance run:

```sh
python scripts/prepare_milestone_audio.py --env-file /path/to/existing/.env --dry-run
```

The script preserves configured random voices and completed clips. Learner requests play bundled recordings without provider calls. Native card media and writing feedback continue to use the existing AI admission and budget controls.
