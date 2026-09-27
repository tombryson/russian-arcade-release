# Lessons as a source of practice

Status: **the lesson → native flashcards integration is implemented**. The [journey games](journey-games.md) also accept eligible selected lesson words as a source for contextual 5/10-round practice, sharing prepared pictures and Russian audio. Writing, conversation and adaptive follow-up below remain the next stages, not shipped features.

## Current flow: highlight → pending cards → create

Open a prepared lesson and choose **Flashcards**, or follow **Select words for flashcards** from **Read & notes**. Tap individual Russian words directly on the original page image. Local Tesseract OCR supplies positioned word targets, including for scanned PDFs. Uncertain readings open a crop with correction suggestions; **Select an area** recovers missed words. See [OCR corrections](lesson-ocr-corrections.md) for the workflow and recognition comparison. The highlight saves immediately into **Pending cards**, with its lesson revision, page, exact inflected form, surrounding text and original OCR reading. Navigate between pages or reload: selections remain saved. Remove a selection before generation, or expand **Context & reading** to correct a misread word. No sentence writing or card authoring is required.

Press **Create cards** when ready. Up to ten pending words are processed per batch; further selections remain pending (up to 100 per lesson). The existing lesson model prepares and independently checks cards for those specific occurrences. It cannot substitute another target. It uses the original complete printed sentence when suitable. For a heading, word list or exercise fragment it can write a new lesson-relevant example using the same selected form; the resulting card is labelled **New example**. This is not presented as a quotation from the PDF. Invalid readings are kept for correction rather than silently replacing the selected spelling or ending. Completed selections leave the pending tray and remain highlighted on the source page.

The app then checks each target against the source page and the Russian morphological dictionary. It links the exact inflected form to an existing lemma, or adds an unambiguous lemma/form pair to the vocabulary library. Existing vocabulary is retained; new entries start without an assigned difficulty. Translations stay on the individual card. The app does not add a canonical English translation column or claim that morphology can distinguish every homograph or meaning.

Cards reuse the existing native generation, image/audio jobs, editing, library counts and scheduler. Each lesson card needs a picture, target-form recording and sentence recording before it can enter practice. Media failures can be retried independently. Optional hints, English cues, answer reveal and Again / Hard / Good / Easy retain the existing player behaviour. Recordings and dictionary/source-page links are withheld from the cloze front.

The lesson's collection is available at `/#flashcards?lesson_id=<id>`. The same cards appear in the main collection, with source-page links, and review sessions retain a **Back to lesson** link. A lesson start no longer resumes an unrelated general-vocabulary session. The shared daily new-card allowance still applies.

Persistence uses migrations **016–019**:

- `lesson_card_requests`: selected revision, exact occurrence snapshots and selection fingerprint, page bounds, owner, saved model response, lease/retry state, batch and rejection report. Previous page-range requests remain valid.
- `lesson_card_targets`: stable identity for a lemma, grammatical form and sentence within a lesson; references the existing native generation item.
- `lesson_card_sources`: links each request and generation item to the original revision/page through real foreign keys.
- `lesson_ocr_pages`: word boxes cached by rendered image digest and OCR policy; raw OCR is retained separately from source-aligned spelling.
- `lesson_word_regions`: stable image coordinates independent of OCR token order, with captured readings and suggestions.
- `lesson_word_picks`: each learner's selected occurrence, region, confirmed reading and linked request/item. Removing a pending word only deselects it; it does not delete cards.

Repeating the same selection reopens its request; choosing different words on the same pages creates a distinct request. A later revision reuses matching card targets without resetting schedules, duplicating media or rewriting saved card text. Pending highlights remain attached to the original revision; they are not guessed onto shifted pages after an upload. A failed preparation can resume its saved response. **Recheck skipped words** reruns source/morphology validation and can append a recovered card to the existing batch; it does not ask the model to rewrite accepted cards. **Retry unfinished cards** and **Retry missing media** resume their respective stages. Removed cards remain removed when their source is encountered again. The old page-range POST remains for compatibility; its controls have been removed from the current lesson UI.

