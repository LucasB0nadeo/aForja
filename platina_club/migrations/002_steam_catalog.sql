CREATE TABLE steam_catalog (
    steam_app_id INTEGER PRIMARY KEY CHECK (steam_app_id > 0),
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    developer TEXT NOT NULL DEFAULT '',
    release_date TEXT NOT NULL DEFAULT '',
    platforms TEXT NOT NULL DEFAULT '',
    icon_url TEXT,
    synced_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
