# First delivery: learn three Russian words, then use them

Revised direction, 15 September 2026. The first delivery is one continuous beginner lesson with saved practice and a one-time welcome reward. It teaches its words before asking the learner to recall them. There is no separate guided hello followed by a second activity.

## Learner flow

The coin introduction reveals the counter. The progress introduction then reveals Barsik's line. An alphabet slide follows, before any word practice. The primary **Continue** button opens the first words. A centred button groups three overlapping letter tiles with the handwritten **Learn the alphabet** label below the explanation. It offers optional alphabet practice without repeating the title or adding a second link beside Continue. The alphabet opens with both voice sets and click-to-play audio; its return link restores the invitation. Learning the alphabet is optional and earns no reward. There is no side invitation on the coin or progress slide.

The learner then meets three word cards in order: **Привет!** (hello), **письмо** (a letter), and **Спасибо!** (thank you). These belong to the same delivery: meeting Barsik, seeing the letter he carries, and thanking him. Each card teaches the Russian word and its meaning before continuing.

After all three cards, the learner answers three recall questions. Every answer button is Russian, and every option is one of the three words already taught. The teaching card and its revealed meaning are absent during recall. Choosing an answer shows feedback; continuing opens the next question immediately. Hints remain available without reducing the welcome reward. The final feedback leads directly to the completion result, with no second “let’s begin” or activity handoff.

The server records each first answer and whether a hint was used before that answer. Feedback follows submission; changing an answer after seeing feedback must not replace its first-attempt evidence. Completing all three questions earns **3 welcome coins**, including when some answers were wrong or supported by hints. The result distinguishes the participation reward from the reading assessment.

The unhinted first recall answers supply one aggregate provisional Reading observation: the number answered correctly divided by the number answered without hints. Wrong unhinted answers count normally; hinted answers are excluded from both sides of that fraction. This is recall after teaching, not evidence of broad reading ability. The existing model uses task prior 1000 and update strength 24. Teaching cards, introduction pages, navigation, cached feedback and repeated completion supply no observations. A fully hinted completion earns the welcome reward without inventing an independent rating.

The header refreshes from the committed result. For a new learner's first qualifying reading result, Barsik can move from the unmeasured starting position to the real resulting position. There is no fabricated fill, minimum positive rating or animation presented as earned progress after a reload or profile switch. Reduced-motion preferences remain respected. See [the skill-progress contract](skill-progress.md).

## Reward contract

The welcome reward is **one grant of 3 coins per profile**, outside the ordinary 12-coin activity allowance. A learner who has used today's activity allowance still receives the full welcome reward. Completing the first delivery does not consume the allowance for later ordinary practice.

The bonus counts toward both the wallet and eligible earnings for Barsik's journey. It uses the separate policy `first-delivery-welcome-v1`; ordinary activity-cap calculations exclude that policy. Journey prerequisites still apply, so the bonus cannot complete a story stop by itself.

This is a separate welcome entitlement. Completing the same three questions must not also issue an ordinary Reading participation reward. Replaying the introduction, retrying the last request, reopening a completed attempt or returning on another day cannot claim another welcome bonus or duplicate its skill evidence. A later content revision cannot reset the lifetime welcome entitlement.

The server derives completion and correctness from its authored task and saved responses. It does not trust a browser-supplied score, coin amount, profile ID or declaration that an activity is complete. Completion, its reward receipt and any eligible skill evidence must commit together. A failed transaction leaves the operation safely retryable. Simultaneous completion requests must converge on the same saved result.

Existing balances, ordinary daily caps, legacy Elo, card schedules and other activity records are preserved. Welcome coins are participation, not an assessment score or a CEFR qualification.

## Guests and profiles

A guest can complete the same first delivery before creating a profile. The result remains pending with that guest's server-side session; it is not a credit to any existing wallet. The interface must distinguish a pending welcome reward from coins already saved to a profile.

Creating a **new personal profile** transfers that guest's introduction milestones, first answers, hint history and completed reward exactly once. The transfer and new profile creation are atomic. An interrupted or retried creation cannot apply the pending completion to two profiles. A selected household learner can complete their own first delivery, but household profile creation does not claim a guest attempt.

