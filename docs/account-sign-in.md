# Account sign-in

Hosted users can sign in with Google or GitHub. The sign-in page shows only
configured providers, with Google first. `/demo/` opens a separate, 24-hour
visitor workspace without sign-in when the guest demo is enabled. Free sample
activities remain available as a fallback.

Sign-in and paid AI are separate. Adding a provider does not change the AI
allowance or enable a paid service. Signing in opens the personal account; it
does not import temporary demo work.

For signed-in users, the avatar opens the profile overview at `/post/profiles`.
It shows the current account's course milestones and skill ratings. **Account
settings** opens `/trial/account` for sign-in methods and sign-out. Local profile
selection and the temporary demo account page keep their existing behaviour.

## Existing accounts

An existing GitHub user should sign in with GitHub, open **Account settings**
from their profile, then choose **Connect Google**. After Google confirms the account, either sign-in
method opens the same words, cards, lessons and progress.

Signing in with an unconnected provider creates a separate account. Matching
names or email addresses do not merge accounts. A provider already connected to
another account cannot be moved through the sign-in page. Combining two existing
workspaces requires a separate data migration; this flow does not merge records.

## Google configuration

1. Create an OAuth client of type **Web application** in Google Cloud's
   [Google Auth Platform](https://console.cloud.google.com/auth/overview).
2. Set the consent-screen name to **Russian Arcade** and the homepage to
   `https://russian-arcade.fly.dev/`. Use the application logo and provide the
   support contact and policy information requested by Google.
3. Add this exact authorized redirect URI:
   `https://russian-arcade.fly.dev/trial/callback/google`.
4. Set `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET` in Fly secrets.
   Use a dedicated sign-in client, not the local Google Drive credentials.
5. If the Google project is in testing mode, add the accounts that will test it.
   Complete Google's publishing requirements before offering it to everyone.
6. Deploy the application and verify a real sign-in, sign-out and connected
   account sign-in. Mocked tests cannot confirm the Cloud Console configuration.

The server requests `openid profile`. It uses the verified Google subject and
display name. It does not request email, Drive access or offline access, and does
not retain Google access or identity tokens. This is the server-side
[OpenID Connect flow](https://developers.google.com/identity/openid-connect/openid-connect).
The Google button follows Google's
[branding guidance](https://developers.google.com/identity/branding-guidelines).

## GitHub configuration

Keep the existing OAuth application and callback:
`https://russian-arcade.fly.dev/trial/callback`.
Its settings are `GITHUB_OAUTH_CLIENT_ID` and `GITHUB_OAUTH_CLIENT_SECRET`.
No repository scopes are requested. Existing GitHub accounts and saved sessions
keep their original account identity.

At least one complete provider pair is required when
`HOSTED_ACCOUNTS_ENABLED=true`. An incomplete provider is omitted from the
sign-in page. It does not disable another configured provider. Configure
`HOSTED_TRIAL_ROOT` on persistent storage as described in the
[Fly runbook](operations-fly.md#hosted-accounts-and-ai-funding).

Never commit credentials or overwrite an existing `.env`. For Fly, put only the
two new Google settings in a private file outside the checkout, protect it with
file mode `600`, then import it:

```sh
fly secrets import -a russian-arcade < /absolute/private/path/google-sign-in.env
```

`fly secrets list -a russian-arcade` shows the configured names without revealing
values. Neither the browser nor `/trial/status` receives client secrets.

## Identity and session storage

`HOSTED_TRIAL_ROOT/identities.sqlite3` stores accounts, connected provider
identities, sign-in flows and hashed session tokens. Startup extends the existing
registry in place. Back it up with the account databases and AI spending ledger
before deployment.

The original account identity remains the workspace key. For existing GitHub
accounts it is `github:<numeric-id>`. New Google account keys use a digest of the
verified provider subject. A connected provider maps to the existing account key,
so it shares the same files, usage history and storage allowance.

The flow records the chosen provider, state, browser binding and PKCE verifier.
Google also records a nonce checked against the signed identity token. State is
single-use and expires after ten minutes. The original GitHub callback remains
valid; Google has its own callback route.

Connecting a provider requires a CSRF-protected POST. The callback must return to
the same authenticated session that started it. Signing out or changing accounts
during connection prevents the link. The provider identity has a unique registry
mapping, so concurrent attempts cannot connect it to two workspaces.

The application sets Secure, HttpOnly, SameSite=Lax cookies. Sign-out revokes the
server session. Authentication pages use a restrictive content security policy,
self-hosted assets and no third-party scripts.

## Verification

The auth tests cover provider validation, callback replay and provider mismatch,
expired flows, CSRF, account switching during connection, identity conflicts and
preservation of the original workspace and AI allowance. Renderer tests cover
escaping, configured-only controls and accessible provider labels.

For a hosted smoke test, check:

- Google and GitHub each return to the requested application page.
- An existing GitHub account can connect Google and reopen its saved data.
- Signing out returns to the sample demo.
- Cancelled or expired sign-in offers a clear retry without provider diagnostics.
- A separate account cannot see or connect an identity belonging to another user.

Email sign-in, Apple sign-in, passkeys and self-service account merging are not
implemented in this pass. Email would require a mail provider, delivery setup,
single-use verification links and request limits.

## Demo routing

With the guest demo enabled, `/` opens the personal workspace or the sign-in entry. `/demo/` opens the temporary workspace directly. `/demo` redirects to `/demo/`; it does not send visitors back to the main app. Demo pages, activity APIs and generated media stay under that prefix. Packaged assets and OAuth routes remain shared at the origin.

The server selects the workspace from the route and its verified cookie. A personal sign-in cookie never replaces the demo workspace, and a demo cookie never activates a demo on the main site. Both can be open in separate tabs. Cookies retain `Path=/` as required by their `__Host-` names. Requests still validate the account scope and CSRF token.

An expired demo API request returns `401` with a link to start again. It never silently creates a replacement workspace. The demo account page has a **Leave demo** link to the main site.
