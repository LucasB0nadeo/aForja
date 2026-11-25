import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from platina_club import create_app
from platina_club.db import get_db, init_db
from platina_club.steam.config import (
    SteamAPIConfigurationError,
    get_steam_api_key,
)
from platina_club.steam.openid import (
    OPENID_ENDPOINT,
    OPENID_NAMESPACE,
    SteamOpenIDError,
    verify_steam_openid_response,
)


class SteamOpenIDTests(unittest.TestCase):
    def setUp(self):
        self.return_to = (
            "http://127.0.0.1:5000/steam/callback?state=test-state"
        )
        self.params = {
            "openid.ns": OPENID_NAMESPACE,
            "openid.mode": "id_res",
            "openid.op_endpoint": OPENID_ENDPOINT,
            "openid.claimed_id": (
                "https://steamcommunity.com/openid/id/76561198000000001"
            ),
            "openid.identity": (
                "https://steamcommunity.com/openid/id/76561198000000001"
            ),
            "openid.return_to": self.return_to,
            "openid.response_nonce": "2026-11-18T00:00:00Zexample",
            "openid.signed": (
                "op_endpoint,claimed_id,identity,return_to,response_nonce"
            ),
            "openid.sig": "test-signature",
        }

    def test_identity_is_returned_only_after_remote_verification(self):
        sent_params = {}

        def verify(params):
            sent_params.update(params)
            return "ns:http://specs.openid.net/auth/2.0\nis_valid:true\n"

        steam_id = verify_steam_openid_response(
            self.params,
            self.return_to,
            post_verification=verify,
        )

        self.assertEqual(steam_id, "76561198000000001")
        self.assertEqual(sent_params["openid.mode"], "check_authentication")

    def test_unsigned_identity_is_rejected_without_remote_verification(self):
        self.params["openid.signed"] = "op_endpoint,identity"

        with self.assertRaises(SteamOpenIDError):
            verify_steam_openid_response(
                self.params,
                self.return_to,
                post_verification=lambda params: self.fail(
                    "Unsigned identity must not be sent for verification."
                ),
            )

    def test_callback_url_mismatch_is_rejected(self):
        with self.assertRaises(SteamOpenIDError):
            verify_steam_openid_response(
                self.params,
                "http://127.0.0.1:5000/steam/callback?state=other-state",
                post_verification=lambda params: self.fail(
                    "Mismatched callback must not be sent for verification."
                ),
            )


class SteamLinkRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = str(Path(self.temp_dir.name) / "steam.sqlite3")
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret-key",
                "DATABASE": database_path,
                "STEAM_API_KEY": None,
                "STEAM_OPENID_RETURN_URL": (
                    "http://127.0.0.1:5000/steam/callback"
                ),
            }
        )
        self.app_context = self.app.app_context()
        self.app_context.push()
        init_db()

    def tearDown(self):
        self.app_context.pop()
        self.temp_dir.cleanup()

    def register_client(self, email):
        client = self.app.test_client()
        response = client.get("/register")
        self.assertEqual(response.status_code, 200)
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
        client.get("/dashboard")
        user_id = get_db().execute(
            "SELECT id FROM users WHERE email = ?",
            (email.casefold(),),
        ).fetchone()["id"]
        return client, user_id

    def callback_query(self, client, steam_id):
        with client.session_transaction() as flask_session:
            state = flask_session["_steam_openid_state"]

        return_to = (
            "http://127.0.0.1:5000/steam/callback?state="
            f"{state}"
        )
        identity = f"https://steamcommunity.com/openid/id/{steam_id}"
        return {
            "state": state,
            "openid.ns": OPENID_NAMESPACE,
            "openid.mode": "id_res",
            "openid.op_endpoint": OPENID_ENDPOINT,
            "openid.claimed_id": identity,
            "openid.identity": identity,
            "openid.return_to": return_to,
            "openid.response_nonce": "2026-11-18T00:00:00Zexample",
            "openid.signed": (
                "op_endpoint,claimed_id,identity,return_to,response_nonce"
            ),
            "openid.sig": "test-signature",
        }

    def test_link_redirects_to_steam_openid(self):
        client, _ = self.register_client("player@example.com")

        response = client.get("/steam/link")

        self.assertEqual(response.status_code, 302)
        target = urlsplit(response.location)
        self.assertEqual(target.netloc, "steamcommunity.com")
        self.assertEqual(target.path, "/openid/login")
        query = parse_qs(target.query)
        self.assertEqual(query["openid.mode"], ["checkid_setup"])
        self.assertEqual(query["openid.ns"], [OPENID_NAMESPACE])
        self.assertNotIn("password", target.query.lower())

    def test_callback_links_a_verified_steam_id(self):
        client, user_id = self.register_client("player@example.com")
        client.get("/steam/link")
        query = self.callback_query(client, "76561198000000001")

        with (
            patch(
                "platina_club.steam.routes.verify_steam_openid_response",
                return_value="76561198000000001",
            ) as verify,
            patch(
                "platina_club.steam.routes.sync_owned_games",
                return_value=0,
            ) as sync_library,
            patch(
                "platina_club.steam.routes.sync_steam_avatar",
                return_value={
                    "steam_id": "76561198000000001",
                    "persona_name": "Steam Player",
                    "avatar_url": "https://avatars.steamstatic.com/avatar.jpg",
                },
            ) as sync_avatar,
        ):
            response = client.get("/steam/callback", query_string=query)

        self.assertEqual(response.status_code, 302)
        verify.assert_called_once()
        sync_avatar.assert_called_once_with(user_id, "76561198000000001")
        sync_library.assert_called_once_with(user_id)
        link = get_db().execute(
            "SELECT steam_id FROM steam_links WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        self.assertEqual(link["steam_id"], "76561198000000001")

    def test_steam_account_can_be_linked_to_multiple_users(self):
        first_client, first_user_id = self.register_client("first@example.com")
        second_client, second_user_id = self.register_client("second@example.com")
        get_db().execute(
            "INSERT INTO steam_links (user_id, steam_id) VALUES (?, ?)",
            (first_user_id, "76561198000000001"),
        )
        get_db().commit()
        second_client.get("/steam/link")
        query = self.callback_query(second_client, "76561198000000001")

        with (
            patch(
                "platina_club.steam.routes.verify_steam_openid_response",
                return_value="76561198000000001",
            ),
            patch("platina_club.steam.routes.sync_steam_avatar"),
            patch(
                "platina_club.steam.routes.sync_owned_games",
                return_value=0,
            ),
        ):
            response = second_client.get(
                "/steam/callback",
                query_string=query,
                follow_redirects=True,
            )

        self.assertIn("Conta Steam vinculada.", response.get_data(as_text=True))
        links = get_db().execute(
            "SELECT user_id, steam_id FROM steam_links ORDER BY user_id"
        ).fetchall()
        self.assertEqual(
            [(row["user_id"], row["steam_id"]) for row in links],
            [
                (first_user_id, "76561198000000001"),
                (second_user_id, "76561198000000001"),
            ],
        )

    def test_unlink_preserves_snapshots_and_awards(self):
        client, user_id = self.register_client("player@example.com")
        db = get_db()
        db.execute(
            "INSERT INTO steam_links (user_id, steam_id) VALUES (?, ?)",
            (user_id, "76561198000000001"),
        )
        game_id = db.execute(
            """
            INSERT INTO games (
                user_id, source, name, steam_app_id
            ) VALUES (?, 'steam', ?, ?)
            """,
            (user_id, "Completed Game", 54321),
        ).lastrowid
        award_id = db.execute(
            """
            INSERT INTO badge_awards (
                user_id, game_id, steam_app_id, game_name_snapshot, badge_type
            ) VALUES (?, ?, ?, ?, 'ember')
            """,
            (user_id, game_id, 54321, "Completed Game"),
        ).lastrowid
        db.execute(
            """
            INSERT INTO forja_slots (user_id, slot, badge_award_id)
            VALUES (?, 1, ?)
            """,
            (user_id, award_id),
        )
        db.commit()
        client.get("/dashboard")
        with client.session_transaction() as flask_session:
            csrf = flask_session["_csrf_token"]

        response = client.post(
            "/steam/unlink",
            data={"csrf_token": csrf},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            db.execute(
                "SELECT COUNT(*) FROM steam_links WHERE user_id = ?",
                (user_id,),
            ).fetchone()[0],
            0,
        )
        self.assertIsNotNone(
            db.execute("SELECT id FROM games WHERE id = ?", (game_id,)).fetchone()
        )
        self.assertIsNotNone(
            db.execute(
                "SELECT id FROM badge_awards WHERE id = ?",
                (award_id,),
            ).fetchone()
        )
        self.assertIsNotNone(
            db.execute(
                "SELECT badge_award_id FROM forja_slots WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        )

    def test_library_sync_route_reports_missing_steam_link(self):
        client, _ = self.register_client("player@example.com")
        with client.session_transaction() as flask_session:
            csrf = flask_session["_csrf_token"]

        response = client.post(
            "/steam/library/sync",
            data={"csrf_token": csrf},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Vincule uma conta Steam antes de sincronizar.", response.get_data(as_text=True))

    def test_web_api_key_is_required_only_for_web_api_calls(self):
        with self.app.app_context():
            with self.assertRaises(SteamAPIConfigurationError):
                get_steam_api_key()

            self.app.config["STEAM_API_KEY"] = "configured-test-key"
            self.assertEqual(get_steam_api_key(), "configured-test-key")


if __name__ == "__main__":
    unittest.main()
