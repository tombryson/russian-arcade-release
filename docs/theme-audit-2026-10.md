# Theme audit — 6 October 2026

## Findings

The live My words page used pale text on a light background. Its local fix
(`9107397`) and the illustrated Phrasebook link (`a30ccf8`) had not been deployed.
Fly was serving `git-fabf1f1` when this audit started.

Seven theme defects were confirmed, including My words. Six additional
component families affected seven other page areas.

| Area | Problem | Correction |
| --- | --- | --- |
| My words | Heading copy, totals, source labels and tools used fixed pale colours. The Drive cleanup button also retained Bootstrap's grey text. | Use theme text tokens on the page and its tools. Preserve the readable cream table and dark ink. |
| Lessons | An undefined text token fell back to cream. Outer content also inherited fixed dark ink in dark mode. | Use theme ink outside lesson cards; retain dark ink on fixed paper cards and count badges. |
| Describe the scene | Filled answers and feedback used pale yellow, green and red directly on light paper. | Use contrasting theme accents for answers, feedback and focus rings. |
| Directions | Mobile route controls referenced an undefined surface token and fell back to a dark background. | Use the defined paper surface token. |
| Profiles and household | Body text colours overrode links in the permanently dark header. | Give header links the header foreground colour. |
| Anki tools | On `/tools/anki/`, Bootstrap `text-dark` totals and `text-primary` percentages remained dark on themed cards in dark mode. | Scope theme ink and learning accents to `#metrics`; preserve the readable fixed light table header. |
| Legacy journey feedback | Correct-answer and completion text used fixed green on dark sheet surfaces. Existing unlocked journey stops, including `/#journey/market-town`, still render this feedback. | Use the theme learning accent for `.journey-feedback.correct` and `.journey-complete`. |

The Phrasebook issue was a separate deployment mismatch. The shared illustrated
button replaces the plain blue link. The collection itself already has compact
Russian, English and audio columns; it did not need another redesign.
Live verification also found the new Phrasebook icon missing from the public
asset allowlist. Its exact path is now allowed without a profile cookie. Tests
cover both the main and `/demo` mounts while retaining private-media protection.

Static stylesheet versions for My words and Lessons were increased so browsers
request the corrected files. Bundled application styles have content hashes.

## Coverage and checks

Source review covered shared navigation, forms, activity headers, account pages,
curriculum, Comprehension, Writing, translation, Word Jumble, Phrasebook,
Flashcards, Speaking, the alphabet, introduction, journey, shop and game styles.
Templates and dynamic scripts were checked for fixed colours and Bootstrap
utilities that conflict with the shared palette.

Browser checks used a disposable local database with synthetic words and phrases.
My words and Phrasebook were visually checked in light and dark themes. The
add-word dialog and profile header were also checked. Entry-page text contrast
was inspected in both themes for Lessons, Comprehension, Writing, translation,
curriculum, Profiles, Speaking, Flashcards, journey, alphabet and shop. Activity
and game entry pages were checked for horizontal overflow. My words was checked
at a narrow viewport as well.
Anki statistics were also checked in the browser in both themes after correction.

The corrected token pairs provide approximately 4.85:1–13.3:1 contrast for the
affected text in light mode. These calculations do not establish whole-page
accessibility compliance.

The Anki totals and percentages previously measured 1.34:1 and 2.55:1 on dark
cards; legacy journey success feedback measured 2.07:1. Their theme replacements
provide at least 6.73:1 on dark sheets. The Anki `table-light` header retains its
fixed black-on-light pairing (19.92:1) and is intentionally unchanged.

Decorative emoji and expansion icons were excluded from text contrast findings;
the latter exceed the 3:1 graphical-control target.

No additional comparable light-mode mismatch was found in the reviewed styles
and entry states. Follow-up review confirmed the Anki and legacy journey defects
above in dark mode. Translation, Writing, Word Jumble, Comprehension, tutorial,
first-step and conversation feedback use theme text or explicit readable surface
pairs; no additional comparable text mismatch was confirmed in those source rules.
This is not exhaustive coverage of every generated activity, error, hover, dialog
or mobile state. Scene feedback, legacy journey feedback and mobile route controls
were checked through source and colour-pair analysis, not a complete live game.

## Follow-up

- Include both themes and a narrow viewport when reviewing future UI changes.
  Test feedback states as well as entry pages.
- Verify deployed asset versions after publishing. A local commit does not
  update Fly automatically.

## Release checks

The production build exposed a missing Docker copy step for shared JavaScript.
That step was added. Dependency checks also required patches for Werkzeug
(`CVE-2026-102598`) and source-map-js (`GHSA-68fv-2mgg-jv7q`). The release includes
those narrowly scoped updates; neither audit was bypassed.
