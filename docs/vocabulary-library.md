# Vocabulary library uplift

Implemented 11 September 2026 at `/vocab`. The page uses the existing Flask shell and Preact vocabulary component, with scoped paper styling. It does not migrate or rewrite the vocabulary data model.

## Using the library

- **Word library** shows structured vocabulary; **Google Drive** shows the existing capture list. **Add a word** continues to save to Drive, and the dialog explains this. Sync and cleanup remain under **Sync & tools**, with the existing review steps and capture/export semantics.
- Search matches lemmas and stored inflected forms, ignoring case, optional stress marks and the ё/е distinction for search only. Nothing is normalised in the database.
- Part-of-speech and difficulty filters come from actual stored values. This fixes missing matches caused by the old hard-coded `ADV`/`PRON`/`NUM` filters against `ADVB`/`NPRO`/`NUMR` rows.
- The compact table shows words, topics, difficulty and card coverage. A word expands to reveal its mnemonic, added date, card history summary, original grammatical form records and links to generation/dictionary lookup. Identical spellings with different grammatical tags remain separate forms; homographic lemma records remain keyed by their word ID.
- Current card counts link to `/#flashcards?word_id=<id>`. The card browser opens that word's collection, and generator links preselect the same word. Applying further card filters retains the word selection; **Show all cards** clears it.

## What “Cards” counts

The previous column displayed `words.count`, a historical Anki export counter. Native generation already writes stable `card_definitions` and version references linked to `words.id` and, where known, `forms.id`. It intentionally does not increment the Anki counter.

The vocabulary response now includes:

| Field | Meaning |
| --- | --- |
| `native_count` | Distinct current published, unretired in-app card identities for the word |
| `native_total` | All saved native card identities, including unpublished and retired records |
| `anki_exports` | Existing `words.count`, explicitly labelled as historical exports |
| `form_count`, `forms_search` | Stored form-record count and spellings used for search |

The API retains the old `count` value for existing consumers. It is not a combined total. Adding it to the native count would mix a cumulative export counter with a current inventory, and cannot establish how many cards still exist in Anki.

`repositories/vocabulary_inventory.py` derives native counts from the same published-version selection used by the reviewer in `card_repository.py`. It counts a stable card once across revisions and collection memberships. New cards appear on refresh or returning to the tab; deleting/retiring a card removes it from current coverage but keeps its historical record. Suspended cards still exist in the collection and remain counted; suspension only affects scheduling. Failed generation creates no saved card. No increment triggers, duplicated counter column or backfill are needed.

`GET /vocab/words/<word_id>` provides the exact form records and saved native card identities. Form coverage uses the recorded `form_id`, never a guess from spelling. A card without a form ID contributes to its word count but not to an invented form count. Reading counts, browsing forms and using filters make no AI or Anki calls and do not change schedules.
