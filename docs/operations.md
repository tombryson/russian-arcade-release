# Local operation and data recovery

## Data locations

`VOCAB_DB_PATH` selects the learning database; its default remains `flask_vocab_app/vocab.db` for existing installations. Relative environment paths resolve from the repository root. The root `vocab.db` and the externally archived backend database contain different historical data and must not replace the canonical database blindly.

Use separate paths for development database, sessions, uploads, generated media, and Anki media. `.env.example` documents their overrides. Generated media and uploads are served through configured directories. Credentials, OAuth tokens, caches, databases, media, uploads, and virtual environments remain local and ignored by Git.

When cloning an existing database into a development instance, copy its referenced application media into that instance's `APP_MEDIA_DIR` as well. Saved stories store `/static/media/<filename>` URLs; the route resolves those names exclusively against `APP_MEDIA_DIR`. Copying SQLite alone leaves images and audio returning 404 even though the original files still exist. Preserve filenames, check hashes before replacing any existing file, and verify saved image URLs plus audio range requests through the target server. Story titles and their translations are independent of these filenames. Native flashcard assets use a separate store and do not supply legacy story media.

The application is still local first, with personal use by default and optional household profiles. Remote hosting and a production authentication/deployment model remain separate work. New learning and lesson mutations have CSRF protection; this is not a completed security migration of every historical route. The default development secret is suitable only for a local development session; configure a real session secret for personal use.

## Upgrade

1. Stop writes from old application processes and maintenance scripts.
2. Preserve the canonical database and its media/uploads. If SQLite WAL files exist, use SQLite's backup API rather than copying only the main file.
3. Install the dependency lock into a fresh Python 3.12 environment.
4. Check the selected path with `db-status`, then run `db-upgrade`.
5. Start the app and run its route smoke checks.

`db-upgrade` makes a sibling `.pre-migration-<timestamp>.bak` SQLite backup before pending migrations on an existing database. Migrations run transactionally, retain existing table contents, and reject incompatible schemas. They never merge the three historical databases. Re-running an up-to-date migration is a no-op.

Sync also creates a timestamped database backup before importing, and retains a run summary. Database backups do not include Drive or local media. Back up those separately. The repository cleanup removed files from Git's index only; it did not delete the local files or rewrite existing Git history.

## Restore

Stop the app before restoring. Preserve the failed/current database for diagnosis. With no open connections, remove or move stale WAL/SHM companions together with that database, then copy a verified database backup into the configured location. Restore corresponding media/uploads where needed. Run `db-status` and SQLite integrity checks before resuming; use the application version compatible with the backup, or upgrade it explicitly.

## Reading model and story titles