Implementation: `services/lesson_ocr.py`, `services/lesson_selection.py`, `services/lesson_cards.py`, `services/lesson_ai.py`, `services/card_generation.py`, `services/native_review.py`, `static/js/lesson_word_selection.js`, the lesson Flashcards tab, and the existing native UI. The configured lesson/text/speech/image models and voice-selection policy are reused without changing keys or model settings. See [operations](operations.md) for local OCR installation.

### Pilot and test coverage

The live pilot uses pages 20–25 of **Unusual Professions** and produced five clozes: «народной», «выставку», «писателя», «племени» and «заботятся», each with all three media files. A failed word recording was retried without rebuilding text. A finite verb initially rejected for an unsupported voice tag was recovered into the same batch; OpenCorpora does not supply voice tags for finite verbs. The exhibition image initially included the answer in a sign: it was replaced, and native image prompts now explicitly prohibit readable text. This prompt improves generation but is not an automated OCR guarantee.

Tests cover pending persistence/removal, request identity, unselected-word rejection, corrected readings, explicitly labelled new examples, access/CSRF, accent alignment, media readiness, lemma/form ownership and the existing review flow. Browser checks covered word placement on the actual scan, enlarged-page alignment, reload and cross-page persistence, and the narrow layout. OCR on page 24 found 177 selectable Russian tokens; 169 aligned to existing printed-text extraction. The count is an example from this page, not an accuracy guarantee.

### Deliberate limits of this stage

- Selection targets individual Russian words. A dragged box can recover missed regions, with resize handles and a correction view. Handwriting, faint text and joined words can still require a typed correction; phrase cards remain a later feature.
- Stress marks can resemble other glyphs. Source alignment repairs narrowly supported accent errors while preserving the source spelling, including ё. Unmatched endings and handwriting are not automatically corrected. The original scan and OCR reading remain available.
- New examples are labelled separately from original sentences. Dictionary checks and model review do not guarantee that every interpretation is correct; pending words and generated cards remain editable.
- Vocabulary capture includes the observed form, not a newly generated full paradigm. Existing forms and metadata are preserved; inherited topic labels can still need editing.
- Dictionary recognition supports contextual matching but does not prove that a sentence, translation or interpretation is correct. Cards remain editable and discardable.
- Lesson writing tasks, generalised conversation scenarios, targeted follow-ups, standalone vocabulary capture and completion coins have not been added in this stage.

## Product idea

A lesson supplies the language, situations and specific difficulties that make the other activities useful. The learner reads with a tutor, practises a small set of relevant cards, uses that language in a conversation or short piece of writing, and encounters it again later. Each activity remains available independently.

Let learners choose the language they want to revisit through highlights. Broader writing and conversation activities can draw on those selections and the lesson section they came from, rather than indiscriminately extracting unfamiliar words from the entire PDF.

## What the current application can actually supply

The inspected lesson is **Unusual Professions**, with 25 extracted pages in its current revision. Its contents cover several distinct areas: absence with «у … нет …», past and future absence, dates, museum descriptions and a reading passage about a linguist. The filename/title alone is a poor generation prompt.

The saved plan contains four vocabulary occurrences: «учёбы», «лингви́ст», «пле́мени» and «изуча́л», each with a lemma, source sentence, page and contextual meaning. They are a small model-selected sample, not a complete vocabulary inventory. Page 8 contains extensive handwritten work on endings; page 12 has date annotations and a homework note; page 20 marks the distinction between the museum noun and its dependent genitive phrase.

One saved exercise assessment distinguishes correct genitive endings from an incomplete possession/absence construction. That is a useful *specific follow-up signal*, not evidence that the learner needs every genitive ending taught again, or has mastered the case. Keep the submitted answer and assessment separate.

