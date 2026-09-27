# Word Post design system

This document defines how the visual design extends to real content, errors and adult workflows.

The home page uses a strong welcome hero and a coherent delivery narrative with tiered exploration. The [current A1 milestones](course-milestones.md) and [journey build plan](journey-milestones-build-plan.md) supply the narrative and layout contract. The [earlier Barsik journey brief](barsik-journey.md) remains a version-1 reference. Conventional activity navigation remains; the former passport and placeholder adventure do not return.

## 1. The design idea

The application helps learners practise Russian through words, reading and enjoyable language activities. Its identity uses original cut-paper art, bold type, a limited ink palette and tactile paper details. Barsik's travels provide a narrative throughline; ordinary activity labels provide navigation. Free practice remains available alongside the planned chapter sequence.

Preserve the distinctive visual composition without forcing every exercise into a delivery, letter or adventure. Illustrations support the learning task; instructions and navigation use ordinary language. Barsik is a travelling postcat trying to deliver a letter to the learner. Future chapters explain their immediate objective, and their exercises help him along that route.

The experience review recommends **Russian Arcade — Learn and practise Russian** as the working label. This is a recommendation, not a confirmed permanent rename. Technical package and route names can remain unchanged.

## 2. Visual foundations

### Palette and surfaces

| Role | Light appearance | Dark appearance | Use |
|---|---|---|---|
| Paper | `#FFF5DB` | `#242844` | Main product surface |
| Letter sheet | `#FFFCF1` | `#323854` | Letter, readable content and contained controls |
| Ink | `#24264B` | `#FFF5DB` | Body, labels and key structure |
| Secondary ink | `#656078` | `#C8C8DA` | Supporting explanations |
| Cobalt accent | `#294ACC` | `#B5C4FF` | Learning emphasis, word outlines and focus context |
| Tomato accent | `#C63821` | `#FF9C7D` | Delivery labels and occasional editorial accents |
| Ticket yellow | `#F8C843` | `#F8C843` | Primary adventure ticket and collectible paper |
| Ink on yellow | `#24264B` | `#24264B` | Every text/control foreground on yellow |
| Rule/border | `#D9CCB1` | `#555B78` | Quiet separators |
| Postal header | `#24264B` | `#24264B` | Header with cream text |

These are starting tokens extracted from the approved concept, not a blanket contrast certification. Test each actual pairing, disabled state, focus ring and text size. Meet WCAG 2.2 AA contrast for applicable text and controls; decorative illustration colours are not automatically usable as text colours. [W3C contrast guidance](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html).

Use physical-looking edges selectively: one torn/perforated ticket, airmail edge on the letter, a paper label. Keep most layout unframed. Paper textures belong in artwork or subtle decorative surfaces, never behind Russian body text. Shadows should look like small paper offsets, not generic floating dashboard panels.

### Type

- **Unbounded:** brand, short headings and selected decorative lettering. Preserve the striking shape and asymmetry of the reference.
- **Golos Text:** body, Russian reading, learning word labels, forms and explanatory feedback. Avoid making early readers decode a display face for an entire paragraph or instruction.
- Self-host reviewed font files with Cyrillic support and their licence files. Check `ё`, `й`, `ь`, `ъ`, uppercase/lowercase forms and combining stress marks in the component catalogue.
- Initial scale: body 16–18px; Russian passage 20–24px at comfortable width; heading 28–40px; home display 32–58px. Use responsive values and respect text zoom. Keep helper text at least 12px and make essential instructions full body size.
- Reading line height approximately 1.55–1.7; short display headings approximately 1.15–1.25. Do not apply headline tracking/tilts to exercise sentences.
- No all-caps Russian passages. Cyrillic decorative branding should not be presented as a pronunciation lesson.

### Space and geometry

Use a small spacing scale (4, 8, 12, 16, 24, 32, 48px). Maintain a predictable content width with generous reading space. The reference's occasional rotated slip is an accent; keep input hit areas stable and avoid overlapping rotated controls.

### Activity entry pages

Flashcards, Reading, Speaking, Writing, Lessons, Word Jumble and Translation share one entry layout. Show the activity name followed by one sentence explaining the task. Do not add slogans, category labels or an extra link back to Activities above the title.

Use `ActivityHeader.tsx` in native pages and the `_activity_header.html` macro in Flask templates. Both use `static/css/activity_entry.css`: a 1120px content limit, 40px top padding and 32px side padding on desktop; 24px and 20px on small screens. Titles and descriptions share the same type scale. Existing header actions sit on the right and move below the description on small screens. Loaded exercises retain their task navigation.

Use semantic tokens such as `surface.paper`, `text.primary`, `action.primary.background`, `feedback.hint` and `motion.confirmation`, mapped to raw palette tokens. The authoritative source now lives in [the UI package](../flask_vocab_app/ui/src/styles/tokens.json); `npm run tokens` generates its CSS. The former documentation token file has been moved, so there is no second independently editable token set.

### Welcome and practice hierarchy

