CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL COLLATE NOCASE UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE profiles (
    user_id INTEGER PRIMARY KEY,
    display_name TEXT NOT NULL CHECK (length(trim(display_name)) > 0),
    bio TEXT NOT NULL DEFAULT '',
    custom_avatar_path TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE steam_links (
    user_id INTEGER PRIMARY KEY,
    steam_id TEXT NOT NULL UNIQUE,
    linked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    games_sync_status TEXT NOT NULL DEFAULT 'never'
        CHECK (games_sync_status IN ('never', 'success', 'stale', 'error')),
    games_synced_at TEXT,
    games_sync_error TEXT,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE games (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('manual', 'steam')),
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    platform TEXT,
    developer TEXT,
    release_year INTEGER CHECK (release_year IS NULL OR release_year > 0),
    steam_app_id INTEGER CHECK (steam_app_id IS NULL OR steam_app_id > 0),
    playtime_minutes INTEGER CHECK (
        playtime_minutes IS NULL OR playtime_minutes >= 0
    ),
    icon_url TEXT,
    achievements_sync_status TEXT NOT NULL DEFAULT 'never'
        CHECK (achievements_sync_status IN ('never', 'success', 'stale', 'error')),
    achievements_synced_at TEXT,
    achievements_sync_error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (id, user_id),
    UNIQUE (user_id, steam_app_id),
    CHECK (
        (source = 'manual'
            AND steam_app_id IS NULL
            AND length(trim(COALESCE(platform, ''))) > 0
            AND length(trim(COALESCE(developer, ''))) > 0
            AND release_year IS NOT NULL)
        OR
        (source = 'steam' AND steam_app_id IS NOT NULL)
    ),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX idx_games_user_source ON games (user_id, source);

CREATE TABLE achievements (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    game_id INTEGER NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('manual', 'steam')),
    steam_api_name TEXT,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    description TEXT NOT NULL DEFAULT '',
    rarity TEXT,
    unlocked INTEGER NOT NULL DEFAULT 0 CHECK (unlocked IN (0, 1)),
    unlocked_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (game_id, steam_api_name),
    UNIQUE (id, user_id),
    CHECK (
        (source = 'manual'
            AND steam_api_name IS NULL
            AND length(trim(description)) > 0
            AND length(trim(COALESCE(rarity, ''))) > 0)
        OR
        (source = 'steam' AND steam_api_name IS NOT NULL)
    ),
    FOREIGN KEY (game_id, user_id)
        REFERENCES games (id, user_id) ON DELETE CASCADE
);

CREATE INDEX idx_achievements_game ON achievements (game_id, user_id);

CREATE TABLE badge_awards (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    game_id INTEGER,
    steam_app_id INTEGER NOT NULL CHECK (steam_app_id > 0),
    game_name_snapshot TEXT NOT NULL
        CHECK (length(trim(game_name_snapshot)) > 0),
    badge_type TEXT NOT NULL CHECK (
        badge_type IN (
            'copper_sparks',
            'bronze_hammer',
            'silver_hammer',
            'gold_hammer',
            'ember'
        )
    ),
    awarded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, steam_app_id, badge_type),
    UNIQUE (id, user_id, badge_type),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (game_id) REFERENCES games (id) ON DELETE SET NULL
);

CREATE TRIGGER validate_badge_award_game_owner_insert
BEFORE INSERT ON badge_awards
WHEN NEW.game_id IS NOT NULL
    AND NOT EXISTS (
        SELECT 1
        FROM games
        WHERE id = NEW.game_id
            AND user_id = NEW.user_id
            AND source = 'steam'
            AND steam_app_id = NEW.steam_app_id
    )
BEGIN
    SELECT RAISE(ABORT, 'badge award must match an owned Steam game');
END;

CREATE TRIGGER validate_badge_award_game_owner_update
BEFORE UPDATE OF game_id, user_id, steam_app_id ON badge_awards
WHEN NEW.game_id IS NOT NULL
    AND NOT EXISTS (
        SELECT 1
        FROM games
        WHERE id = NEW.game_id
            AND user_id = NEW.user_id
            AND source = 'steam'
            AND steam_app_id = NEW.steam_app_id
    )
BEGIN
    SELECT RAISE(ABORT, 'badge award must match an owned Steam game');
END;

CREATE TABLE forja_slots (
    user_id INTEGER NOT NULL,
    slot INTEGER NOT NULL CHECK (slot BETWEEN 1 AND 9),
    badge_award_id INTEGER NOT NULL UNIQUE,
    badge_type TEXT NOT NULL DEFAULT 'ember' CHECK (badge_type = 'ember'),
    PRIMARY KEY (user_id, slot),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (badge_award_id, user_id, badge_type)
        REFERENCES badge_awards (id, user_id, badge_type) ON DELETE CASCADE
);

CREATE TABLE collections (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (id, user_id),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX idx_collections_user ON collections (user_id);

CREATE TABLE collection_games (
    user_id INTEGER NOT NULL,
    collection_id INTEGER NOT NULL,
    game_id INTEGER NOT NULL,
    PRIMARY KEY (collection_id, game_id),
    FOREIGN KEY (collection_id, user_id)
        REFERENCES collections (id, user_id) ON DELETE CASCADE,
    FOREIGN KEY (game_id, user_id)
        REFERENCES games (id, user_id) ON DELETE CASCADE
);

CREATE TABLE game_reviews (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    steam_app_id INTEGER NOT NULL CHECK (steam_app_id > 0),
    review_text TEXT NOT NULL CHECK (length(trim(review_text)) > 0),
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, steam_app_id),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX idx_game_reviews_user ON game_reviews (user_id);

CREATE TABLE wishlist_entries (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    steam_app_id INTEGER NOT NULL CHECK (steam_app_id > 0),
    priority INTEGER NOT NULL CHECK (priority BETWEEN 1 AND 5),
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, steam_app_id),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX idx_wishlist_user_priority
    ON wishlist_entries (user_id, priority);

CREATE TABLE personal_goals (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    objective TEXT NOT NULL CHECK (length(trim(objective)) > 0),
    due_date TEXT,
    steam_app_id INTEGER CHECK (steam_app_id IS NULL OR steam_app_id > 0),
    status TEXT NOT NULL DEFAULT 'in_progress'
        CHECK (status IN ('in_progress', 'completed')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX idx_personal_goals_user ON personal_goals (user_id);
