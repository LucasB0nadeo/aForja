import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from platina_club import create_app
from platina_club.db import get_db, init_db
from platina_club.steam.api import SteamAPIError, fetch_store_game, parse_store_game


STORE_GAME = {
    "steam_app_id": 12345,
    "name": "Example Steam Game",
    "developer": "Example Studio",
    "release_date": "2024",
    "platforms": "Windows",
    "icon_url": "https://cdn.example/game.jpg",
}


class SteamStoreAPITests(unittest.TestCase):
    def test_store_details_are_parsed_and_invalid_apps_are_rejected(self):
        payload = {
            "12345": {
                "success": True,
                "data": {
                    "type": "game",
                    "name": "Example Steam Game",
                    "developers": ["Example Studio"],
                    "release_date": {"date": "2024"},
                    "platforms": {"windows": True, "mac": False},
                    "header_image": "https://cdn.example/game.jpg",
                },
            }
        }
        self.assertEqual(parse_store_game(payload, 12345), STORE_GAME)

        with self.assertRaises(SteamAPIError):
            parse_store_game({"12345": {"success": False}}, 12345)

    def test_fetch_uses_public_store_endpoint_without_web_api_key(self):
        payload = {
            "12345": {
                "success": True,
                "data": {
                    "type": "game",
                    "name": "Example Steam Game",
                    "developers": ["Example Studio"],
                    "release_date": {"date": "2024"},
                    "platforms": {"windows": True},
                    "header_image": "https://cdn.example/game.jpg",
                },
            }
        }
        with patch(
            "platina_club.steam.api._request_json",
            return_value=payload,
        ) as request_json:
            result = fetch_store_game(12345)

        self.assertEqual(result, STORE_GAME)
        endpoint, params = request_json.call_args.args
        self.assertEqual(endpoint, "https://store.steampowered.com/api/appdetails")
        self.assertEqual(params, {"appids": 12345, "l": "english"})


class ReviewRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = str(Path(self.temp_dir.name) / "reviews.sqlite3")
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret-key",
                "DATABASE": database_path,
            }
        )
        self.app_context = self.app.app_context()
        self.app_context.push()
        init_db()

    def tearDown(self):
        self.app_context.pop()
        self.temp_dir.cleanup()

    def create_client(self, email):
        client = self.app.test_client()
        client.get("/register")
        with client.session_transaction() as flask_session:
            csrf_token = flask_session["_csrf_token"]
        response = client.post(
            "/register",
            data={
                "csrf_token": csrf_token,
                "email": email,
                "password": "test-password",
            },
        )
        self.assertEqual(response.status_code, 302)
        return client

    def token(self, client, path="/reviews/new"):
        response = client.get(path)
        self.assertEqual(response.status_code, 200)
        with client.session_transaction() as flask_session:
            return flask_session["_csrf_token"]

    def review_data(self, csrf_token, **overrides):
        data = {
            "csrf_token": csrf_token,
            "steam_app_id": "12345",
            "review_text": "Muito divertido.",
            "rating": "5",
        }
        data.update(overrides)
        return data

    def test_create_read_update_and_delete_private_review(self):
        client = self.create_client("reviewer@example.com")
        csrf_token = self.token(client)
        with patch(
            "platina_club.reviews.fetch_store_game",
            return_value=STORE_GAME,
        ) as fetch:
            response = client.post(
                "/reviews/new",
                data=self.review_data(csrf_token),
            )
        self.assertEqual(response.status_code, 302)
        fetch.assert_called_once_with(12345)

        review_id = get_db().execute(
            "SELECT id FROM game_reviews WHERE steam_app_id = 12345"
        ).fetchone()["id"]
        response = client.get("/reviews")
        self.assertIn(b"Example Steam Game", response.data)
        self.assertIn(b"Muito divertido.", response.data)

        response = client.post(
            f"/reviews/{review_id}/edit",
            data=self.review_data(
                self.token(client, f"/reviews/{review_id}/edit"),
                steam_app_id="99999",
                review_text="Ainda melhor.",
                rating="4",
            ),
        )
        self.assertEqual(response.status_code, 302)
        review = get_db().execute(
            "SELECT steam_app_id, review_text, rating FROM game_reviews WHERE id = ?",
            (review_id,),
        ).fetchone()
        self.assertEqual(tuple(review), (12345, "Ainda melhor.", 4))

        response = client.post(
            f"/reviews/{review_id}/delete",
            data={
                "csrf_token": self.token(client, f"/reviews/{review_id}/delete"),
                "confirm": "delete",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            get_db().execute("SELECT COUNT(*) FROM game_reviews").fetchone()[0],
            0,
        )
        self.assertEqual(
            get_db().execute("SELECT name FROM steam_catalog WHERE steam_app_id = 12345").fetchone()[0],
            "Example Steam Game",
        )

    def test_duplicate_and_invalid_review_inputs_are_not_saved(self):
        client = self.create_client("duplicate-review@example.com")
        csrf_token = self.token(client)
        with patch(
            "platina_club.reviews.fetch_store_game",
            return_value=STORE_GAME,
        ) as fetch:
            created = client.post(
                "/reviews/new",
                data=self.review_data(csrf_token),
            )
        self.assertEqual(created.status_code, 302)

        response = client.post(
            "/reviews/new",
            data=self.review_data(
                self.token(client),
                review_text="Duplicada.",
                rating="3",
            ),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"edite a avalia\xc3\xa7\xc3\xa3o existente", response.data)
        self.assertIn(b"/reviews/1/edit", response.data)
        fetch.assert_called_once_with(12345)

        for data in (
            self.review_data(self.token(client), rating="6"),
            self.review_data(self.token(client), steam_app_id="not-an-app"),
            self.review_data(self.token(client), review_text="   "),
        ):
            response = client.post("/reviews/new", data=data)
            self.assertEqual(response.status_code, 400)

        self.assertEqual(
            get_db().execute("SELECT COUNT(*) FROM game_reviews").fetchone()[0],
            1,
        )

    def test_invalid_store_app_id_is_reported_without_creating_review(self):
        client = self.create_client("invalid-app@example.com")
        with patch(
            "platina_club.reviews.fetch_store_game",
            side_effect=SteamAPIError("Steam does not recognize this game AppID."),
        ):
            response = client.post(
                "/reviews/new",
                data=self.review_data(self.token(client)),
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Steam does not recognize this game AppID.", response.data)
        self.assertEqual(
            get_db().execute("SELECT COUNT(*) FROM game_reviews").fetchone()[0],
            0,
        )

    def test_reviews_cannot_be_seen_or_changed_by_another_account(self):
        owner = self.create_client("review-owner@example.com")
        other = self.create_client("review-other@example.com")
        with patch(
            "platina_club.reviews.fetch_store_game",
            return_value=STORE_GAME,
        ):
            owner.post(
                "/reviews/new",
                data=self.review_data(self.token(owner)),
            )
        review_id = get_db().execute(
            "SELECT id FROM game_reviews WHERE steam_app_id = 12345"
        ).fetchone()["id"]

        response = other.get("/reviews")
        self.assertNotIn(b"Muito divertido.", response.data)
        self.assertEqual(other.get(f"/reviews/{review_id}/edit").status_code, 404)
        self.assertEqual(other.get(f"/reviews/{review_id}/delete").status_code, 404)
        response = other.post(
            f"/reviews/{review_id}/edit",
            data=self.review_data(
                self.token(other),
                review_text="Tentativa de alteração",
            ),
        )
        self.assertEqual(response.status_code, 404)

        self.assertEqual(
            get_db().execute(
                "SELECT review_text FROM game_reviews WHERE id = ?",
                (review_id,),
            ).fetchone()[0],
            "Muito divertido.",
        )


if __name__ == "__main__":
    unittest.main()