| Area | Existing foundation | Missing connection |
| --- | --- | --- |
| Lessons | Original files, revisions, OCR word selections, notes, tasks, drafts and attempts | Reuse selected occurrences as writing/conversation focus |
| Vocabulary | Lemmas, linked forms, grammatical tags, mnemonics, card counts and contextual lesson-card capture | Standalone capture without creating a card |
| Flashcards | Selected lesson occurrences, clozes, contextual translations, media, source links and shared native schedules | Deliberate variation across constructions and later follow-up |
| Journey games | Eight mechanics with selected lesson contexts, saved 5/10-round sets, cached pictures/audio and explicit native-card reuse | Full-page content adaptation, broader linguistic quality checks and calibrated skill evidence |
| Writing | Saved tasks, drafts, feedback and suggested vocabulary | Receive a saved lesson brief and return progress to its source lesson |
| Conversation | Saved scenarios per session, speech input and separate feedback | Generalise the currently fixed café scenario and café-specific instructions |

Relevant implementation boundaries: `services/lesson_companion.py`, `services/lesson_ai.py`, `services/card_generation.py`, `contracts/flashcards.py`, `services/writing_service.py`, `repositories/writing_repository.py`, `services/conversation_ai.py`, `services/conversation_service.py` and `services/live_conversation.py`.

## Practice that follows from this lesson

The following are proposed examples, not newly generated or saved learner activities.

| Lesson focus | Remember it | Use it |
| --- | --- | --- |
| Absence and possession | A contextual cloze targeting «велосипеда» in «У моего младшего брата нет горного […].» with English support. A separate short sentence-building exercise practises the whole «у … нет …» frame. | Discuss what someone needs for a trip and what they do not have. Follow with a short message explaining what to bring. |
| Agreement across a phrase | Vary one target at a time, then rebuild the entire adjective–noun phrase in a fresh sentence. | Describe what is missing from a room or local area, retaining adjective–noun agreement. |
| Dates | Contrast naming a calendar date with saying when an event happens. Keep the month and the question in view. | Arrange a meeting: the partner has one calendar and the learner another. Agree on a date, then write a confirmation. |
| Museum descriptions | Practise the changing form of «музей» while preserving «русской фотографии» as its dependent phrase. | Plan a museum visit, ask which exhibition is available and explain a change of plans to a friend. |
| Reading about a linguist | Revisit «изучал» and «племени» in the actual source sentence, with the correct contextual meanings. | Explain what the linguist studied to a partner who has not read the passage, then write a short summary. |

Three useful variations go beyond a standard “make cards” button:

1. **Try it somewhere new.** After an exercise needs revision, create one later task using the same construction in a different situation. Avoid repeatedly presenting the learner's exact answer as the only thing to memorise.
2. **Different information for each speaker.** Use museum timetables, appointments or missing supplies so that conversation requires asking, clarifying and deciding. A scenario needs an achievable purpose, not just a topic and a chat box.
3. **Prepare for the tutor.** Assemble a short recap of material studied, examples completed and questions the learner wants to ask. Uncertain readings and uncertain feedback remain questions, not attributed tutor corrections.

## Selecting useful language

Use three inputs separately: the printed material, annotations, and the learner's saved practice. A highlight is evidence of attention; it does not establish that a word is unknown. A handwritten answer is not automatically a correction, an instruction or a mark of completion. The current extraction stores prose descriptions of notes, not reliable region-level annotation identities or authorship.

Rank proposed practice by its connection to the selected section and objective, readable annotations, specific feedback and existing card coverage. An existing vocabulary entry means the word is in the library; it does not prove the learner knows every form or use. An existing review schedule says something about that card, not every sense of its lemma.

Store the occurrence as encountered: source revision/page, exact context, target span, surface form, possible lemma/form links and the focus being practised. Preserve printed stress marks in the source record. Normalisation can help retrieve candidates, but contextual grammar must resolve homographs and forms that share a spelling. Do not select the first matching form row.

Contextual English belongs to the occurrence/card. This integration does not need `translation_1`, `translation_2` or a universal English field on `words`.

Unambiguous new vocabulary can be captured through the existing enrichment workflow as part of generation. The learner should not need to enter sentences, translations and grammar by hand. Ambiguous items can be skipped with a concise explanation or offered for optional editing; they should not block a whole useful set. The UI can show which words are already in the library and which would be added.

## Flashcard contract

Start with source-sentence clozes targeting one exact occurrence. Provide English support sufficient to recover the intended meaning, and preserve the full sentence translation with the card. The front must not reveal the Russian target, its dictionary link or an answer-bearing recording. Mnemonics remain optional on click; dictionary links and word/example audio belong after reveal for these clozes. Picture, target-form audio and sentence audio use the existing media jobs and retry workflow.

