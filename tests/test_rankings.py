import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

from platina_club import create_app
from platina_club.db import get_db


class RankingHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.boards = {}
        self.current_board = None
        self.current_entry = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "section" and attributes.get("class") == "ranking-card":
            self.current_board = attributes["aria-label"]
            self.boards[self.current_board] = []
        elif tag == "li" and self.current_board is not None:
            self.current_entry = []

    def handle_data(self, data):
        if self.current_entry is not None:
            self.current_entry.append(data)

    def handle_endtag(self, tag):
        if tag == "li" and self.current_entry is not None:
            self.boards[self.current_board].append(
                " ".join(" ".join(self.current_entry).split())
            )
            self.current_entry = None
        elif tag == "section" and self.current_board is not None:
            self.current_board = None


class RankingRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret-key",
                "DATABASE": str(Path(self.temp_dir.name) / "rankings.sqlite3"),
            }
        )
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.client = self.app.test_client()

        with get_db() as db:
            self.user_ids = {}
            for email, display_name, privacy in (
                ("visible@example.com", "Visible Player", "all"),
                ("second@example.com", "Second Player", "all"),
                ("hidden@example.com", "Hidden Player", "nobody"),
            ):
                user_id = db.execute(
                    "INSERT INTO users (email, password_hash) VALUES (?, 'unused')",
                    (email,),
                ).lastrowid
                db.execute(
                    """
                    INSERT INTO profiles (user_id, display_name, privacy)
                    VALUES (?, ?, ?)
                    """,
                    (user_id, display_name, privacy),
                )
                self.user_ids[display_name] = user_id

        with self.client.session_transaction() as session:
            session["user_id"] = self.user_ids["Visible Player"]

    def tearDown(self):
        self.app_context.pop()
        self.temp_dir.cleanup()

    def _time_values(self):
        return get_db().execute(
            """
            SELECT datetime('now') AS current_time,
                   datetime('now', '+1 day') AS future_time,
                   datetime(
                       'now',
                       printf(
                           '-%d days',
                           ((CAST(strftime('%w', 'now') AS INTEGER) + 6) % 7) + 1
                       )
                   ) AS previous_week,
                   datetime('now', 'start of month', '-1 second') AS previous_month,
                   datetime('now', 'start of month') AS month_start
            """
        ).fetchone()

    def _add_embers(self, user_id, app_ids, awarded_at):
        with get_db() as db:
            for app_id in app_ids:
                db.execute(
                    """
                    INSERT INTO badge_awards (
                        user_id, steam_app_id, game_name_snapshot, badge_type,
                        awarded_at
                    ) VALUES (?, ?, ?, 'ember', ?)
                    """,
                    (user_id, app_id, f"Game {app_id}", awarded_at),
                )

    def _add_achievements(self, user_id, app_id, unlock_times):
        db = get_db()
        game_id = db.execute(
            """
            INSERT INTO games (user_id, source, name, steam_app_id)
            VALUES (?, 'steam', ?, ?)
            """,
            (user_id, f"Game {app_id}", app_id),
        ).lastrowid
        with db:
            for index, unlocked_at in enumerate(unlock_times):
                db.execute(
                    """
                    INSERT INTO achievements (
                        user_id, game_id, source, steam_api_name, name,
                        unlocked, unlocked_at
                    ) VALUES (?, ?, 'steam', ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        game_id,
                        f"ACHIEVEMENT_{index}",
                        f"Achievement {index}",
                        int(unlocked_at is not None),
                        unlocked_at,
                    ),
                )

    def test_rankings_count_periods_and_exclude_non_public_profiles(self):
        times = self._time_values()
        visible_user = self.user_ids["Visible Player"]
        second_user = self.user_ids["Second Player"]
        hidden_user = self.user_ids["Hidden Player"]

        self._add_embers(
            visible_user,
            (10001, 10002, 10003),
            times["current_time"],
        )
        self._add_embers(visible_user, (10004,), times["previous_week"])
        self._add_embers(visible_user, (10005,), times["previous_month"])
        self._add_embers(visible_user, (10006,), times["future_time"])
        self._add_embers(second_user, (20001,), times["current_time"])
        self._add_embers(
            hidden_user,
            (30001, 30002, 30003, 30004),
            times["current_time"],
        )

        self._add_achievements(
            visible_user,
            40001,
            (
                times["current_time"],
                times["previous_week"],
                times["previous_month"],
                times["future_time"],
                None,
            ),
        )
        self._add_achievements(
            second_user,
            40002,
            (times["current_time"], None),
        )
        self._add_achievements(
            hidden_user,
            40003,
            (
                times["current_time"],
                times["current_time"],
                times["current_time"],
                times["current_time"],
            ),
        )

        response = self.client.get("/rankings")

        self.assertEqual(response.status_code, 200)
        parser = RankingHTMLParser()
        parser.feed(response.get_data(as_text=True))
        self.assertEqual(
            set(parser.boards),
            {
                "Mais Brasas — geral",
                "Mais Brasas — mês",
                "Mais Brasas — semana",
                "Mais conquistas — geral",
                "Mais conquistas — mês",
                "Mais conquistas — semana",
            },
        )

        total_embers = parser.boards["Mais Brasas — geral"]
        self.assertIn("Visible Player", total_embers[0])
        self.assertIn("6 Brasas", total_embers[0])
        self.assertIn("Second Player", total_embers[1])
        self.assertIn("1 Brasa", total_embers[1])

        current_month_count = 3 + int(
            times["previous_week"] >= times["month_start"]
        )
        self.assertIn(
            f"{current_month_count} Brasas",
            parser.boards["Mais Brasas — mês"][0],
        )
        self.assertIn(
            "3 Brasas",
            parser.boards["Mais Brasas — semana"][0],
        )

        total_achievements = parser.boards["Mais conquistas — geral"]
        self.assertIn("4 conquistas", total_achievements[0])
        self.assertIn("1 conquista", total_achievements[1])
        self.assertIn(
            (
                f"{1 + int(times['previous_week'] >= times['month_start'])} "
                f"{'conquista' if times['previous_week'] < times['month_start'] else 'conquistas'}"
            ),
            parser.boards["Mais conquistas — mês"][0],
        )
        self.assertIn(
            "1 conquista",
            parser.boards["Mais conquistas — semana"][0],
        )
        self.assertNotIn(
            "Hidden Player",
            response.get_data(as_text=True),
        )

    def test_rankings_require_login(self):
        guest_client = self.app.test_client()

        response = guest_client.get("/rankings")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/login")
