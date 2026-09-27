# Household mode: shared learning foundation

**Current scope:** this guide describes optional household mode. Individual flashcards do not require these PIN, profile-selection or approval steps. Use the [native MVP guide](native-flashcards-mvp.md) for automatic generation and personal study.


This is the shared learning foundation: the minimum of WP-04/05/06 and the reward/asset boundaries. Native FSRS review is now implemented separately in the [Stage 2 MVP](native-flashcards-mvp.md) (WP-17); this page records the original shared foundation. The subsequent interface rebuild replaces Moon Picnic with a real approved-choice activity player; see the implementation record.

## Delivered behaviour

- Local household setup, a hashed grown-up PIN, persistent failed-login throttling, expiring access and explicit learner selection. Selecting a learner ends grown-up access in all tabs of that browser. The selected profile is checked again inside learning transactions.
- New learner profiles own their attempts and evidence. Legacy user 1 gets an archived, explicitly labelled history mapping during setup; existing totals and records are retained. They are never copied to new learners.
- One shared access policy covers legacy tools, media/uploads, the catalogue and new APIs when household mode is enabled. New routes default to adult access unless explicitly classified. Same-origin CSRF tokens protect forms, JSON, HTMX and the two legacy GET operations that generate sentences or run sync.
- Validated JSON content imports as drafts. Grown-ups inspect prompts, answers, hints and attachments, then explicitly publish immutable versions. Edits create new versions. Withdrawal blocks further use while retaining saved sessions/history.
- Server-issued choice activities prove start/read/help/attempt persistence, revision conflicts, retries, independent learner histories and atomic completion. This is a foundation adapter exercised by tests/API, not a new child game release or a recall scheduler.
- The participation ledger is the balance authority. The initial versioned activity policy awards 3 coins per stable activity/study day, up to 12 activity coins/day, including incorrect answers. Review and activity categories have separate allowance scopes. The child coin UI, configurable economy, spending and review rewards are later work.
- Local content-addressed assets have database metadata and protected delivery. PNG/JPEG/WebP and short PCM WAV are supported now. Text-only cards are valid. MP3/provider conversion and Fly/Tigris are later adapters.
- A five-card basic/cloze starter pack is provided as an **unapproved draft**. It contains no inferred personal vocabulary IDs. Optional `word_id` links are validated and protected by relational references; link real library entries deliberately when preparing a household deck.

No external service, cloud resource, personal content approval or live personal-database upgrade was required to implement/test this stage.

## Enable on a local development database

