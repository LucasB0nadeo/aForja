import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from platina_club import create_app
from platina_club.db import get_db, init_db
from platina_club.steam.achievements import (
    SteamGameRequiredError,
    sync_game_achievements,
)
from platina_club.steam.api import (
    GAME_SCHEMA_ENDPOINT,
    GLOBAL_ACHIEVEMENTS_ENDPOINT,
    PLAYER_ACHIEVEMENTS_ENDPOINT,
    SteamAPIError,
    fetch_game_achievements,
    merge_player_achievements,
)


STEAM_ID = "76561198000000001"
GAME_ACHIEVEMENTS = [
    {
        "steam_api_name": "ACH_WIN",
        "name": "Winner",
        "description": "Win a match.",
        "rarity": None,
        "global_percent": 42.5,
        "icon_url": "https://cdn.akamai.steamstatic.com/achievement/ach-win.jpg",
        "icon_gray_url": "https://cdn.akamai.steamstatic.com/achievement/ach-win-gray.jpg",
        "unlocked": 1,
        "unlocked_at": "1970-01-01 00:01:40",
    }
]


class SteamAchievementAPITests(unittest.TestCase):
    def test_global_percentages_are_merged_with_icon_fields(self):
        definition = {
            "steam_api_name": "ACH_WIN",
            "name": "Winner",
            "description": "Win a match.",
            "icon_url": "https://cdn.akamai.steamstatic.com/achievement/ach-win.jpg",
            "icon_gray_url": "https://cdn.akamai.steamstatic.com/achievement/ach-win-gray.jpg",
        }
        merged = merge_player_achievements(
            [definition],
            {
                "playerstats": {
                    "achievements": [
                        {"apiname": "ACH_WIN", "achieved": 1, "unlocktime": 100}
                    ]
                }
            },
            {
                "achievementpercentages": {
                    "achievements": [
                        {"name": "ACH_WIN", "percent": "42.5"}
                    ]
                }
            },
        )

        self.assertEqual(merged[0]["global_percent"], 42.5)
        self.assertEqual(
            merged[0]["icon_url"],
            "https://cdn.akamai.steamstatic.com/achievement/ach-win.jpg",
        )
        self.assertEqual(
            merged[0]["icon_gray_url"],
            "https://cdn.akamai.steamstatic.com/achievement/ach-win-gray.jpg",
        )

    def test_fetch_uses_schema_and_player_achievement_endpoints(self):
        schema = {
            "game": {
                "availableGameStats": {
                    "achievements": [
                        {
                            "name": "ACH_WIN",
                            "displayName": "Winner",
                            "description": "Win a match.",
                            "icon": "https://cdn.akamai.steamstatic.com/achievement/ach-win.jpg",
                            "icongray": "https://cdn.akamai.steamstatic.com/achievement/ach-win-gray.jpg",
                        }
                    ]
                }
            }
        }
        player = {
            "playerstats": {
                "achievements": [
                    {"apiname": "ACH_WIN", "achieved": 1, "unlocktime": 100}
                ]
            }
        }
        global_percentages = {
            "achievementpercentages": {
                "achievements": [
                    {"name": "ACH_WIN", "percent": "42.5"}
                ]
            }
        }
        with (
            patch(
                "platina_club.steam.api.get_steam_api_key",
                return_value="configured-key",
            ),
            patch(
                "platina_club.steam.api._request_json",
                side_effect=[schema, player, global_percentages],
            ) as request_json,
        ):
            result = fetch_game_achievements(STEAM_ID, 12345)

        self.assertEqual(result, GAME_ACHIEVEMENTS)
        self.assertEqual(
            request_json.call_args_list[0].args,
            (
                GAME_SCHEMA_ENDPOINT,
                {"key": "configured-key", "appid": 12345},
            ),
        )
        self.assertEqual(
            request_json.call_args_list[1].args,
            (
                PLAYER_ACHIEVEMENTS_ENDPOINT,
                {
                    "key": "configured-key",
                    "steamid": STEAM_ID,
                    "appid": 12345,
                    "l": "english",
                },
            ),
        )
        self.assertEqual(
            request_json.call_args_list[2].args,
            (
                GLOBAL_ACHIEVEMENTS_ENDPOINT,
                {"gameid": 12345, "format": "json"},
            ),
        )

    def test_game_without_defined_achievements_needs_no_player_stats(self):
        with (
            patch(
                "platina_club.steam.api.get_steam_api_key",
                return_value="configured-key",
            ),
            patch(
                "platina_club.steam.api._request_json",
                return_value={
                    "game": {"availableGameStats": {"achievements": []}}
                },
            ) as request_json,
        ):
            result = fetch_game_achievements(STEAM_ID, 12345)

        self.assertEqual(result, [])
        request_json.assert_called_once_with(
            GAME_SCHEMA_ENDPOINT,
            {"key": "configured-key", "appid": 12345},
        )

    def test_incomplete_or_duplicate_player_stats_are_rejected(self):
        definition = {
            "steam_api_name": "ACH_WIN",
            "name": "Winner",
            "description": "",
        }
        for achievements in (
            [],
            [
                {"apiname": "ACH_WIN", "achieved": 1},
                {"apiname": "ACH_WIN", "achieved": 0},
            ],
            [{"apiname": "ACH_WIN", "achieved": 2}],
        ):
            with self.subTest(achievements=achievements):
                with self.assertRaises(SteamAPIError):
                    merge_player_achievements(
                        [definition],
                        {"playerstats": {"achievements": achievements}},
                    )


class SteamAchievementSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = str(Path(self.temp_dir.name) / "steam-achievements.sqlite3")
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret-key",
                "DATABASE": database_path,
                "STEAM_API_KEY": None,
            }
        )
        self.app_context = self.app.app_context()
        self.app_context.push()
        init_db()

        db = get_db()
        self.user_id = db.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            ("steam-player@example.com", "hash"),
        ).lastrowid
        db.execute(
            "INSERT INTO steam_links (user_id, steam_id) VALUES (?, ?)",
            (self.user_id, STEAM_ID),
        )
        self.game_id = db.execute(
            """
            INSERT INTO games (user_id, source, name, steam_app_id)
            VALUES (?, 'steam', 'Example Game', 12345)
            """,
            (self.user_id,),
        ).lastrowid
        db.commit()

    def tearDown(self):
        self.app_context.pop()
        self.temp_dir.cleanup()

    def test_sync_persists_unlocked_state_and_removes_obsolete_definitions(self):
        first = [
            GAME_ACHIEVEMENTS[0],
            {
                "steam_api_name": "ACH_OLD",
                "name": "Old",
                "description": "",
                "rarity": None,
                "unlocked": 0,
                "unlocked_at": None,
            },
        ]
        sync_game_achievements(
            self.user_id,
            self.game_id,
            lambda _steam_id, _app_id: first,
        )
        sync_game_achievements(
            self.user_id,
            self.game_id,
            lambda _steam_id, _app_id: [
                {
                    **GAME_ACHIEVEMENTS[0],
                    "name": "Updated Winner",
                    "unlocked": 0,
                    "unlocked_at": None,
                }
            ],
        )

        achievements = get_db().execute(
            """
            SELECT steam_api_name, name, unlocked, unlocked_at, source,
                   global_percent, icon_url, icon_gray_url
            FROM achievements
            WHERE game_id = ?
            """,
            (self.game_id,),
        ).fetchall()
        self.assertEqual(
            [tuple(row) for row in achievements],
            [(
                "ACH_WIN",
                "Updated Winner",
                0,
                None,
                "steam",
                42.5,
                "https://cdn.akamai.steamstatic.com/achievement/ach-win.jpg",
                "https://cdn.akamai.steamstatic.com/achievement/ach-win-gray.jpg",
            )],
        )
        game = get_db().execute(
            """
            SELECT achievements_sync_status, achievements_synced_at,
                   achievements_sync_error
            FROM games WHERE id = ?
            """,
            (self.game_id,),
        ).fetchone()
        self.assertEqual(game["achievements_sync_status"], "success")
        self.assertIsNotNone(game["achievements_synced_at"])
        self.assertIsNone(game["achievements_sync_error"])

    def test_failed_refresh_preserves_snapshot_and_marks_it_stale(self):
        sync_game_achievements(
            self.user_id,
            self.game_id,
            lambda _steam_id, _app_id: GAME_ACHIEVEMENTS,
        )

        def fail(_steam_id, _app_id):
            raise SteamAPIError("Steam Web API is unavailable.")

        with self.assertRaises(SteamAPIError):
            sync_game_achievements(self.user_id, self.game_id, fail)

        achievement = get_db().execute(
            "SELECT name, unlocked FROM achievements WHERE game_id = ?",
            (self.game_id,),
        ).fetchone()
        game = get_db().execute(
            """
            SELECT achievements_sync_status, achievements_synced_at,
                   achievements_sync_error
            FROM games WHERE id = ?
            """,
            (self.game_id,),
        ).fetchone()
        self.assertEqual(tuple(achievement), ("Winner", 1))
        self.assertEqual(game["achievements_sync_status"], "stale")
        self.assertIsNotNone(game["achievements_synced_at"])
        self.assertIn("unavailable", game["achievements_sync_error"])

    def test_initial_failure_does_not_create_empty_success_snapshot(self):
        def fail(_steam_id, _app_id):
            raise SteamAPIError("Steam Web API is unavailable.")

        with self.assertRaises(SteamAPIError):
            sync_game_achievements(self.user_id, self.game_id, fail)

        game = get_db().execute(
            """
            SELECT achievements_sync_status, achievements_synced_at
            FROM games WHERE id = ?
            """,
            (self.game_id,),
        ).fetchone()
        self.assertEqual(game["achievements_sync_status"], "error")
        self.assertIsNone(game["achievements_synced_at"])
        self.assertEqual(
            get_db().execute(
                "SELECT COUNT(*) FROM achievements WHERE game_id = ?",
                (self.game_id,),
            ).fetchone()[0],
            0,
        )

    def test_game_with_no_defined_achievements_syncs_as_empty_success(self):
        count = sync_game_achievements(
            self.user_id,
            self.game_id,
            lambda _steam_id, _app_id: [],
        )

        game = get_db().execute(
            """
            SELECT achievements_sync_status, achievements_synced_at
            FROM games WHERE id = ?
            """,
            (self.game_id,),
        ).fetchone()
        self.assertEqual(count, 0)
        self.assertEqual(game["achievements_sync_status"], "success")
        self.assertIsNotNone(game["achievements_synced_at"])
        self.assertEqual(
            get_db().execute(
                "SELECT COUNT(*) FROM achievements WHERE game_id = ?",
                (self.game_id,),
            ).fetchone()[0],
            0,
        )

    def test_progress_thresholds_are_idempotent_and_awards_are_permanent(self):
        definitions = [
            {
                "steam_api_name": f"ACH_{index}",
                "name": f"Achievement {index}",
                "description": "",
                "rarity": None,
                "unlocked": int(index == 0),
                "unlocked_at": None,
            }
            for index in range(4)
        ]
        sync_game_achievements(
            self.user_id,
            self.game_id,
            lambda _steam_id, _app_id: definitions,
        )

        awards = get_db().execute(
            """
            SELECT badge_type FROM badge_awards
            WHERE user_id = ? AND steam_app_id = 12345
            ORDER BY badge_type
            """,
            (self.user_id,),
        ).fetchall()
        self.assertEqual([row["badge_type"] for row in awards], ["copper_sparks"])

        sync_game_achievements(
            self.user_id,
            self.game_id,
            lambda _steam_id, _app_id: [
                {**item, "unlocked": 1, "unlocked_at": "1970-01-01 00:01:40"}
                for item in definitions
            ],
        )
        sync_game_achievements(
            self.user_id,
            self.game_id,
            lambda _steam_id, _app_id: [
                {**item, "unlocked": 1, "unlocked_at": "1970-01-01 00:01:40"}
                for item in definitions
            ],
        )
        get_db().execute(
            """
            UPDATE achievements SET unlocked = 0, unlocked_at = NULL
            WHERE game_id = ?
            """,
            (self.game_id,),
        )
        sync_game_achievements(
            self.user_id,
            self.game_id,
            lambda _steam_id, _app_id: [
                {**item, "unlocked": 0, "unlocked_at": None}
                for item in definitions
            ],
        )

        awards = get_db().execute(
            """
            SELECT badge_type FROM badge_awards
            WHERE user_id = ? AND steam_app_id = 12345
            """,
            (self.user_id,),
        ).fetchall()
        self.assertEqual(
            {row["badge_type"] for row in awards},
            {
                "copper_sparks",
                "bronze_hammer",
                "silver_hammer",
                "gold_hammer",
                "ember",
            },
        )
        self.assertEqual(len(awards), 5)

    def test_manual_games_are_not_steam_sync_targets(self):
        manual_game_id = get_db().execute(
            """
            INSERT INTO games (
                user_id, source, name, platform, developer, release_year
            ) VALUES (?, 'manual', 'Manual Game', 'PC', 'Developer', 2025)
            """,
            (self.user_id,),
        ).lastrowid
        get_db().commit()
        with self.assertRaises(SteamGameRequiredError):
            sync_game_achievements(
                self.user_id,
                manual_game_id,
                lambda _steam_id, _app_id: [],
            )
        self.assertEqual(
            get_db().execute(
                "SELECT achievements_sync_status FROM games WHERE id = ?",
                (manual_game_id,),
            ).fetchone()[0],
            "never",
        )


class SteamAchievementRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = str(Path(self.temp_dir.name) / "steam-routes.sqlite3")
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret-key",
                "DATABASE": database_path,
                "STEAM_API_KEY": None,
            }
        )
        self.app_context = self.app.app_context()
        self.app_context.push()
        init_db()
        self.client = self.app.test_client()
        response = self.client.get("/register")
        with self.client.session_transaction() as flask_session:
            csrf_token = flask_session["_csrf_token"]
        response = self.client.post(
            "/register",
            data={
                "csrf_token": csrf_token,
                "email": "route-player@example.com",
                "password": "test-password",
            },
        )
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as flask_session:
            self.user_id = flask_session["user_id"]
        self.game_id = self.add_steam_game()

    def tearDown(self):
        self.app_context.pop()
        self.temp_dir.cleanup()

    def add_steam_game(self):
        db = get_db()
        db.execute(
            "INSERT INTO steam_links (user_id, steam_id) VALUES (?, ?)",
            (self.user_id, STEAM_ID),
        )
        game_id = db.execute(
            """
            INSERT INTO games (user_id, source, name, steam_app_id)
            VALUES (?, 'steam', 'Route Game', 7654)
            """,
            (self.user_id,),
        ).lastrowid
        db.commit()
        return game_id

    def test_opening_game_syncs_missing_and_expired_snapshots_only(self):
        with patch(
            "platina_club.steam.achievements.fetch_game_achievements",
            return_value=GAME_ACHIEVEMENTS,
        ) as fetch:
            first = self.client.get(f"/games/{self.game_id}")
        self.assertEqual(first.status_code, 200)
        self.assertIn(b"Winner", first.data)
        self.assertIn(b"1 de 1", first.data)
        self.assertIn("Brasa do Ferreiro".encode(), first.data)
        fetch.assert_called_once_with(STEAM_ID, 7654)

        with patch(
            "platina_club.steam.achievements.fetch_game_achievements"
        ) as fetch:
            self.client.get(f"/games/{self.game_id}")
        fetch.assert_not_called()

        get_db().execute(
            """
            UPDATE games SET achievements_synced_at = datetime('now', '-16 minutes')
            WHERE id = ?
            """,
            (self.game_id,),
        )
        get_db().commit()
        with patch(
            "platina_club.steam.achievements.fetch_game_achievements",
            return_value=GAME_ACHIEVEMENTS,
        ) as fetch:
            expired = self.client.get(f"/games/{self.game_id}")
        self.assertEqual(expired.status_code, 200)
        fetch.assert_called_once_with(STEAM_ID, 7654)

    def test_failed_first_sync_is_visible_without_claiming_zero_progress(self):
        with patch(
            "platina_club.steam.achievements.fetch_game_achievements",
            side_effect=SteamAPIError("Steam stats are private."),
        ):
            response = self.client.get(f"/games/{self.game_id}")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Steam stats are private.", response.data)
        self.assertIn(b"conquistas ainda n\xc3\xa3o est\xc3\xa3o dispon\xc3\xadveis", response.data)
        self.assertNotIn(b"Steam n\xc3\xa3o definiu conquistas", response.data)
        self.assertEqual(
            get_db().execute(
                "SELECT achievements_sync_status FROM games WHERE id = ?",
                (self.game_id,),
            ).fetchone()[0],
            "error",
        )

    def test_manual_sync_action_is_available_and_works(self):
        get_db().execute(
            """
            UPDATE games
            SET achievements_sync_status = 'success',
                achievements_synced_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (self.game_id,),
        )
        get_db().commit()
        self.client.get(f"/games/{self.game_id}")
        with self.client.session_transaction() as flask_session:
            csrf_token = flask_session["_csrf_token"]

        with patch(
            "platina_club.steam.achievements.fetch_game_achievements",
            return_value=GAME_ACHIEVEMENTS,
        ) as fetch:
            response = self.client.post(
                f"/games/{self.game_id}/achievements/sync",
                data={"csrf_token": csrf_token},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, f"/games/{self.game_id}")
        fetch.assert_called_once_with(STEAM_ID, 7654)

    def test_unlinked_steam_game_keeps_snapshot_without_remote_sync(self):
        sync_game_achievements(
            self.user_id,
            self.game_id,
            lambda _steam_id, _app_id: GAME_ACHIEVEMENTS,
        )
        self.client.get("/dashboard")
        with self.client.session_transaction() as flask_session:
            csrf_token = flask_session["_csrf_token"]
        self.client.post(
            "/steam/unlink",
            data={"csrf_token": csrf_token},
        )
        with patch(
            "platina_club.steam.achievements.fetch_game_achievements"
        ) as fetch:
            response = self.client.get(f"/games/{self.game_id}")

        self.assertEqual(response.status_code, 200)
        fetch.assert_not_called()
        self.assertEqual(
            get_db().execute(
                "SELECT COUNT(*) FROM achievements WHERE game_id = ?",
                (self.game_id,),
            ).fetchone()[0],
            1,
        )


if __name__ == "__main__":
    unittest.main()
