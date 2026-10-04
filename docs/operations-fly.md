# Russian Arcade on Fly.io

## Hosted personal accounts

Application: https://russian-arcade.fly.dev/

The public demo is retired. Visitors sign in with Google or GitHub before opening
activities. Signed-in accounts retain their database, media, lessons and progress.
Old `/demo/` page links return to the main site. Guest API requests and mutations
return `410`; they never fall through into a personal workspace.

`PUBLIC_DEMO=true` is the legacy name for the restricted public hosting boundary.
Keep it enabled. Set `HOSTED_PUBLIC_DEMO_ENABLED=false` and
`HOSTED_GUEST_DEMO_ENABLED=false` to disable both guest workspaces and the old
anonymous sample fallback. Account-only hosting requires `HOSTED_TRIAL_ROOT`.
It does not create a disposable sample database at startup.

The base `/data/vocab.db` must exist and contain the migrated schema. It is used
for health checks and application setup, not as a shared learning workspace.
Before the first account-only deployment, initialize it if absent with the
application's `upgrade_database` function. Never replace an existing database.
Back up all account databases, the identity registry and spending ledger first.

The service uses one Sydney Machine, one threaded Gunicorn process (eight
threads), one shared CPU and 2 GB RAM. Removing demo access does not delete guest
files, reset budgets or alter personal accounts. Later storage reclamation is a
separate operation after backups and retention decisions.

Before deploying, check that the configured volume exists in Sydney:

```sh
fly volumes list -a russian-arcade
```

If there is no `arcade_data` volume in `syd`, create it once:

```sh
fly volumes create arcade_data --region syd --size 1 -a russian-arcade
```

Reuse the existing volume on later deployments. Do not create a replacement
volume for an existing trial: it contains identity, learning data and spending
records. Then deploy from the repository root:

```sh
fly deploy --remote-only --ha=false
fly status -a russian-arcade
fly checks list -a russian-arcade
```

The Docker build compiles Node 24 assets and uses the Python dependency lock.
The `.dockerignore` allowlist excludes runtime data and secrets. Do not pass
provider keys or `.env` as build arguments. HTTPS is enforced by Fly and secure
responses include a one-year HSTS policy; `/healthz`
checks database readiness. Keep a single Machine: in-memory/background ownership
and SQLite are not configured for replicas.

Validation covers account isolation, anonymous request rejection, retired demo
routes, CSRF, provider budgets and saved media. Verify the live sign-in page,
stylesheet assets, `/healthz`, and existing signed-in workspaces after deployment.

## Hosted accounts and AI funding

Visitors sign in to a persistent account. Account access and paid AI have separate switches. Accounts need Google or GitHub sign-in and
persistent storage. AI also needs dedicated provider credentials and an existing
spending ledger. A source release does not activate either switch.

`hosted_trial.py` verifies authorization codes with state and PKCE. Google also
uses a signed identity token and a flow nonce. The application requests no
repository or Google Drive access and discards provider tokens after verifying
the account. Register the GitHub callback as
`https://russian-arcade.fly.dev/trial/callback` and the Google callback as
`https://russian-arcade.fly.dev/trial/callback/google`. Provider identity uses a
stable subject, not a browser-supplied name. Signing out returns to the main sign-in entry. Old demo sessions no longer grant access.

See [account sign-in](account-sign-in.md) for Google configuration and connecting
Google to an existing GitHub account. Connected methods share the same account
data and AI allowance. Sign-in never merges accounts by email or display name.

When accounts are available, **Sign in** appears in the header and sidebar.
After sign-in, the avatar opens the profile overview at `/post/profiles`.
Its **Account settings** link opens `/trial/account` for sign-in methods and sign-out.
When sign-in is unavailable, that page explains the deployment's current state.
`GET /trial/status` reports `enabled` (accounts), `configured` (OAuth), configured
providers and `ai_enabled` (paid AI). It never returns credential values.

Each verified identity receives its own database, media, uploaded lessons and
Flask sessions. The hosted profile is selected by the server. The local profile
picker cannot switch into another visitor's workspace. New workspaces start
with authored sample material, never a copy of a personal learning database.

Each open page also carries an account marker. An account change in another tab
reloads the old page; stale activity requests are rejected even when both
workspaces use the same internal profile ID. The marker is not an authentication
credential. The verified session cookie still decides which workspace is used.

Persist the identity registry, all trial workspaces and the shared AI budget on
the mounted volume. Keep one Machine and one application process. The spending
ledger must survive restarts: missing storage pauses AI rather than creating a
fresh allowance. Back up identity, budget, workspace databases and media together.

### Account maintenance and storage

