# Games discovered along Barsik’s journey

Eight games are available through the shop. Learners choose a permanent unlock for 25 Lingocoins on their first purchase and 50 on later purchases. First steps does not unlock games. See [game access](game-access.md) for the requirements and migration rules. Vocabulary games combine familiar material from SQLite or a saved tutor lesson with newly generated language. Describe the scene uses authored grammar questions, and Follow the directions composes assignments from map facts and authored Russian sentences. Existing lemma/form relationships and grammatical metadata remain intact. A saved word is a familiarity signal, not proof that the learner has mastered it.

The games share the application’s profiles, contextual examples, media, rewards and skill observations. Game access belongs to the selected profile; optional household mode retains its existing rules. Saved guest sessions and public demo samples remain playable. New purchases spend the visible wallet balance. Existing ownership is preserved. Purchases do not reduce the eligible earned total used for journey destinations.

## Discovery and the eight mechanics

| Game | Current interaction |
|---|---|
| Pack the bag | Read or hear Russian messages, then pack their matching picture cards. Pictures can represent actions, situations and abstract vocabulary as well as objects. |
| Follow the directions | Follow Russian instructions through a saved town. Generated assignments vary collection points, recipients, addresses and encounters. Earlier authored sessions remain playable. Both formats support reading or listening practice and section replay. |
| Describe the scene | Build a sentence from an illustration and a short situation. Practise location, case endings, motion, placement, agreement and participant roles. |
| Missing Stamp | Restore the missing Russian surface form using the sentence and its full English translation. |
| Post Office Radio | Listen to one coherent Russian radio programme, then answer four Russian comprehension questions about its main idea and details. Replay it or explicitly reveal the transcript. |
| Mailbox Sort | Put each Russian message into the mailbox labelled with its contextual English meaning. These are sentence meanings, not permanent word definitions or generic topic categories. |
| A Letter Back | Listen to a Russian message and reconstruct the recorded wording with shuffled word or phrase tiles. The full English translation supplies context. |
| Lost Parcel Detective | Combine a contextual picture clue and a route clue to choose the delivery card that fits both. |

The shop shows prices and owned games. Activities offers direct access to owned games and links to the shop. Starting a game clears its “new” status. Introductory lessons do not grant games. Ownership survives review undo and changes to vocabulary sources.

## Choosing a fresh set

[Describe the scene](scene-builder.md) uses authored grammatical contrasts and bundled illustrations. Its options are a practice set and five or ten questions. It starts without generating new examples or pictures. Older Postcard Pairs sessions remain playable, but its matching mechanic is no longer advertised in the catalogue.

For vocabulary-based games, **My vocabulary** and saved tutor-lesson selections provide the familiar material. The available options include:

- Vocabulary source: optionally filter by topic and local difficulty band, 1–8.
- Saved lesson source: use its eligible selected word occurrences and their page context. Topic and difficulty controls are omitted because the lesson selection defines the scope.
- Game length: 5 rounds by default, or 10 rounds. Radio instead has one programme and four comprehension questions.

**Let’s play** explicitly starts preparation. An unfinished game has a direct **Continue saved game** link; **Start a new game** creates a new selection while preserving the previous session and answers. Retrying the same start request resumes its saved result rather than creating another game.

Selections prefer words and forms not used in recent games. Picture games normally prepare three familiar examples plus one new word, so a new set requires at most four example pictures. Missing Stamp, Mailbox Sort and Letter Back normally use four familiar examples plus one new word. If familiar material is scarce, additional discoveries can fill the small pool; each discovery excludes previously selected and discovered lemmas. A set may reuse its examples over several rounds.

Familiar selections retain lemma and form IDs, case/conjugation tags, context and provenance. Compatible native-card contexts and prepared game examples can be reused. Vocabulary that needs a sentence goes through the existing structured contextual-card provider. New discoveries use the configured model to propose a genuinely new lemma in a short, natural sentence, with exact surface morphology and contextual English meaning. Both paths validate their context without publishing a flashcard or adding a universal English field to `words`. Newly encountered vocabulary is not silently imported into the learner’s library.

Follow the directions combines a saved tile map with [generated delivery assignments](procedural-deliveries.md). A new assignment selects reachable places and connects encounters through validated Russian clues. The player discovers its events while following the dialogue. It has no vocabulary source or round-count control. The five [earlier deliveries](directions-delivery-implementation.md) remain playable. Radio uses familiar words as anchors for a coherent programme and introduces two to four new words in understandable context; it is not restricted to quoting existing card sentences. Neither activity prepares example pictures.

The saved-lesson source uses eligible, confirmed word selections and prepared lesson-card contexts belonging to the learner. It does not turn every word in an uploaded PDF into a game automatically. Unresolved OCR readings and ambiguous noun/verb analyses are excluded until resolved. Source links retain the lesson, revision and page where available. Generated examples remain distinguishable from exact source sentences.

## Context, pictures and recordings

