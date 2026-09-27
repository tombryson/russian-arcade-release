# Vocabulary data model and flashcard generation

This guide describes the vocabulary schema, import rules and card-generation paths as of September 2026. The final section lists proposed improvements.

## Modelling rationale

The database groups Russian forms under a lemma: the dictionary form of a word.

A learner may save **книгу**, encounter **книги** in a lesson, and look up **книга** in a dictionary. These forms belong together. Their endings are part of what the learner needs to practise.

The same spelling can have several grammatical readings. **Книги** can be genitive singular, nominative plural or accusative plural. The sentence determines which reading applies.

The schema therefore distinguishes three things:

1. **Vocabulary entry:** the lemma and part of speech.
2. **Form:** its spelling and grammatical tags.
3. **Example or card:** its use and meaning in a sentence.

Review history is stored separately. Saving a word does not show that a learner knows its forms.

## Core tables and constraints

The original definitions are in [001_baseline.sql](../flask_vocab_app/migrations/001_baseline.sql).

| Table | Identity and relationships | Information stored |
| --- | --- | --- |
| `words` | Integer `id` primary key; `UNIQUE(lemma, pos)` | Lemma, part of speech, historical Anki count, lemma difficulty, topics, mnemonic and date added |
| `forms` | Integer `id`; `word_id` references `words.id`; `UNIQUE(word_id, form, tags)` | Spelling, JSON grammatical tags, historical Anki count and form difficulty |
| `anki_cards` | Anki `card_id`; foreign keys to both word and form | Imported Anki scheduling/review metadata |

Other tables link to numeric IDs. The lemma’s spelling is not the primary key.

The uniqueness rule permits separate noun and verb entries for **печь**. It does not separate meanings that share both spelling and part of speech. The older importer also skips a lemma if that spelling already exists. It therefore does not make full use of this schema rule.

Tags describe the form’s grammar. New imports retain the analyser's exact form POS (`ADJF`, `ADJS`, `PRTF`, `PRTS`, `GRND`, and so on), case, number, gender, animacy and applicable verbal features. The lemma's broader POS label remains separate. Older form rows retain their original tags and IDs.

SQLite compares the stored JSON text when checking uniqueness. Different key order or spacing can make equivalent tags appear different. The importer uses `form_selection.canonical_tags` with sorted keys and the existing spacing convention. Explicit lexical backfill compares decoded tags so equivalent key ordering does not create another row. Other writers still need consistent formatting too.

## Form generation pipeline

The application uses [SyncService.process_word](../flask_vocab_app/services/sync_service.py) for vocabulary import.

For each new entry, the service:

1. Uses `pymorphy3` to identify possible grammatical readings.
2. Ranks them using the analyser’s score and `wordfreq` frequency estimates.
3. Generates the chosen reading’s family of forms through `lexeme`.
4. Filters candidates, removes duplicates and saves the remaining forms.

After that transaction commits, `SyncService.enrich_words` assigns topics and a mnemonic through the existing AI methods. This is part of vocabulary import, not optional card decoration. Drive imports, lesson selections and game captures share this step. Existing annotations are preserved. A failed call leaves the missing fields eligible for retry; it does not save a placeholder as a completed mnemonic.

The ranking formula is `analyser score + frequency × 1,000,000`. It favours common readings but does not resolve meaning from sentence context.

### Current filters in `SyncService.process_word`

| Candidate | Current rule | Purpose and caveat |
| --- | --- | --- |
| Noun | Keep `nomn`, `gent`, `datv`, `accs`, `ablt`, `loct`; require `sing` or `plur`; reject frequency below `6e-7` | Covers the six main cases. Other case categories are excluded. |
| Full/short participle (`PRTF`, `PRTS`) | Reject frequency below `2e-6` | Uses a stricter threshold to reduce uncommon participles. |
| Finite verb/infinitive (`VERB`, `INFN`) | Reject zero-frequency candidates | Removes forms absent from the frequency lookup. This does not prove they are invalid. |
| Adjective/short adjective/comparative (`ADJF`, `ADJS`, `COMP`) | Reject zero-frequency candidates | Applies the same frequency check. |
| Superlative | Reject below `1e-7` when the analyser includes `Supr` | Uses the actual analyser grammeme, rather than an unavailable degree accessor. |
| Neuter noun form ending in `ь` | Reject unless it matches the lemma | A legacy filter for a specific spelling/tag combination. |

