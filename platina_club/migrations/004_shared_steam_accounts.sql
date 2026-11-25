CREATE TABLE steam_links_new (
    user_id INTEGER PRIMARY KEY,
    steam_id TEXT NOT NULL,
    linked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    games_sync_status TEXT NOT NULL DEFAULT 'never'
        CHECK (games_sync_status IN ('never', 'success', 'stale', 'error')),
    games_synced_at TEXT,
    games_sync_error TEXT,
    avatar_url TEXT,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

INSERT INTO steam_links_new (
    user_id,
    steam_id,
    linked_at,
    games_sync_status,
    games_synced_at,
    games_sync_error,
    avatar_url
)
SELECT
    user_id,
    steam_id,
    linked_at,
    games_sync_status,
    games_synced_at,
    games_sync_error,
    avatar_url
FROM steam_links;

DROP TABLE steam_links;
ALTER TABLE steam_links_new RENAME TO steam_links;
