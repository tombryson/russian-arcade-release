# Vocabulary capture and synchronization

## Product contract

Drive is an easy place to capture Russian words on mobile. SQLite stores the validated and organized learning library. The vocabulary page can capture words in Drive, and the explicit sync action imports suitable words into SQLite. In-activity capture saves directly into SQLite through the same lexical pipeline. This preserves the deliberate multi-channel capture workflow.

Removing a word from Drive never deletes its SQLite record, inflections, or learning history. The existing reverse-export behavior is preserved: sync adds SQLite-only lemmas back to the Drive list. Drive is therefore a capture list that can also contain exported library words, not a consumable queue. Changing that export policy requires an explicit product decision.

## Saving words from Comprehension

Selecting a word reads its dictionary-supported lemma and part of speech. Existing words also show their saved mnemonic. Lookup makes no AI call. The popup does not assign a universal English translation to the lemma; meanings remain attached to their examples. If the dictionary supports different words or parts of speech, the learner chooses the reading that fits the sentence.

**Add to my words** uses the same lemma/form resolver as games and lesson cards, which calls `SyncService.process_word`. It commits the lemma and filtered forms, then calls `SyncService.enrich_words` for missing topics and mnemonics. Hosted calls use the existing AI allowance controls. A provider failure leaves the word saved and reports that enrichment needs a retry. Retrying keeps its identity, forms and history.

The server verifies that the selected surface appears in the learner's owned story. A text fingerprint prevents an old tab from capturing against a different story. Newly generated, unsaved stories use the current server session as their source. The popup does not use a browser-wide vocabulary cache or report success before the server confirms it.

This direct capture does not require Drive access. The next explicit sync can export its SQLite lemma to Drive through the existing reverse-export step.

## Preview

`GET /sync/preview` returns `db_only` and `preview` (`to_add`, `rejected`). The HTML equivalent is `GET /sync_vocab`.

Preview fetches the latest Drive list, with no stale-cache fallback. It normalizes case and Unicode, validates Russian captures, considers existing lemmas/forms, and explains skipped/rejected entries. It does not change the vocabulary database, create backups, or alter schema. The provider may refresh its local token/cache as needed.

## Apply

`POST /sync` accepts JSON such as:

```json
{"to_add": [{"word": "машины", "lemma": "машина"}]}
```

The server treats `word` as the capture and recomputes its interpretation; it does not trust client-supplied lemma/POS decisions. A fresh Drive read verifies that each selected capture still exists. If the list changed, refresh the preview. An empty selection is allowed for exporting SQLite-only words.

A database backup is created immediately before importing. Each capture uses a savepoint, so a failed import does not leave half-created rows. Existing lemmas, inflections, counts, and enrichment are preserved on retries. New words are committed before provider enrichment; AI calls and Drive export do not hold a SQLite write transaction.

The response includes `run_id`, `status`, `imported`, `skipped`, `failed`, `enrichment_pending`, `exported`, `warnings`, and `backup_path`. `status` is `completed` or `partial` for returned results. A run interrupted by an unexpected failure is recorded as `failed`. A process terminated mid-operation can leave a `running` record for investigation. Latest run records are available through `GET /sync/history` (up to 20).

The UI displays counts and warnings. Missing AI configuration leaves normalized words in SQLite and reports pending enrichment. Drive export failure does not undo successful imports. Retrying sync is safe for already imported vocabulary and can retry the export. Dedicated enrichment retry controls and a background worker are not yet implemented; run history records which words need attention.

## Cache and concurrency

Ordinary Drive-list browsing can use the one-hour cache and can fall back to it when unavailable. Explicit preview/sync and every add/edit/delete/append operation use a fresh read and fail rather than rewriting Drive from stale cached content. Transport failures are reported as errors, not as duplicate-word results.

Fresh reads fix the previously identified hour-old-cache overwrite risk. The text-file read/modify/write protocol still has a smaller race if another device edits after the fresh read and before the upload. Conditional revision checks or a dedicated capture/event store are future work. Sync preview approval also does not freeze the external file. Do not describe this implementation as conflict-free bidirectional synchronization.

Sanitization remains a separate, explicit Drive-list rewrite. It does not delete SQLite learning history. Snapshot-aware sanitization and conflict handling remain on the roadmap; avoid applying an old sanitization preview after mobile edits.