Each hosted workspace has a 100 MiB storage limit. An operator can give a known
account a larger limit without changing other visitors' limits. Store overrides
in `HOSTED_TRIAL_ROOT/operator/storage-limits.json`. This is a JSON object whose
keys are the SHA-256 hex digests of verified identities such as `github:12345`.
Values are positive integer byte limits; 256 MiB is `268435456` bytes. The identity
must come from the identity registry, not a display name or browser request.

Write admission distinguishes a full workspace (`storage_limit`) from low free
space on the server (`server_storage_low`). Both return HTTP 507; the latter asks
the learner to retry and sets `Retry-After: 30`. Server logs include the byte
counts for the failed check without recording account identities or file paths.
Raising a workspace allowance does not resolve low server disk space.

Write this file atomically and keep the operator directory outside tenant upload
and media directories. Overrides are read on each write admission. Missing,
invalid or oversized configuration keeps the default limit. Upload limits, free
disk requirements, request limits and AI budgets still apply. This file is not a
way to grant additional AI spending or to expose private content publicly.

For a data migration, create an empty file at
`HOSTED_TRIAL_ROOT/operator/maintenance/<identity-digest>`. New content requests
for that account receive HTTP 503 with `Retry-After: 60`. Sign-in, account status
and sign-out remain available, and signing in does not open or seed the paused
workspace. Other accounts continue to work.

The marker blocks new requests; it does not cancel requests or background jobs
already running. Drain those jobs or stop the worker before taking the final
backup and replacing files. Keep the marker present during the cutover. Restart
the worker to discard cached application state, verify the imported database and
media, then remove the marker. Preserve the original backup until the account
has been checked. Never copy an owner's database into the public sample seed.

The hosted configuration uses the `arcade_data` volume mounted at `/data`:

| Setting or path | Purpose |
|---|---|
| `HOSTED_TRIAL_ROOT=/data/trial` | Identity registry and per-account workspaces |
| `/data/trial/ai-budget.sqlite3` | Shared persistent spending ledger |
| `HOSTED_ACCOUNTS_ENABLED=false` | Enable account sign-in only after OAuth is configured |
| `HOSTED_PUBLIC_DEMO_ENABLED=false` | Disable all public demo access and anonymous samples |
| `HOSTED_GUEST_DEMO_ENABLED=false` | Disable temporary visitor admission |
| `ELEVENLABS_MODEL=eleven_v4` | Model for new generated speech |
| `AI_TRIAL_ENABLED=false` | Keep paid work off until configuration and checks pass |
| `GITHUB_OAUTH_CLIENT_ID`, `GITHUB_OAUTH_CLIENT_SECRET` | Dedicated GitHub OAuth application |
| `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` | Dedicated Google OAuth web client; separate from Drive capture |
| `DEMO_OPENAI_API_KEY` | Dedicated OpenAI trial credential |
| `DEMO_ELEVENLABS_API_KEY` | Dedicated speech credential |
| `DEMO_OPENROUTER_API_KEY` | Dedicated transcription credential |

The trial uses these dedicated provider keys rather than inheriting personal
development credentials. Keep OAuth and provider secrets in Fly secrets.
Prepare a dedicated file outside the repository with `NAME=value` entries for
the credentials being added. Protect it with mode `600`, then import its
contents without printing them:

```sh
fly secrets import -a russian-arcade < /absolute/private/path/russian-arcade-trial.env
```

Use a file containing only the intended hosted secrets. Omit blank entries;
do not replace the existing application session secret or import the local
development `.env`. Check secret names with `fly secrets list -a russian-arcade`.

Activate accounts first with at least one provider's client ID and secret, then set
`HOSTED_ACCOUNTS_ENABLED=true` through Fly secrets. Leave `AI_TRIAL_ENABLED=false`
until provider setup is complete. Accounts can sign in and save ordinary
practice without provider credentials or a spending ledger. AI requests remain
blocked, including when development credentials exist elsewhere in the environment.

For older configurations that omit `HOSTED_ACCOUNTS_ENABLED`, its value follows
`AI_TRIAL_ENABLED`. An explicitly disabled account switch prevents new sign-ins;
it does not end existing sessions. Use
`AI_TRIAL_ENABLED=false` or the ledger's `pause` command to stop paid work.

Initialize the budget explicitly with `python trial_cli.py init --root /data/trial`
inside the deployed application. `status` reports the ledger and `pause` blocks
new paid work. Normal startup must not recreate a missing ledger. Existing
model and voice choices remain unchanged unless deliberately reconfigured.

After the dedicated provider keys and ledger have been checked, set
`AI_TRIAL_ENABLED=true`. Existing accounts gain access without signing in again.
This registers their verified identity in the ledger; it does not reset spending
or re-enable an account whose AI access was revoked. Turning AI off later keeps
account sign-in and saved work available.

