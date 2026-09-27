# Russian Arcade UI

This is the active child-interface package inside the existing Flask application. It is independent of the retired frontend/backend port. See [development commands](../../docs/development.md#preact-interface) and [design rules](../../docs/design-system.md).

| Source | Responsibility |
|---|---|
| `src/main.tsx` | Bundled fonts/styles and page bootstrap; loads the catalogue only on its route |
| `src/App.tsx` | Home, activity discovery, learner context and recent vocabulary |
| `src/components.tsx` | Barsik artwork, activity links, reading sheet and feedback |
| `src/Catalogue.tsx` | Gated component guide with light/dark sample states |
| `src/styles/tokens.json` | Canonical design tokens; generated CSS is ignored |
| `src/assets/` | Curated production artwork |
| `public/licenses/` | Redistributed font licences |
| `scripts/generate-tokens.mjs` | Deterministic token-to-CSS build step |

Approved choice activities now use the existing household/session API through `src/learning-api.ts` and `src/Practice.tsx`. Answers, hints, corrections and completion are saved by Flask; retries reuse the same command ID. Home reloads learner context after returning from another tab. Native card scheduling remains a separate upcoming capability.

`src/legacy.ts` builds the shared typography/tokens and a scoped CSS layer for the working Flask templates. It does not mount Preact or change their form/HTMX ownership. Existing activity routes remain restricted to grown-ups in household mode until their content and assessment adapters are ready.

No production Vite server, CDN imports, AI generation or provider credentials are needed. `dist/` is disposable build output served by Flask; do not check it into Git. Full document links cross to the existing grown-up workspace.

## Asset provenance

`barsik.webp` is the hero illustration, encoded with `cwebp -q 80 -m 6` (1254 × 1254 pixels, 135,942 bytes).

Unbounded and Golos Text are pinned Fontsource packages. Latin and Cyrillic subsets are bundled locally; the Cyrillic subset includes U+0301 for stress marks. Their SIL Open Font Licences are copied without modification into `public/licenses/` and shipped with each build. Refresh those files when changing font versions.
