from .api import SteamAPIError, fetch_game_achievements
from .config import SteamAPIConfigurationError
from .library import SteamLinkRequiredError
from ..db import get_db
from ..rankings import (
    refresh_achievement_ranking_records,
    refresh_ember_ranking_records,
)


BADGE_LABELS = {
    "copper_sparks": "Faíscas de Cobre",
    "bronze_hammer": "Martelo de Bronze do Aprendiz",
    "silver_hammer": "Martelo de Prata do Ferreiro",
    "gold_hammer": "Martelo de Ouro do Mestre",
    "ember": "Brasa do Ferreiro",
}
BADGE_THRESHOLDS = (
    (25, "copper_sparks"),
    (50, "bronze_hammer"),
    (75, "silver_hammer"),
    (100, "gold_hammer"),
)


class SteamGameRequiredError(RuntimeError):
    pass


def _award_progress_badges(db, user_id, game_id, game, achievements):
    total = len(achievements)
    if total == 0:
        return

    unlocked = sum(achievement["unlocked"] for achievement in achievements)
    earned_badges = [
        badge_type
        for threshold, badge_type in BADGE_THRESHOLDS
        if unlocked * 100 >= total * threshold
    ]
    if unlocked == total:
        earned_badges.append("ember")

    ember_awarded = False
    for badge_type in earned_badges:
        cursor = db.execute(
            """
            INSERT INTO badge_awards (
                user_id, game_id, steam_app_id, game_name_snapshot, badge_type
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, steam_app_id, badge_type) DO NOTHING
            """,
            (
                user_id,
                game_id,
                game["steam_app_id"],
                game["name"],
                badge_type,
            ),
        )
        if badge_type == "ember" and cursor.rowcount:
            ember_awarded = True

    if ember_awarded:
        refresh_ember_ranking_records(db)


def sync_game_achievements(user_id, game_id, fetcher=None):
    db = get_db()
    game = db.execute(
        """
        SELECT steam_app_id, name, achievements_synced_at
        FROM games
        WHERE id = ? AND user_id = ? AND source = 'steam'
        """,
        (game_id, user_id),
    ).fetchone()
    if game is None:
        raise SteamGameRequiredError("Este jogo não possui conquistas Steam sincronizáveis.")

    link = db.execute(
        "SELECT steam_id FROM steam_links WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if link is None:
        raise SteamLinkRequiredError("Vincule uma conta Steam antes de sincronizar.")

    fetch = fetcher or fetch_game_achievements
    try:
        achievements = fetch(link["steam_id"], game["steam_app_id"])
    except (SteamAPIConfigurationError, SteamAPIError) as error:
        status = "stale" if game["achievements_synced_at"] is not None else "error"
        with db:
            db.execute(
                """
                UPDATE games
                SET achievements_sync_status = ?, achievements_sync_error = ?
                WHERE id = ? AND user_id = ?
                """,
                (status, str(error), game_id, user_id),
            )
        raise

    with db:
        for achievement in achievements:
            db.execute(
                """
                INSERT INTO achievements (
                    user_id, game_id, source, steam_api_name, name,
                    description, rarity, global_percent, icon_url,
                    icon_gray_url, unlocked, unlocked_at
                ) VALUES (?, ?, 'steam', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(game_id, steam_api_name) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    rarity = excluded.rarity,
                    global_percent = excluded.global_percent,
                    icon_url = excluded.icon_url,
                    icon_gray_url = excluded.icon_gray_url,
                    unlocked = excluded.unlocked,
                    unlocked_at = excluded.unlocked_at,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    user_id,
                    game_id,
                    achievement["steam_api_name"],
                    achievement["name"],
                    achievement["description"],
                    achievement.get("rarity"),
                    achievement.get("global_percent"),
                    achievement.get("icon_url"),
                    achievement.get("icon_gray_url"),
                    achievement["unlocked"],
                    achievement["unlocked_at"],
                ),
            )

        if achievements:
            placeholders = ", ".join("?" for _ in achievements)
            db.execute(
                f"""
                DELETE FROM achievements
                WHERE game_id = ? AND user_id = ? AND source = 'steam'
                    AND steam_api_name NOT IN ({placeholders})
                """,
                (
                    game_id,
                    user_id,
                    *(item["steam_api_name"] for item in achievements),
                ),
            )
        else:
            db.execute(
                """
                DELETE FROM achievements
                WHERE game_id = ? AND user_id = ? AND source = 'steam'
                """,
                (game_id, user_id),
            )

        _award_progress_badges(db, user_id, game_id, game, achievements)
        refresh_achievement_ranking_records(db)

        db.execute(
            """
            UPDATE games
            SET achievements_sync_status = 'success',
                achievements_synced_at = CURRENT_TIMESTAMP,
                achievements_sync_error = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND user_id = ?
            """,
            (game_id, user_id),
        )

    return len(achievements)
