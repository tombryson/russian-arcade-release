# Mixed vocabulary and radio practice

First steps introduces the games; it does not limit their vocabulary. A standalone game should help a learner use words they have met and discover a little new language. The vocabulary library is a source of familiar material, not a closed dictionary from which every future activity must be assembled.

This replaces the earlier assumption that all games need the same picture-and-audio preparation pipeline. The original introductory sessions remain readable. New sessions freeze their chosen content and preparation progress so a refresh or retry does not change the activity halfway through.

## Resources follow the activity

| Activity | Default content | Prepared resources |
|---|---|---|
| Pack the bag, Lost Parcel Detective | Three familiar contextual examples and one new word in context | Pictures for these examples |
| Describe the scene | Rule-generated grammatical contrasts composed from semantic scene facts | Reusable visual components; no per-game AI picture generation |
| Missing Stamp, Mailbox Sort | One distinct context per round: four familiar examples plus one discovery for five rounds; nine plus one for ten rounds | Fresh text; no mandatory picture or recording |
| A Letter Back | The same distinct-context mix, with one sentence per round | Sentence recordings for reconstruction |
| Follow the directions | Route language and a map | No vocabulary picture pool |
| Post Office Radio | One coherent Russian broadcast supported by familiar vocabulary, introducing two to four new words | One complete broadcast recording and four comprehension questions; no pictures |

The counts describe the normal mix when familiar words are available. Text games can reuse a familiar lemma in a different generated sentence when the library is small; they do not cycle four or five identical targets through ten rounds. An empty familiar pool is completed with discoveries. Preparation excludes library lemmas and recent encountered discoveries, including words the learner has not saved. Topic, local difficulty and selected lesson context guide the material; local difficulty bands are not a TORFL qualification.

Picture games prepare at most four pictures. A ten-round Pack the Bag uses the ten different one- or two-picture subsets. The retained Postcard Pairs activity uses the ten different two- or three-picture subsets. Lost Parcel Detective combines a picture with a distinct route; changing only option order is not counted as a new round. Existing saved picture contexts and media remain reusable. These are deliberately reusable scenes with different tasks, not ten new images.

## Fresh runs and recent context

`services/content_variation.py` provides the shared editorial request used by vocabulary games, radio, generated Reading/Listening, Writing, Translation, Word Jumble and new vocabulary flashcards. Migration 062 stores at most 100 recent exposures per profile or guest in that workspace. Requests include at most twelve short recent examples, recent encountered lemmas, a fresh seed, and a suggested situation/purpose. The suggestion is subordinate to the requested topic, level and communicative objective. Ownership identifiers are removed before provider calls and learner projections.

The existing provider call receives this context; there is no extra novelty-model call or automatic retry for a repeated result. Normalized exact recent text is rejected, including case, punctuation and ё/е-only changes. This is not semantic equivalence detection: the prompt asks for a meaningfully different situation rather than renamed actors, but human language-quality review remains necessary. Text-game sentences are fresh for a new run; saved sessions, retries of successful preparation stages, source-derived study cards and published curriculum tasks retain their frozen wording. New translation preparation cannot silently reopen an existing exact translation task or overwrite its draft.

Word Jumble prefers familiar words absent from the learner's last ten sets. If a small library would repeat a complete set, the existing word generator keeps the familiar majority and adds one new word; sparse libraries can still need more discoveries. Budget denial is never treated as a content-repair retry. Generated task and media calls remain subject to the existing hosted rate/spend policy.

Editorial history is noncanonical and is deliberately discarded during account import. Pending imported generation rebinds its editorial history to the verified receiving owner. Submitted responses, curriculum contracts, saved content and media are not rewritten by this history.

Pictures should depict a useful situation, action or object. They are not an automatic requirement just because another activity happens to use them. Additional Listen actions can reuse or prepare the exact saved Russian wording through the existing media service. They do not regenerate the text.

## Introducing one new word

`services/game_vocabulary_discovery.py` supplies `generate_discovery`. The existing configured flashcard text model receives the known lemmas, familiar contextual examples, selected options and a variation seed. One structured response contains:

- A dictionary lemma and its exact declined or conjugated surface form.
- One short Russian sentence containing that form once.
- The complete English sentence translation and the form’s meaning in that example.
- Part of speech and grammatical tags, plus an optional contextual note.

The surrounding language should be familiar or ordinary for the selected difficulty. A new meaning is taught in a sentence, not appended as a universal English definition on a lemma. The model must respect Russian agreement, case government, aspect and conjugation.

Before an example enters a game, the service checks that the lemma is absent from the known and selected sets, that the form and grammatical tags have a compatible dictionary analysis, and that the surface occurs exactly once in the Russian sentence. A new example cannot repeat a familiar example’s Russian sentence or English translation; choosing a new target inside the same sentence must not produce indistinguishable matching choices. The service also runs the existing contextual-card pack validator in memory. There is no native-card publication or database vocabulary insertion at this stage.