Starting a set saves durable preparation progress. The browser advances pending work on the saved-game page, including after refresh. Resources follow the mechanic: Pack the bag and Detective require example pictures; older Pairs sessions retain that preparation flow; Describe the scene uses bundled illustrations; Letter Back requires sentence recordings; Missing Stamp and Mailbox Sort require neither media type to begin. Directions uses a map and Russian route wording. Radio prepares its complete programme and one recording. Existing compatible assets are reused. The game opens when its own required resources are ready, rather than waiting for an identical image-and-audio pipeline in every activity.

The preparation service saves progress after each stage and caches completed contextual examples by their lexical/context identity within the owner’s scope. A failed stage stops with **Retry preparation**. Retrying preserves selected words and completed stages. A new-word discovery makes one structured provider attempt; a rejected example does not trigger an invisible extra call. The randomly selected voice is saved before an audio provider call and retained on retry. Preparation uses a claim/lease so overlapping browser requests cannot overwrite newer work. Browsing the catalogue alone does not call paid providers.

Russian audio uses exact-sentence hashes and owned media references. The API resolves a hash against accessible lessons, native cards or game content; clients cannot submit arbitrary text. Reusable game/native recordings keep their saved voice. Old short route instructions use the same cached, explicit Listen workflow. New deliveries use committed speaker-and-text recordings with no runtime provider request. No browser speech synthesis or English voice fallback substitutes for Russian audio.

Picture boards use each example’s actual picture. Shared `LessonVisual.tsx` illustrations remain discovery artwork, map landmarks and the fallback for old saved introductory sessions. Picture descriptions are accessible labels, not visible Russian answers.

Missing Stamp hides the selected form in context and always shows the whole English sentence. Complete-sentence audio is available after checking, so it cannot pronounce the missing word before the attempt.

Radio begins with a roughly one-minute programme: one connected local-interest item, a presenter’s introduction and a natural ending. Four Russian questions follow; each has one intended answer and a saved supporting passage from the script. It tests listening comprehension rather than matching a spoken flashcard sentence to a picture. Its newly introduced words retain their actual broadcast sentences and contextual meanings.

Radio and vocabulary-based Letter Back start without the Russian transcript in the initial API response or DOM. Radio records listening when the recording ends; Letter Back records it when playback starts. Explicitly revealing the transcript saves support and allows supported practice. The draft survives listening, transcript requests and retries. Letter Back checks reconstruction of the recording’s order; it does not claim that other Russian word orders are ungrammatical. Open composition remains in Writing and Word Jumble.

## Words encountered during play

Completed games expose their encountered words. Radio also permits word lookup once the learner explicitly opens the transcript as support. Lookup first checks that the surface actually occurs in the saved, owned activity. It shows the sentence, dictionary link and existing vocabulary status. A saved contextual reference can provide its meaning and full sentence translation; clicking an arbitrary transcript word does not fabricate a translation.

**Add to vocabulary** explicitly saves the chosen lemma and linked forms through the existing lexical resolver. Noun/verb homographs such as **печь** offer separate readings; unresolved case variants within one lexeme do not become a forced case-selection exercise. Existing entries are reused. A validated, unambiguous contextual example and its prepared media are linked to the saved form in the same owner’s cache, so another game can reuse them without rewriting the completed activity. Looking up or merely encountering a word performs no lexical writes, and Add does not create cards or change review schedules. These SQLite additions do not depend on Drive. Existing Reading lookup and Drive routes remain unchanged.

## Saved answers, rewards and skill observations

Every session freezes its seed, selection, prepared content, first answers, support use and acknowledged feedback. Responses are deterministic for those saved rounds. Submitted answers cannot be replaced by a retry. The correct matches or route appear after checking; the learner acknowledges the final feedback before completion. Choosing a new game supersedes the old active session without deleting its history.

After a wrong answer, **Try again** opens a separate correction attempt. Learners can skip it or continue. Completion offers **Practise missed items** when needed. These attempts survive a refresh and cannot overwrite first answers or award extra rewards.

Completion uses the existing participation ledger: up to 3 Lingocoins within the ordinary 12-coin daily activity allowance. The same game and saved content identity cannot earn another reward that day. A new random arrangement alone does not create another entitlement; genuinely different vocabulary sets still share the daily activity cap. Mistakes and hints do not reduce participation rewards. Guest work attaches when creating a new personal profile, never when switching to someone else’s existing profile.

Except for Describe the scene and the new delivery format, the first completed session for a game and content identity can provide one **provisional** skill observation. Deliveries and Describe the scene save first checks and corrections and award participation coins, but do not yet contribute Elo. Visible-context games supply Reading evidence. Radio and vocabulary-based Letter Back supply Listening evidence only for rounds with saved playback receipts and no transcript or requested English-hint support. Radio measures programme comprehension. Letter Back still supplies English context and tiles: its observation measures supported listening/reconstruction, not independent writing, pronunciation or fluency. A playback receipt records browser activity; it cannot prove that the learner heard the recording attentively.

