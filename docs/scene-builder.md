# Describe the scene

## Purpose

Describe the scene replaces Postcard Pairs in the activity catalogue. The learner chooses Russian words and endings to describe a simple illustration and a short situation. Each question tests a specific grammatical distinction.

Postcard Pairs could often be solved by recognising one noun in each unrelated sentence. The new activity holds the scene and surrounding vocabulary steady. Its alternatives differ in the feature being practised: a preposition, case ending, motion verb, agreement or participant role. Existing Postcard Pairs sessions remain readable and playable.

## Practice sets

| Set | What the learner chooses | What the question must establish |
|---|---|---|
| Location | A spatial preposition and the noun form it requires | Where the subject is relative to the named object |
| Motion | The verb form that fits the journey | Travel on foot or by transport, a current trip or habit, and the relevant stage of the journey |
| Position and placement | A verb describing a position or placing something | Whether the object is already there or somebody is putting it there |
| Agreement | The adjective form matching its noun | The noun's gender and case in the sentence |
| Who does what | The noun forms identifying the participants | Which person acts and which person receives the action |
| Mixed practice | Questions from several sets | The same evidence as each individual set |

New games use a rule-driven generator. It chooses the objects, relationship, movement, time and participant roles first, then derives the Russian sentence, correct forms, alternatives and illustration from those facts. The activity offers five or ten questions. Choice order varies, and learners can change their selection before checking.

The retained 108 authored questions remain reference examples and regression fixtures. They no longer limit new games. Version 4 currently supports 922 distinct semantic specifications before character names, choice order and visual decoration. This is a bounded grammar engine, not unlimited AI generation.

| Focus | Semantic specifications | Meaningful changes |
|---|---:|---|
| Location | 186 | Six subjects, four reference objects, valid spatial relations and reversed perspective |
| Motion A1 | 272 | Destination, travel mode, current journey or round trips, tense and setting off |
| Motion A2 | 230 | Arrival, departure, entry, exit, proximity, crossing, carrying and aspect constructions |
| Motion B1 | 90 | Ordered route actions, crossings and simultaneous accompanying/carrying |
| Position and placement | 48 | Object, support or container, orientation, state or completed action |
| Agreement | 60 | Object gender, colour adjective and nominative/accusative/prepositional case |
| Who does what | 36 | Nine actions, actor/recipient direction and sentence order |

A photo cannot establish that a trip happens every day, or that an arrival has just been completed. The short situation supplies those facts. It must not leave the learner guessing what the illustration was intended to mean.

## Motion progression

Motion practice has three task levels, independent of the numeric difficulty stored against a word. The level selector appears for **Verbs of motion** and **Mixed practice**; in mixed practice it changes the motion questions only. The other grammar sets remain selected by grammatical focus, without a level selector.

| Level | Coverage |
|---|---|
| A1 | `идти / ходить` and `ехать / ездить`: travel mode, directionality, present, past and future. Setting off with `пойти / поехать`. |
| A2 | Prefixed motion and aspect, including `входить / войти`, `приходить / прийти` and `уходить / уйти`. Carrying, transporting and accompanying someone with `нести / носить`, `везти / возить` and `вести / водить`. |
| B1 | Combine earlier material in routes and decisions about people and cargo. Each sentence contains two independently marked verbs. |

A1 begins with mode of travel, then contrasts a journey in progress with repeated or multidirectional movement. Past examples distinguish a journey in progress from a whole visit. Future examples include `будет идти / будет ходить` and `пойдёт / поедет`. Both members of the unprefixed pairs are imperfective. Directionality and aspect are separate features.

A2 introduces prefixed aspect pairs through regular actions, planned arrivals and future constructions. For example, after `будет`, learners choose `входить` rather than the perfective infinitive `войти`. The bank avoids treating imperfective past as inherently wrong when describing a completed visit: `приходил` can have a general-factual meaning. Carrying and accompanying are introduced here; B1 combines them with another action.

