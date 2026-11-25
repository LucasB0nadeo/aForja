from .api import SteamAPIError, fetch_owned_games
from .config import SteamAPIConfigurationError
from ..db import get_db


class SteamLinkRequiredError(RuntimeError):
    pass


def upsert_steam_game(db, user_id, game, update_playtime=True):
    db.execute(
        """
        INSERT INTO games (
            user_id, source, name, steam_app_id, playtime_minutes
        ) VALUES (?, 'steam', ?, ?, ?)
        ON CONFLICT(user_id, steam_app_id) DO UPDATE SET
            name = excluded.name,
            playtime_minutes = CASE
                WHEN ? THEN excluded.playtime_minutes
                ELSE games.playtime_minutes
            END,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            user_id,
            game["name"],
            game["steam_app_id"],
            game.get("playtime_minutes", 0),
            int(update_playtime),
        ),
    )
    return db.execute(
        """
        SELECT id FROM games
        WHERE user_id = ? AND steam_app_id = ? AND source = 'steam'
        """,
        (user_id, game["steam_app_id"]),
    ).fetchone()["id"]


def sync_owned_games(user_id, fetcher=None):
    db = get_db()
    link = db.execute(
        "SELECT steam_id, games_synced_at FROM steam_links WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if link is None:
        raise SteamLinkRequiredError("Vincule uma conta Steam antes de sincronizar.")

    fetch = fetcher or fetch_owned_games
    try:
        games = fetch(link["steam_id"])
    except (SteamAPIConfigurationError, SteamAPIError) as error:
        status = "stale" if link["games_synced_at"] is not None else "error"
        with db:
            db.execute(
                """
                UPDATE steam_links
                SET games_sync_status = ?, games_sync_error = ?
                WHERE user_id = ?
                """,
                (status, str(error), user_id),
            )
        raise

    with db:
        for game in games:
            upsert_steam_game(db, user_id, game)

        db.execute(
            """
            UPDATE steam_links
            SET games_sync_status = 'success',
                games_synced_at = CURRENT_TIMESTAMP,
                games_sync_error = NULL
            WHERE user_id = ?
            """,
            (user_id,),
        )

    return len(games)
