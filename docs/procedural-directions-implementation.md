# Procedural directions implementation

Status: implemented locally, 17 September 2026. This is the first release of the [procedural directions design](procedural-directions-engine-design.md). The public demo continues to use prepared sample content.

## Player experience

Follow the directions creates a delivery in a saved town. A new assignment changes the people, collection point, destination and encounters. It does not move the town's buildings.

Select **Explore a new town** when starting a delivery to change the geography. The new town uses a different layout family from the previous one. Existing deliveries keep their maps, route history and rewards.

The setup offers **Read and listen** and **Listen first**. It does not list upcoming twists. Russian dialogue reveals where to go and who to meet. English help is optional.

A delivery has two to four travel encounters. Every assignment includes a real distinction: matching buildings in different locations, or the main and courtyard entrances of one building. Recognising the noun “library” alone is not enough to finish the main task.

The current event library supports:

| Event | What the learner does |
| --- | --- |
| Collection | Finds the collection point and receives a letter or parcel. |
| Address clarification | Asks a Russian question to distinguish two possible addresses. Some assignments involve a local who knows the address. |
| Entrance choice | Finds the stated courtyard entrance instead of the main entrance. |
| Relocation | Receives new information on arrival and continues to the recipient's new location. |

The letter or parcel has a purpose. Current examples include an invitation, family news, a borrowed book and forgotten gloves. The purpose stays consistent throughout the assignment.

## Components

| Component | Responsibility |
| --- | --- |
| `content/deliveries/map-blocks.json` | Reusable neighbourhood geometry, plots, connections and permitted rotations. |
| `content/deliveries/town-layouts.json` | Town arrangements, central features and connections between neighbourhoods. |
| `content/deliveries/landmarks.json` | Landmark definitions, entrance requirements, tags and checked Russian forms. |
| `content/deliveries/events.json` | Event requirements, selection weights, story premises and character circumstances. |
| `services/route_world.py` | Assembles blocks, places landmarks and validates the movement graph. |
| `services/route_mission.py` | Binds events to places and produces checked dialogue, arrival rules and a saved mission. |
| `services/route_preparation.py` | Prepares short AI dialogue additions, checks them and prepares audio. |
| `services/route_jobs.py` | Owns preparation claims, retry state, checkpoints and audio access. |
| `services/route_delivery.py` | Runs the existing movement, encounters, questions, replay and completion flow. |

The renderer still uses the existing map contract. Connected roads render as continuous surfaces. The engine does not generate a new picture for every town or encounter.

## Town assembly

The first block library contains six templates. Their internal routes, plots and boundary connections are explicit. The assembler rotates compatible blocks and joins matching connections. It then assigns landmark definitions to usable plots.

The generator selects among three layouts:

| Layout | Geography and routes |
| --- | --- |
| Market square | A central market, a street ring and four connecting streets. |
| Garden neighbourhood | A central park, a pedestrian loop and two connecting paths. |
| Riverside | Neighbourhoods on two river banks, joined by two crossings. |

Market and garden towns are 21 by 21 tiles. Riverside towns are 19 by 18. A river is optional. The assembler also supports three block rows, although the game currently uses two. Fifteen landmarks include repeated banks and coloured houses, plus a building with separate entrances.

The validator checks graph connectivity, adjacent connections, plot overlap, entrance access and matching block connections. For river towns, it also checks that either crossing can remain usable if the other is blocked. Land towns must not contain river or bridge tiles. The mission composer excludes riverbank clues when there is no river.

This is assembly from a finite content library. It is not unrestricted city generation. Different seeds change block placement, orientation and landmark assignment; they do not create new building types.

### Map presentation

The map opens with the whole town visible and keeps that view when route planning begins. **Explore streets** shows about 11 tiles across, instead of six. Zoom and pan remain separate from movement. Zooming out from the overview cannot zoom the player in.

Landmark labels use the displayed map size to remain readable at different zoom levels. Labels avoid nearby landmarks and other labels. Buildings occupy more of their plots, while narrower roads make destinations easier to distinguish from the street network. These changes also apply to saved towns; their underlying coordinates do not change.

## Mission composition

The composer selects compatible events and binds their roles to the saved town. It derives spatial clues from actual geometry. A clue must identify exactly one destination, and its reference landmark must also be identifiable.

Current relationships include cardinal position, the same street, the same river bank and an opposite frontage where the geometry supports it. The engine uses checked Russian phrases and case forms. It does not insert dictionary headwords into an English sentence template.

Each mission stores its seed, town snapshot, event sequence, item, recipients, dialogue, routes and accepted entrances. Every leg starts at the previous encounter's destination. The item must be collected before it can be handed over.

Recent assignment fingerprints exclude repeated combinations of events, place roles, spatial relationships and entrances. Changing a person's name or the parcel's contents does not create a new fingerprint by itself. The last 20 assignments are considered when starting another delivery.

The runtime still uses a linear sequence of legs, with optional questions inside an encounter. The composer has not introduced a general branching story engine.

## Dialogue and language

The engine supplies the clauses that determine the correct answer. These clauses remain unchanged during AI preparation. The model adds one or two short conversational sentences around them.

Each request identifies Barsik as the listener and supplies the current speaker's disclosed facts, checked lines and permitted story context. It does not receive the full map, later encounters or a clarification answer that the learner has not requested. Dialogue checkpoints record the draft and review prompt versions.