Matching and sorting can receive partial credit. New results use the chance-aware `game-evidence-v2` policy and an uncalibrated task prior of 1000. Vocabulary bands remain content filters, not task calibration or TORFL placement. Feedback-exposed items are excluded from new skill evidence. Historical receipts retain their original calculation. Replays cannot replace the first observation for the same content. Entirely supported practice remains useful and can earn participation coins without producing independent skill evidence.

## Optional native flashcards

Playing and preparing games does **not** create flashcards, change Anki, increment card-generation counts or update FSRS schedules.

After completing a contextual-example game, a selected profile can explicitly choose **Practise these words**. An optional word checklist limits the batch to the contexts they want to keep. This sends selected contextual vocabulary through the existing native generator, preserving lemma/form identity, grammatical tags, sentence meaning and source. Existing compatible native, lesson and game cards are reused rather than duplicated, including their schedules, media and retirement decisions. An already prepared picture or sentence recording can be reused; native generation supplies the remaining card media, including word audio. Cards become study-ready under the existing native requirements. New Directions deliveries expose selected encountered forms with their exact dialogue context for native cards. Old arrow games have no vocabulary-card pool. Radio currently offers explicit vocabulary saving rather than exporting a broadcast as flashcards.

The resulting batch links back to the game. There is no separate game-card database or review scheduler, and export is never an automatic consequence of completing a game.

## Storage and interfaces

Migrations 030–032 introduced game unlocks, saved sessions, shared audio and support tracking while preserving earlier answers and rewards. Migration 033 adds owner-scoped `journey_game_examples`, durable `journey_game_preparations` and `superseded_at` for replacing an active selection without losing history. Migration 034 adds `journey_game_corrections`; current review position stays in the session support record. Migration 035 adds delivery state and immutable action receipts in `journey_route_state` and `journey_route_actions`. Migration 038 introduced `journey_game_access` and its historical core-practice backfill. Migration 039 preserves those entitlements and existing non-demo saved-game access, then adds `journey_game_purchases` and wallet debits. Automatic coin milestones no longer grant games. Old tutorial unlock snapshots and three-round First steps sessions remain readable; they do not authorize new sessions or define their default vocabulary.

| Interface | Purpose |
|---|---|
| `#shop` | Browse games and buy permanent access |
| `#games/<game-id>` | Introduction, purchase or play controls, and word source |
| `#games/session/<id>` | Saved preparation, play, feedback and completion |
| `GET /api/v1/games` | Discoveries, current sessions and available word sources |
| `POST /api/v1/games/<game-id>/purchase` | Buy with a stable request ID and the displayed price |
| `POST /api/v1/games/<game-id>/start` | Start/resume with a stable request ID and vocabulary/lesson options |
| `POST /api/v1/games/sessions/<id>/prepare` | Advance saved preparation; explicit retry after failure |
| `POST /api/v1/games/sessions/<id>/route-command` | Revision-checked delivery actions, including planning, conversations and arrival |
| Session commands `quiz`, `hint`, `listen`, `transcript`, `answer`, `continue`, `complete` | Open radio questions, save supported practice and progression |
| `POST /api/v1/games/sessions/<id>/flashcards` | Explicit handoff to native generation |
| `GET /api/v1/games/sessions/<id>/words?word=<surface>` | Look up an actual word after completion or explicit radio transcript support |
| `POST /api/v1/games/sessions/<id>/words` | Explicitly add a selected lemma/POS reading through the existing lexical pipeline |
| Session asset and `/api/v1/games/media` routes | Authorised pictures, recordings and cached media preparation |

Current game IDs are `pack-bag`, `directions`, `scene-builder`, `missing-stamp`, `radio`, `mailbox-sort`, `letter-back` and `detective`. The retired `pairs` ID remains supported for saved games. Mutations use the existing CSRF and profile checks. A changed profile clears stale UI rather than applying another learner’s response.

## Validation and remaining refinements

Focused tests cover real vocabulary/form selection, lesson occurrences, media preparation/cache/retry, retained source context, image rendering, saved-session navigation, unlocks, deterministic answers, support tracking, rewards, provisional observations and native-card reuse. New discovery tests cover novelty, exact morphology, single-call failures, contextual lookup and explicit idempotent vocabulary saving. Radio tests cover saved programme preparation, questions, audio and transcript support. UI tests cover all eight mechanics, audio/transcript draft preservation, different map dimensions and old saved sessions. Browser/provider checks use an isolated database copy before rollout; their test progress is not copied into the learner’s profile.

The mechanics now combine familiar contextual material with controlled new-language exposure, using resources appropriate to each activity. Dictionary validation establishes possible morphology; it does not prove a model’s grammatical choices, translations or comprehension-question quality. Those outputs, picture ambiguity and real learner calibration need continued evaluation. Full PDF-page-to-game generation, open spoken/written responses inside these mechanics, and adaptive difficulty selection are separate improvements. See [Mixed vocabulary and radio practice](mixed-vocabulary-and-radio.md) for the detailed generation and vocabulary-saving contract.
