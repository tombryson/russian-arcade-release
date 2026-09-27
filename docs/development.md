# Development

Python 3.12 is the supported baseline. The active app uses `pymorphy3`, the maintained successor to `pymorphy2`, so morphology works on this runtime. Existing database forms are not regenerated during upgrade. New captures use the pinned dictionary version. See the [upstream project](https://github.com/no-plagiarism/pymorphy3) for compatibility information.

`flask_vocab_app/requirements.txt` lists direct dependencies and compatibility constraints. `requirements.lock` pins the complete dependency graph with hashes. Install the lock file into a fresh virtual environment. All platforms use the patched cryptography release. On Intel macOS it builds from source and requires a recent Rust toolchain, Xcode command-line tools and OpenSSL headers. Do not downgrade it to obtain an older wheel.

To refresh the lock deliberately with uv:

```sh
uv pip compile --python-version 3.12 --universal --generate-hashes flask_vocab_app/requirements.txt -o flask_vocab_app/requirements.lock
```

The newly installed environment and test suite must pass after refreshing. Install `ffmpeg`, Poppler and Tesseract (including its Russian language data) to run the full media and OCR test suite. These are system packages; the Python lock does not install them. CI and the deployment image install them explicitly.

Run the suite from the root:

```sh
python -m unittest discover -s flask_vocab_app/tests -t flask_vocab_app -v
```

Use `tests.support.isolated_app` for app tests. It creates a migrated temporary database, optionally seeds three synthetic words, isolates file/session paths, blanks provider keys, and blocks external connections. Pass doubles such as `{'GoogleDriveService': fake_drive}` or `{'SentenceService': fake_sentences}`. Tests must not use the global configured database or existing OAuth files.

Migration tests exercise empty databases, adoption of a compatible legacy schema, rollback of incompatible schemas, and backup behavior. Sync tests exercise fresh mobile capture, inflection normalization, retries, failed imports, export failure, and database lock release before enrichment. Concurrent reward tests verify uniqueness of sentence awards.

Historical maintenance scripts have not all been converted to shared commands/configuration. Read them and use a copied database before running one. The supported entry points for setup are currently `db-upgrade`, `seed-demo`, `db-status`, and the Flask application factory.

## Preact interface

The UI package lives in `flask_vocab_app/ui`. Use Node 24 (24.20.0 is pinned in the root `.nvmrc`) and the committed npm lockfile:

```sh
nvm use
npm ci --prefix flask_vocab_app/ui
npm run build --prefix flask_vocab_app/ui
npm test --prefix flask_vocab_app/ui
WORD_POST_REQUIRE_BUILD=1 python -m unittest discover -s flask_vocab_app/tests -t flask_vocab_app -v
```

The build runs TypeScript checking, generates CSS from `ui/src/styles/tokens.json`, and emits hashed assets plus `.vite/manifest.json` in ignored `ui/dist/`. `tokens.json` is the only editable token authority. The generator is also available as `npm run tokens --prefix flask_vocab_app/ui`. Artwork is imported from `ui/src/assets`; Fontsource packages supply pinned Latin/Cyrillic fonts and the public directory supplies their OFL licences.

Flask serves the Preact interface at `/` in its own document. It loads bundled assets from `/post/assets/`, without the legacy Bootstrap or HTMX shell. Navigation between Preact and Jinja pages loads a new document. The integration follows [Vite's backend manifest contract](https://vite.dev/guide/backend-integration.html); there is no separate production frontend process.

The Anki generator is at `/tools/anki/`. Old `/post` and `/post/` links redirect to `/`, retaining query strings and activity fragments such as `#flashcards`. A missing or invalid UI build returns a 503 setup page at the homepage; the Anki route remains available subject to the configured access controls.

For iteration, run `npm run watch --prefix flask_vocab_app/ui` beside Flask. This watches production builds; **reload the browser after each successful build**. It does not provide HMR. Restart Flask for Python changes. Keep development output out of Git; rebuild from the lockfile on a fresh checkout.

Set `WORD_POST_CATALOGUE_ENABLED=1` before starting Flask to open `/post/catalogue`. The catalogue provides theme controls, a complete interactive preview, and sample feedback/empty/save-error/capture states. Those samples do not perform network operations. Keep the catalogue disabled for ordinary household use. `WORD_POST_ENABLED=false` disables the Preact interface and its asset routes on app restart. `WORD_POST_DIST_DIR` can select a prepared build directory.

Component tests cover hints, wrong-answer recovery, sentence rearrangement, duplicate taps, navigation focus, temporary evidence and reload/reset semantics. Python tests cover manifest validation, route switches, stylesheet dependencies, private-path rejection, local production asset delivery and lazy-service isolation. `WORD_POST_REQUIRE_BUILD=1` makes a missing build fail the suite, as in CI.

Local profiles support individual use without passwords. Optional household controls are separate. Public hosting must use the hosted entry point; exposing the local profile selector does not provide account authentication. See [Security](../SECURITY.md).
