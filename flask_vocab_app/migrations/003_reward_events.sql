CREATE TABLE reward_events (
 user_id INTEGER NOT NULL,
 reward_key TEXT NOT NULL,
 coins INTEGER NOT NULL,
 elo_change INTEGER NOT NULL,
 legacy INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(user_id, reward_key),
 FOREIGN KEY(user_id) REFERENCES users(user_id)
);
INSERT INTO reward_events(user_id, reward_key, coins, elo_change, legacy)
 SELECT 1, 'sentence:' || id, 0, 0, 1 FROM sentences;