Story generation and preparation of pasted passages use `OPENAI_MODEL_STORY=gpt-6-astra` and `OPENAI_STORY_REASONING_EFFORT=low` by default. These are separate from `OPENAI_MODEL_HIGH` and `OPENAI_MODEL_FAST`; assessment and other activities retain their existing settings. Restart the app after changing configuration. A configured OpenAI API key and access to the chosen model are required for live generation. The [GPT-6 Astra model documentation](https://developers.openai.com/api/docs/models/gpt-6-astra) describes supported reasoning levels and APIs.

Reading uses the Responses API with a strict JSON schema: Russian `title`, English `title_en`, Russian `text`, and exactly five Russian `questions`. Both titles must be nonempty plain text of at most 100 characters, naming the same subject or event. For pasted passages, the model supplies both titles and questions, and the application keeps the supplied passage. Missing titles, incomplete responses and refusals fail preparation rather than becoming excerpts. Saving, checking answers and adding questions preserve both titles; an older open form cannot rename an existing saved story. The selected record ID is retained when multiple saved copies share the same text.

The library and reader heading use the selected interface language. The original Russian title remains in `saved_stories.title`; English titles are stored separately in `story_title_translations`, added by migration 005. Language switching never translates or rewrites the story itself and makes no provider call. Older databases can still be read before migration; records without an English translation fall back to the original title with its Russian language annotation. Backfill those records with the command below.

Existing titles can be replaced with an authored, reviewed plan. This is an explicit operation, separate from `db-upgrade`; it does not generate content. Russian plans only update the original title. English plans create the translation table if absent, using the same idempotent migration 005 definition, without applying unrelated pending migrations. A later `db-upgrade` remains safe. Keep plans under ignored `instance/` because their titles and identifiers belong to the household's library. A plan has this shape, with real values from the selected database:

```json
{
  "version": 1,
  "stories": [
    {
      "id": 123,
      "expected_title": "Old title",
      "text_sha256": "SHA-256 of the full stored text encoded as UTF-8",
      "title": "A reviewed Russian title"
    }
  ]
}
```

Stop other writers, confirm `VOCAB_DB_PATH`, then preview and apply:

```sh
python -m flask --app flask_vocab_app/app.py:create_app story-titles --plan instance/story-titles.json
python -m flask --app flask_vocab_app/app.py:create_app story-titles --plan instance/story-titles.json --apply
```

For an English plan, use `--language en` for both preview and apply. Its `title` contains the English title and `expected_title` contains the current English translation, or `""` when none exists. The default `--language ru` retains the original command's behaviour. In a new installation, `db-upgrade` creates the translation table before story generation is used; existing local installations can apply the English backfill directly.

The command validates every entry's ID, full-text hash and expected title before writing. Apply creates a consistent sibling SQLite backup named `.pre-migration-story-titles-<timestamp>.bak`, then applies the specified titles in one transaction. Repeating the same plan makes no changes. Text, questions, answers, scores, assets and duplicate copies are preserved. To reverse a change from a previous nonempty title while retaining subsequent learning, create a reverse plan with the old/new titles exchanged and the same language, IDs and text hashes. The command does not remove translations. For a full database restore, use the procedure above; a full restore also removes changes made after the backup.

## Known integration limits

Drive synchronization still uses a text-file read/modify/write protocol; simultaneous edits can race. Failed enrichment is visible in sync summaries but has no dedicated retry worker yet. OAuth token storage still uses the existing local serialized format; do not import tokens from untrusted repositories. Historically tracked credentials require revocation/rotation verification outside Git cleanup. No credential rotation or history rewrite is performed automatically.

The Git checkpoint on 8 September 2026 also removed six hard-coded Yandex/ElevenLabs credential literals from four historical scripts. Those scripts now require `YANDEX_API_KEY` and, where applicable, `ELEVENLABS_API_KEY` in the shell environment. This does not remove the old values from existing Git history or rotate them at the providers. The scripts remain historical utilities and should be reviewed before use.

## Sentence practice drafts and checks

Run `db-upgrade` before using the updated **Word Jumble** activity. Migration 006 adds `word_jumble_drafts` and `word_jumble_attempts`; old game rows are retained and their existing feedback is copied once into legacy attempts. Unknown historical score scales and check dates remain unknown. The normal migration command backs up an existing database before applying any pending migrations; its backup uses SQLite's DELETE journal mode so it can be restored as one file.

Migration 020 adds optional structured tutor feedback to each Word Jumble attempt. New checks contain a personal response, up to three explained corrections, an optional polished sentence with separate phrasing advice, and an optional extension. Necessary corrections quote the learner's exact text; malformed or unrelated corrections cannot be saved. The existing four-point rubric is unchanged. Previous answers, scores and feedback are retained; older structured comments are displayed as connected paragraphs. The readable `feedback` summary remains available for exports and older readers. Apply the migration before starting the updated server; it does not regenerate past assessments.

Word selection uses matching vocabulary first: 3 words for Easy, 4 for Intermediate and 5 for Expert. If the library is short, the same text provider supplies the missing words for the selected topic and level. New words are validated for count, Cyrillic spelling and duplicates before the complete set is saved with the game. These additions are exercise material; they do not bypass the separate lemma/form ingestion pipeline or sync to Drive. Existing saved games keep their original words. Generation failures preserve the selected options and allow a retry without saving a partial activity. Selection remains offline when the library already has enough words, and draft saving always works without a provider.

**Check sentence** and word top-ups use `OPENAI_MODEL_FAST` (`gpt-5-mini`) through the Responses API, with strict output schemas and `store=False`. Sentence checking uses medium reasoning following linguistic test failures at low reasoning; word selection stays on low. The reading generation setting is separate and remains Astra low. API behaviour is documented in the [Responses structured-output guide](https://developers.openai.com/api/docs/guides/structured-outputs). Configure `OPENAI_API_KEY` for live generation/checks; restarting Flask is required after configuration changes. The test suite uses mock responses and never spends provider credits.

Tutor feedback should match the scale of the answer: a brief encouraging comment and one plain-language explanation for a small mistake, a more personal paragraph for richer writing. Grammar terms must describe the word's role in the actual sentence. English feedback uses English explanations with Russian examples. A missing final full stop is not a separate error or grading penalty. Mechanically redundant whole-sentence corrections are removed from new feedback; previous assessments remain unchanged. Explanations still come from a model and require representative linguistic checks, beyond JSON validation.

Drafts are saved only when **Save draft** or a successful **Check sentence** completes. Closing or changing activities with unsaved edits triggers a browser warning. A failed check leaves writing in the editor and does not record a grade. If another tab has saved a newer draft, the stale tab receives a conflict message: copy any changes you want to retain, then reload. Saving again with the stale revision cannot overwrite the newer draft. The activity preserves past checks for revision but is not yet linked to household learner rewards.

## Translation practice

Run `db-upgrade` before using the updated **Translate a sentence** activity at `/sentences`. Migration 007 adds translation drafts and check history while preserving all existing sentences, scores and reward records. Old translation answers were not stored, so these records start without invented answers or check history. Existing legacy reward events still prevent repeated awards. The normal upgrade creates a database backup before applying the migration.

Choose a saved English sentence, write its meaning in Russian, then **Save draft** or **Check translation**. A successful check saves the submitted answer, feedback and existing coin/Elo outcome together. Saving a draft does not award progress. The editor stays available for revision; later edits made while a request is running remain unsaved until explicitly saved. Failed checks leave the answer in the editor without recording a score. The same stale-tab protection and copy/reload recovery described above apply.

Saved practice, draft saving and adding a Russian/English pair to the library work without AI. Creating a new pair, checking a translation or filling a missing English translation uses `OPENAI_MODEL_FAST` (`gpt-5-mini`) through Responses with low reasoning, strict structured output and `store=False`. Reading preparation continues to use Astra low independently. Configure `OPENAI_API_KEY` and restart Flask for live generation/checking. Provider failures display an error instead of returning an unrelated fallback sentence or a fabricated grade.

The reference translation becomes available after a check. Preparing pronunciation is a separate optional request using the existing ElevenLabs configuration; a missing key or unavailable audio does not undo saved feedback. Existing audio remains playable from the reference library.

Generation now requires `POST /sentence/generate` with `topic` and `difficulty` (1–5). Old GET generation links redirect to the activity without generating content. Save/check clients must post `sentence_id`, `revision` and `user_response` to `/sentence/save` or `/sentence/assess`; the server loads the authoritative prompt and level. Old forms that submit reference text and a client-supplied grade cannot create a saved sentence or reward. Direct saved-reference URLs remain available, and `/sentences/saved?fetch_all=true` retains its JSON topic string list when JSON is requested.

## Writing drafts and feedback

Run `db-upgrade` for migration 008 before using the updated Writing page. It adds `writing_details`, `writing_drafts` and `writing_attempts`. Original task rows remain intact; existing answers become drafts, and any historical feedback is copied once. Unknown check dates and invalid historical score scales remain undisplayed. Generated tasks now require separate Russian/English titles and bilingual instructions. Historical records without metadata use their readable topic as a fallback label and retain Russian instructions; migration does not call AI to translate them.

Writing opens with the most recent task and a **Continue writing** action. The saved library and creation controls are disclosures. New tasks offer A1/A2/B1 language levels and independent targets of approximately 30 or 100 words. The stored targets of older exercises remain unchanged. Targets guide feedback; they never prevent checking a shorter draft. The counter is a writing aid, not an assessment of vocabulary coverage. Inflected Russian words are judged by the tutor, not by substring badges.

**Save draft** updates the selected draft rather than inserting another exercise. **Check writing** saves the submitted version and validated feedback together, preserving previous checks. Both support complete paragraphs and punctuation up to 20,000 characters. Checks reject stale revisions before and after provider work. Failed checks retain the editor but do not save a new grade or claim that unsaved edits were saved. Use Save draft separately, or copy your writing before reloading a stale tab. There is no autosave.

The optional timer starts only when requested. It can pause/reset, never disables the editor, and resets when leaving the task. Its elapsed time is not stored as learning progress. The timer does not submit or assess writing automatically.

Loading and saving existing writing require no provider. Preparation and assessment use `OPENAI_MODEL_FAST` (`gpt-5-mini`) through Responses with low reasoning, strict structured output and `store=False`; the separate reading model remains Astra low. Configure `OPENAI_API_KEY` and restart Flask for live checks. Writing feedback uses the chosen UI language, with a short Russian example; old feedback keeps its original language. No new coin or Elo policy is introduced by this uplift.

Compatibility URLs `/writing`, `/writing/load/<id>`, `/writing/generate`, `/writing/save` and `/writing/assess` remain. Generation is a POST with `topic`, `difficulty` (`beginner`, `intermediate`, `advanced`) and `target_words` (`30` or `100`). Save/check clients now post `exercise_id`, `revision` and `user_response`; old base64 task fields cannot create or redefine a task. Successful native submissions redirect to the saved task; JSON requests return a destination or the new revision/feedback. Direct, full-shell and legacy inner-fragment reads remain supported.

## Lesson companion

Run `db-upgrade` before using the versioned `/lessons` workflow. Migration 015 adds lesson continuity; 016 links lesson card requests to native generation and source pages; 017 adds OCR caches and pending word selections. Migrations 018–019 anchor selections to source-image regions and distinguish confirmed readings from earlier captures. Migration 017 rebuilds the request table to include the exact selection in request identity, copying existing requests and checking foreign keys before commit. Upgrades receive the normal pre-migration database backup. Historical lessons and answers remain unchanged. Existing source URLs resolve both configured uploads and the historical app upload directory. See the [lesson guide](lessons-companion.md) and [lesson flashcard integration](lesson-driven-practice.md) for shipped behaviour and later writing, conversation, recap and reward work.

Word selection needs the `tesseract` executable and Russian/English language data (`rus` and `eng`). `LESSON_OCR_BINARY` overrides the executable; `LESSON_OCR_DATA_DIR` overrides the language-data directory. By default, a directory named `ocr-data` beside the configured database is used when present; otherwise Tesseract uses its installed data. Run `tesseract --list-langs` (with `--tessdata-dir <directory>` when using a custom directory) to check both languages. See the official [Tesseract data installation guide](https://tesseract-ocr.github.io/tessdoc/Data-Files.html) and [tessdata_fast models](https://github.com/tesseract-ocr/tessdata_fast). The preview has local copies beside its database; these ignored runtime files must be installed separately on another machine or a future host. OCR runs locally, with a 45-second page timeout and two concurrent jobs per application process. Coordinate results are cached by source-image digest and OCR policy; selecting a word makes no AI generation call.

Lesson card preparation stores its model output before saving cards. Reopen an interrupted request from the lesson's Flashcards tab. A live preparation lease expires after five minutes; a concurrent retry waits for that lease rather than creating another batch. Missing card media is retried from the native generation page without replacing text or reviews. Keep the database and existing lesson/native asset directories together when backing up or moving the application.

The dedicated settings are `OPENAI_MODEL_LESSONS=gpt-6-astra`, `OPENAI_LESSONS_REASONING_EFFORT=low` and `LESSON_PDF_RENDERER=pdftoppm`. They use the existing `OPENAI_API_KEY`; no new provider key is required. Reading saved pages, saving drafts and bookmarks, opening originals and importing files without preparation work without an AI call. Preparation and answer checking call the configured lesson model. Other model settings remain independent.

PDF preparation requires Poppler's `pdftoppm` on PATH, or an absolute executable path in `LESSON_PDF_RENDERER`. Install Poppler in a new deployment image before enabling PDF preparation. PDF, PNG, JPEG and WebP are accepted: 1–5 files, at most 40 pages in total, and a 25 MB overall web request limit. Originals are stored unchanged in `lesson-assets/` beside the selected database; rendered annotated pages are stored there too. Neither credentials nor originals are rewritten during preparation.

Choose the intended database with `VOCAB_DB_PATH` and check `db-status` before these commands. From the repository root, using the project virtual environment:

```sh
.venv/bin/python -m flask --app flask_vocab_app/app.py:create_app lessons import '/absolute/path/lesson.pdf' --title 'My tutor lesson'
.venv/bin/python -m flask --app flask_vocab_app/app.py:create_app lessons import '/absolute/path/lesson.pdf' --prepare
.venv/bin/python -m flask --app flask_vocab_app/app.py:create_app lessons import '/absolute/path/updated.pdf' --lesson-id LESSON_ID --prepare
.venv/bin/python -m flask --app flask_vocab_app/app.py:create_app lessons adopt-legacy
.venv/bin/python -m flask --app flask_vocab_app/app.py:create_app word-post backup instance/learning-backup-YYYYMMDD
```

`--prepare` explicitly calls the model; importing the same ordered files reuses the existing version. `adopt-legacy` copies original sources into managed storage without preparing them. It reports missing files rather than replacing them. A ready version is immutable: uploading changed material creates another version, while retrying the same ready version does not regenerate questions.

The local preparation worker records each stage and page extraction. Closing the browser does not cancel it. After a process interruption, allow its five-minute lease to expire and use **Retry preparation**. Completed page extractions are reused. Answer checks have a three-minute lease and preserve the submitted draft on failure. No background startup sweep spends credits on old queued lessons. A multi-instance deployment needs a dedicated worker in place of the current bounded thread pool.

Drafts autosave after typing and before an exercise check or lesson navigation. Conflicting tabs receive an error; copy the unsaved answer before reloading. Answers are never silently overwritten. Updated notes retain old task IDs and attempts with their original revision; they do not carry those checks forward as completion of new questions. A bookmark transfers only when the original base page has a unique match.

The learning backup now includes lesson originals and page assets, validates checksums, and makes historical file references portable **inside the backup database only**. Let preparation and checking finish before creating a backup. Restore its `lesson-assets/` directory alongside its `vocab.db`, plus the other asset directories documented by the manifest. Keep ordinary legacy story media, Anki and Drive backups separately. Source lesson documents and private test records should remain outside Git.

## Vocabulary card coverage

The `/vocab` library now projects native counts from saved card identities, independently of the historical Anki export counters. No schema migration or counter backfill is required. `words.count` and `forms.count` retain their existing Anki meaning; native generation, publication, withdrawal and retirement are reflected by the inventory query. See [the vocabulary implementation guide](vocabulary-library.md) for field definitions and validation. The word-specific flashcard route requires rebuilding the frontend and copying the build to the configured `WORD_POST_DIST_DIR` when the preview uses a separate output directory.

A disk-full or database I/O failure in the shared learning transaction layer returns HTTP 503 with code `storage_unavailable`. Free disk space, then retry the same action. Do not remove SQLite WAL/SHM files from a running application. After an interrupted write, inspect database integrity and preserve its files before attempting recovery.

Lesson OCR corrections and area selection are described in the [correction guide](lesson-ocr-corrections.md). These use the installed fast Russian OCR model; the slower model in the local comparison is not required.
