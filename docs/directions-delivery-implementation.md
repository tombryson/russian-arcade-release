# Neighbourhood delivery implementation

**Status:** the original authored deliveries remain playable. The later [procedural town implementation](procedural-deliveries.md) now composes new assignments from places and encounters in a saved town. This document describes the original five deliveries and their shared runtime.

**Updated:** 16 September 2026.

This implements the connected delivery game. There are five authored deliveries across two neighbourhoods. Listening practice and section replay are implemented. Tutor review, skill-rating integration and spoken conversations remain future work.

## Activity flow

The activity remains **Follow the directions** in Activities. It unlocks through the existing “Which way?” introduction. New sessions open a neighbourhood delivery. Saved arrow games retain their original format and history.

The learner chooses a delivery and either **Read and listen** or **Listen first**. Each delivery follows three connected encounters:

| Neighbourhood | Encounters | Final task |
| --- | --- | --- |
| Park Quarter | Nina at the post office → Sasha at the fountain → Olya at the bakery | Find Anna’s second house on the right, Nikolai’s first house on the right, or Vera’s house opposite the bakery. |
| Riverside | Nina at the post office → Boris at the market → Lena at the library | Find Dima’s second house on the left, or Irina’s house beside the station. |

The first neighbourhood teaches a turn **before** a bridge. The second requires crossing the river and turning **after** the bridge. Missions within a neighbourhood share the first two stops. This is a small authored collection, not an unlimited generator.

The learner selects connected map points and presses **Go**. Planning does not move Barsik. Each successful encounter provides the next directions. At the correct address, **Deliver the letter** completes the activity and shows the handover.

These practice deliveries are separate from the campaign’s final letter to the learner.

## Map and interaction

The map’s streets, entrances and landmarks correspond to the saved mission graph. Both neighbourhoods have distinct geography. Riverside adds a market, square, library, school, station and café.

Left and right refer to the direction of travel. House numbers identify buildings; recipient names do not reveal the correct door. The bridge and nearby junctions are separate points, so “before” and “after” change the route.

The checker validates connected movement, the destination and any relevant spatial constraint. It checks straight movement, required approaches and places the route must avoid. It accepts harmless retracing where the instruction allows it. It does not require every successful route to be the shortest one.

A large map sits beside the conversation on desktop. On narrow screens, the encounter appears first. Starting a route brings the map and current directions together. Both audio messages remain available during listening practice. The map can be enlarged and panned. Large adjacent-stop buttons and keyboard controls provide alternatives to small map points.

Barsik moves along the submitted route. Reduced-motion settings skip the animation. Refreshing keeps the checkpoint, draft, help and feedback.

## Language and recordings

Russian directions are authored in `services/route_content.py`. English UI labels explain the controls. Sentence translations appear only on request, except for the recipient’s final thanks.

There are **33 prepared Russian recordings**. Each character keeps a consistent voice. Audio keys include both speaker and text. Playback offers repeat, pause and slower speed. Starting another clip pauses the previous one.

**Read and listen** displays the Russian directions. **Listen first** withholds the transcript from the session response, notebook and audio labels. Finishing the received recordings enables **Go**. The learner can always reveal the text instead. A requested Russian clarification can also supply the directions, with that help recorded.

Playback completion is a browser receipt, not proof of listening comprehension. The server checks that its recording belongs to the current encounter. It does not treat that receipt as a certified assessment.

Help includes:

- A simpler Russian clarification, including a question about which side of the bridge to turn on.
- The Russian transcript or English meaning.
- Meanings of selected encountered forms, with their original sentence.
- A suggested route.
- A notebook of directions received so far.

Future dialogue and hidden route constraints are excluded from the ordinary session response. Requesting a route intentionally reveals the current route. Replay and slower audio do not mark an attempt as assisted. Revealed text, translations and other help are saved. Hiding the text later cannot erase its use from the first-attempt record.

The Russian wording and generated speech still need a tutor’s review. Automated tests establish content consistency and application behaviour, not natural pronunciation or teaching quality.

## Results and section practice

A wrong route shows where Barsik stopped and explains the relevant mistake. **Try from the last stop** returns to the character who gave those directions. The learner can retry or ask for help.

The first check for each section is immutable. Later corrections have separate records. Results distinguish a first success using text, a first success using listening, and an attempt completed with help or correction. There is no timer penalty.

After delivery, missed or assisted sections offer **Practise this section**. Any section can also be chosen under **Revisit a section**. Practice starts at that encounter and ends when the learner reaches its destination. Its draft, help and position survive refresh.

Practice records are separate from the original checks. Returning to the results restores the completed delivery. Practice cannot award coins again, overwrite the original result or advance into another delivery section.

Completion uses the existing Lingocoin ledger and its daily allowance and replay rules. Repeating the completion request cannot duplicate a reward. Guest completion can attach to a newly created profile under the existing ownership rules.

**This format does not currently change Elo.** It preserves route evidence, but the arrow drill’s chance model does not measure these decisions. A reviewed assessment policy must precede Reading or Listening rating updates. Participation rewards work independently.

## Vocabulary and native flashcards

Completion offers selected words from the received directions. Each reference keeps its lemma, encountered form, grammatical tags, full source sentence and contextual English meaning.

