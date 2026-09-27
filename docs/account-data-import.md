# Local account import

Local profiles and hosted accounts have separate databases. Hosted sign-in does
not upload local vocabulary, lessons, recordings or card schedules. The hosted
database is selected using the account's canonical identity, not its display name.
Connecting Google to an existing GitHub account keeps the original identity and
database. See [account sign-in](account-sign-in.md).

`scripts/import_local_account.py` prepares an offline database artifact for a
private account. It never connects to Fly.io and never replaces a live database.
The original snapshots remain unchanged. Personal data must stay outside Git.

## Supported merge

The local snapshot supplies the existing learning history. It is upgraded in a
temporary copy. Hosted vocabulary, sample cards, writing and speaking sessions
are then added. The utility checks both input databases and validates every
foreign key in the output.

- Words match by lemma and part of speech. Forms match by word, form and tags.
- Card IDs remain stable. Linked word and form IDs are remapped in both the
  relational records and card payloads. Card objective hashes and sibling keys
  are rebuilt using the existing flashcard contracts.
- Existing hosted writing URLs keep their meaning. Colliding local writing IDs
  move together with their titles, drafts and other declared references.
- Writing criterion contracts follow their typed task and attempt references.
  Frozen contract and report text stays unchanged. Embedded identities that
  would require rewriting a frozen payload stop the import for review.
- The original study timezone is kept. The hosted account name is retained.
  Completed introductions from either workspace remain completed.
- Local review history, schedules, lessons, other profiles and Anki records are
  retained. Browser access credentials and household PIN settings are excluded.
- Conflicting vocabulary metadata is retained in `account_import_archive` in
  the private output database. It does not become a new user-facing screen.

This utility supports the initial import into an account with sample cards and
writing/speaking work. It is not continuous sync. Hosted review, reward or game
history needs an additional merge policy before import. Unknown conflicts stop
the process; they are never silently overwritten. Re-importing a previously
merged database also stops for review.

## Preparation

1. Confirm the intended canonical identity and tenant directory through the
   hosted identity registry. Resolve connected providers to that account first.
   Never select an account from a submitted username alone.
2. Back up the local database with `backup_learning_store`. This copies lesson
   sources, content-addressed assets and recordings and makes legacy lesson
   paths portable in the snapshot. Collect legacy story and sentence media too.
3. Pause requests for the target tenant and finish any provider operations.
   Back up its database and media on the server, then download a SQLite snapshot.
4. Keep both snapshots and their checksums. Run the importer:

```sh
python scripts/import_local_account.py \
  --local /private/import/local/vocab.db \
  --hosted /private/import/hosted.db \
  --output /private/import/merged.db \
  --report /private/import/merge-report.json
```

If the local snapshot contains Speaking criterion reports, also supply
`--local-audio-root /private/import/local/live-conversation-audio`.
The importer checks original recording bytes, sample timing and the assembled
audio hash before producing the database. It refuses missing or altered
recordings and conflicting filenames. It does not copy media or rebuild audio
evidence from captions. Imports with hosted criterion history remain unsupported
until a separate merge policy exists.

## Verification and installation

The report lists counts, ID changes and metadata merge decisions. Check these
against both input libraries. Verify card payloads, schedules, phrasebook rows,
lesson sources, speaking recordings and existing hosted writing URLs.

Media is deliberately separate. Merge the two file sets by relative path and
checksum. A matching path with different bytes requires a new path and explicit
reference updates. Check every referenced file before installation. Review the
tenant storage allowance against the combined data size.

Before installing, verify the paused hosted database still matches the snapshot.
Replace only that tenant's database and media while its requests remain paused.
Restart the application process so it opens the new database. Check the private
account and unauthenticated demo separately, then resume requests. Retain the
server-side rollback backup and original local data.

The import does not touch the shared AI budget, OAuth identity registry, public
demo database, other accounts or external Anki collection.
