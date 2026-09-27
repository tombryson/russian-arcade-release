# Lessons companion: first implementation

Implemented 11 September 2026. This preserves historical lesson material and builds a complete, resumable practice workflow. It does not complete the later activity integrations.

## The learner flow

`/lessons` opens a saved library with **Continue lesson** and a collapsed **Add lesson** form. A lesson has three sections:

1. **Get ready:** a bilingual title, a short introduction, three learning objectives, preparation advice and selected vocabulary in its original context.
2. **Read & notes:** the original page, including its annotations; page navigation; **We reached here** to remember a place. Extracted text, handwriting and uncertain details are available in a disclosure beneath the page.
3. **Practise:** six exercises, two per objective, presented one at a time. Hints are optional. Answers autosave, checking gives brief grammatical/contextual feedback, and **Next exercise** continues the session. Earlier attempts remain available. A possible answer appears only after a completed check.

Feedback distinguishes a correct answer, an answer needing revision and an uncertain assessment. Six checked exercises mean the learner has worked through the practice; they do not establish mastery or a calibrated score. There are no new account, approval or PIN steps in personal mode.

An exact repeat upload opens the existing lesson version. **Upload updated notes** explicitly attaches changed material to the same lesson. Versions preserve earlier questions, answers and files. A different filename or similar title alone does not establish identity: fuzzy matching and a cross-library match suggestion are not implemented.

## What changed technically

The existing Flask/Jinja/HTMX shell remains. `blueprints/lessons.py` owns the routes. `lesson_companion.py` coordinates persistence, preparation and checking; `lesson_files.py` validates and renders originals; `lesson_ai.py` defines the model contracts. The small `lessons.js` module enhances ordinary forms with autosave, polling and save-before-navigation. Legacy JSON is read through `lesson_service.py` without rewriting it.

Migration **015** adds the following beside the existing `lessons` table:

| Records | Purpose |
| --- | --- |
| Files, revisions and pages | Immutable originals, ordered versions, annotated page images and page identity |
| Extraction cache | Reuse unchanged page analysis for the same policy/model |
| Plans and tasks | One validated task set per version, with application-assigned identifiers |
| Drafts and attempts | Individual answers, optimistic draft revisions, durable checking history |
| Progress | Reading bookmark and current exercise using the existing learner profile |

Files live in `lesson-assets/` alongside the selected SQLite database, under SHA-256 names. SQLite stores references and provenance; it does not contain PDF/image blobs. PDF rendering retains annotations. A second render without annotations provides a base-page fingerprint. A unique base-page match can carry a bookmark across page reordering or changed handwriting. Ambiguous or substantially changed pages fall back to page one; handwriting is never interpreted as a completion mark.

The annotated page fingerprint identifies the extraction cache. A revised document reuses unchanged pages, reads changed pages and creates a new complete plan. Old task IDs, drafts and checks are retained with their original version. This is page-level reuse, not region-level comparison or semantic document alignment.

Preparation runs in a bounded local background thread pool, with persisted stages, leases and explicit retry after interruption. It does not depend on keeping the browser open. Expired jobs show **Retry preparation**; the app does not silently start all historical queued lessons on launch. This local worker should become an external worker before multi-instance hosting.

## Model and evidence contracts

Lessons uses dedicated settings: **`OPENAI_MODEL_LESSONS=gpt-6-astra`** and **`OPENAI_LESSONS_REASONING_EFFORT=low`**, through the OpenAI Responses API with strict JSON schemas and `store=False`. Other activity model settings are unchanged. Extraction receives up to four rendered pages per call, with printed text, handwritten notes and uncertainty kept separate. Notes have unknown authorship unless the document explicitly establishes it.

Preparation receives the extracted lesson and a bounded vocabulary sample. A separate model pass checks the exercise plan. Application validation then requires three objectives, six exercises and exact source quotations for every exercise. Vocabulary keeps its surface form, lemma, sentence and contextual explanation; an unambiguous exact lemma match may link to an existing word. It does not assign morphological tags from spelling, insert words/forms or add a canonical English translation field.

Answer checking receives the saved task, its rubric, relevant source pages and recent answers. Corrections must quote an exact span of the submitted answer. The answer is saved before the provider call. Failed calls keep the draft and a retryable attempt; command IDs prevent the same submitted request from being recorded twice. Concurrent draft changes cause a visible conflict instead of overwriting the newer draft.

These checks establish format and traceability. They cannot prove that an AI transcription, interpretation or grammar judgement is correct. The original annotated page remains the reference. The module does not grade handwriting, infer tutor approval, invent missing audio or automatically repair the learner's source text.

## Historical compatibility

Existing saved lesson documents are copied into managed storage without calling AI on their contents. Original lesson rows and answer JSON are unchanged. Both historical `{question, answer}` and `{id, prompt}` formats are readable, with unique display IDs.

Old generated exercises and responses are retained under **Earlier exercises & answers**. They are a read-only record: the old marking endpoint no longer assesses them without source analysis. **Prepare practice** produces the new validated exercise set. Existing lesson and original-file URLs remain available.

## Verification and the Siberia example

The supplied *Народы Сибири* document is the first prepared lesson. Its original twenty pages, including visible annotations, were rendered and read. The old text-only extraction returned just 213 characters. The new lesson includes plural prepositional agreement, reading comprehension and possessive reference, with six source-linked tasks.

The pilot's displayed title, introduction and objective wording were edited for clarity after generation; its task prompts, rubrics, source quotations and original files were retained. The original generated plan is saved privately for comparison. This is a curated pilot, not a claim that every generated phrase is ready without review.

Verification included:

- Four live Astra grammar fixtures: correct/incorrect case agreement and correct/incorrect possessive reference. All four produced the expected outcome. These are narrow quality checks, not a general accuracy benchmark.
- Browser checks in an isolated restored copy: draft save/reload, actual incorrect-answer feedback, next exercise, annotated image display and a persistent page-16 bookmark.
- Backup and restore including 25 original/page assets; original-file access works after relocation.
- Automated checks for duplicate uploads, changed/reordered pages, cache reuse, interrupted preparation, stale drafts, answer retries, escaping, ownership, CSRF and real PDF ink rendering.
- Four browser-script tests covering serialized draft saves, draft conflicts before grading, provider failure after saving and failed bookmarks.

## Flashcards and the next integrations

The **Flashcards** tab lets learners tap Russian words on the original page through OCR and save them to **Pending cards**. Creating cards uses those exact inflected targets, with pictures, audio and source links. Migration 016 connects the cards to the existing vocabulary library and scheduler; 017 persists word selections and OCR coordinates. Migrations 018–019 add stable image regions and remembered corrections. Unclear readings show the source crop and suggestions; a drawn box can recover missed words. See [lesson-driven practice](lesson-driven-practice.md) and [OCR corrections](lesson-ocr-corrections.md) for implementation, recovery behaviour and remaining limits.

Next: create saved writing tasks from a lesson section; generalise speaking scenarios beyond the café; then add targeted follow-up, tutor recap and a mixed final review. Completion coins need an explicit, idempotent completion rule. These later features are not exposed as working controls yet.

See [operations](operations.md#lesson-companion) for configuration, import and recovery commands.