New examples for the same construction are useful too, but must be identified as generated practice inspired by the lesson, rather than quotations from its pages. Save the original evidence and the generated example separately.

The current cloze contract can represent a single blank containing a phrase, but its vocabulary metadata and dictionary link describe one word/form. Do not misrepresent multiword agreement cards as fully integrated today. Initially use single-target clozes and the existing typed lesson exercises for whole-phrase production; add multiple linked targets only when that card type is implemented properly.

Reuse native card identities, collection filtering, media, Again/Hard/Good/Easy and scheduling. A lesson collection is a view over the same cards, not another copy of their schedules. Matching vocabulary alone must never substitute an unrelated example for the requested lesson sentence.

## A small interface addition

Within a selected lesson section, add **Practise this lesson**, with working actions introduced incrementally:

- **Flashcards:** proposed words/forms and a short focus description, then Generate. Created cards also appear in the main Flashcards library under this lesson.
- **Useful words:** original context, library status and an easy capture action.
- **Conversation:** a concrete situation and goal, then the existing speaking activity.
- **Writing:** a short purpose and relevant vocabulary, then the existing writing workspace.

Every resulting activity has a small source label and **Back to lesson** link. Reopening resumes the saved activity. Offer a next activity after feedback, but keep it optional. Do not display inactive promises for integrations that have not shipped.

## Persistence and generation

Keep the existing vocabulary, card and activity stores. Add a narrow integration layer around them:

- A persisted practice-set request records the lesson revision, selected pages/section, learner, selected focus, generation policy and retry state.
- Source occurrences retain evidence and optional vocabulary/form references. Link to existing lesson tasks and attempts where they motivated follow-up.
- Use typed relation tables with real foreign keys to cards, writing tasks and saved scenarios. The underlying activity remains the owner of its content, media and attempt history.

Generate from the cached extraction and the relevant vocabulary/attempts, not by sending the entire PDF for every card or conversation turn. Start with relational queries and bounded context; a vector database is not needed for this first integration.

Repeated clicks and interrupted generation must return the same request/result. Deduplicate by the learning target and context, not just lemma or a newly generated ID. Reuploading an annotated PDF retains existing cards, attempts and due dates. New notes can suggest an additional practice set; they do not silently rewrite published cards or retire useful earlier practice.

Validate and save text once, then resume missing media independently. Do not advertise a media-complete set until its required files exist. Content changes and repairs must respect the native distinction between stable card identity and immutable versions.

For speaking, first replace the fixed café policy with saved role, situation, goals, relevant facts and grammar focus. Passing museum text to the current café worker prompt will not create a coherent new activity. Keep unverified speech transcripts separate from confirmed learner errors when choosing subsequent remedial work.

## Implementation order and acceptance

1. **Lesson vocabulary → native clozes.** Add section selection, contextual matching, a source-aware generation adapter, lesson collections and return links. Pilot roughly five complete cards from one section. Acceptance: real source references, correct form ownership, context preserved, all three media assets, no answer leakage, existing-card counts, retry without duplication, and unchanged schedules after a repeated upload.
2. **Lesson writing.** Reuse the same selection to create one saved writing task. Acceptance: its instructions and feedback use the lesson's focus, its draft survives navigation, and it is discoverable in both Writing and the originating lesson.
3. **Lesson conversation.** Generalise scenario creation and both dialogue backends. Start with one purposeful museum or calendar scenario. Acceptance: the agent follows that role and goal, remembers conversation state, and keeps speech uncertainty out of asserted error records.
4. **Adaptive follow-up and recap.** Use saved outcomes to suggest a short later task and a tutor recap. Add completion rewards through the shared reward ledger when the completion rule is agreed. Generating content, reuploading notes and replaying the same completion must not mint repeated coins; counts of completed tasks must not be presented as demonstrated mastery.

The first release should prove this loop: **lesson section → complete contextual cards → study in the existing player → return to the lesson**, with one coherent source record throughout.