Choice banks contain two to six alternatives according to the contrast being tested. A level is defined by its grammatical coverage, not its button count. There is no rule that carrying verbs first become available at B1. Course boundaries vary; these levels describe the application's teaching progression.

A caption saying “every morning” does not, by itself, make `идёт` wrong. A regular outward journey can also use the directed verb. Pacing, repeated return trips and explicit journey stages establish the distinction. Likewise, `пойти` can mean going to an event without specifying transport; mode contrasts therefore give a clear walking or transport context.

Settings include `motion_level` (`A1`, `A2` or `B1`), defaulting to A1. Unsupported levels are rejected. A new game receives a seed; resuming keeps the original content. Selection balances grammatical contrasts and prefers meanings absent from the learner's last 20 scene sessions. Renaming a person or changing wallpaper does not count as novelty. Questions within one game have distinct semantic identities. If the available meanings are exhausted, the oldest are reused and recorded as repeated in private provenance.

Examples include a walk to a nearby pharmacy, a taxi to the station with heavy luggage, a bus commute, a car crossing a bridge and a parent accompanying a child. The interface assembles simple route illustrations from each situation's mode, setting and movement stage. It does not reuse the old café picture for an airport or bus journey.

The heading appears once. During play, the round counter and a small level label accompany it; the caption supplies the situation beside the sentence and choices. There is no second “Build the sentence to describe the scene” heading.

## Content rules

- Write and check the sentence, correct forms, alternatives and explanation together.
- Keep the surrounding wording natural. Use Russian choices even when the interface language is English.
- Test the noun ending as a separate choice where that is the objective. Do not silently correct it when a preposition is chosen.
- Use a caption to resolve genuine visual ambiguity. Do not disguise a vocabulary test as a grammar exercise.
- Avoid rejecting a reasonable alternative. Either include it as an accepted answer or make the situation specific enough to distinguish the intended response.
- Keep grammar explanations short and in the interface language. Russian examples remain in Cyrillic.
- Vary words and situations beyond the introductory lessons. Familiar vocabulary can support a question; it must not limit the whole curriculum to the learner's saved word list.

The engine uses explicit noun/adjective paradigms and checked motion forms. It rejects unsupported combinations instead of guessing endings for arbitrary vocabulary. Syncretic forms receive one button: for example, identical dative and prepositional `девочке` cannot appear as secretly different answers. Captions constrain distinctions that could otherwise admit more than one answer. Automated checks validate contracts and dictionary forms; they do not establish naturalness or learner comprehension.

## Interaction and feedback

The scene and situation appear beside a sentence with visible blanks. A labelled bank of buttons fills each blank. Selected buttons remain visible so learners can reconsider their choices before checking.

Feedback distinguishes the parts of an answer. A learner who chooses the right spatial relation and the wrong ending should see which decision was right and why the ending needs to change. The correct sentence becomes available after checking. Local installations can then request its Russian recording through the existing speech service; the public demo does not offer these unbundled recordings. Full-answer audio must not be accessible before the attempt through a guessed audio key.

The existing correction and missed-question review flows retain the first answer. Completing practice uses the normal participation reward rules. Rechecking a sentence or replaying a correction must not create another reward. The activity is guided practice, not certification of a CEFR level or spontaneous writing ability.

## Implementation

The new game has the stable ID `scene-builder`. Its saved question payload includes the scene identifier, bilingual situation, sentence segments and ordered slots. Each slot owns its allowed choices. Answer IDs are validated on the server against those slots.

`scene_builder.py` owns settings, retained authored examples and session persistence. `scene_generator.py` selects and realizes semantic plans. `scene_lexicon.py` contains the checked noun/adjective paradigms. `scene_motion_generator.py` composes compatible journeys; `scene_motion.py` retains the original reference questions and supplies motion paradigms. Both verbs from a two-part sentence remain available to the existing vocabulary/card pipeline.

Every answer has explicit lexical morphology. Past forms carry gender and number; present and synthetic future forms carry person and number. The perfective future `пойдёт` is linked to lemma `пойти`, not `идти`.