Before announcing activation, verify real sign-in and sign-out for each enabled
provider, saved progress after returning, connected-account access, isolation
between two accounts, and a bounded AI provider test. Report authentication and
AI status separately if only one is activated.

### Budget and provider limits

| Scope | Admission limit |
|---|---|
| One personal account | US$1 per UTC day; US$2 total |
| All accounts and providers, including historical guest spend | US$1 per UTC day; US$20 per UTC calendar month; US$10 total |
| Provider calls per account | 30 in a rolling 60-second window; 120 per UTC day |
| Standard flashcard generator | Five cards per hosted batch; local installations retain twenty |

The tightest applicable limit wins. The US$10 total ceiling currently takes
precedence over the US$20 monthly ceiling. Limits count historical usage already
in the ledger; deployment, sign-out, new cookies and calendar changes do not
replenish a lifetime allowance. Additional funding needs an explicit change to
the approved total ceiling, not deletion or reinitialisation of spending records.

The application reserves
an operation's maximum cost before sending it. Reported usage settles that
reservation; ambiguous failures or missing usage consume the reserved allowance.
An interrupted process leaves its reservation held until reviewed. An actual
charge above its reservation is recorded and stops further admission for review.

Concurrency limits permit one ordinary paid operation per account at a time and
two globally. A live voice reservation can coexist with that account's metered
delegation call. Failed calls and zero-cost results also count towards the request
limits. Exact retries of the same reserved request do not spend or count again.
These are provider operations, not complete activities: a card batch may request text,
pictures and several recordings. The shared money limit can stop work sooner.
Lingocoins and game purchases never increase the AI allowance.

The CLI `status` command reports configured ceilings, remaining shared allowance
and outstanding reservations without listing account identities. `pause` stops
new paid work without removing recorded usage. Saved and sample practice remain
available after a spending or request limit is reached.

`services/trial_provider.py` bounds text, image, translation, transcription and
speech calls. It uses server-approved models and prices, disables automatic SDK
retries and rejects unsupported tools, endpoints and request overrides. Current
bounds include:

| Operation | Maximum or restriction |
|---|---|
| Text generation | 96,000 input bytes and 12,000 output tokens per call |
| Lesson images sent to a model | Four embedded images per call; 8 MB and 4096 pixels per image |
| Generated picture | One medium-quality, 1024 × 1024 image per call |
| Audio assessment | A valid recording of at most five minutes |
| Transcription | A valid recording of at most 90 seconds |
| Speech or legacy translation | 3,000 characters per call |
| Hosted live speaking | Server closes after one minute; at most two metered delegation calls |

These are upper bounds; an activity may use smaller limits, and an unaffordable
request is refused before the provider call. Review the rates in the adapter
when changing models. New provider operations require an explicit budget adapter.
Do not bypass it to make a failed activity work.

Store dedicated provider credentials as Fly secrets. A verified provider-side
hard monthly spending limit of US$20 is required before enabling funded live
speaking. A billing alert or adjustable application budget is not a hard limit.
Never place personal development keys in the image, source snapshot or browser.
Keep the global trial switch available so generation can be paused while saved
practice stays usable.

Live speaking has an additional limitation. The provider does not expose a
configurable maximum session duration. The server closes calls after 60 seconds,
uses a hangup fallback and attempts to close unfinished sessions on restart.
If the server dies while the browser remains connected, the provider can keep
charging until the call ends. Keeping the reservation held prevents further
admission but does not stop that existing charge. The application therefore
cannot guarantee a US$1 daily provider bill in this failure case. Do not enable
hosted live speaking if that daily invoice guarantee is required; the ordinary
bounded AI activities can operate independently.

Before enabling the trial, test OAuth callback replay, profile isolation, CSRF,
budget races, provider retries, missing usage, restart recovery, uploaded media
ownership and server-enforced live-call termination. Confirm the final hosted
settings and a successful provider-backed run; unit tests alone do not verify
the deployed OAuth app or provider account.

## Optional private household installation

The following is a separate future deployment procedure for real personal data.
Use another app, omit `PUBLIC_DEMO`, mount a persistent volume and configure the
mandatory HTTP Basic credentials. Do not change the hosted service into a personal
installation by merely copying its data.

## Build and storage

The Docker build compiles the UI with Node 24 and installs the hash-locked Python
3.12 dependencies plus Gunicorn. FFmpeg, Poppler and Russian Tesseract are
included. The build context excludes credentials, databases, uploads, generated
media and local sessions. Secrets enter through Fly runtime secrets, never
Docker build arguments or a copied `.env`.

