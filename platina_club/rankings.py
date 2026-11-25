from flask import Blueprint, render_template

from .auth import login_required
from .db import get_db


rankings = Blueprint("rankings", __name__, url_prefix="/rankings")


def _current_ember_standings(db):
    players = db.execute(
        """
        SELECT p.user_id, p.display_name, COUNT(*) AS total_embers
        FROM profiles AS p
        JOIN badge_awards AS b ON b.user_id = p.user_id
        WHERE p.privacy = 'all'
          AND p.show_ranking_position = 1
          AND b.badge_type = 'ember'
        GROUP BY p.user_id, p.display_name
        """
    ).fetchall()
    return sorted(
        (dict(player) for player in players),
        key=lambda player: (
            -player["total_embers"],
            player["display_name"].casefold(),
            player["user_id"],
        ),
    )


def _current_achievement_standings(db):
    players = db.execute(
        """
        SELECT p.user_id, p.display_name, COUNT(*) AS total_achievements
        FROM profiles AS p
        JOIN achievements AS a ON a.user_id = p.user_id
        WHERE p.privacy = 'all'
          AND p.show_ranking_position = 1
          AND a.unlocked = 1
        GROUP BY p.user_id, p.display_name
        """
    ).fetchall()
    return sorted(
        (dict(player) for player in players),
        key=lambda player: (
            -player["total_achievements"],
            player["display_name"].casefold(),
            player["user_id"],
        ),
    )


def refresh_ember_ranking_records(db):
    standings = _current_ember_standings(db)
    for position, player in enumerate(standings, start=1):
        db.execute(
            """
            INSERT INTO ember_ranking_records (user_id, best_position)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                best_position = MIN(
                    ember_ranking_records.best_position,
                    excluded.best_position
                ),
                recorded_at = CASE
                    WHEN excluded.best_position
                        < ember_ranking_records.best_position
                    THEN CURRENT_TIMESTAMP
                    ELSE ember_ranking_records.recorded_at
                END
            """,
            (player["user_id"], position),
        )
    return standings


def refresh_achievement_ranking_records(db):
    standings = _current_achievement_standings(db)
    for position, player in enumerate(standings, start=1):
        db.execute(
            """
            INSERT INTO achievement_ranking_records (user_id, best_position)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                best_position = MIN(
                    achievement_ranking_records.best_position,
                    excluded.best_position
                ),
                recorded_at = CASE
                    WHEN excluded.best_position
                        < achievement_ranking_records.best_position
                    THEN CURRENT_TIMESTAMP
                    ELSE achievement_ranking_records.recorded_at
                END
            """,
            (player["user_id"], position),
        )
    return standings


def get_ember_ranking_positions(user_id):
    db = get_db()
    with db:
        standings = refresh_ember_ranking_records(db)

    for position, player in enumerate(standings, start=1):
        if player["user_id"] == user_id:
            record = db.execute(
                """
                SELECT best_position
                FROM ember_ranking_records
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
            return {
                "best": record["best_position"],
                "current": position,
                "total_players": len(standings),
            }
    return None


def get_achievement_ranking_positions(user_id):
    db = get_db()
    with db:
        standings = refresh_achievement_ranking_records(db)

    for position, player in enumerate(standings, start=1):
        if player["user_id"] == user_id:
            record = db.execute(
                """
                SELECT best_position
                FROM achievement_ranking_records
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
            return {
                "best": record["best_position"],
                "current": position,
                "total_players": len(standings),
            }
    return None


@rankings.get("")
@login_required
def leaderboard():
    with get_db() as db:
        refresh_ember_ranking_records(db)
        refresh_achievement_ranking_records(db)

    players = get_db().execute(
        """
        WITH ember_stats AS (
            SELECT user_id,
                   COUNT(*) AS total_embers,
                   SUM(
                       awarded_at >= date('now', 'start of month')
                       AND awarded_at < date('now', 'start of month', '+1 month')
                       AND awarded_at <= CURRENT_TIMESTAMP
                   ) AS monthly_embers,
                   SUM(
                       awarded_at >= date(
                           'now',
                           printf(
                               '-%d days',
                               (CAST(strftime('%w', 'now') AS INTEGER) + 6) % 7
                           )
                       )
                       AND awarded_at < date(
                           'now',
                           printf(
                               '-%d days',
                               (CAST(strftime('%w', 'now') AS INTEGER) + 6) % 7
                           ),
                           '+7 days'
                       )
                       AND awarded_at <= CURRENT_TIMESTAMP
                   ) AS weekly_embers
            FROM badge_awards
            WHERE badge_type = 'ember'
            GROUP BY user_id
        ),
        achievement_stats AS (
            SELECT user_id,
                   SUM(unlocked = 1) AS total_achievements,
                   SUM(
                       unlocked = 1
                       AND unlocked_at >= date('now', 'start of month')
                       AND unlocked_at < date('now', 'start of month', '+1 month')
                       AND unlocked_at <= CURRENT_TIMESTAMP
                   ) AS monthly_achievements,
                   SUM(
                       unlocked = 1
                       AND unlocked_at >= date(
                           'now',
                           printf(
                               '-%d days',
                               (CAST(strftime('%w', 'now') AS INTEGER) + 6) % 7
                           )
                       )
                       AND unlocked_at < date(
                           'now',
                           printf(
                               '-%d days',
                               (CAST(strftime('%w', 'now') AS INTEGER) + 6) % 7
                           ),
                           '+7 days'
                       )
                       AND unlocked_at <= CURRENT_TIMESTAMP
                   ) AS weekly_achievements
            FROM achievements
            GROUP BY user_id
        )
        SELECT p.user_id, p.display_name,
               COALESCE(e.total_embers, 0) AS total_embers,
               COALESCE(e.monthly_embers, 0) AS monthly_embers,
               COALESCE(e.weekly_embers, 0) AS weekly_embers,
               COALESCE(a.total_achievements, 0) AS total_achievements,
               COALESCE(a.monthly_achievements, 0) AS monthly_achievements,
               COALESCE(a.weekly_achievements, 0) AS weekly_achievements
        FROM profiles AS p
        LEFT JOIN ember_stats AS e ON e.user_id = p.user_id
        LEFT JOIN achievement_stats AS a ON a.user_id = p.user_id
        WHERE p.privacy = 'all'
          AND p.show_ranking_position = 1
        """
    ).fetchall()

    categories = (
        ("total_embers", "Mais Brasas — geral", "Todos os tempos"),
        ("monthly_embers", "Mais Brasas — mês", "Mês atual"),
        ("weekly_embers", "Mais Brasas — semana", "Semana atual"),
        ("total_achievements", "Mais conquistas — geral", "Todos os tempos"),
        ("monthly_achievements", "Mais conquistas — mês", "Mês atual"),
        ("weekly_achievements", "Mais conquistas — semana", "Semana atual"),
    )
    boards = []
    for metric, title, period in categories:
        ordered_players = sorted(
            (dict(player) for player in players if player[metric] > 0),
            key=lambda player: (
                -player[metric],
                player["display_name"].casefold(),
                player["user_id"],
            ),
        )
        boards.append(
            {
                "title": title,
                "period": period,
                "metric": metric,
                "players": [
                    {**player, "rank": position}
                    for position, player in enumerate(ordered_players, start=1)
                ],
            }
        )

    return render_template("rankings/list.html", boards=boards)