| Lemma | Encountered form | Context | Grammar |
| --- | --- | --- | --- |
| фонтан | фонтана | до фонтана | Genitive singular |
| мост | мостом | перед мостом | Instrumental singular |
| мост | моста | после моста | Genitive singular |
| площадь | площадь | через площадь | Accusative singular |
| парк | парку | к парку | Dative singular |
| вокзал | вокзалом | рядом с вокзалом | Instrumental singular |

Only phrases present in that delivery are offered. For example, Vera’s final directions do not mention the park.

Learners can save a word through the vocabulary resolver or select forms for native flashcards. This uses the existing contextual card generator, required media and scheduler. No universal English translation field is added to `words`. Playing does not automatically create cards or change Anki.

The public demo can play the prepared missions, recordings and section reviews. It cannot save vocabulary or invoke the paid card generator through these controls.

## Backend structure

| Component | Responsibility |
| --- | --- |
| `services/route_content.py` | Authored maps, missions, spatial rules, characters, language and vocabulary references |
| `services/route_delivery.py` | Ownership, saved state, response projection, route commands and completion |
| `services/journey_games.py` | Existing catalogue, starts, version dispatch and rewards |
| `blueprints/journey_games.py` | CSRF-protected route command endpoint |
| `ui/src/DeliveryOptions.tsx` | Delivery and presentation choices |
| `ui/src/DeliveryGame.tsx` | Encounters, planning, audio, help, results and section practice |
| `ui/src/DeliveryMap.tsx` | Illustrated map, accessible points and Barsik |
| `scripts/prepare_delivery_audio.py` | Explicit preparation of authored recordings |

Migration **035** added two tables. This continuation needs no further schema migration.

- `journey_route_state` stores the current state and revision. Optional listening and practice state live in the existing JSON document.
- `journey_route_actions` stores actions, request identities and first, correction or review results. A unique index permits only one first check per section.

The parent game session freezes the mission, characters, language and route rules. Its content version remains `journey-delivery-v2`. Early version-2 sessions receive compatibility defaults in memory. Their stored content and answers are not rewritten.

Authored content is checked before a new session starts. Validation checks map connectivity, encounter continuity, route constraints and vocabulary contexts. Each vocabulary form must occur in its attributed sentence.

`POST /api/v1/games/sessions/<id>/route-command` accepts `request_id`, `revision`, `action` and `payload`. Each action has a fixed payload shape and allowed phases:

- Movement: `begin`, `plan`, `go`, `talk`, `retry`, `deliver`.
- Support: `help`, `listen`, `mode`.
- Section practice: `review_start`, `review_exit`.

The server checks ownership and CSRF, rejects stale revisions and disallows impossible transitions. Repeating a request with the same body returns the saved state. Reusing its ID with a different body is a conflict. The UI retries uncertain saves with the same request identity. Audio receipts wait for an outstanding route save rather than racing its revision.

Routes are limited to 32 points and sessions to 1,500 saved actions. Public-demo request limits remain in effect.

## Media and operations

Recordings are committed under `flask_vocab_app/static/audio/deliveries/`. The manifest contains text and speaker assignments, not API credentials. The Docker allowlist includes the directory. These recordings contain authored examples, not learner uploads.

Starting or playing a delivery makes no provider request. To prepare new authored audio explicitly:

```sh
.venv/bin/python scripts/prepare_delivery_audio.py --dry-run
.venv/bin/python scripts/prepare_delivery_audio.py --max-new 14
```

The limit is a ceiling on newly generated clips. The script keeps existing voices, assigns voices to added characters and skips prepared files. An optional `--settings /absolute/path/settings.json` loads an existing preview configuration. It does not rewrite settings or `.env`.

Apply migrations against the intended configured database. Back up and rehearse on a copy first. The current local preview reads its database and built UI paths from `instance/native-flashcards-mvp/settings.json`, separately from the legacy default database.

`DIRECTIONS_DELIVERIES_ENABLED=false` disables new starts in this format. Existing delivery sessions remain playable. A deployment rollback must retain support for version 2 and migration 035. Disabling the flag does not authorise restoring an old database over learner work.

## Verification and remaining work

Automated coverage includes all five routes, before/after bridge errors, contextual native-card export, listening disclosure, recording receipts, immutable first checks, section replay, ownership, CSRF, stale tabs, guest transfer and compatibility with earlier saved deliveries. Public-demo tests complete Riverside listening practice and section review with external connections blocked.

Browser checks use a separate disposable learner database. They cover the Riverside delivery, a wrong turn, correction, text support, completion, section replay and narrow-screen controls. Audio checks decode all 33 recordings. No public deployment is part of this branch.

Remaining work:

1. Review the Russian, speech and map ambiguity with a tutor and a learner.
2. Agree an assessment policy before awarding Reading or Listening Elo.
3. Add optional spoken clarification through Speaking.
4. Expand authored missions from suitable lesson contexts. Arbitrary vocabulary filters should not dictate street geography.
5. Consider controlled generation after varied authored missions have been validated with learners.

Characters speak at the planned encounters. Wrong destinations currently produce route feedback; optional conversations at every building are not implemented.
