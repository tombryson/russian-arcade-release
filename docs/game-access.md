# Game shop and permanent access

Approved policy: 17 September 2026.

Learners buy optional games from the shop with Lingocoins. They choose which game to unlock, and it remains available in Activities. Completing introductory lessons does not unlock games automatically.

Reading, Writing, Sentence practice, Word Jumble, Lessons, Speaking and Flashcards remain available from the start. They are the main ways to practise and earn coins.

## Prices and balance

| Purchase | Price |
|---|---:|
| First paid game for a profile | 25 Lingocoins |
| Each later game | 50 Lingocoins |

These are initial product settings, not evidence-based learning targets. Review the prices against actual use before increasing them. There is no fixed purchase order and no recurring fee. Games retained from an earlier release do not use the first-purchase discount.

Purchases use the same balance shown in the application header or sidebar. Existing balances, introductory bonuses and game rewards are spendable. There is no separate qualifying-coin balance for the shop.

The current rewards remain 3 coins per completed activity, capped at 12 activity coins per study day, and 1 coin per eligible flashcard review, capped at 10 review coins. The separate welcome bonus and existing eligibility rules remain unchanged. Hints and mistakes do not reduce ordinary participation rewards.

## User experience

The shop shows each game’s artwork, description, price and ownership. Learners can read about a game before buying it. An explicit **Unlock** action spends coins; opening the shop or a game preview does not.

An owned game offers **Play** or a saved-session link. A locked game shows how many more coins are needed. A profile is required to purchase because the balance and ownership belong to that profile.

Games use their full content pipelines. Vocabulary games combine familiar material with new language. Describe the scene uses grammar tasks; Follow the directions uses its map and dialogue engine. Buying a game neither restricts it to introductory vocabulary nor creates another vocabulary store.

## Skill and journey progress

Elo remains a provisional skill estimate. It does not set shop prices or prevent purchases. Barsik’s skill bar changes through eligible assessment evidence, not spending.

Journey destinations use eligible earned coins and story prerequisites. Purchases reduce the wallet but do not reduce that earned total, close destinations or undo completed story stops. Game ownership is separate from both journey position and skill estimates.

## Existing access and saved work

Migration 039 preserves every recorded game entitlement. It also grants permanent access to games with an existing saved non-demo session. Earlier tutorial unlock snapshots alone do not grant access. Saved sessions, answers, media, rewards and review history remain intact.

Migration 038 retains its historical backfill for databases upgrading from older versions. After migration, reaching its former 12-coin milestones grants no further games. Reward writes and catalogue reads do not create new entitlements.

Public demo samples remain directly playable. Purchases are disabled in the public demo, where progress is temporary. Sample play does not grant ownership in a personal library.

## Storage and purchase integrity

`services/game_access.py` owns pricing, wallet checks and access rules. `journey_game_access` records permanent ownership per profile. `journey_game_purchases` records the request, game, displayed price and actual charge.

`POST /api/v1/games/<game-id>/purchase` accepts a stable `request_id` and `expected_price`. It uses the existing CSRF and profile checks. The server validates the price, balance and ownership inside one SQLite write transaction, then saves the wallet debit, entitlement and receipt together.

Repeating a purchase request returns its saved receipt. Buying an already owned game costs nothing. Two concurrent first-game purchases cannot both use the introductory price: after one succeeds, the other must show the new price before proceeding. A failed transaction commits neither a debit nor ownership.

Purchase entries have `category=purchase` and are excluded from earned journey progress and daily reward allowances. Purchases do not delete or rewrite reward receipts. Later review undo retains its normal ledger correction and does not revoke an owned game. If the refunded reward was already spent, the balance may briefly be negative. The shop shows that same balance and waits for enough new earnings before another purchase; it does not invent coins to hide the correction.

## Verification

Focused backend and interface checks cover prices, available funds, duplicate requests, concurrent purchases, profile isolation, stale prices, read-only catalogue requests, migrations, preserved access and public demo restrictions. Game-start checks enforce ownership while preserving existing saved sessions. Test fixtures use temporary databases and do not call paid providers.
