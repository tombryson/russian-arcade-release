# A1 generation and passage support

Implemented and deployed on 4 October 2026 at `7e493e6`. This continues the [earlier pass](curriculum-pass-2026-10-04.md) with optional vocabulary support and generation plans for the remaining fourteen units. See the [deployment record](torfl-implementation-2026-10-02.md#deployment-update--4-october-2026) for release verification. The scope of the exam pilot is unchanged.

## Generation coverage

All seventeen A1 units now have two situation families in both reading and listening. A family defines a relationship to understand. A seed chooses people, objects and events within that relationship; the model writes a new message around them. Recent history favours the less encountered family.

The fourteen added units cover these situations:

| Unit | First situation | Second situation |
| --- | --- | --- |
| Personal reference | Identify the recipients of an item and a phone call. | Distinguish individual and shared belongings. |
| Noun–adjective agreement | Find a matching set of clothes. | Keep similar garments with their owners. |
| Present actions | Distinguish an individual action from a shared activity. | Follow the order of people reading and speaking. |
| Time and routines | Understand the day, starting time and activity of a session. | Distinguish yesterday’s action, today’s activity and tomorrow’s plan. |
| Possession and absence | Find someone who has a missing item. | Separate an item’s owner from its current holder. |
| Objects and recipients | Distinguish what is given, who receives it and who is called. | Separate an item being bought from one being given. |
| Basic motion | Understand a change to someone’s usual journey. | Find someone walking from the station after a vehicle journey. |
| Numbers and quantities | Check what is ready for a shared snack. | Identify the current lesson and its available materials. |
| Social exchanges | Learn two names and understand a request for repetition. | Identify what each person asks permission to take. |
| Needs and company | Coordinate an errand and a different need. | Prepare tea with the requested ingredient and companion. |
| Action and aspect | Distinguish work on a letter from a completed letter. | Understand whether reading is finished before a handover. |
| Origins and destinations | Follow an errand’s starting point and destination. | Distinguish leaving one person from going to another. |
| Connected messages | Understand a changed meeting plan. | Understand when someone can call and why they cannot call now. |
| Activities and professions | Connect a current profession with a future plan. | Identify people with shared interests. |

These are bounded language patterns, not complete story banks. Their lexical inventories remain finite. More families and verified word classes are still needed for lasting variety. New prose alone does not establish a new assessment or a different difficulty level.

## Russian and feedback

The plans store the intended event, checked forms, compatible alternatives and the question’s meaning before generation. They distinguish recipient from companion, owner from holder, a routine from a current journey, and activity from completion. An imperfective verb does not by itself prove that an action was never completed.

The new units use authored Russian questions and English equivalents. The model supplies the message and identifies the sentences that answer those questions. Checks bind alternatives to their construction, preserve planned predicates and require exact source evidence. Morphology helps validate forms; it cannot establish every syntactic relationship or contextual meaning.

Short visits now use «был/была» in the calendar plan and its questions. A thought must be explicitly disclosed rather than inferred. Prose guidance discourages unrelated lists, repetitive reporting verbs and titles that reveal answers.

Generation uses `source-v6` and language plan v5. Saved source-v5 tasks retain their original prompt, schema, feedback and pack. New tasks do not rewrite old answers or schedules.

## Optional word support

“Words and phrases” opens contextual meanings beneath the passage. It is collapsed until requested. Entries use words or phrases actually present in the message. They do not become universal English translations on the lemma record.

A new passage is rejected if a content word is outside its declared familiar vocabulary and lacks an annotation or an exact supported expression. Proper names and a frozen function-word policy are handled separately. The latter is a generation convention, not evidence that a learner knows those words. A familiar lemma also does not establish knowledge of every form or sense.

Annotations identify an occurrence and its grammatical reading. A gloss for the noun «печь» cannot also cover the verb «печь» elsewhere in the message. Different contexts or case forms can have separate entries. The limit is three new lemmas and eight visible support entries, including supplied phrases. The generator must simplify a passage that exceeds those limits.

Opening support is saved before meanings are displayed. Remaining questions about that passage count as assisted; earlier answers keep their original status. Reloading or collapsing help cannot erase the receipt. In listening, the transcript must be explicitly opened first. Saved tasks without support keep their existing behaviour.

Selecting and saving a word still uses the shared lemma/form, mnemonic and enrichment pipeline. Opening the glossary does not add anything to the vocabulary store. Automatic flashcard reuse of the original passage sentence remains separate work: it needs a checked contextual meaning and full-sentence translation.

## Generation checks

The [evaluation record](validation/curriculum-expansion-2026-10-04.json) contains results, reviews and provenance hashes. Its accompanying [compressed JSON archive](validation/curriculum-expansion-2026-10-04.json.gz) preserves frozen requests, provider inputs, raw responses and accepted documents. Accepted documents refer to their enclosing request rather than repeating it. No personal learner data was used.

| Phase | Text calls | Original structural acceptance | Purpose |
| --- | ---: | ---: | --- |
| Preliminary support check | 6 | 2 | Find missing word support and source-reference problems. |
| All seventeen units | 68 | 47 | Check both families in reading and listening for every unit. |
| Targeted follow-up | 24 | 18 | Revisit failed families and reference, agreement and thought-disclosure cases with fresh seeds. |

These are different prompt and validation revisions. They must not be pooled as the success rate of one unchanged generator. All calls used the configured `gpt-5.6-luna`, with no automatic retry or audio generation. There were no provider connection failures. The application estimated US$0.120637 across all 98 calls; this is not a provider invoice.

The checks found problems that a schema alone cannot detect. A title gave away a tested place. A later question disclosed whether someone was walking. Some pronouns had two plausible antecedents. One meeting location appeared attached to the reason for a delay. Several messages were grammatical but read like inventories. The initial English hints also embedded direct questions inside sentences; they now use authored indirect prompts.

The final follow-up also exposed false rejections of valid Russian: noun ellipsis, a predicate adjective after its noun, and «Я» misclassified as a personal name. Fixes and offline replays are recorded separately from the original provider outcomes. They are not additional successful generation calls. Assistant review does not establish independent language validation or learner outcomes.

Replaying the 24 unchanged outputs through the final validator accepts 18 and rejects six. Four valid constructions are recovered. Four previously accepted passages are now rejected for the unclear venue, invented encounters or a broken ownership clause. The remaining two failures lack word support or change a reported personal plan into an assertion. The phone-call plan conservatively excludes unplanned encounters and locations; it does not claim that those additions would always be incorrect Russian. These bounded guards are not a general parser or proof of semantic entailment.

A provider-free sweep also checked 6,800 requests: seventeen units, one hundred seeds, both modes and two synthetic vocabulary profiles. For the original three units it checked required fact values; for the added fourteen it checked full reference frames. One meeting family could require four unfamiliar lemmas because only part of its repeated predicate had phrase support. Adding «предлагает встретиться» resolved the pressure in a 400-request follow-up. The maximum for that family fell to two new lemmas and five support entries. These are plan-feasibility checks, not generated-prose quality or vocabulary-adaptation results.

## Software and browser checks

The complete UI suite passes 843 tests in 65 files. TypeScript and the production build pass. An isolated browser check covered optional reading help, a saved assistance receipt after reload, contextual word lookup and saving through a stubbed enrichment provider. A bundled Russian recording played to its native end event; opening its transcript then enabled word help and retained assisted-listening status after reload.

That playback check verifies the player and disclosure rules. It does not assess newly generated speech, provider pronunciation or prosody.

Backend discovery exercised 2,184 tests. Three old plan assertions needed updating for the new coverage and wording. The final affected suite passes all 200 tests, including those assertions, the new language guards, passage help, saved-task compatibility, vocabulary capture and audio access. The suite includes an unchanged source-v5 fixture and all 68 unit/family/mode adapter combinations. The subsequent clean release CI passed all 2,221 backend tests and 843 frontend tests. The release adds no database migration or production speech-provider change.

## Remaining work

- Check fresh prose after the final fixes. The stored-output replay verifies rejection and compatibility changes; it does not measure a new generation success rate. Repeated names and proposals still need refinement in some accepted samples.
- Measure adaptation using matched seeds and different familiar-word inputs. Current checks constrain vocabulary but do not prove good personalisation.
- Extend supported expressions beyond exact passage occurrences where Russian question wording introduces unfamiliar language. English UI already uses the question’s English equivalent.
- Add more communicative purposes and verified lexical classes; retain prerequisite teaching for each extension.
- Prepare complete examples from captured words for original-sentence flashcards.
- Extend fresh Writing and Speaking tasks. These reading/listening plans do not complete original production or full A1 assessment coverage.
- Evaluate generated audio for pronunciation and naturalness. Audio still uses the existing on-demand pipeline; this pass changes no voice provider.
