# Local user sessions

Implemented 15 September 2026. The app now has named local profiles rather than silently putting every browser into “Me”. This follows the local-first household direction. A profile is a learning identity; email/password accounts and hosted account recovery remain a later deployment step.

## Experience

The profile icon appears next to the language menu in both the activity home and the original workspace. Choose a saved profile, add a name, edit your name or end the current session at `/post/profiles`. No password, PIN or adult/child distinction is required in personal mode. Optional household controls remain a separate configuration.

The introduction and activity catalogue remain available before choosing a profile. Ordinary saved practice requires a selection. The [first delivery](first-delivery.md) also supports a guest attempt that can be saved into a newly created profile. Existing valid browser sessions continue as their current profile. Previously saved work stays with “Me”; adding a profile starts separate practice history and a zero coin balance unless that new profile receives its own pending first-delivery welcome reward.

All tabs in one browser share its active profile. Switching or ending a session clears temporary activity state and replaces the browser session, access credential and CSRF token. Other open tabs check on visibility, a profile-change signal and periodically while visible, then reload when the selected profile differs. A page cannot use a refreshed token to silently submit under another profile: the activity app binds API requests to its server-rendered profile ID. Older workspace forms keep their original CSRF token and reject stale submissions.

## What belongs to a profile

| Data | Ownership |
| --- | --- |
| Flashcard schedules, ratings, review sessions and generation batches | Selected profile |
| Speaking conversations, recordings, assessments and history | Selected profile |
| Lesson selections, pending flashcards, drafts, attempts and completion | Selected profile |
| Saved stories, writing tasks, Word Jumble games, translation sentences, drafts and feedback | Selected profile |
| Coins, skill evidence, journey progress and practice preferences | Selected profile |
| Historical lesson responses from the original module | Original “Me” profile |
| Vocabulary, lemmas, grammatical forms, tutor lesson documents and learning materials | Shared library |
| Flashcard definitions, published cards and their reusable media | Shared library; editing or retiring a definition changes the shared collection |

Shared flashcard content has independent schedules for each profile. Card reports shown in the personal editing workspace are limited to that profile; optional household administration retains its existing view. Creating local profiles does not introduce separate private vocabulary databases or make copies of every card.

## Backend

`learning_profiles` remains the identity table. Opaque revocable credentials use the existing `household_access` store, with the selected credential held in Flask's server-side session. Personal access follows `PERMANENT_SESSION_LIFETIME`, currently one hour, renewed by requests. Cookies retain the configured HttpOnly and SameSite settings.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/v1/user-session` | Current profile, available local profiles and CSRF token |
| `POST /api/v1/user-session/profiles` | Create and select a profile |
| `POST /api/v1/user-session/select` | Switch the current browser to a profile |
| `PATCH /api/v1/user-session/profile` | Rename the selected profile |
| `POST /api/v1/user-session/logout` | Revoke access and end the browser session |
| `GET /post/profiles` | Accessible HTML profile picker |
| `POST /post/profiles/actions` | HTML create/select/rename/logout actions |

State changes require CSRF protection. Study routes require an active profile; repository lookups also enforce activity ownership. Foreign activity IDs return 404 before any grading, provider call or update. Private activity media is checked before delivery. Personalized pages, API responses and protected media use `Cache-Control: no-store`.

Migration 025 adds `owner_profile_id` to the four legacy activity tables and assigns existing records to `personal-learning`. It does not rebuild these tables, rewrite content, copy balances, reset schedules or change media paths. Legacy CLI operations still resolve to the original profile. In optional household mode, the legacy adult workspace remains separate from a selected child's rewards.

## Verification and rollout

Session tests cover anonymous access, existing-session compatibility, two independent browsers, create/select/rename/logout, expired access, token and session rotation, stale page requests, validation and optional household behavior. Activity tests verify separate saved work, grading and rewards, foreign-ID rejection, historical lesson-answer isolation and migration preservation.

The development database update is rehearsed on a SQLite backup. Compare every original table and column before and after migration, then check database integrity and foreign keys. Local backups are not source-controlled. Credentials and the separate canonical vocabulary database are not migration inputs.

Before hosting beyond the trusted local household, add authenticated accounts and household membership, secure deployment cookie settings, account/session recovery, and an explicit policy for sharing or privately owning authored library content. These are separate from the profile selection shipped here.

## Introducing the header controls

Migration 026 adds explicit introduction timestamps per profile. Both start unset, including for existing profiles: an old balance or rating does not imply that the new introduction has been seen.

The welcome page initially shows neither the coin counter nor Barsik’s progress bar. Opening **Earn coins as you learn** in the first delivery reveals the counter. The following **Watch your Russian improve** page reveals the bar. The three-word lesson follows these two explanations. Once introduced, the controls remain visible across navigation and future sessions for that profile; replaying the tutorial does not reset them.

`GET /api/v1/onboarding` reads the active profile's milestones. `POST /api/v1/onboarding` accepts `{"milestone":"coins"}` or `{"milestone":"progress"}` with CSRF and the usual page identity checks. Writes are idempotent; progress requires the coin introduction first. The browser reveals each control immediately and saves the milestones in order, with a retry when saving fails. These writes never award coins or change Elo.

Guests can follow the same introduction before creating a profile. Their counter starts at zero and the bar explains that a checked activity starts a skill rating. Guest introduction milestones carry into a newly created profile, but never into an existing profile merely because it was selected. Switching profiles and ending a session do not share these milestones between learners.

The first delivery teaches Привет!, письмо and Спасибо!, then checks recall using only those Russian words as answer choices. Teaching and practice form one continuous lesson; there is no separate guided hello. A guest's completed result and 3-coin welcome reward remain pending until saved to a newly created personal profile. Selecting an existing profile preserves that learner's own answers, milestones and wallet. A selected household learner completes their own attempt; household profile creation does not claim guest practice. Migration 028 preserves old activity work until an explicit restart archives it; an earlier completed reward remains one-time. See [the first-delivery persistence and reward rules](first-delivery.md).

Both the new activity home and legacy activity headers use these gates. The legacy sidebar and reward feedback also wait for the coin introduction. Reward calculation, balances and ratings are unaffected. The visual `progress-preview=50` option does not bypass the introduction gates.

## Skill progress in the profile

Once the learner has reached the progress introduction, the selected profile shows a **Skill progress** section with separate provisional Elo ratings, stages and checked-attempt counts. Unmeasured skills show a dash and **Not started**. Barsik and the header line link directly to this section; the header has no caption or dropdown card. Personal and optional household profiles use the same read-only skill summary, restricted to the current learner.