The welcome gets approximately the first desktop viewport: the original three-line “A small word. A BIG adventure.” composition, a large Barsik illustration and a readable greeting bubble. “Learn Russian with Barsik” establishes the purpose. Keep the story hook short: “Barsik has a letter for you. But to deliver it, he has a whole world yet to explore.” A full-width yellow **Your first delivery · a little adventure** card is the single primary action and opens the tutorial. Avoid a second status strip, duplicate promotional copy or another primary action in the hero.

The tutorial uses the same paper, word buttons, hints and answer feedback as practice. Present one step at a time: Lingocoins, a first greeting, then the next activity. Keep the detailed coin limits behind a disclosure. Explain that the warm-up does not add coins, and never use a fabricated balance or mastery claim as its ending. Home and Activities remain usable throughout.

The practice section has its own generous vertical space. On the existing workspace home, present three unboxed choices with small coloured paper accents and a link to the complete activity list. Household mode shows actual approved content/resume/setup state instead. Keep learner identity with those activities. At phone widths, stack the artwork and activity choices without fixed-height clipping or forced scroll snapping. The greeting is readable HTML; the illustration contains no essential instructions. Keep the full activity list directly accessible from the header.

## 3. Navigation and information architecture

### Child experience

Recommended structure, pending household observation:

1. **Home:** an understandable start/resume action based on actual saved state and available approved material. Returning learners reach practice quickly.
2. **Activities:** recognisable flashcard, reading, sentence, writing and lesson choices. Preserve access to existing capabilities throughout migration.
3. **My words:** vocabulary with context, available pronunciation and honest learning evidence.

A future **My progress** view should use factual practice history. The passport and collectible stamps have been removed by owner direction. See the experience review for first-use, empty and returning states.

Keep alternate activity choices available when there is real content to choose from. Do not fill the home with locked worlds, invented daily counts or unexplained currencies. Labels remain readable text even when an icon/illustration accompanies them.

### Grown-up workspace

Use the same palette, typography family and paper details with less decorative motion and more efficient information density. Preserve advanced functionality through purpose-based sections:

- Learners and reading support.
- Adventures: draft, review, publish, withdraw and assign when assignments are implemented.
- Library: words, forms, examples, imported material and saved legacy content.
- Capture: app/Drive sources, preview, conflicts and enrichment retry.
- Connections: Drive, Anki, audio and generation providers.
- Progress and legacy history; maintenance/export/recovery under secondary actions.

Use “For grown-ups” as the entry, but implement actual server access policy. Keep technical details here where they explain an action: a connection test, an export result, a conflict or a backup location.

## 4. Component contracts

### Activity entry layout

All pages use the same compact top navigation. Its logo, padding and tagline visibility must not change with the route. The shared `navigation_layout.css` owns these dimensions for the native and Flask pages. Mobile navigation may wrap, and the progress bar reserves space when present. Sidebar navigation remains separate. Home's introductory headline can be larger than an activity title.

Keep the activity title, brief context and main action together. Put alternative actions beside the main action, and move detailed progress requirements below the practice choices. On desktop, the milestone topic activities should fit in the first viewport. Check the rendered layout at desktop and narrow widths; reducing text size alone is not a layout fix.

### Navigation cards

When a card opens one destination, its entire surface must be clickable: illustration, text and padding. Use one native link with a clear destination name. The card should have one keyboard stop and a visible focus outline around the whole card. Preserve normal link actions, including opening in a new tab.

A stretched link can extend a title or action link across its card. Keep its hit area within that card and check it at narrow widths. Do not put other links, buttons or form controls inside that hit area; cards with several actions need separate controls. Locked cards remain inactive and outside the tab order. Do not give them hover or pointer treatments that imply they can be opened.

| Component | Purpose | Required states/behaviour |
|---|---|---|
| Postal header/navigation | Locate the child in the world | Active destination, long labels, keyboard focus, profile context, small screen |
| Delivery ticket | One next adventure | New, resumable, completed/revisit, temporarily unavailable; correct action label |
| Barsik greeting | Invite and orient | Decorative art + real text; hideable; never the only carrier of essential instructions |
| Letter | Introduce a concrete learning purpose | New/reopened; readable text; optional narration; no essential text baked into artwork |
| Word slip | Choose/use a Russian word | Default, focus, selected, hint, acknowledged result; generous non-overlapping hit area |
| Sentence builder | Construct a meaningful reply | Tap-to-add/reorder/remove, keyboard alternative, reset, accepted variants, saved state |
| Hint | Make an error useful | On request/always-on support; short explanation; persists hint evidence when relevant |
| Feedback | Explain what happened | Correct, try again, assessment pending, service issue; colour never carries meaning alone |
| Audio control | Hear approved Russian | Play/pause/replay, loading, unavailable, speed if useful; text alternative and no autoplay |
| Save indicator | Explain persistence accurately | Saving, saved, retry needed; no false success |
| Word pocket entry | Revisit learned context | Empty, seen/used/recalled evidence, example sentence, audio; no invented mastery percentage |
| Capture receipt | Adult view of new vocabulary | Captured, interpreted, linked, rejected/needs review, details pending, export status |
| Adult job row | Explain slow work | Queued, current stage, retry, partial outcome, cancelled/failed; real stage labels |