`/data` is a persistent Fly volume:

| Location | Contents |
| --- | --- |
| `/data/vocab.db` | Vocabulary, profiles, schedules, lessons and progress |
| `/data/assets` | Content-addressed flashcard/game/speaking media |
| `/data/lesson-assets` | Original lesson documents and page renders |
| `/data/media`, `/data/uploads` | Legacy story/audio/image/upload files |
| `/data/sessions` | New hosted sessions; do not import local browser sessions |
| `/data/anki-media` | Generated Anki media where applicable |
| `/data/private` | Optional separately transferred Drive OAuth files |

Source the import from `instance/native-flashcards-mvp/settings.json` and its
configured paths. **Do not use the old `flask_vocab_app/vocab.db`.** Snapshot the
live database with SQLite's backup API, never copy a database in WAL mode by
itself. Copy its sibling `lesson-assets`, configured Word Post assets, uploads,
media and any required Anki media. Resolve legacy absolute media references on
the imported copy and verify representative lessons, stories, flashcards and
recordings. Keep originals unchanged.

Pause generation while taking the final database/media snapshot. Inspect pending
jobs and apply their existing recovery procedures on the hosted copy; in-process
threads do not migrate. Do not run simultaneous local/cloud edits expecting sync.
Choose the hosted copy as the active data store after cutover; keep the local
snapshot for recovery.

## Launch sequence

1. Confirm the release access model. This configuration is for private access.
2. Verify name availability and create the app in the intended Fly organisation.
3. Build the image and inspect the build context. Create one Sydney Machine and
   its volume without exposing an unprotected app. Use a maintenance command
   initially while importing data; the normal entry point refuses a missing DB.
4. Transfer the verified database/media snapshot privately with Fly SSH/SFTP.
   Verify integrity and file checksums before switching to the normal command.
5. Set `FLASK_SECRET_KEY`, `HOSTED_ACCESS_USERNAME`, `HOSTED_ACCESS_PASSWORD` as
   Fly secrets. Use independently generated credentials: session secret at least
   32 characters, access password at least 24. Set provider keys and preserve
   the current model/voice environment overrides. Do not print secret values or
   place them on command lines. Do not upload the local settings JSON wholesale.
6. Deploy with `fly deploy --ha=false` so Fly does not create a second Machine.
   Startup applies transactional migrations on the mounted volume, taking a
   pre-migration backup when needed. Do not add a `release_command`: release
   Machines do not mount this volume.
7. Verify unauthenticated HTML/API/media requests are denied; then verify sign-in,
   profiles, secure session cookies, CSRF-protected writes, existing media and
   microphone access over HTTPS. Smoke-test one provider-backed activity.
8. Establish an off-Machine backup and test restore before relying on the hosted
   installation. Volume snapshots alone are not the complete backup procedure.

This sequence is a runbook, not an automated deployment already performed.

## Limitations and follow-up

AnkiConnect on the server cannot reach Anki on your Mac through `localhost`.
Keep native study available and use the local Anki accessory until a supported
export or local bridge is implemented. Drive's interactive OAuth login must
remain disabled on the server; transfer/re-authorise its credentials explicitly
if hosted Drive sync is needed.

Deploy while no lessons, media batches or speaking assessments are running.
Graceful shutdown is bounded and cannot guarantee completion of long background
jobs. Durable workers/recovery supervision are needed before multiple instances.

Schedule off-volume SQLite snapshots plus media backups, with encryption and a
retention policy. Tigris is a reasonable later home for media/backups; the live
SQLite database must remain on a filesystem, not an object-store blob. A single
Machine/volume is not a high-availability deployment. Roll back code only when
schema-compatible; otherwise restore the verified snapshot and matching media
together during maintenance.

References: [Fly volumes](https://fly.io/docs/volumes/overview/),
[configuration](https://fly.io/docs/reference/configuration/),
[runtime secrets](https://fly.io/docs/apps/secrets/).

## Speech model

New recorded speech uses `eleven_v4`. Both ElevenLabs adapters share model-aware
settings: stability `0.8`, similarity boost `0.85`, with no unsupported style or
speed field. The existing four Russian voices remain randomly selected.

Pending recordings adopt v4 while preserving their text and selected voice.
Completed recordings and their original model metadata remain intact. The
application does not regenerate a user's saved audio just because a model changes.
Fluent Speaking retains its separate OpenAI live audio transport.

The budget adapter reserves v4 speech at the standard US$0.08 per 1,000 characters,
not the temporary launch discount. Existing shared and per-account limits apply.
Legacy `DEMO_*_API_KEY` secret names still supply hosted accounts; do not delete
those credentials when removing demo access.
