# Speaking scenarios

Updated 2 October 2026.

Speaking has five settings: café, shops, directions, station and meeting people.
Each has separate A1 and A2 tasks. Fluent conversation and Step-through use the
same selected situation, facts and curriculum objectives.

## Catalogue and curriculum

The published catalogue retains 30 original situations: three for each setting
and level. New starts normally assemble a versioned situation from compatible
authored dimensions (604 distinct recipes across the ten groups). The A1 and A2 cards have different descriptions so learners can see what
changes before opening a task.

| Setting | A1 focus | A2 focus |
| --- | --- | --- |
| Café | Request food and drinks, specify a quantity and ask the price. | Clarify ingredients, make a request and check the order. |
| Shops | Describe an item and ask its price. | Ask for another size or alternative and check payment or change. |
| Directions | Ask where a familiar place is and check a simple detail. | Clarify a route, landmarks or walking time. |
| Station | Ask for a ticket, departure time and price. | Plan a connection or coordinate a more detailed journey. |
| Meeting people | Introduce yourself and exchange simple personal information. | Discuss interests and agree on a plan, time or place. |

Each setting and level has an explicit curriculum topic. A topic's teaching band
and the task's level remain separate: a simple A1 ticket exchange can introduce
the Travel topic, which enters the full course at A2. Neither field changes word
difficulty or inserts vocabulary into a learner's database.

The saved situation includes the shared curriculum version, topic, objectives,
grammar, vocabulary and Speaking brief. It also contains a small set of selected
requirements for that conversation. The topic supplies context; a short task is
not expected to cover the whole topic. Curriculum pages link to Speaking where
a matching implemented task exists. The other topic briefs remain future work.

## Variation

New starts use the free procedural assembler in `services/speaking_procedural.py`.
It combines explicitly inflected objects with compatible goals, service details,
constraints and interactions. Quantities, totals, change and train connections are
derived together. It never asks a model to invent facts or repair a recipe.

| Setting | A1 recipes | A2 recipes | Dimensions beyond names/prices |
| --- | ---: | ---: | --- |
| Café | 64 | 32 | Food/drink, service, accessory; ingredient constraint, replacement, portions, billing |
| Shops | 36 | 48 | Item, agreeing colour, service; size direction, payment, replacement clarification |
| Directions | 64 | 128 | Destination, landmark, turn, walking time; landmark order and entrance clarification |
| Station | 64 | 72 | Destination, day, departure, passengers; transfer, connection/deadline/platform interaction |
| Meeting people | 24 | 72 | Setting/register, personal-information question; activity, day, unavailable/alternative time, equipment/meeting point |

This is a larger bounded authored space, not unlimited AI story generation. The
recipe identity includes version 3 and a deterministic index. Pool order or meaning
changes require a new version; published seeds must never be repurposed.

Both modes consult the same profile's last 100 starts in the selected setting and
level, across Fluent and Step-through. The selector compares semantic fact keys,
ignoring cosmetic names, prices and seed identities. It prefers a meaning outside
that recent window, then the least recent available meaning. Larger groups can
cycle beyond the window; deleting session history also removes its exclusions.
**Another situation** excludes the current preview without recording a play or
calling an AI provider. Separate simultaneous previews do not reserve tasks.

An explicit enabled legacy seed remains valid. A disabled/edited original group
falls back to its enabled stored variants, so the assembler does not bypass
catalogue publication controls. B1/B2 remain unavailable unless separately
published; procedural assembly does not manufacture higher-level coverage.

The preview seed identifies its exact facts and objectives. Switching modes
keeps that seed. Starting saves a complete snapshot, so later catalogue updates
do not change an existing conversation. Dialogue wording can vary between new
sessions; resuming a saved Step-through session keeps its original dialogue.

## Generation and assessment

Fluent prompts receive the saved curriculum context and task requirements. The
character should create opportunities to practise them while accepting natural
Russian, valid short answers and requests to repeat. Task completion and grammar
accuracy are separate. Correct simple language must not be marked wrong merely
because a more elaborate construction was possible.

Step-through generation supplies evidence for every selected requirement. Each
evidence item identifies a turn and quotes the correct Russian learner reply.
Validation rejects missing requirements, duplicate or unknown IDs, invalid turn
references, invented quotes and evidence taken only from the character's speech.
The same check runs before the service publishes the dialogue. Coverage records
are internal; the exercise displays the dialogue, task, replies and optional hint.

These checks establish traceable coverage. They do not prove that a quoted reply
fulfils an objective or that every distractor is linguistically sound. Generated
examples also need content review. No additional model judge or automatic paid
repair loop runs on every conversation.

New Fluent snapshots also freeze a narrow fact-dependent diagnostic mapping.
A1 checks the requested order/item/ticket/location question or reciprocal name
exchange. A2 checks the selected clarification and response, or a shared plan and
changed time. These mappings validate against the versioned recipe and cite the
corresponding reference requirement; they do not claim coverage of its entirety,
independent conditions, grammar mastery or general proficiency. Existing exact-seed
legacy mappings remain unchanged. Fluent feedback uses recorded learner audio and
the saved task. Step-through
checks selected replies and gives explanations; it does not award spoken
fluency scores. See [Speaking assessment](speaking-assessment.md) and
[Step-through Speaking](step-through-speaking.md).

## Storage and migration

Migration 042 adds level-specific catalogue descriptions and curriculum mappings,
and installs the 30 current situations. Earlier variant rows remain for foreign
keys and historical sessions, but are disabled for new selection. Saved dialogue,
recordings, feedback, scores and vocabulary are not rewritten.

A preview is read-only. Starting materializes its procedural variant in the
existing variant table inside the session transaction; no new migration is needed.
Catalogue availability counts retain the published base variants rather than
growing with saved procedural starts. New sessions reference the selected variant
and store their curriculum snapshot
in `scenario_json`. Fluent and Step-through retain their existing session tables,
ownership, idempotency, spending limits and audio storage. Repeat selection reads
those tables rather than keeping a separate progress ledger.

## Verification

Automated checks cover catalogue relationships, level separation, compatible
facts, curriculum snapshots, shared repeat avoidance, preview-to-start stability,
objective evidence, historical sessions and request concurrency. UI tests cover
level-specific descriptions and curriculum links into both conversation modes.
Provider-free fixtures test storage and validation mechanics, not Russian
teaching quality. Representative model-generated dialogues require a separate
content check.
