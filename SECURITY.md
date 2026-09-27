# Security

## Deployment modes

Local profiles are intended for a trusted installation. They are not internet accounts. Do not expose the development server or the local profile selector directly to the internet.

The hosted entry point supports these modes:

- **Private installation:** HTTPS and site credentials protect all application routes and assets.
- **Public sample demo:** a disposable database contains authored sample content. Each browser receives a separate profile. An explicit route list permits sample practice. AI generation, uploads, editing and profile switching are blocked. Provider credentials are blanked during startup.
- **Guest AI demo:** `/demo` issues a temporary, server-generated visitor identity. Each visitor has an isolated workspace and a signed browser cookie. It requires no OAuth login and uses the same persistent spending ledger as personal accounts. Guest admission and expiry limit workspace growth.
- **Signed-in AI trial:** Google or GitHub sign-in selects an isolated, persistent workspace for each verified account. Dedicated demo credentials stay on the server. Provider calls reserve funds in a shared ledger before running. This mode requires explicit configuration and activation.

The anonymous demo limits requests and writes in SQLite. Limits are shared across threads and browser sessions. New profiles have a separate admission limit and an atomic total cap. No IP addresses are stored. These controls bound application work; they do not replace an edge firewall or protect against every denial-of-service attack.

Sample limits reset when its disposable database is recreated. They are not the spending ledger. Guest and signed-in AI access use persistent identity and budget stores. Each account has US$1 per UTC day and US$2 total. Shared admission limits are US$1 per UTC day, US$20 per calendar month and US$10 total. Every unsettled reservation counts, including holds from earlier periods. Signing out does not reset account usage. Clearing guest cookies can create another visitor identity, subject to admission limits, but cannot reset shared spending. Guest access is not verified personal identity.

Each account is limited to 30 provider calls per rolling minute and 120 per UTC day. All paid providers and live voice share these limits. Existing concurrency controls also apply. The standard flashcard generator allows at most five cards per hosted batch. Missing budget storage or unsupported provider operations block new paid work. Lingocoins do not increase the allowance.

Google sign-in verifies the signed identity token, audience, issuer, expiry and flow nonce. Both providers use authorization codes, PKCE and single-use state bound to the initiating browser. Provider tokens are discarded after verification. Google sign-in does not grant Drive access.

Accounts are never joined by matching email addresses or display names. Connecting another sign-in method requires an authenticated account, a CSRF-protected request and verification of the new provider in the same live session. A provider identity already attached to another account cannot be connected. Connected methods use the original account's workspace, storage limits and AI budget. See [account sign-in](docs/account-sign-in.md).

Live speaking also requires a provider-side spending limit: a server failure can leave a call running beyond its one-minute application timer. The timer and ledger cannot guarantee an invoice cap in that case. See the [trial runbook](docs/operations-fly.md#hosted-accounts-and-ai-funding).

## Credentials and publication

Keep credentials in ignored local environment files or the hosting provider's secret store. Never send them to the browser, put them in generated content or print them in logs. `.gitignore` prevents ordinary staging of local files; it does not remove secrets from old commits.

This repository is published from a reviewed source snapshot. Keep personal databases, tutor documents, recordings, OAuth files and environment files out of it.

If a credential is ever committed, rotate it: create a replacement, update the installation, verify it, then revoke the old credential.

## Automated checks

CI scans the committed source and incoming commit ranges with Gitleaks. It also audits the Python and JavaScript lockfiles. Reports redact detected credentials. Existing private history is not declared clean by these checks.

Before publishing a new repository, run a full-history scan in its clean checkout:

```sh
gitleaks git . --log-opts=--all --redact=100 --ignore-gitleaks-allow
```

Enable GitHub secret scanning and push protection where available. Review dependency alerts and rerun tests when updating the lockfiles. A passing scan cannot guarantee the absence of vulnerabilities or personal information.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting feature when it is enabled. Do not include credentials or personal learning data in a public issue. Until private reporting is available, contact the repository owner privately before sharing technical details.
