ALTER TABLE profiles
ADD COLUMN privacy TEXT NOT NULL DEFAULT 'all'
    CHECK (privacy IN ('all', 'friends', 'nobody'));

CREATE TABLE friendships (
    user_low_id INTEGER NOT NULL,
    user_high_id INTEGER NOT NULL,
    requested_by_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'accepted')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_low_id, user_high_id),
    CHECK (user_low_id < user_high_id),
    CHECK (requested_by_id IN (user_low_id, user_high_id)),
    FOREIGN KEY (user_low_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (user_high_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (requested_by_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX idx_friendships_pending_high
    ON friendships (user_high_id, status, requested_by_id);