Structured output constrains the response shape, not the truth of a translation or the quality of a sentence. Dictionary validation checks possible morphology; it cannot prove that a model chose the right case for the sentence. Real generated examples therefore still need continued language-quality evaluation. The schema follows the existing provider’s [Structured Outputs interface](https://developers.openai.com/api/docs/guides/structured-outputs); this feature changes neither the configured model nor credentials.

Each call makes at most one provider attempt. Refusal, malformed output, unsupported morphology or a repeated known word leaves the saved stage failed with a retry action. The durable preparation service retains successful earlier stages and controls explicit retries. It does not hide a second billed generation inside the helper.

## Radio is listening comprehension

Post Office Radio generates a short, coherent programme rather than reading unrelated flashcard sentences. Its prompt asks for roughly 110–140 Russian words: a presenter’s greeting, one local-interest item, concrete details and a natural ending. Examples include a community event, cultural report or weather-and-outing report. The programme uses familiar words in whatever inflections its sentences require and introduces two to four useful new words.

Four Russian questions test the main idea and details actually stated in the programme. Each has one intended answer, plausible alternatives and a saved supporting quotation. A question’s English help translates its task without revealing the answer. The Russian transcript is support the learner explicitly requests, not hidden answer text placed in the initial page.

The complete recording belongs to the saved broadcast. It is not assembled from vocabulary-card audio, and pictures are not part of preparation. The saved transcript supports replay, feedback and word lookup after the exercise. New word references retain their exact broadcast sentence, contextual translation and grammatical metadata; an unrelated old card sentence must not be presented as its translation.

Listen receipts, transcript use and hints remain attached to the session. Listening evidence describes supported comprehension; it does not certify pronunciation, spontaneous speaking or general fluency. The existing rewards and completion rules continue to apply.

## Looking up and saving words

The word helpers share the existing relational vocabulary and lexical resolver. They do not create another word store or depend on a Google Drive sync completing first. Existing Reading routes remain unchanged.

After the permitted activity stage, a Russian transcript word or completed-game word can be selected. The server checks that its exact surface actually occurs in the saved activity before returning a lookup. The response includes its sentence, dictionary link, possible lemma/part-of-speech readings and whether each reading is already in the vocabulary. A saved contextual reference can also supply its English meaning and full sentence translation. An arbitrary transcript word has no fabricated translation simply because the user clicked it.

Homographs remain explicit. For example, **печь** can identify a noun or an infinitive; the learner chooses that lexical reading before Add. A form with several possible cases within one lexeme does not require the learner to guess a grammatical case in a modal. The helper reports only shared dictionary features and stores valid form readings without claiming that an unresolved case was established from context.

Only **Add to vocabulary** writes a lemma and its linked forms through the existing `LessonCards.resolve` / `_game_word` path. Repeated adds reuse existing records, including older lowercase part-of-speech labels. No permanent English field is added to `words`; contextual meanings remain with the activity example. Saving vocabulary does not generate flashcards, increment card counts, change a review schedule or touch Anki.

When the saved example has a validated, unambiguous grammatical reading, Add also associates its context and prepared media with the canonical form in the same owner’s existing game cache. Future picture selections and explicit saved study can reuse them; new text-game runs request fresh contexts. It preserves the completed game and original source record, does not replace a newer canonical cache entry, and creates no association for another profile or guest. An unresolved case reading is not cached as if the sentence had established that case.

### Interfaces

| Interface | Behaviour |
|---|---|
| `generate_discovery(provider, known_lemmas, familiar_records, options, seed)` | Return one validated contextual record; no database writes |
| `read_word(conn, content, word)` | Resolve a word occurring in frozen content; no paid calls or writes |
| `save_word(conn, content, word, lemma, pos=None, *, profile_id=None, guest_token=None)` | Explicitly save the selected dictionary reading; associate validated context within the authorized owner’s cache |
| `GET /api/v1/games/sessions/<id>/words?word=<surface>` | Owned-session lookup at the permitted activity stage |
| `POST /api/v1/games/sessions/<id>/words` with `{word, lemma, pos?}` | Owned-session explicit Add; a POS choice distinguishes lexical homographs |

Routes enforce profile/guest ownership, progression and mutation checks before calling these helpers. A word lookup never accepts arbitrary text for generation or speech synthesis. Provider failures use generic messages; credentials and raw provider exceptions are not returned.

## Checks

`tests/test_game_vocabulary_discovery.py` uses a fake provider and an isolated database. It covers one-call generation, exact declensions and conjugations, novelty, rejected morphology, repeated or missing forms, sanitized provider failures, read-only lookup, idempotent Add, lowercase POS compatibility, noun/verb homographs, unresolved case readings and rejected words outside the saved content. It also checks that an old card’s contextual meaning cannot be substituted for a different broadcast sentence.

These checks verify the contract and lexical behaviour. They do not replace listening to generated recordings, reviewing question ambiguity or evaluating sentence quality with real learners.

`tests/test_content_variation.py` checks profile/guest separation, bounded history, exact-repeat rejection, idempotent generation identities, migration 062 upgrading an existing database by itself, ten meaningful rounds with four images, and novelty context/repeat rejection in ordinary generators. The game, radio, flashcard, Translation and Word Jumble route suites exercise saved originals, unsaved discoveries, failed preparations and budget-denied calls through the existing application paths. These checks use provider stubs; no live language-quality or cost measurements are implied.
