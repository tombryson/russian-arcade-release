# Earlier procedural delivery missions

This document describes the earlier `delivery-town-v3.1` and `delivery-dispatch-v1` generators. They remain available for saved sessions, introductory samples and the public demo. New local deliveries use the [block and event engine](procedural-directions-implementation.md). The details below are a compatibility reference, not the current local generator's limits.

## Purpose

Follow the directions creates a delivery from the places in a saved town. The learner talks to people, follows Russian directions and discovers the next part of the task on arrival.

The town stays recognisable between deliveries. The mission composer varies collection points, recipients, destinations and intervening encounters. Each completed assignment is saved with its seed and facts so that refreshing or replaying it does not change the task.

The language comes from a bounded set of checked Russian sentences. The game combines them to describe generated facts. It does not ask an AI model to invent streets or decide which answer to accept.

The map generator still has four street plans. Mission composition adds variation within those towns; it does not make the geography unlimited.

## Town structure

`services/route_town.py` generates a 19 by 15 tile map. Each tile is 100 map units wide. The town has three named districts and two river crossings.

The generator uses four controlled street plans. It lays out streets, divides the space into blocks, then places buildings on plots within those blocks. The seed selects a plan and varies house positions. Civic buildings, a market square, a park and a residential courtyard give different parts of the town a purpose. Most destinations sit inside the street network instead of along the map boundary.

Main streets, residential streets and pedestrian paths have separate classifications. Streets contain loops and staggered junctions. Either river crossing remains usable when the other closes. Blocking both crossings separates the two banks. Buses use roads; walking routes may also use pedestrian paths.

Buildings occupy their own tiles. Their entrances are adjacent walkable nodes. A building can have more than one entrance: the courtyard house has a front door and a separate southern entrance. Building colour and location are explicit data, not details guessed from an illustration.

The map contract contains:

| Field | Purpose |
|---|---|
| `width`, `height`, `tile_size` | Map dimensions and scale. |
| `nodes` | Walkable positions with names, kinds and optional entrance or building references. |
| `edges` | Connections between adjacent walkable tiles. |
| `tiles` | Background, river, street, bridge, courtyard and building tiles. Street exits match the graph. |
| `districts` | Named areas with rectangular bounds. |
| `street_segments` | The class of each graph edge: main street, residential street or pedestrian path. |
| `blocks` | Areas enclosed or served by streets, with a civic, residential, market, park or courtyard use. |
| `plots` | Building grounds and public spaces, including their frontage. |
| `closures` | Mission-specific closed crossings, with an explanation. |

The complete world also stores building records, named place IDs, bridge IDs and an ordered bus-stop list. These are used to construct and validate missions.

## Generated assignments

`services/route_dispatch.py` composes a connected assignment at the start of a new game. It selects distinct, reachable places from the saved town, places the relevant characters there and builds directions from those facts. A delivery can involve collecting a letter or parcel, learning that its recipient has moved, clarifying an address or asking a worker about a river crossing.

The composer chooses the facts independently where the map permits. It does not select one of the old fourteen story variations. Spatial clues must identify a valid entrance, and each new leg starts where the previous encounter ended. Recent assignment fingerprints are excluded to avoid immediate repeats.

The setup page offers a new delivery and a reading or listening mode. It does not name the upcoming complication. English headings and future stage labels also avoid revealing the destination or solution. English dialogue translations remain available through the help control.

### Earlier authored missions

The eight earlier town missions remain supported for saved sessions and explicit legacy requests. They are no longer listed as the new-game menu. Their finite variations are documented here for maintenance:

| Mission | Encounters and decisions | Seeded variation |
|---|---|---|
| The closed bridge | Find a road worker. Learn which crossing is closed. Choose a valid detour to the library. | North or south bridge closes. The meeting point, instructions and route change. |
| An unfinished address | Ask the librarian for the missing address. Combine house colour with its position between two landmarks. | The recipient lives in the yellow or blue house. Both colours also appear elsewhere, so colour alone is insufficient. |
| Collect the parcel | Collect the item, receive its address, then take it to the recipient. | Collection at the bakery or market; delivery to the café or library. |
| A change of plan | Visit the recipient’s home. A neighbour explains where she has gone. Follow the new information. | The recipient has gone to the market or park. |
| The courtyard entrance | Meet the caretaker at the front door. Walk around the building to the entrance he describes. | One authored scenario. |
| Which bank? | Ask which bank is intended before leaving. The answer distinguishes two possible destinations. | One authored scenario. |
| Two stops after the square | Find the bus stop, board the service, choose where to get off and deliver the letter at the station. | One authored scenario. |
| Give someone directions | Build directions from a visitor’s position and heading to the library. | One authored scenario. |

These older missions have fourteen fact combinations in total. Explicit legacy requests still cycle through their variations. The generated-delivery flow uses the composer instead.

The clarification question is part of the activity. Asking it is not a hint penalty. The initial address is deliberately incomplete, and the player must be able to obtain the missing detail before being graded.

## State and runtime contract

`route_town.build_world(seed)` returns a deterministic, JSON-safe world. The application stores it for reuse. `route_dispatch.build_mission(world, seed, ...)` freezes a composed assignment, its dialogue and accepted route constraints for one session. The older town builder remains available for compatibility.

The world seed controls geography. A fresh mission seed controls assignment facts and encounters. Both are saved. `generator_version` identifies the world format; the current version is `delivery-town-v3.1`.

Mission packs retain the existing `journey-delivery-v2` format. Each leg still has a starting point, target, route, speaker, arrival speaker, dialogue and rules. New optional fields describe additional actions:

