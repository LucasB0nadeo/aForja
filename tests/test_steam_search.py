import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from platina_club import create_app
from platina_club.db import init_db
from platina_club.steam.api import (
    SteamAPIError,
    parse_store_search,
    search_store_games,
)


SEARCH_RESULTS = [
    {"steam_app_id": 400, "name": "Portal"},
    {"steam_app_id": 620, "name": "Portal 2"},
]


class SteamStoreSearchTests(unittest.TestCase):
    def test_search_results_are_validated_and_non_apps_are_ignored(self):
        results = parse_store_search(
            {
                "items": [
                    {"id": 400, "type": "app", "name": "Portal"},
                    {"id": 620, "type": "app", "name": " Portal 2 "},
                    {"id": 123, "type": "sub", "name": "Portal Bundle"},
                ]
            }
        )

        self.assertEqual(results, SEARCH_RESULTS)
        with self.assertRaises(SteamAPIError):
            parse_store_search({"items": [{"id": 0, "type": "app", "name": "Bad"}]})

    def test_search_uses_public_store_endpoint(self):
        with patch(
            "platina_club.steam.api._request_json",
            return_value={
                "items": [{"id": 400, "type": "app", "name": "Portal"}]
            },
        ) as request_json:
            results = search_store_games("  Portal  ")

        self.assertEqual(results, [{"steam_app_id": 400, "name": "Portal"}])
        endpoint, params = request_json.call_args.args
        self.assertEqual(
            endpoint,
            "https://store.steampowered.com/api/storesearch/",
        )
        self.assertEqual(
            params,
            {"term": "Portal", "l": "brazilian", "cc": "br"},
        )

    def test_search_rejects_too_short_query(self):
        with self.assertRaises(SteamAPIError):
            search_store_games("a")


class SteamSearchRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret-key",
                "DATABASE": str(Path(self.temp_dir.name) / "search.sqlite3"),
            }
        )
        with self.app.app_context():
            init_db()

    def tearDown(self):
        self.temp_dir.cleanup()

    def create_client(self):
        client = self.app.test_client()
        client.get("/register")
        with client.session_transaction() as flask_session:
            csrf_token = flask_session["_csrf_token"]
        response = client.post(
            "/register",
            data={
                "csrf_token": csrf_token,
                "email": "search-player@example.com",
                "password": "test-password",
            },
        )
        self.assertEqual(response.status_code, 302)
        return client

    def test_authenticated_search_returns_game_choices(self):
        client = self.create_client()
        with patch(
            "platina_club.steam.routes.search_store_games",
            return_value=SEARCH_RESULTS,
        ) as search:
            response = client.get("/steam/search?q=Portal")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"results": SEARCH_RESULTS})
        search.assert_called_once_with("Portal")

    def test_search_errors_are_reported(self):
        client = self.create_client()
        with patch(
            "platina_club.steam.routes.search_store_games"
        ) as search:
            response = client.get("/steam/search?q=x")
            search.assert_not_called()
        self.assertEqual(response.status_code, 400)

        with patch(
            "platina_club.steam.routes.search_store_games",
            side_effect=SteamAPIError("Steam Web API is unavailable."),
        ):
            response = client.get("/steam/search?q=Portal")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.get_json()["error"],
            "Steam Web API is unavailable.",
        )


if __name__ == "__main__":
    unittest.main()