Frequency estimates come from language data, not the learner’s vocabulary. The thresholds are roughly 0.6 occurrences per million for nouns and 2 per million for participles. Useful specialist or literary forms may fall below them.

The limits are 12 distinct noun readings and 24 distinct full-adjective readings, in dictionary order. Reaching the full-adjective limit no longer stops traversal before short adjectives or comparatives. Short forms still follow their frequency rules and have no invented case tag.

The stored forms are a study selection, not a complete dictionary entry. Some lemmas may have no forms left after filtering.

### Deduplication and historical information loss

Duplicate detection compares spelling and saved tags. Noun forms with different case or number tags remain separate.

New imports preserve case and animacy before deduplication, including separate genitive and animate accusative readings of the same adjective or participle spelling. Past-tense verb gender and participle aspect/voice remain available. Full and short forms have distinct POS tags; a short adjective does not require a case.

Older imports lost some of these distinctions. No automatic backfill rewrites those rows or guesses which reading an old card intended. An explicit lexical backfill may add newly identified analyses alongside them while retaining old IDs, scores and card/review links. Part-of-speech labels still vary in historical data and some contextual writers.

### Lemma and form difficulty

The importer estimates lemma difficulty on a 1–5 scale using rarity and spelling length. It then derives form difficulty from that base:

- Add 1 for plural forms.
- Add 2 when tags identify a participle.
- Cap the result at 8.

The same +2 adjustment now applies to new adverbial-participle (`GRND`, also called gerund) forms using their saved POS. Existing nonzero difficulty values remain unchanged.

These scores help filter vocabulary. They are separate from curriculum task levels, learner skill estimates and the FSRS scheduler’s difficulty values.

### Curriculum topics

The [curriculum](curriculum.md) assigns the fifty canonical vocabulary topics to A1, A2, B1, B2 or a shared C1–C2 band. The topic band describes where the subject enters the course. Activity generators use a separately selected A1–C2 task level. Neither field replaces `lemma_difficulty` or `form_difficulty`.

The versioned catalogue holds target lemmas, phrases, grammar and activity objectives. It does not create vocabulary rows or rewrite their annotations. A learner's saved word still passes through `process_word` and `enrich_words`, including form generation, topics and a mnemonic. The existing `grammar` category remains cross-topic.

## Form selection and card generation

The [Anki batch service](../flask_vocab_app/services/flashcard_service.py) filters words by part of speech, topic, lemma difficulty and export count. It then applies any case and form-difficulty filters and selects a form at random. A separate `process_word_forms` method iterates stored forms.

Generation receives the lemma, selected form and tags. It produces a sentence containing that form, a missing-word prompt, contextual English meaning and full translation. Images, audio and grammar/topic tags support the card. Successful exports update the word and form counts.

Some older filters match JSON as text. They can fail when spacing differs. Newer queries use `json_extract` to read tag values directly.

### Native card identity, versioning and learner state

The native card structure begins in [009_native_flashcards.sql](../flask_vocab_app/migrations/009_native_flashcards.sql). Later migrations add [media jobs](../flask_vocab_app/migrations/011_card_media.sql) and [four-button ratings](../flask_vocab_app/migrations/012_four_review_ratings.sql).

| Table | Role |
| --- | --- |
| `card_definitions` | Card identity, optional word/form links, recall direction and identifiers for its meaning and task |
| `card_versions` | Link a card identity to an item in a saved content version |
| `learning_content_versions` | Store the versioned payload, including contextual wording and translations |
| `learner_card_state` | Each learner’s schedule, due date, counts and suspension setting for a card |
| `review_sessions`, `review_session_cards`, `review_session_items` | Record the review session and individual presentations of its cards |
| `review_events`, `review_reversals` | Record answers/ratings and explicit undo events without deleting the original history |
| `learning_assets`, `learning_content_assets` | Store media metadata and links from content to its assets |

Word and form links are optional for compatibility with existing content. When supplied, validation checks that the form belongs to the word. It also checks that filling the blank restores the Russian sentence.

Native card counts come from published, active cards. The historical `words.count` and `forms.count` fields still track Anki exports. Anki scheduling records in `anki_cards` also remain separate. See [vocabulary inventory](../flask_vocab_app/repositories/vocabulary_inventory.py).

The [native batch selector](../flask_vocab_app/services/card_generation.py) filters words by topic, part of speech and active card count. It can filter forms by case and by form difficulty, using lemma difficulty when a form's score is missing. A lemma without stored forms is eligible for a difficulty filter only when its own score matches; a case filter requires a matching stored form.

