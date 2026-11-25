import tempfile
import unittest
from pathlib import Path

from platina_club import create_app
from platina_club.db import get_db, init_db


class ManualAchievementTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = str(Path(self.temp_dir.name) / "achievements.sqlite3")
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
            csrf = flask_session["_csrf_token"]
        response = client.post(
            "/register",
            data={
                "csrf_token": csrf,
                "email": email,
                "password": "test-password",
            },
        )
        self.assertEqual(response.status_code, 302)
        return client

    def csrf_token(self, client, path):
        response = client.get(path)
        self.assertEqual(response.status_code, 200)
        with client.session_transaction() as flask_session:
            return flask_session["_csrf_token"]

    def create_game(self, client):
        token = self.csrf_token(client, "/games/new")
        response = client.post(
            "/games/new",
            data={
                "csrf_token": token,
                "name": "Celeste",
                "platform": "PC",
                "developer": "Maddy Makes Games",
                "release_year": "2018",
            },
        )
        self.assertEqual(response.status_code, 302)
        return get_db().execute(
            "SELECT id FROM games ORDER BY id DESC LIMIT 1"
        ).fetchone()["id"]

    def achievement_data(self, csrf, **overrides):
        data = {
            "csrf_token": csrf,
            "name": "First Steps",
            "description": "Complete the first chapter.",
            "rarity": "Common",
        }
        data.update(overrides)
        return data

    def test_manual_achievement_crud_and_unlock_state(self):
        client = self.create_client("player@example.com")
        game_id = self.create_game(client)
        token = self.csrf_token(
            client,
            f"/games/{game_id}/achievements/new",
        )
        response = client.post(
            f"/games/{game_id}/achievements/new",
            data=self.achievement_data(token),
        )
        self.assertEqual(response.status_code, 302)
        achievement_id = get_db().execute(
            "SELECT id FROM achievements WHERE game_id = ?",
            (game_id,),
        ).fetchone()["id"]

        response = client.get(f"/games/{game_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"First Steps", response.data)
        self.assertIn(b"Bloqueada", response.data)

        token = self.csrf_token(
            client,
            f"/games/{game_id}/achievements/{achievement_id}/edit",
        )
        response = client.post(
            f"/games/{game_id}/achievements/{achievement_id}/edit",
            data=self.achievement_data(
                token,
                name="Chapter One",
                rarity="Rare",
                unlocked="1",
            ),
        )
        self.assertEqual(response.status_code, 302)
        achievement = get_db().execute(
            """
            SELECT name, description, rarity, unlocked, unlocked_at
            FROM achievements
            WHERE id = ?
            """,
            (achievement_id,),
        ).fetchone()
        self.assertEqual(achievement["name"], "Chapter One")
        self.assertEqual(achievement["rarity"], "Rare")
        self.assertEqual(achievement["unlocked"], 1)
        self.assertIsNotNone(achievement["unlocked_at"])

    def test_invalid_manual_achievement_is_not_saved(self):
        client = self.create_client("player@example.com")
        game_id = self.create_game(client)
        token = self.csrf_token(
            client,
            f"/games/{game_id}/achievements/new",
        )
        response = client.post(
            f"/games/{game_id}/achievements/new",
            data=self.achievement_data(token, description="   ", rarity=""),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            get_db().execute(
                "SELECT COUNT(*) FROM achievements WHERE game_id = ?",
                (game_id,),
            ).fetchone()[0],
            0,
        )

    def test_achievement_crud_cannot_cross_account_or_edit_steam_data(self):
        owner = self.create_client("owner@example.com")
        other = self.create_client("other@example.com")
        game_id = self.create_game(owner)
        achievement_token = self.csrf_token(
            owner,
            f"/games/{game_id}/achievements/new",
        )
        owner.post(
            f"/games/{game_id}/achievements/new",
            data=self.achievement_data(achievement_token),
        )
        achievement_id = get_db().execute(
            "SELECT id FROM achievements WHERE game_id = ?",
            (game_id,),
        ).fetchone()["id"]

        self.assertEqual(other.get(f"/games/{game_id}").status_code, 404)
        self.assertEqual(
            other.get(
                f"/games/{game_id}/achievements/{achievement_id}/edit"
            ).status_code,
            404,
        )
        token = self.csrf_token(other, "/games/new")
        response = other.post(
            f"/games/{game_id}/achievements/{achievement_id}/edit",
            data=self.achievement_data(token, name="Unauthorized"),
        )
        self.assertEqual(response.status_code, 404)

        owner_id = get_db().execute(
            "SELECT id FROM users WHERE email = ?",
            ("owner@example.com",),
        ).fetchone()["id"]
        steam_game_id = get_db().execute(
            """
            INSERT INTO games (
                user_id, source, name, steam_app_id
            ) VALUES (?, 'steam', ?, ?)
            """,
            (owner_id, "Steam Game", 765),
        ).lastrowid
        steam_achievement_id = get_db().execute(
            """
            INSERT INTO achievements (
                user_id, game_id, source, steam_api_name, name
            ) VALUES (?, ?, 'steam', ?, ?)
            """,
            (owner_id, steam_game_id, "ACH_TEST", "Steam Achievement"),
        ).lastrowid
        get_db().commit()

        self.assertEqual(owner.get(f"/games/{steam_game_id}").status_code, 200)
        self.assertEqual(
            owner.get(
                f"/games/{steam_game_id}/achievements/{steam_achievement_id}/edit"
            ).status_code,
            404,
        )

    def test_achievement_delete_requires_confirmation_and_preserves_game(self):
        client = self.create_client("player@example.com")
        game_id = self.create_game(client)
        token = self.csrf_token(
            client,
            f"/games/{game_id}/achievements/new",
        )
        client.post(
            f"/games/{game_id}/achievements/new",
            data=self.achievement_data(token),
        )
        achievement_id = get_db().execute(
            "SELECT id FROM achievements WHERE game_id = ?",
            (game_id,),
        ).fetchone()["id"]

        response = client.get(
            f"/games/{game_id}/achievements/{achievement_id}/delete"
        )
        self.assertEqual(response.status_code, 200)
        token = self.csrf_token(
            client,
            f"/games/{game_id}/achievements/{achievement_id}/delete",
        )
        response = client.post(
            f"/games/{game_id}/achievements/{achievement_id}/delete",
            data={"csrf_token": token, "confirm": "cancel"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIsNotNone(
            get_db().execute(
                "SELECT id FROM achievements WHERE id = ?",
                (achievement_id,),
            ).fetchone()
        )

        token = self.csrf_token(
            client,
            f"/games/{game_id}/achievements/{achievement_id}/delete",
        )
        response = client.post(
            f"/games/{game_id}/achievements/{achievement_id}/delete",
            data={"csrf_token": token, "confirm": "delete"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(
            get_db().execute(
                "SELECT id FROM achievements WHERE id = ?",
                (achievement_id,),
            ).fetchone()
        )
        self.assertIsNotNone(
            get_db().execute("SELECT id FROM games WHERE id = ?", (game_id,)).fetchone()
        )

    def test_game_cascade_requires_confirmation_and_can_be_cancelled(self):
        client = self.create_client("player@example.com")
        game_id = self.create_game(client)
        token = self.csrf_token(
            client,
            f"/games/{game_id}/achievements/new",
        )
        client.post(
            f"/games/{game_id}/achievements/new",
            data=self.achievement_data(token),
        )
        achievement_id = get_db().execute(
            "SELECT id FROM achievements WHERE game_id = ?",
            (game_id,),
        ).fetchone()["id"]

        response = client.get(f"/games/{game_id}/delete")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"1 conquista", response.data)
        self.assertIsNotNone(
            get_db().execute("SELECT id FROM games WHERE id = ?", (game_id,)).fetchone()
        )
        client.get("/games")
        self.assertIsNotNone(
            get_db().execute(
                "SELECT id FROM achievements WHERE id = ?",
                (achievement_id,),
            ).fetchone()
        )

        token = self.csrf_token(client, f"/games/{game_id}/delete")
        response = client.post(
            f"/games/{game_id}/delete",
            data={"csrf_token": token, "confirm": "delete"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(
            get_db().execute("SELECT id FROM games WHERE id = ?", (game_id,)).fetchone()
        )
        self.assertIsNone(
            get_db().execute(
                "SELECT id FROM achievements WHERE id = ?",
                (achievement_id,),
            ).fetchone()
        )


if __name__ == "__main__":
    unittest.main()