A separate model request checks the additions for unsupported facts, directions, spoilers, inaccurate translation and unnatural Russian. Code also rejects malformed output and new direction language. Rejected additions never change the map or the accepted answer.

The first content rejection triggers an automatic rewrite. After two content rejections for an encounter, preparation uses a checked circumstance from the content library. It records this fallback separately from model-reviewed dialogue. Missing credentials, provider failures and model refusals still pause preparation; they do not trigger that fallback.

These checks reduce inconsistency. They do not prove linguistic correctness. Tutor review and real playthroughs remain useful, particularly when adding new phrases or difficulty levels.

The implementation uses the existing configured text model and speech provider. It does not change API keys, the model selection or the general voice-selection policy. Preparation records the selected model and character voices so that a retry uses the same settings. Character voices remain consistent within a delivery.

Vocabulary references retain the lemma, encountered form, grammatical case, sentence and contextual English meaning. No universal English translation is added to the vocabulary database.

## Preparation and audio

The complete short mission is prepared before play. This includes later dialogue, clarification replies and the ending. Those recordings remain hidden until the corresponding encounter is available.

Preparation advances in small steps. A step makes at most one provider request. Network calls run outside the SQLite transaction; the result is then saved as a checkpoint.

Recorded speech is cached by exact text, voice, language, provider settings and learner scope. A separate cache table links each speech specification to its asset. Multiple specifications can share identical stored audio bytes without losing their separate cache records. Existing compatible static recordings can be reused. New audio uses the existing learning-asset store. It is not written into the public static directory.

The session audio endpoint checks ownership and current disclosure. Owning a mission does not grant access to all its future dialogue. Other learners cannot request its private recordings.

The job has a durable claim and lease. Duplicate requests cannot run the same active step. A stale response cannot replace a newer checkpoint. An expired claim requires an explicit retry because its provider call may already have completed.

Retries preserve the town, assignment and completed recordings. Starting another delivery supersedes the earlier preparation. This prevents its late result from becoming the active game; it cannot reverse a provider request already in flight.

If a completed recording later disappears from storage, the delivery shows a retry option. Reading or refreshing the session does not start a paid repair. An explicit retry restores the missing recording while retaining the saved assignment.

Preparation has limits on request attempts, line count and speech characters. New paid preparation is disabled in the public demo. Play itself makes no text-generation or speech-generation requests.

## Persistence and compatibility

Migration `036_procedural_deliveries.sql` adds `journey_route_preparations`. It stores status, error, claim, lease and attempt information for a game session.

Migration `037_route_audio_cache.sql` adds `journey_route_audio_cache`. It maps the scoped speech-specification hash to a learning asset. Both migrations are required for the new preparation flow.

The complete town and mission remain in the existing session content snapshot. Route actions and player position remain in the existing route tables. Audio stays in the learning-asset store. No vocabulary or learner progress is rewritten by this migration.

New local deliveries use `town-procedural`. The town format is `delivery-block-town-v2`, and the event composer is `delivery-events-v1`. Saved content retains the `journey-delivery-v2` runtime format.

Older sessions keep their original maps and dialogue. Their generators remain available for compatibility. When a learner starts a new delivery, the application reuses their latest town with the current world version. If none exists, it assembles one.

The public demo and introductory samples retain the earlier prepared assignment path. They do not silently start paid preparation.

## Assessment and rewards

Stopping partway along a street is navigation, not a failed answer. Near the correct building, the engine can explain how to reach its entrance. A stated courtyard entrance is a meaningful choice; the front door is not interchangeable with it.

Arrival rules are explicit data. They record the target entrance, accepted nodes, connected approach nodes and whether the entrance distinction is assessed. The player should not have to guess an invisible point.

The existing participation reward remains in place: 3 Lingocoins for an eligible completion, within the shared daily activity cap. New generation does not enable Elo updates. Route assessment still needs calibration before it represents language proficiency.

## Verification

The focused composer suite exercises 200 deliveries across 20 towns. The checks cover reproducibility, event variation, truthful clues, item continuity, real distractors, hidden answers, contextual forms and rejected corruptions. Additional assignments in both land layouts verify that dialogue never invents a river.

The world suite has 12 tests, including generation across 200 seeds. It checks all three layout families, block connections, entrances, overlap, reachable landmarks, requirements and topology variation. The current sample produced 69 market towns, 70 garden towns and 61 river towns, with 184 distinct driving-road graphs.

Additional preparation and HTTP tests cover model failures, audio reuse, ownership, retry claims and compatibility. These tests support the implementation; they do not establish that every generated conversation is enjoyable or grammatically flawless.

The HTTP tests complete new deliveries in reading and listening modes. Listening tests require the learner to hear a clarification reply before acting on it. They also check that completion awards one eligible reward and leaves the saved mission unchanged.

## Remaining work

- Compose bus journeys, bridge closures and visitor guidance through the new event engine. Their earlier authored versions remain available in saved sessions.
- Add more landmark and block definitions after reviewing actual town layouts.
- Add checked compound route instructions, with route constraints that accept alternative valid paths.
- Expand the small premise library and review the resulting Russian with learners or a tutor.
- Add branching objectives and unordered collections only when the runtime can represent them explicitly.

Free-form spoken NPC conversations, moving traffic, opening hours and automatic lesson-derived deliveries are not included in this release.