Build a small development catalogue in the active app before introducing a separate documentation framework. Give components fixtures for empty, populated, long Russian, pending, error, keyboard and narrow-width states. Add Storybook or similar only when its authoring/review benefit outweighs another tool to operate.

## 5. Child interaction and copy

An adventure has one clear objective, a small number of steps and a satisfying outcome. The first pack should teach a few useful words through repeated meaningful use. The current adult writing minimums and countdown do not carry over automatically.

- Give an instruction before asking for an answer: “Choose the Russian word for apple.”
- Explain errors concretely: “Дом means house. Яблоко means apple.”
- Offer hints without moral judgement or currency cost. Record help as evidence, not failure.
- Distinguish story language from instruction language. An English interface can contain Russian learning content with `lang="ru"`; changing hint language should not unexpectedly translate the whole navigation.
- Avoid claims such as “mastered” or “fluent” after one answer. Say “You used this word in a sentence.”
- A saved draft, connection failure or delayed evaluation is a system state, not the child's mistake.
- Preserve real Russian spelling in display. Transliteration, if later added, is an optional reading aid with its own policy rather than the default replacement for Cyrillic.

Use one canonical UI message catalogue to produce server/client messages. Keep adventure content and translations versioned with the content pack; do not put stories into generic interface translations. Map backend error codes to audience-appropriate copy without showing raw exception/provider text.

## 6. Motion, audio and accessibility

Use brief response to an intentional action: envelope opens, a word settles into a message, an answer is acknowledged. Suggested durations are 150–240ms for small actions and at most roughly 400ms for a completion flourish. Never make the child wait for animation before the next control is usable. Honour reduced motion with immediate transitions; avoid looping attention-grabbing motion and flashing.

Design targets of **at least 48×48 CSS pixels** for primary child actions. This is a product usability target, not a claim that WCAG requires 48px: WCAG 2.2's AA minimum has 24px sizing/spacing rules and exceptions. [W3C target-size guidance](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html).

Support taps and keyboard interaction for every sentence-building operation. Dragging may be an enhancement, never the only method; keyboard support alone also does not replace a non-drag pointer alternative. [W3C dragging guidance](https://www.w3.org/WAI/WCAG22/Understanding/dragging-movements.html).

Manage focus when a step changes, return focus from dialogs, give controls accessible names, and announce saved/result states politely. Ensure a correct answer is understandable without sound or colour. Narration is user initiated with replay, an accompanying transcript and graceful unavailable state. Test with VoiceOver and keyboard, not only an automated audit.

For long-term audio production, retain a pronunciation/stress review step and clear voice/asset versions. The current prototype contains no working audio; adding a speaker icon alone would not complete this requirement.

## 7. Responsive and performance requirements

Review 320, 360, 390, 768, 1024 and 1440px widths, text zoom, long translations and touch input. These are target test widths, not devices already certified. In narrow layouts prioritise the child's next action, reduce decorative art and collapse space before shrinking text. Let the page scroll normally; avoid several nested scroll regions.

Proposed initial performance budgets, to measure and refine during Phase 1:

- Initial child JS + CSS: at most 200KB compressed, excluding fonts/media.
- Initial illustration: target at most 250KB at the necessary display resolution; use responsive image variants and reserve layout space.
- Initial fonts: target at most 150KB compressed for the used subsets/weights, preserving required Cyrillic/stress coverage.
- Prepared adventure start: target usable content within 2 seconds on the agreed reference phone/network, measured separately from cached desktop localhost.
- Local touch feedback: immediate; visible acknowledgement or saving state within 100ms, with server confirmation tracked separately.

The approved JPEG is approximately 386KB and the original PNG approximately 2MB; preserve the original for art direction but optimise production variants. Do not embed the prototype's base64 image into the production JS bundle. Lazy-load optional adult charts and non-current adventure illustrations. No live image generation is needed during the child lesson.

## 8. Art direction and asset governance

Keep Barsik's ginger silhouette, cobalt postal jacket, red satchel, friendly expression and tactile paper material consistent. Expand places/characters through a short style sheet and reviewed reference images. Maintain a limited palette, strong silhouettes and generous space around important objects.

Assets need stable names, original and web derivatives, alt-text intent, attribution/licence/provenance, and an approval record. Avoid generating a different Barsik every time an adventure opens. Curated scene art can be shared between adventures; vocabulary-specific images must accurately depict the intended sense.

Confirm asset and font redistribution requirements when packaging production files, and keep licence records alongside shipped fonts.

## 9. Design acceptance

Accept the implementation when the home, an active letter, a wrong answer, a resumed session, completion, empty pocket and grown-up capture screen all feel like the same product. Verify that the illustrated world remains recognisable when real text is long, audio fails or a save is retried.

Use side-by-side visual checks against the approved concept, plus observed child use. Treat the prototype as a direction to preserve, not a reason to copy its temporary grading logic, in-memory state, navigation semantics or lack of audio.
