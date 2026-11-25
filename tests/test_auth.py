import unittest
import tempfile
from pathlib import Path

from werkzeug.security import check_password_hash

from platina_club import create_app
from platina_club.db import get_db, init_db


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = str(Path(self.temp_dir.name) / "auth.sqlite3")
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

    def get_csrf_token(self, client, path):
        response = client.get(path)
        self.assertEqual(response.status_code, 200)
        with client.session_transaction() as flask_session:
            return flask_session["_csrf_token"]

    def test_registration_hashes_password_and_protects_dashboard(self):
        client = self.app.test_client()
        response = client.get("/dashboard")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/login")

        token = self.get_csrf_token(client, "/register")
        response = client.post(
            "/register",
            data={
                "csrf_token": token,
                "email": "Player@example.com",
                "password": "plain-password",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/dashboard")
        self.assertEqual(client.get("/dashboard").status_code, 200)

        user = get_db().execute(
            "SELECT id, email, password_hash FROM users"
        ).fetchone()
        profile = get_db().execute(
            "SELECT display_name FROM profiles WHERE user_id = ?",
            (user["id"],),
        ).fetchone()
        self.assertEqual(user["email"], "player@example.com")
        self.assertNotEqual(user["password_hash"], "plain-password")
        self.assertTrue(check_password_hash(user["password_hash"], "plain-password"))
        self.assertEqual(profile["display_name"], "player")

    def test_duplicate_email_is_case_insensitive(self):
        client = self.app.test_client()
        token = self.get_csrf_token(client, "/register")
        response = client.post(
            "/register",
            data={
                "csrf_token": token,
                "email": "player@example.com",
                "password": "first-password",
            },
        )
        self.assertEqual(response.status_code, 302)

        another_client = self.app.test_client()
        token = self.get_csrf_token(another_client, "/register")
        response = another_client.post(
            "/register",
            data={
                "csrf_token": token,
                "email": "PLAYER@example.com",
                "password": "second-password",
            },
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("já está cadastrado", response.get_data(as_text=True))
        self.assertEqual(
            get_db().execute("SELECT COUNT(*) FROM users").fetchone()[0],
            1,
        )

    def test_login_rejects_bad_credentials_and_logout_ends_session(self):
        client = self.app.test_client()
        token = self.get_csrf_token(client, "/register")
        client.post(
            "/register",
            data={
                "csrf_token": token,
                "email": "player@example.com",
                "password": "correct-password",
            },
        )
        client.get("/dashboard")

        with client.session_transaction() as flask_session:
            token = flask_session["_csrf_token"]
        response = client.post("/logout", data={"csrf_token": token})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(client.get("/dashboard").location, "/login")

        token = self.get_csrf_token(client, "/login")
        response = client.post(
            "/login",
            data={
                "csrf_token": token,
                "email": "player@example.com",
                "password": "wrong-password",
            },
        )
        self.assertEqual(response.status_code, 401)

        with client.session_transaction() as flask_session:
            token = flask_session["_csrf_token"]
        response = client.post(
            "/login",
            data={
                "csrf_token": token,
                "email": "PLAYER@example.com",
                "password": "correct-password",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(client.get("/dashboard").status_code, 200)

    def test_post_without_csrf_token_is_rejected(self):
        response = self.app.test_client().post(
            "/register",
            data={"email": "player@example.com", "password": "password"},
        )
        self.assertEqual(response.status_code, 400)

    def test_account_deletion_requires_password_and_removes_user_data(self):
        client = self.app.test_client()
        token = self.get_csrf_token(client, "/register")
        client.post(
            "/register",
            data={
                "csrf_token": token,
                "email": "delete@example.com",
                "password": "correct-password",
            },
        )

        user = get_db().execute(
            "SELECT id FROM users WHERE email = ?",
            ("delete@example.com",),
        ).fetchone()
        get_db().execute(
            """
            INSERT INTO games (
                user_id, source, name, platform, developer, release_year
            )
            VALUES (?, 'manual', 'Teste', 'PC', 'Estúdio', 2026)
            """,
            (user["id"],),
        )
        get_db().commit()

        token = self.get_csrf_token(client, "/delete-account")
        response = client.post(
            "/delete-account",
            data={"csrf_token": token, "password": "wrong-password"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertIsNotNone(
            get_db().execute(
                "SELECT id FROM users WHERE id = ?", (user["id"],)
            ).fetchone()
        )

        with client.session_transaction() as flask_session:
            token = flask_session["_csrf_token"]
        response = client.post(
            "/delete-account",
            data={"csrf_token": token, "password": "correct-password"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/register")
        self.assertIsNone(
            get_db().execute(
                "SELECT id FROM users WHERE id = ?", (user["id"],)
            ).fetchone()
        )
        self.assertIsNone(
            get_db().execute(
                "SELECT user_id FROM profiles WHERE user_id = ?", (user["id"],)
            ).fetchone()
        )
        self.assertEqual(client.get("/dashboard").location, "/login")


if __name__ == "__main__":
    unittest.main()