Analytical future is kept separate from lexical morphology. An option can display `будет идти`, while its vocabulary reference retains `идти`, part of speech `INFN` and imperfective aspect. The separate `construction` field records the full phrase and its future tense, person and number. This prevents `будет идти` from being inserted as one word variation, or future tense from being falsely assigned to an infinitive. The same rule applies when the exercise supplies `будет` and the learner chooses the infinitive.

The activity uses existing `journey_game_sessions` storage for ownership, frozen questions, first attempts, hints and completion. A private generation record holds the rule version, semantic identity and plan. It is omitted from the unanswered public response. No separate vocabulary database, queue or migration is needed. Versions 1–3 retain their original content and answer history. Only new starts use version 4. Changing levels, seeds or content versions does not reset the daily reward identity for a grammar focus.

Spatial illustrations compose a cat, book, ball, cup, bag or letter with a table, chair, box or shelf. Geometry, colour and orientation come from the same plan as the language. Motion uses the existing route illustration contract. Trains go between towns; vehicles enter courtyards, not shop doorways. A multi-action route's caption remains necessary because a single illustration cannot show every event. No per-round image generation occurs.

Completed contextual examples can use the existing explicit vocabulary and native-card actions. These actions preserve the Russian sentence, surface form and contextual meaning. They do not introduce a universal English translation field on the lemma table or alter Anki progress.

## Verification

Automated checks realize every semantic specification, verify lexical targets independently with the Russian morphology dictionary, exercise 100 seeds per focus and test real session history. They cover case contrasts, irregular feminine motion forms, future infinitives, duplicate visible forms, physical compatibility, frozen old sessions, retries, private answers and unchanged rewards. The frontend has component tests for the composable illustrations. These checks do not establish classroom effectiveness or official TORFL assessment validity; the activity remains standalone guided practice.

## Remaining work

- Add reviewed lexical paradigms and constructions based on learner errors, and introduce explicit levels for the other grammar sets.
- Allow compatible lesson vocabulary to populate these rules after morphological and visual checks. Arbitrary uploaded sentences are not automatically valid scene specifications.
- Add an optional typed or spoken answer after button-based practice. Recognition and sentence construction should not be presented as proof of unaided recall.
- Add a listening-led variant with prompts that supply the situation without speaking the answer.
- Evaluate alternative answers and illustration clarity before using this guided practice as evidence of independent grammatical production.

## Language references

[Direction and location](https://www.pelister.org/russian/tutorials/0061.html) explains the accusative/prepositional contrast with `в` and `на`. [OpenRussian's verbs of motion reference](https://en.openrussian.org/grammar/verbs-of-motion) describes travel mode, directionality and motion prefixes. These are reference aids; each exercise still needs contextual review.

The [TSU Russian grammar reference](https://vital.lib.tsu.ru/vital/access/services/Download/koha%3A000846498/SOURCE1), page 93, includes a regular unidirectional journey. The [Rostov State Medical University motion-verbs manual](https://rostgmu.ru/wp-content/uploads/2023/04/%D0%93%D0%BB%D0%B0%D0%B3%D0%BE%D0%BB%D1%8B-%D0%B4%D0%B2%D0%B8%D0%B6%D0%B5%D0%BD%D0%B8%D1%8F.pdf) provides further teaching contexts for motion verbs and their complements. These references inform the task design; the levels here are application curriculum targets, not an official TORFL examination syllabus.

The Pushkin Institute's references on [unprefixed motion](https://courses.pushkininstitute.ru/guide_pages/590) and [по- forms](https://courses.pushkininstitute.ru/guide_pages/596) explain these contrasts. Its guide includes some material earlier than this application's sequence. The [Complete Russian Language Course explanation](https://completerussianlanguagecourse.com/russian-verbs-of-motion-explained/) also distinguishes directionality from aspect. These references support the grammar; they do not establish one exclusive A1/A2 boundary for every course.
