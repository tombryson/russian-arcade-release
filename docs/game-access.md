# Game shop and permanent access

Approved policy: 17 September 2026. Per-game prices updated: 5 October 2026.

Learners buy optional games from the shop with Lingocoins. They choose which game to unlock, and it remains available in Activities. Completing introductory lessons does not unlock games automatically.

Reading, Writing, Sentence practice, Word Jumble, Lessons, Speaking and Flashcards remain available from the start. They are the main ways to practise and earn coins.

## Prices and balance

| Game | Price |
|---|---:|
| Pack the bag | 500 Lingocoins |
| Missing Stamp | 600 Lingocoins |
| Mailbox Sort | 700 Lingocoins |
| Describe the scene | 800 Lingocoins |
| A Letter Back | 900 Lingocoins |
| Post Office Radio | 1,000 Lingocoins |
| Lost Parcel Detective | 1,100 Lingocoins |
| Follow the directions | 1,200 Lingocoins |

Each game has a fixed price, the same for a profile’s first and later purchases. These are product settings, not evidence-based learning targets. There is no fixed purchase order and no recurring fee. Games retained from an earlier release remain owned; saved purchase receipts keep their original prices.

Purchases use the same balance shown in the application header or sidebar. Existing balances, introductory bonuses and game rewards are spendable. There is no separate qualifying-coin balance for the shop.

The current rewards remain 3 coins per completed activity, capped at 12 activity coins per study day, and 1 coin per eligible flashcard review, capped at 10 review coins. The separate welcome bonus and existing eligibility rules remain unchanged. Hints and mistakes do not reduce ordinary participation rewards.

## User experience

The shop shows each game’s artwork, description, price and ownership. Learners can read about a game before buying it. An explicit **Unlock** action spends coins; opening the shop or a game preview does not.

An owned game offers **Play** or a saved-session link. A locked game shows how many more coins are needed. A profile is required to purchase because the balance and ownership belong to that profile.

When earned coins first make an unowned game affordable, a short confetti animation and a dismissible shop link appear. The game is only purchased when the learner chooses **Unlock**. The notice does not take focus or interrupt the activity. Reduced-motion users see the notice without animation.

The browser remembers each reached price for that account, profile and pricing policy. Reloads, repeated progress checks, price reductions and spending then re-earning coins do not repeat the celebration. A fresh browser starts from the current balance, so an already wealthy profile does not receive a burst of old notifications.

Games use their full content pipelines. Vocabulary games combine familiar material with new language. Describe the scene uses grammar tasks; Follow the directions uses its map and dialogue engine. Buying a game neither restricts it to introductory vocabulary nor creates another vocabulary store.

## Skill and journey progress

Elo remains a provisional skill estimate. It does not set shop prices or prevent purchases. Barsik’s skill bar changes through eligible assessment evidence, not spending.

Purchases reduce the wallet but do not alter earned practice history, milestone evidence or passed checkpoints. Game ownership is separate from both journey position and skill estimates.

## Existing access and saved work

Migration 039 preserves every recorded game entitlement. It also grants permanent access to games with an existing saved non-demo session. Earlier tutorial unlock snapshots alone do not grant access. Saved sessions, answers, media, rewards and review history remain intact.

Migration 038 retains its historical backfill for databases upgrading from older versions. After migration, reaching its former 12-coin milestones grants no further games. Reward writes and catalogue reads do not create new entitlements.

Migration 066 allows the new per-game charges while preserving every saved receipt, its original charge and row order. It retains the uniqueness and append-only protections on purchase history, and leaves ownership and the coin ledger unchanged.

In read-only sample-demo mode (`PUBLIC_DEMO`), samples remain directly playable and purchases are disabled. Sample play does not grant ownership in a personal library.

## Storage and purchase integrity

`services/game_access.py` owns pricing, wallet checks and access rules. `journey_game_access` records permanent ownership per profile. `journey_game_purchases` records the request, game, displayed price and actual charge.

`POST /api/v1/games/<game-id>/purchase` accepts a stable `request_id` and `expected_price`. It uses the existing CSRF and profile checks. The server validates the price, balance and ownership inside one SQLite write transaction, then saves the wallet debit, entitlement and receipt together.

Repeating a purchase request returns its saved receipt, including receipts from the earlier pricing policy. Buying an already owned game costs nothing. Concurrent purchases validate each game’s current price and available balance within their write transaction, so they cannot overspend. A failed transaction commits neither a debit nor ownership.

Catalogue prices come from each game’s `purchase.price`. Progression snapshots include `game_shop` with the pricing policy and unowned game offers, allowing the interface to detect when newly earned coins make a game affordable. Read-only sample-demo snapshots disable these offers.

Purchase entries have `category=purchase` and are excluded from earned journey progress and daily reward allowances. Purchases do not delete or rewrite reward receipts. Later review undo retains its normal ledger correction and does not revoke an owned game. If the refunded reward was already spent, the balance may briefly be negative. The shop shows that same balance and waits for enough new earnings before another purchase; it does not invent coins to hide the correction.

## Verification

Focused backend and interface checks cover prices, available funds, duplicate requests, concurrent purchases, profile isolation, stale prices, read-only catalogue requests, migrations, preserved access and public demo restrictions. Game-start checks enforce ownership while preserving existing saved sessions. Test fixtures use temporary databases and do not call paid providers.