[Form selection](../flask_vocab_app/services/form_selection.py) uses previous native generation selections to favour less-used words. Within a word, it ranks eligible forms by commonness, previous form use, previous use of the grammatical reading, whether the spelling differs from the lemma, frequency and ID. Reading groups include POS, case, agreement and verbal features, so distinct gender or aspect readings no longer share a bucket merely because their tense matches. This is deterministic rotation, unlike the Anki generator's random choice. Non-failed generation selections contribute to this history; they do not establish learner mastery. Explicit lesson selections retain their original form.

Tasks can call `choose_form(..., constraints={'case': 'accs', 'number': 'sing', 'animacy': 'anim'})`. Each named analyser tag accepts one value or a nonempty collection of alternatives. All constraints must match before the existing frequency and rotation ranking applies; missing historical tags do not count as a match. No compatible form returns `None`, which a targeted task must handle as unavailable rather than substitute a lemma. A rare stored form can be selected when it is the compatible reading. These constraints express morphology, not a semantic function such as possession: the saved sentence and task contract establish that function. They add no new learner-facing filter or automatic backfill.

## Lesson and game integration

A lesson selection records a word as it appeared in the source. It keeps the exact form, sentence, document revision, page, OCR reading and corrections. It can link to existing vocabulary or add a validated lemma/form pair. For a new lemma, it now runs the same form-generation and frequency filters as the vocabulary importer. The exact, dictionary-validated form selected in the lesson is retained even if those frequency filters would exclude it. Existing vocabulary rows and their IDs are preserved.

| Table | Purpose |
| --- | --- |
| `lesson_word_picks` | Save selected words and their source details |
| `lesson_card_requests` | Track card preparation |
| `lesson_card_targets` | Identify targets that can reuse existing cards |
| `lesson_card_sources` | Link generated items to source pages |

Lesson cards use the same review tables and scheduler as other native cards.

[Journey vocabulary](../flask_vocab_app/services/journey_vocabulary.py) draws from stored forms, confirmed lesson selections and prepared examples. Difficulty filters use form difficulty where available, with lemma difficulty as a fallback. New words use a separate validation and capture workflow.

## Sample vocabulary

The public demo and hosted trial use authored examples, not personal vocabulary. Their words go through the same form generation, topic assignment and mnemonic generation as other imports. The prepared topics and mnemonics are stored in `flask_vocab_app/data/sample_vocabulary.json`, with the model names and preparation date.

Maintainers regenerate that file with `scripts/prepare_sample_vocabulary.py`. The script uses a temporary database and the existing provider configuration. It publishes the file only when every sample word has valid topics and a mnemonic. Deployment loads the saved results, so restarts and new visitors do not trigger paid generation.

“First steps” identifies a lesson source. It is not a lexical topic. Trial startup backs up and repairs incomplete sample entries without replacing word IDs, linked cards, counts, custom mnemonics or review history. New sample cards retain their lesson source separately from vocabulary metadata.

Lesson and game capture run enrichment after saving the validated word and its forms. Card preparation refreshes its saved selection with that enrichment before generating the card. Existing cards without their own hint can use the linked vocabulary mnemonic. Hints remain hidden until requested. Contextual meanings stay on the cards.

## Contextual meanings and translations

The `words` table has no required English translation. A word can have several meanings; a card needs the one used in its sentence.

Card content stores the English cue and sentence translation alongside the Russian example. A `sense_key` helps identify the intended meaning within the card system. It is not a full dictionary of word senses.

Part of speech, grammatical form and contextual meaning are separate concerns. Numbered translation columns would not capture these relationships.

## Limitations and proposed improvements

Recommended follow-up work:

1. Share one form-selection policy across Anki, native generation and games, while preserving lesson-specific occurrences.
2. Connect task grammatical constraints to reviewed functions and sentences; morphology alone cannot establish the intended meaning.
3. Audit incomplete historical tags without relabelling old cards or replacing linked forms.
4. Extend canonical part-of-speech names and JSON formatting to remaining writers. Query tag values directly.
5. Make frequency thresholds and form limits explicit import settings, with a preview of what will be excluded.
6. Handle ambiguous lemma and part-of-speech readings consistently across capture paths.
7. Test difficult examples—homographs, short forms, participles, past-tense gender, low-frequency vocabulary and ё/е—before backfilling existing records.

Schema or data repairs should preserve IDs, card links, lesson selections and review history. Test them on a backed-up copy before migrating existing data.
