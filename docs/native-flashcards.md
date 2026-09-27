# Native flashcards and optional Anki Link requirements

Status: native-first direction, 8 September 2026. This document defines WP-17 and the revised WP-12 scope. The shared foundation and [native flashcards MVP](native-flashcards-mvp.md) now exist. This document retains the wider requirements; the MVP guide identifies exact implemented APIs, limits and remaining work.

**Scheduling decision:** start an independent native schedule and leave Anki untouched. Legacy counts, intervals and rewards do not seed native progress. Content may be imported through review and approval; historical scheduling import is not a first-release dependency.

**Meaning decision:** there is deliberately no universal English field. Keep card-specific reviewed senses, contexts and explanations. A content problem can be reported and corrected without recording a forgotten answer.

**Workflow correction, 9 September:** generation is automatic and cards save directly for individual study. Manual writing, household setup, PINs and another person’s approval are not prerequisites. Approval below applies only to explicitly enabled household mode. See the [current MVP guide](native-flashcards-mvp.md).

## Product outcome

A learner can discover, recall and revisit vocabulary inside Word Post. Cards are automatically generated from selected vocabulary and saved for the individual; native review works without Anki or a live AI provider. Users may choose **Anki Link** to create corresponding cards in their existing Anki workflow.

Anki uses HTML/CSS card templates. Word Post will use structured card content and owned components, allowing consistent accessibility and presentation. A controlled import/export adapter can translate supported Anki fields and cloze syntax; arbitrary template JavaScript is not part of the child renderer. [Anki template documentation](https://docs.ankiweb.net/templates/intro.html).

## Scope and functional requirements

| ID | Requirement | Acceptance evidence |
|---|---|---|
| FC-01 | Persist native cards before provider export. Keep vocabulary/form linkage, source provenance and a stable card identity. | Anki unavailable still leaves a complete approved native card. A failed generation leaves a recoverable draft/status. |
| FC-02 | Support basic front/back meaning cards and a single-target cloze type first. Attach prepared audio/images optionally. | Both types can be previewed, published, revealed and reviewed; text-only cards are valid. |
| FC-03 | Individual generation saves directly; optional household approval is separate. Version the prompt, answer, context, support and media used by a review. | Existing review content remains reproducible after edits; no PIN or other person’s approval is required in individual mode. |
| FC-04 | Store progress per learner and per review item/direction. | Reading `яблоко` and recalling it from “apple” have separate state; one learner does not inherit another's results. |
| FC-05 | Provide reveal, Again/Hard/Good/Easy, interval previews, replay, help, pause/resume and completion states. | All four ratings reach FSRS unchanged; four keyboard shortcuts and undo work. An optional two-button preference is available to the individual. |
| FC-06 | Use a maintained, pinned FSRS implementation behind an application scheduler interface. Persist its state and policy/version. | Fixed-time fixtures verify due transitions and serialization; no LLM decides intervals. |
| FC-07 | Own due/new/learning queue policy, limits and related-card spacing separately from the FSRS calculation. | Related forms/directions are not introduced in an overwhelming batch; a day off creates no penalty or lost coins. |
| FC-08 | Append review history and update scheduling/session state atomically. | A retry or concurrent double tap creates one logical review and its original result. |
| FC-09 | Allow a safe undo of the latest accepted review. | Before-state restored, reversal event retained, dependent evidence/reward effects reconciled; later conflicting activity blocks a destructive undo. |
| FC-10 | Give the individual card inspection/editing, suspend/resume, limits and history. | Retiring a card does not erase past reviews. A small validated authoring/publish command can precede a full editor. |
| FC-11 | Preserve legacy vocabulary, Anki links, generated media and review provenance. | Copied-data reconciliation succeeds; unsupported imported state is reported rather than guessed. |
| FC-12 | Make Anki Link an explicit optional action on approved cards. | Export failure neither deletes native cards nor changes their memory state. |

The current native MVP covers a subset of FC-01–11 with automatic text, picture and Russian speech generation, lexical tags/filters and a four-rating reviewer. The first media pass preserves the existing schedules; timing and interval previews remain next. FC-12 and export acceptance belong to the later Anki Link release (WP-12), which depends on native review. The existing AI generator is adapted to save drafts through FC-01/03 before that export release; its full asynchronous authoring interface is not required to prove a small local deck.

## Scheduling and child interaction

Use [py-fsrs](https://github.com/open-spaced-repetition/py-fsrs), an MIT-licensed Python implementation, subject to dependency pinning and compatibility checks during implementation. Wrap it so library upgrades do not leak into every route. Record scheduler version, parameters/retention policy and the resulting state with each review. Personal parameter optimisation can follow sufficient review data; the starter deck uses the library's documented defaults.

Anki supports using only Again and Good. Hard represents successful recall with difficulty, so it must not become a softer label for forgetting. The initial MVP implemented two buttons; the current reviewer uses all four ratings. [Anki answer buttons](https://docs.ankiweb.net/studying.html#answer-buttons), [FSRS guidance](https://docs.ankiweb.net/deck-options.html#fsrs).

An ordinary answer reveal follows an attempt to recall. Revealing alone does not imply failure. Explicit answer-bearing help before recall is separately recorded: the current reviewer records assistance separately and preserves the individual’s chosen rating. The four-rating policy applies only to new reviews; historical assisted ratings remain unchanged. Merely hearing the prompt audio is not a hint when listening is the card's intended modality. Do not infer recall from a multiple-choice success or copy-the-model activity.

Queue requirements:

- Store instants in UTC and the learner's study timezone/day policy separately; inject the clock in tests. Daylight saving and timezone changes must not grant extra reward allowances or shift old history.
- New cards have no invented review history. Suspend/bury state is application policy, separate from Learning/Review/Relearning scheduler state.
- Give due work priority, keep new introductions modest/configurable and space related cards. Stop a short session honestly even when more reviews remain; do not move unreviewed due dates merely to empty the queue.
- Store any scheduler randomness outcome once; retries return that result rather than resampling. A parameter update is versioned and does not silently rewrite history or mass-reschedule cards.
- Keep a stable retrieval objective. A substantial prompt/answer/sense change needs a new review item or an explicit adult-reviewed carryover policy. Decorative changes may retain the item identity while reviews still reference their content version.

## Data model boundary

Reuse the implemented `learning_profiles`, `learning_sessions`, `activity_attempts`, `learner_word_evidence`, `learning_assets` and reward/command ledgers from [Stage 1](household-mode.md). `legacy_record_links` remains part of the broader proposed architecture, not an existing foundation table. Extend the session contract explicitly for review occurrences and mixed content versions; do not create separate user identities or competing attempt histories.

| Proposed entity | Responsibility / invariant |
|---|---|
| `card_definitions` / `card_versions` | Stable retrieval item and immutable reference to a `learning_content_versions` item, plus validated indexing metadata; the published pack remains the sole answer payload and approval authority |
| `decks` / assignments | Grown-up grouping and learner eligibility; a card can appear in several decks without duplicating that learner's memory state |
| `learner_card_state` | Unique learner + card; current FSRS state, due/last-review time, counters, revision and policy reference; suspend/bury controls |
| `review_events` | One-to-one scheduling extension of the canonical accepted attempt: prior/next state, rating, time, policy, content version; links undo/reversal events |
| `review_session_items` | Server-issued items, pinned versions and reveal/support state; validates what the learner is answering |
| `anki_exports` | Native card/version + selected Anki destination, operation key, status, remote note/card IDs and reconciliation metadata |

Identity, ownership, due dates and uniqueness are relational/indexed fields. Validated JSON is appropriate for typed card payloads and a versioned FSRS state snapshot. Blob storage holds media and backup objects, not a mutable document replacing these database transactions.

An attempt is the canonical learning fact. `review_events` extends it for scheduling; consumers must not count both records as two answers. Word evidence, coin balance and skill summaries must be traceable to this one event.

## Proposed server contract

Use the existing same-origin `/api/v1` namespace, with child/adult policy enforced on every route. These native-review paths extend the implemented learning API; none of the paths below exist yet:

| Operation | Intent |
|---|---|
| `POST /api/v1/review-sessions` | Authorise learner/deck, pin eligible content and issue a session/revision |
| `GET /api/v1/review-sessions/{id}` | Resume that learner's state; safe read with no grading side effect |
| `POST .../{id}/reveal` and `POST .../{id}/help` | Persist the issued item's reveal/support state |
| `POST .../{id}/reviews` | Submit issued item ID, idempotency key, expected revision and permitted rating/response |
| `POST .../{id}/undo` | Request reversal of the latest eligible accepted review with its current revision |
| Grown-up card/publication/export operations | Separate authorised routes; exact URLs follow the adult workspace contract |

Before returning a cached response or mutating state, authorise the current profile/session. Replaying a committed submission with the same payload returns its original result even if its original revision is old. Reusing its key with changed content is rejected. A new submission with a stale revision returns a conflict and current state. Client-supplied due dates, rewards, scores, learner ownership and arbitrary answer keys are never authoritative.

In one short database transaction: validate the issued item and publication policy, append the accepted attempt/review, update card/session revisions, append qualifying word evidence and any reward event, then commit. Do not hold this transaction across provider calls. Self-report ratings remain self-reports; server validation cannot prove a child's internal recall and should not claim to.

Undo is an append-only reversal, not deletion of history. First release allows undo only for the latest unconflicted review before dependent completion rewards/spending. Reverse its derived evidence and any participation credit/cap use in the same transaction; the original credit and its compensation remain auditable. A later re-review can earn at most one net award for that eligibility key. Cosmetic spending comes later; reject unsafe reversal when a dependent purchase or later completion prevents restoring the earlier state.

Review coins follow the working review/undo loop. The existing reward ledger's unique eligibility key cannot be reused for a compensation entry. The design requires a review entitlement/claim plus unique grant/reversal operation keys before enabling that policy. Do not delete old ledger entries or silently promise review coins before they exist.

## Anki Link and legacy migration

The [existing generator](../flask_vocab_app/services/flashcard_service.py) already creates cloze text, translation, mnemonic, image and audio fields. Refactor it into preparation → persisted draft → approval → optional export. Reuse formatting/provider adapters after review. Fix its conditional media markup construction, unbounded Anki request, duplicate policy and remote/local identity handling as part of the exporter, rather than copying them into a second generator.

Requirements for Anki Link:

1. Export the approved native version; validate the chosen deck/note type and field mapping before sending. Store returned **note IDs and card IDs separately**.
2. Transfer referenced media through the adapter. A desktop Anki media-directory path is not a portable application asset ID.
3. Use a durable operation key and stable native identity in the remote note/tag mapping. Following a timeout or crash, reconcile whether a note was created before retrying. `allowDuplicate: true` alone is not a retry policy.
4. Keep native review state and Anki scheduling independent. An exported card does not become learned; a remote review does not silently award native coins or change native due state.
5. Existing Anki material/history is preserved in Anki. First inspect a backup/export read-only, report supported content types and media, then import selected content with stable mappings and a reconciliation report. The local `anki_cards` summary table is insufficient to reconstruct full review logs. Do not infer old Anki `due` values as Unix timestamps across queue types.
6. Native review uses a separate new schedule. Do not import historical intervals or infer reviews from content imports. Exact Anki history replay is outside this release; revisiting that choice would require its own collection audit and explicit migration policy.

Local Anki Link can call the existing desktop AnkiConnect service. A future Fly Machine's `localhost` is the server, not the learner's laptop. Hosted export therefore requires a file export or deliberately designed local bridge; never expose AnkiConnect publicly merely to make the existing call work. Two-way scheduling sync is a separate future project.

## Acceptance tests

- Published basic/cloze deck completes with all external providers unavailable; optional missing media has a readable fallback.
- Draft, withdrawn, another learner's card/session and private assets cannot be fetched through child or legacy bypass routes.
- Reveal/help/resume and accepted reviews survive refresh and process restart; no transition occurs from a GET.
- Concurrent duplicate requests create one attempt, one schedule transition and at most one coin award. Changed-payload key reuse fails; stale new answers cannot overwrite newer state.
- Two decks containing the same card share one learner memory state; sibling spacing and daily limits remain consistent across sessions/tabs.
- New, recalled, forgotten and assisted cases have expected scheduler outcomes under a fixed clock; date boundaries and policy upgrades are covered.
- Undo preserves an audit event, restores the appropriate state once and refuses unsafe reversal after later dependent work.
- Existing IDs/history are unchanged in a copied-data migration; backup/restore includes referenced assets and publication versions.
- Keyboard, touch, Cyrillic/stress text, audio fallback and truthful queue counts pass the existing design gates.

### Anki Link acceptance (WP-12)

- Repeated/ambiguous Anki export does not create duplicate notes; failure leaves native data usable; remote note/card identities reconcile.
- Supported legacy imports retain provenance and reconcile against a copied collection; unsupported history is reported for an explicit migration decision.