| Field | Runtime meaning |
|---|---|
| `questions` | Available questions and their recorded replies. |
| `required_question` | A question that supplies necessary information before travel. |
| `arrival_item` | An item received after a successful arrival. |
| `requires_item` | An item needed for the next leg. |
| `arrival_remove_item` | An item handed over at the destination. |
| `arrival_text`, `arrival_text_ru` | Brief contextual feedback on arrival. |
| `arrival_action_label`, `arrival_action_label_ru` | A specific next-action label where useful. |
| `transport` | Service ID, ordered stops, boarding point and correct alighting point. |
| `guide` | A route built through direction phrases for another character. |
| `completion_text`, `completion_text_ru` | A conclusion appropriate to the mission. |
| `visible_contacts` | Named people whose meeting point has already been described in the dialogue. |

The route engine remains responsible for ownership, revision checks, action receipts, rewards and persistence. The content generator supplies facts and validates them; it does not mutate a learner’s session or award progress.

Existing saved mission packs retain their original map and routes. A content compatibility layer can clarify directions for recognised geometry without replacing the saved pack. The detour now specifies Sergei’s bank-side meeting point and the library entrance. Its replacement recordings use the same character voices. New missions reuse the latest town with the current generator version. If only an older town format exists, the next new mission creates a compatible town; it does not rewrite the old session.

### Navigation and assessment

Stopping on a street, an open bridge or a walking waypoint is an unfinished journey, not an incorrect answer. The player can continue from that position. The server stores the route already walked; Undo and Clear affect only the part still being planned.

Stopping immediately outside a building gives entrance guidance. This uses the building’s actual connected frontage, not a distance radius. A neighbouring house or the wrong courtyard entrance still counts as a different destination. Bus alighting remains an assessed choice.

The detour shows separate progress for crossing the correct bridge and reaching the library entrance. Selecting the closed bridge while looking for Sergei stops Barsik at the barrier beside him and completes that meeting. Trying to cross it after receiving the detour instructions is still a route mistake.

Navigation stops have separate action receipts and do not use the first assessed attempt. Known older failures at the bridge meeting point or a walking waypoint are corrected in the displayed result; their original receipts remain unchanged. This also lets existing sessions continue with the clearer rules.

The map starts with a town overview. Local view adds zoom, panning, centring and a small overview inset. Selecting a straight stretch advances the planned route to the next junction, bend or landmark. Players can still choose individual adjacent steps. The direction-building mission uses the same connections to compose Russian instructions for the visitor. It distinguishes a pedestrian-path branch from a road junction.

Road borders and surfaces render in separate passes so connected segments meet without individual outlines across the road. Street width follows its class. Building grounds and public spaces render beneath roads and landmarks. Older saved maps receive the continuous-road rendering while retaining their original geography.

Completed missions use the existing participation reward: 3 Lingocoins, within the shared daily activity cap. Corrections and section replays preserve the first attempt. These deliveries do not yet change Elo; route assessment needs calibration before it becomes evidence of a language level.

## Russian content and audio

Dialogue is short and authored. Inflected vocabulary is stored with its lemma, the form actually encountered, grammatical metadata and the original sentence. There is no attempt to assign one permanent English translation to a lemma.

Examples include `по южному мосту`, `между библиотекой и аптекой`, `у прилавка` and `после площади`. A stored vocabulary item must occur in the precise line linked to its encounter.

Audio is prepared in advance. The composer exposes every complete sentence it can use through `all_audio()`. Recordings are cached by speaker and text, so different assignments can reuse a sentence without a paid request during play. The older mission catalogues remain available for their saved sessions.

Prepare generated dialogue with `scripts/prepare_delivery_audio.py --generated`. Use `--dry-run` to inspect the number of missing recordings and characters before running the explicit preparation command. The command refuses to exceed its `--max-new` limit. It does not change service credentials.

A new sentence must appear in the audio catalogue. Coverage tests verify that generated assignments contain only prepared lines. Listening mode must not silently fall back to missing recordings or start a provider request.

## Validation

World validation checks connectivity, loops, adjacent street connections, matching tile exits and building entrances. It rejects overlapping buildings, plots that cover roads or the river, and entrances that disagree with their building’s frontage. Most landmarks must have streets around them. It also proves that either crossing can carry a delivery when the other closes.

Mission validation checks continuous encounters, reachable routes, stated restrictions, available clarification, item collection before delivery and bus-stop order. Bus routes cannot use footpaths. Address clues must identify exactly one house. A courtyard instruction must lead to the correct side of the same building. The café is directly south of the station; the bank and library clues are checked against their river bank.

Alternative routes remain valid unless the spoken instruction rules them out. The engine should not penalise a longer route simply because the prepared example is shorter. A shortest-path requirement would need to be stated to the learner.

The unit tests generate many seeds and independently inspect their graphs and tile exits. They also verify that changing the mission seed changes actual routes and wording, while keeping the same world. Audio coverage is tested across generated variants.

## Further work

The next useful additions are multiple delivery orders, opening hours and further dialogue branches. They need explicit objective state and visible time costs before they become fair assessment tasks.

Bus travel, courtyard-specific instructions and guiding a visitor still belong to the earlier authored missions. They need compatible encounter rules before they can join the new assignment composer.

Additional districts should add meaningful choices and landmarks rather than long stretches of empty walking. New Russian templates still need language review. Procedural variation cannot replace that review or make a single interaction into a complete course.

Free-form spoken directions, open-ended NPC conversation and automatic lesson-derived missions remain separate features. This implementation does not claim to provide them.
