CREATE TABLE achievement_ranking_records (
    user_id INTEGER PRIMARY KEY,
    best_position INTEGER NOT NULL CHECK (best_position > 0),
    recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES profiles (user_id) ON DELETE CASCADE
);