Use the isolated database/runtime variables from the [root setup guide](../README.md#local-setup), Python 3.12 and a built UI. Keep development and personal runtime directories separate. Then, from the repository root:

```sh
export WORD_POST_ASSET_DIR="$PWD/instance/word-post-assets"
python -m flask --app flask_vocab_app/app.py:create_app db-upgrade
python -m flask --app flask_vocab_app/app.py:create_app word-post setup
python -m flask --app flask_vocab_app/app.py:create_app word-post import-pack flask_vocab_app/content/starter-postcards.json
```

`setup` prompts for a 6–12 digit PIN and confirmation; only its password hash is stored. It refuses to overwrite an existing household. Set a private random `FLASK_SECRET_KEY` of at least 32 characters in your ignored environment file and set `WORD_POST_HOUSEHOLD_ENABLED=true`. Restart the server, bound to `127.0.0.1`, and open `/post/household`.

Unlock, add a learner, and inspect the starter pack. Publishing requires a reviewer name and an explicit approval checkbox. Review the Russian, meanings, support and learner suitability before approving. Publishing a deck makes it available to the native reviewer when `NATIVE_FLASHCARDS_ENABLED` is enabled. New v2 contextual cards can be prepared in the [MVP editor](native-flashcards-mvp.md).

Household mode defaults **off** to preserve the existing development workflow until setup. When enabled it accepts loopback hosts only, expires adult access after 15 minutes and browser access after one hour, and locks PIN attempts for five minutes after five failures. These are local household controls, not hosted accounts. LAN/public hosting needs its own authenticated deployment boundary; do not simply expose this PIN app on Fly.

Local PIN recovery (retains learning data and revokes all browser access):

```sh
python -m flask --app flask_vocab_app/app.py:create_app word-post reset-pin
```

Keep household mode enabled when rolling back a visual change. Turning that flag off deliberately restores the unprotected legacy development mode; it is not an access-preserving production rollback.

## Content and asset contracts

[Starter deck](../flask_vocab_app/content/starter-postcards.json) demonstrates schema version 1. The validator rejects unknown fields/types, duplicate item IDs, ambiguous choice labels, missing lexical IDs/assets and invalid cloze markers. Text is rendered escaped; arbitrary Anki HTML/JavaScript is unsupported. A stable content ID can acquire several immutable versions; it cannot change between deck and activity kinds.

For an optional image or WAV file:

```sh
python -m flask --app flask_vocab_app/app.py:create_app word-post import-asset /absolute/path/to/media.png --source "Describe its source and permission to use it"
```

Reference the resulting asset ID in an item's `asset_ids`. Asset bytes are stored outside public static directories. Unpublished attachments are adult-only; published attachments are available to the currently authorised learner. The first household release makes published content available to all its active learners; per-learner assignments and required-audio activity types come later. Withdrawal removes child access unless another published version still references the asset.

## API boundary

All enabled JSON APIs are same-origin. Obtain a session CSRF token from `GET /api/v1/household` and send it as `X-CSRF-Token` on writes. Successful unlock rotates the browser session and token. Private responses use `Cache-Control: no-store`.

| Route | Current responsibility |
|---|---|
| `GET /api/v1/household` | Setup/access status, current learner and CSRF token; learner list only for an unlocked adult |
| `POST /api/v1/household/unlock`, `/lock` | PIN access / revoke this browser's access |
| `POST /api/v1/grownups/profiles` | Create a learner using `display_name`, `study_timezone`, optional `avatar` |
| `POST /api/v1/grownups/profiles/{id}/select`, `/archive` | Select or archive an existing learner; no history deletion |
| `GET /api/v1/grownups/content/{version}` | Inspect a frozen payload and publication metadata |
| `POST /api/v1/grownups/content/{version}/publish`, `/withdraw` | Explicit approval / withdrawal |
| `GET /api/v1/post` | Latest published content, this learner's sessions and balance; `native_review_available` reflects the native feature flag |
| `POST /api/v1/learning-sessions` | Create a choice-activity session using `profile_id`, `version_id`, `submission_id` |
| `GET /api/v1/learning-sessions/{id}` | Recover the pinned version, current item, saved responses and revision |
| `POST /api/v1/learning-sessions/{id}/help`, `/attempts` | Record help or a reviewed choice; only the issued item is accepted |
| `GET /api/v1/word-pocket` | This learner's raw recognition evidence and reward ledger; no mastery claims |
| `GET /api/v1/assets/{id}` | Authorised local asset delivery |

An attempt needs `submission_id`, `expected_revision`, `item_id` and `answer: {"choice_id": "..."}`. Help uses the same fields except `answer`. Client scores, rewards, arbitrary learner attribution and extra keys are rejected. A repeated committed key/payload returns the original response; changed-payload reuse or a new stale revision returns 409. A stale-revision response includes `error.current_session`; a GET can also recover the current session. A withdrawn version is unavailable even for a retry, and cross-profile access is checked before any cached response is returned. A new start key intentionally creates a new session; resuming uses the stored session ID from the home response.

The transaction reserves the SQLite writer before reading mutable state, then records attempts, evidence, progress, rewards and the retry response together. If any write fails, all effects roll back. Lock contention can return 503; retry the same submission ID. [SQLite transaction behaviour](https://www.sqlite.org/lang_transaction.html). Browser session rotation and synchronizer CSRF tokens follow [Flask-Session guidance](https://flask-session.readthedocs.io/en/latest/security.html) and [OWASP's token guidance](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).

## Backup and restore

```sh
python -m flask --app flask_vocab_app/app.py:create_app word-post backup /absolute/path/to/a-new-backup-directory
```

This snapshots the **entire application SQLite database plus Word Post assets**, checks integrity/foreign keys and asset hashes, and writes `manifest.json`. An existing destination is never overwritten. An interrupted/failed backup retains an `INCOMPLETE` marker and must not be used as a verified backup. Word Post files are immutable by content hash; no automatic garbage collection is enabled.

Also retain the existing application media/uploads, external Anki collection and Drive capture backups described in [operations](operations.md). The command does not include those separate stores. Keep backups private: SQLite contains profile/history data and the household PIN hash.

Restore into a new directory while the target app is stopped. Verify the database and asset hashes against the manifest, point `VOCAB_DB_PATH` at `vocab.db` and `WORD_POST_ASSET_DIR` at `assets`, and use a fresh session directory. Unlock with the household PIN, select the existing learner and verify a saved session and its media. Never restore an old database merely to roll back CSS or a template.

## Verification and remaining boundary

The automated suite covers concurrent duplicates/caps, changed-payload retries, stale revisions and profile switches, failure rollback, PIN throttling/expiry/recovery, CSRF, legacy URL bypass, draft/withdrawn/private access, validated assets, immutable content, local study-day boundaries, exact legacy-row preservation, and database/media restoration into a fresh app. The UI suite exercises the legacy CSRF adapter as well as the existing Word Post interactions. Unit workflows block external network calls.

The [native MVP](native-flashcards-mvp.md) now implements per-card memory state, FSRS, the review queue, reveal/Again/Good, history and safe undo on this foundation. The deterministic choice adapter must not be treated as recall evidence. Add native review rewards separately from activity allowances, then extend the connected choice player with the native review API. Anki Link, Elo adaptation, remaining game adapters, provider jobs, richer authoring/assignment controls and hosted storage remain later work.
