import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from platina_club import create_app
from platina_club.db import get_db, init_db
from platina_club.steam.api import (
    OWNED_GAMES_ENDPOINT,
    SteamAPIError,
    fetch_owned_games,
    parse_owned_games,
)
from platina_club.steam.config import SteamAPIConfigurationError
from platina_club.steam.library import sync_owned_games


class SteamOwnedGamesAPITests(unittest.TestCase):
    def test_complete_library_response_is_validated(self):
        payload = {
            "response": {
                "game_count": 2,
                "games": [
                    {"appid": 123, "name": "First Game", "playtime_forever": 45},
                    {"appid": 456, "name": "Second Game", "playtime_forever": 0},
                ],
            }
        }

        games = parse_owned_games(payload)

        self.assertEqual(
            games,
            [
                {
                    "steam_app_id": 123,
                    "name": "First Game",
                    "playtime_minutes": 45,
                },
                {
                    "steam_app_id": 456,
                    "name": "Second Game",
                    "playtime_minutes": 0,
                },
            ],
        )

    def test_private_incomplete_and_duplicate_library_responses_are_rejected(self):
        for payload in (
            {"response": {}},
            {
                "response": {
                    "game_count": 2,
                    "games": [{"appid": 123, "name": "Only One"}],
                }
            },
            {
                "response": {
                    "game_count": 2,
                    "games": [
                        {"appid": 123, "name": "First"},
                        {"appid": 123, "name": "Duplicate"},
                    ],
                }
            },
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(SteamAPIError):
                    parse_owned_games(payload)

    def test_empty_visible_library_is_distinct_from_private_library(self):
        self.assertEqual(
            parse_owned_games({"response": {"game_count": 0, "games": []}}),
            [],
        )
        self.assertEqual(
            parse_owned_games({"response": {"game_count": 0}}),
            [],
        )

    def test_fetch_uses_server_configured_key_and_owned_games_endpoint(self):
        payload = {"response": {"game_count": 0, "games": []}}
        with (
            patch(
                "platina_club.steam.api.get_steam_api_key",
                return_value="secret-test-key",
            ),
            patch(
                "platina_club.steam.api._request_json",
                return_value=payload,
            ) as request_json,
        ):
            games = fetch_owned_games("76561198000000001")

        self.assertEqual(games, [])
        request_json.assert_called_once_with(
            OWNED_GAMES_ENDPOINT,
            {
                "key": "secret-test-key",
                "steamid": "76561198000000001",
                "include_appinfo": "1",
                "include_played_free_games": "1",
            },
        )


class SteamLibrarySyncTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = str(Path(self.temp_dir.name) / "steam-library.sqlite3")
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
        self.user_id = get_db().execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            ("steam-player@example.com", "hash"),
        ).lastrowid
        get_db().execute(
            "INSERT INTO steam_links (user_id, steam_id) VALUES (?, ?)",
            (self.user_id, "76561198000000001"),
        )
        get_db().commit()

    def tearDown(self):
        self.app_context.pop()
        self.temp_dir.cleanup()

    def test_sync_inserts_and_updates_games_without_duplicates(self):
        responses = [
            [
                {
                    "steam_app_id": 123,
                    "name": "First Name",
                    "playtime_minutes": 15,
                }
            ],
            [
                {
                    "steam_app_id": 123,
                    "name": "Updated Name",
                    "playtime_minutes": 120,
                },
                {
                    "steam_app_id": 456,
                    "name": "New Game",
                    "playtime_minutes": 0,
                },
            ],
        ]

        def fetcher(steam_id):
            self.assertEqual(steam_id, "76561198000000001")
            return responses.pop(0)

        self.assertEqual(sync_owned_games(self.user_id, fetcher), 1)
        self.assertEqual(sync_owned_games(self.user_id, fetcher), 2)

        games = get_db().execute(
            """
            SELECT steam_app_id, name, playtime_minutes
            FROM games
            WHERE user_id = ?
            ORDER BY steam_app_id
            """,
            (self.user_id,),
        ).fetchall()
        self.assertEqual(
            [tuple(game) for game in games],
            [(123, "Updated Name", 120), (456, "New Game", 0)],
        )
        link = get_db().execute(
            "SELECT games_sync_status, games_synced_at FROM steam_links WHERE user_id = ?",
            (self.user_id,),
        ).fetchone()
        self.assertEqual(link["games_sync_status"], "success")
        self.assertIsNotNone(link["games_synced_at"])

    def test_initial_sync_failure_does_not_create_zero_progress_snapshot(self):
        def fail(_steam_id):
            raise SteamAPIError("Steam did not make this library available.")

        with self.assertRaises(SteamAPIError):
            sync_owned_games(self.user_id, fail)

        self.assertEqual(
            get_db().execute(
                "SELECT COUNT(*) FROM games WHERE user_id = ?",
                (self.user_id,),
            ).fetchone()[0],
            0,
        )
        link = get_db().execute(
            """
            SELECT games_sync_status, games_synced_at, games_sync_error
            FROM steam_links
            WHERE user_id = ?
            """,
            (self.user_id,),
        ).fetchone()
        self.assertEqual(link["games_sync_status"], "error")
        self.assertIsNone(link["games_synced_at"])
        self.assertIn("library", link["games_sync_error"])

    def test_failed_refresh_preserves_last_snapshot_and_marks_it_stale(self):
        original = [
            {
                "steam_app_id": 123,
                "name": "Last Known Name",
                "playtime_minutes": 60,
            }
        ]
        sync_owned_games(self.user_id, lambda _steam_id: original)

        def fail(_steam_id):
            raise SteamAPIError("Steam Web API is unavailable.")

        with self.assertRaises(SteamAPIError):
            sync_owned_games(self.user_id, fail)

        game = get_db().execute(
            """
            SELECT name, playtime_minutes, achievements_sync_status
            FROM games
            WHERE user_id = ? AND steam_app_id = ?
            """,
            (self.user_id, 123),
        ).fetchone()
        link = get_db().execute(
            "SELECT games_sync_status FROM steam_links WHERE user_id = ?",
            (self.user_id,),
        ).fetchone()
        self.assertEqual(game["name"], "Last Known Name")
        self.assertEqual(game["playtime_minutes"], 60)
        self.assertEqual(link["games_sync_status"], "stale")

    def test_missing_api_key_marks_initial_sync_as_error(self):
        with self.assertRaises(SteamAPIConfigurationError):
            sync_owned_games(self.user_id)

        status = get_db().execute(
            "SELECT games_sync_status FROM steam_links WHERE user_id = ?",
            (self.user_id,),
        ).fetchone()["games_sync_status"]
        self.assertEqual(status, "error")


if __name__ == "__main__":
    unittest.main()
