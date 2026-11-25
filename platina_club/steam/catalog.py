def cache_store_game(db, game):
    db.execute(
        """
        INSERT INTO steam_catalog (
            steam_app_id, name, developer, release_date, platforms, icon_url
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(steam_app_id) DO UPDATE SET
            name = excluded.name,
            developer = excluded.developer,
            release_date = excluded.release_date,
            platforms = excluded.platforms,
            icon_url = excluded.icon_url,
            synced_at = CURRENT_TIMESTAMP
        """,
        (
            game["steam_app_id"],
            game["name"],
            game["developer"],
            game["release_date"],
            game["platforms"],
            game["icon_url"],
        ),
    )