Selecting an **existing** profile never imports the guest's answers, rating evidence, bonus or introduction milestones. That profile resumes its own first delivery. Switching or ending a session must not make one learner's attempt available to another. Guest ownership must survive ordinary reloads without relying on an arbitrary attempt ID supplied by the browser.

The invitation uses `#first-delivery?step=alphabet` so reload and browser Back restore it. An ordinary `#first-delivery` visit still resumes saved practice. Continuing from the invitation resumes the same attempt, including a completed result, without resetting answers or rewards. A fresh session must see the coin and progress introductions first. A failed initial read keeps starting practice disabled until retry succeeds.

## Persistence and verification

Migration 026 remains the record of which header controls have been introduced. Migration 027 adds `first_delivery_attempts`, retaining the authored version, first answers, hint history, feedback acknowledgements and completion time. Each row belongs to either one profile or one guest token; a unique profile owner prevents multiple first-delivery attempts per profile. Its persistence must not infer completion from introduction timestamps, an old balance, existing grades or the previous guided hello. It creates no historical awards or rating observations.

Migration 028 adds `learned_json` for the taught words and nullable `previous_attempt_json` for the earlier activity snapshot. It leaves every v1 attempt, answer, hint, acknowledgement, completion time and reward intact. Reading or normally starting an old attempt does not reinterpret it as v2. An explicit `start` with `{"restart":true}` archives the entire v1 row and begins v2 in the same owned row. Its old welcome receipt and skill evidence remain unchanged; completing v2 cannot earn a second bonus or replace the original rating evidence.

A completed v1 guest attempt also retains its pending entitlement through an explicit restart. Creating a new personal profile can save that original completion even while the new lesson is unfinished. The prior answers remain the evidence for that entitlement. An unfinished v1 attempt is archived without an award, and completing the revised lesson can earn the profile's still-unused welcome bonus.

`GET /api/v1/onboarding/practice` reads the current owner's attempt without creating one. JSON `POST` requests under the same path use `start`, `learn`, `hint`, `answer`, `continue` and `complete`. Writes require the current CSRF token and the two introduction milestones. The server rejects extra fields, unknown questions and invalid choices; callers cannot choose an attempt owner or submit a reward or score. All three words must be taught in order before recall. Feedback acknowledgements must follow the saved questions in order before completion. Repeating a successful learning acknowledgement, answer, hint, feedback acknowledgement or completion returns the saved state.

Guest ownership is derived from the established server-generated CSRF token and stored in the server session. Simultaneous first starts therefore resolve the same guest owner. A write transaction reserves SQLite's writer before reading the attempt, so racing submissions see the preceding commit. The fixed `first_delivery` / `first-delivery-welcome` event identity and profile-specific ledger operation provide the lifetime reward receipt. The retained v1 catalogue keeps old work readable; unknown future versions require an explicit compatibility decision, not a fresh entitlement.

Required checks cover:

- The teaching position, all three first answers, hint history, feedback and completion survive reloads and retries.
- All words are taught before recall; answer buttons contain only taught Russian words, and teaching text is absent while recalling.
- Partial completion, introduction pages and teaching cards award nothing.
- Supported and incorrect answers still permit the full welcome reward; hinted evidence cannot become independent Elo on a later retry.
- The bonus remains exactly 3 coins when the ordinary activity cap is already used and does not reduce that allowance.
- Duplicate and concurrent completion create one bonus and one set of eligible evidence, including across day changes and content revisions.
- Guests retain pending work across reloads; transfer occurs once when creating a new profile and never when selecting an existing one.
- A foreign attempt ID cannot reveal or alter another guest's or profile's answers.
- The first saved rating updates the real line; reloads, replays, profile switches and failed saves cannot simulate another improvement.
- Migration preserves every pre-existing field, balance, receipt and schedule and passes SQLite integrity and foreign-key checks on an isolated copy.
- Explicit v1 restart retains an exact archive and cannot duplicate or reinterpret a completed profile or guest entitlement.

For a previously unmeasured learner, three correct unhinted answers produce one Reading observation at 1012 and a 6% Stage 1 position. Three wrong unhinted answers produce 988 and remain at the start of the line; the reward is still 3 coins.

Rehearse deployment on a database copy; do not use real learner attempts to manufacture progress for a visual preview.
