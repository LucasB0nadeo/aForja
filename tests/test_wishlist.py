import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from platina_club import create_app
from platina_club.db import get_db, init_db
from platina_club.steam.api import SteamAPIError


STORE_GAME = {
    "steam_app_id": 12345,
    "name": "Example Steam Game",
    "developer": "Example Studio",
    "release_date": "2024",
    "platforms": "Windows",
    "icon_url": "https://cdn.example/game.jpg",
}


class WishlistRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = str(Path(self.temp_dir.name) / "wishlist.sqlite3")
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

    def token(self, client, path="/wishlist/new"):
        response = client.get(path)
        self.assertEqual(response.status_code, 200)
        with client.session_transaction() as flask_session:
            return flask_session["_csrf_token"]

    def data(self, csrf_token, **overrides):
        values = {
            "csrf_token": csrf_token,
            "steam_app_id": "12345",
            "priority": "3",
            "notes": "Talvez nas férias.",
        }
        values.update(overrides)
        return values

    def test_create_read_update_and_delete_wishlist_item(self):
        client = self.create_client("wish-player@example.com")
        with patch(
            "platina_club.wishlist.fetch_store_game",
            return_value=STORE_GAME,
        ) as fetch:
            response = client.post(
                "/wishlist/new",
                data=self.data(self.token(client)),
            )
        self.assertEqual(response.status_code, 302)
        fetch.assert_called_once_with(12345)

        entry_id = get_db().execute(
            "SELECT id FROM wishlist_entries WHERE steam_app_id = 12345"
        ).fetchone()["id"]
        response = client.get("/wishlist")
        self.assertIn(b"Example Steam Game", response.data)
        self.assertIn(b"Talvez nas f\xc3\xa9rias.", response.data)

        response = client.post(
            f"/wishlist/{entry_id}/edit",
            data=self.data(
                self.token(client, f"/wishlist/{entry_id}/edit"),
                steam_app_id="99999",
                priority="5",
                notes="Prioridade máxima.",
            ),
        )
        self.assertEqual(response.status_code, 302)
        entry = get_db().execute(
            """
            SELECT steam_app_id, priority, notes FROM wishlist_entries
            WHERE id = ?
            """,
            (entry_id,),
        ).fetchone()
        self.assertEqual(tuple(entry), (12345, 5, "Prioridade máxima."))

        response = client.post(
            f"/wishlist/{entry_id}/delete",
            data={
                "csrf_token": self.token(client, f"/wishlist/{entry_id}/delete"),
                "confirm": "delete",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            get_db().execute("SELECT COUNT(*) FROM wishlist_entries").fetchone()[0],
            0,
        )
        self.assertEqual(
            get_db().execute(
                "SELECT name FROM steam_catalog WHERE steam_app_id = 12345"
            ).fetchone()[0],
            "Example Steam Game",
        )

    def test_duplicate_app_id_keeps_one_entry_and_reports_it(self):
        client = self.create_client("wish-duplicate@example.com")
        with patch(
            "platina_club.wishlist.fetch_store_game",
            return_value=STORE_GAME,
        ) as fetch:
            first = client.post(
                "/wishlist/new",
                data=self.data(self.token(client)),
            )
            duplicate = client.post(
                "/wishlist/new",
                data=self.data(self.token(client), priority="5"),
                follow_redirects=True,
            )

        self.assertEqual(first.status_code, 302)
        self.assertEqual(duplicate.status_code, 200)
        self.assertIn(
            b"Esse jogo j\xc3\xa1 est\xc3\xa1 na sua lista de desejos.",
            duplicate.data,
        )
        fetch.assert_called_once_with(12345)
        self.assertEqual(
            get_db().execute("SELECT COUNT(*) FROM wishlist_entries").fetchone()[0],
            1,
        )

    def test_invalid_input_and_unknown_app_are_not_saved(self):
        client = self.create_client("wish-invalid@example.com")
        for data in (
            self.data(self.token(client), priority="6"),
            self.data(self.token(client), steam_app_id="-1"),
        ):
            response = client.post("/wishlist/new", data=data)
            self.assertEqual(response.status_code, 400)

        with patch(
            "platina_club.wishlist.fetch_store_game",
            side_effect=SteamAPIError("Steam does not recognize this game AppID."),
        ):
            response = client.post(
                "/wishlist/new",
                data=self.data(self.token(client)),
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Steam does not recognize this game AppID.", response.data)
        self.assertEqual(
            get_db().execute("SELECT COUNT(*) FROM wishlist_entries").fetchone()[0],
            0,
        )

    def test_wishlist_is_private_and_other_accounts_cannot_modify_items(self):
        owner = self.create_client("wish-owner@example.com")
        other = self.create_client("wish-other@example.com")
        with patch(
            "platina_club.wishlist.fetch_store_game",
            return_value=STORE_GAME,
        ):
            owner.post(
                "/wishlist/new",
                data=self.data(self.token(owner)),
            )
        entry_id = get_db().execute(
            "SELECT id FROM wishlist_entries WHERE steam_app_id = 12345"
        ).fetchone()["id"]

        response = other.get("/wishlist")
        self.assertNotIn(b"Talvez nas f\xc3\xa9rias.", response.data)
        self.assertEqual(other.get(f"/wishlist/{entry_id}/edit").status_code, 404)
        self.assertEqual(other.get(f"/wishlist/{entry_id}/delete").status_code, 404)
        response = other.post(
            f"/wishlist/{entry_id}/edit",
            data=self.data(
                self.token(other),
                priority="1",
                notes="Acesso indevido",
            ),
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            get_db().execute(
                "SELECT priority FROM wishlist_entries WHERE id = ?",
                (entry_id,),
            ).fetchone()[0],
            3,
        )


if __name__ == "__main__":
    unittest.main()
