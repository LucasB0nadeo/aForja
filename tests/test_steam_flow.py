import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from platina_club import create_app
from platina_club.db import get_db, init_db
from platina_club.steam.api import SteamAPIError


STEAM_ID = "76561198000000001"
APP_ID = 12345
ACHIEVEMENTS = [
    {
        "steam_api_name": f"ACH_{index}",
        "name": f"Achievement {index}",
        "description": "",
        "rarity": None,
        "unlocked": 1,
        "unlocked_at": "2026-01-01 00:00:00",
    }
    for index in range(4)
]


class SteamProgressFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret-key",
                "DATABASE": str(Path(self.temp_dir.name) / "steam-flow.sqlite3"),
                "STEAM_API_KEY": "test-api-key",
                "STEAM_OPENID_RETURN_URL": (
                    "http://127.0.0.1:5000/steam/callback"
                ),
            }
        )
        self.app_context = self.app.app_context()
        self.app_context.push()
        init_db()
        self.client, self.user_id = self.register_client(
            "steam-owner@example.com"
        )
        self.other_client, self.other_user_id = self.register_client(
            "steam-other@example.com"
        )

    def tearDown(self):
        self.app_context.pop()
        self.temp_dir.cleanup()

    def register_client(self, email):
        client = self.app.test_client()
        csrf = self.csrf(client, "/register")
        response = client.post(
            "/register",
            data={
                "csrf_token": csrf,
                "email": email,
                "password": "test-password",
            },
        )
        self.assertEqual(response.status_code, 302)
        with client.session_transaction() as flask_session:
            user_id = flask_session["user_id"]
        return client, user_id

    def csrf(self, client, path):
        response = client.get(path)
        self.assertEqual(response.status_code, 200)
        return self.session_csrf(client)

    def session_csrf(self, client):
        with client.session_transaction() as flask_session:
            return flask_session["_csrf_token"]

    def test_registration_steam_progress_rewards_forja_and_recovery(self):
        self.client.get("/steam/link")
        with self.client.session_transaction() as flask_session:
            state = flask_session["_steam_openid_state"]

        with (
            patch(
                "platina_club.steam.routes.verify_steam_openid_response",
                return_value=STEAM_ID,
            ),
            patch("platina_club.steam.routes.sync_steam_avatar"),
            patch(
                "platina_club.steam.library.fetch_owned_games",
                return_value=[
                    {
                        "steam_app_id": APP_ID,
                        "name": "Flow Game",
                        "playtime_minutes": 120,
                    }
                ],
            ) as fetch_library,
        ):
            response = self.client.get(
                "/steam/callback",
                query_string={"state": state, "openid.mode": "id_res"},
            )
        self.assertEqual(response.status_code, 302)
        fetch_library.assert_called_once_with(STEAM_ID)

        game = get_db().execute(
            "SELECT id, name FROM games WHERE user_id = ? AND steam_app_id = ?",
            (self.user_id, APP_ID),
        ).fetchone()
        self.assertIsNotNone(game)
        self.assertEqual(game["name"], "Flow Game")

        with patch(
            "platina_club.steam.achievements.fetch_game_achievements",
            return_value=ACHIEVEMENTS,
        ) as fetch_achievements:
            detail = self.client.get(f"/games/{game['id']}")
        self.assertEqual(detail.status_code, 200)
        self.assertIn(b"100.0%", detail.data)
        self.assertIn("Martelo de Ouro do Mestre".encode(), detail.data)
        fetch_achievements.assert_called_once_with(STEAM_ID, APP_ID)

        rewards = get_db().execute(
            """
            SELECT id, badge_type FROM badge_awards
            WHERE user_id = ? AND steam_app_id = ?
            ORDER BY badge_type
            """,
            (self.user_id, APP_ID),
        ).fetchall()
        self.assertEqual(
            {row["badge_type"] for row in rewards},
            {
                "copper_sparks",
                "bronze_hammer",
                "silver_hammer",
                "gold_hammer",
                "ember",
            },
        )
        self.assertEqual(len(rewards), 5)
        ember_id = next(
            row["id"] for row in rewards if row["badge_type"] == "ember"
        )

        response = self.client.post(
            "/profile/forja",
            data={
                "csrf_token": self.csrf(self.client, "/profile/forja"),
                "badge_award_ids": str(ember_id),
            },
        )
        self.assertEqual(response.status_code, 302)
        public_profile = self.client.get(f"/profiles/{self.user_id}")
        self.assertEqual(public_profile.status_code, 200)
        self.assertIn(b"Flow Game", public_profile.data)
        self.assertIn("Brasa do Ferreiro".encode(), public_profile.data)

        private_library = self.other_client.get("/games")
        self.assertEqual(private_library.status_code, 200)
        self.assertNotIn(b"Flow Game", private_library.data)
        self.assertEqual(
            self.other_client.get(f"/games/{game['id']}").status_code,
            404,
        )
        other_forja = self.other_client.post(
            "/profile/forja",
            data={
                "csrf_token": self.csrf(
                    self.other_client, "/profile/forja"
                ),
                "badge_award_ids": str(ember_id),
            },
        )
        self.assertEqual(other_forja.status_code, 400)
        self.assertEqual(
            get_db().execute(
                "SELECT COUNT(*) FROM forja_slots WHERE user_id = ?",
                (self.other_user_id,),
            ).fetchone()[0],
            0,
        )

        with patch(
            "platina_club.steam.achievements.fetch_game_achievements",
            side_effect=SteamAPIError("Steam is temporarily unavailable."),
        ):
            failed_refresh = self.client.post(
                f"/games/{game['id']}/achievements/sync",
                data={"csrf_token": self.session_csrf(self.client)},
            )
        self.assertEqual(failed_refresh.status_code, 302)
        self.assertEqual(
            get_db().execute(
                "SELECT achievements_sync_status FROM games WHERE id = ?",
                (game["id"],),
            ).fetchone()[0],
            "stale",
        )
        self.assertEqual(
            get_db().execute(
                "SELECT COUNT(*) FROM achievements WHERE game_id = ?",
                (game["id"],),
            ).fetchone()[0],
            4,
        )
        self.assertEqual(
            get_db().execute(
                "SELECT COUNT(*) FROM badge_awards WHERE user_id = ? AND steam_app_id = ?",
                (self.user_id, APP_ID),
            ).fetchone()[0],
            5,
        )

        with patch(
            "platina_club.steam.achievements.fetch_game_achievements",
            return_value=ACHIEVEMENTS,
        ) as fetch_achievements:
            self.client.post(
                f"/games/{game['id']}/achievements/sync",
                data={"csrf_token": self.session_csrf(self.client)},
            )
        fetch_achievements.assert_called_once_with(STEAM_ID, APP_ID)
        self.assertEqual(
            get_db().execute(
                "SELECT achievements_sync_status FROM games WHERE id = ?",
                (game["id"],),
            ).fetchone()[0],
            "success",
        )
        self.assertEqual(
            get_db().execute(
                "SELECT COUNT(*) FROM badge_awards WHERE user_id = ? AND steam_app_id = ?",
                (self.user_id, APP_ID),
            ).fetchone()[0],
            5,
        )
        self.assertEqual(
            get_db().execute(
                "SELECT badge_award_id FROM forja_slots WHERE user_id = ?",
                (self.user_id,),
            ).fetchone()[0],
            ember_id,
        )

        self.client.post(
            "/logout",
            data={"csrf_token": self.csrf(self.client, "/dashboard")},
        )
        login = self.client.post(
            "/login",
            data={
                "csrf_token": self.csrf(self.client, "/login"),
                "email": "steam-owner@example.com",
                "password": "test-password",
            },
        )
        self.assertEqual(login.status_code, 302)
        with patch(
            "platina_club.steam.achievements.fetch_game_achievements"
        ) as fetch_achievements:
            persisted_detail = self.client.get(f"/games/{game['id']}")
        self.assertEqual(persisted_detail.status_code, 200)
        self.assertIn(b"Flow Game", persisted_detail.data)
        fetch_achievements.assert_not_called()
        self.assertEqual(
            get_db().execute(
                "SELECT COUNT(*) FROM forja_slots WHERE user_id = ?",
                (self.user_id,),
            ).fetchone()[0],
            1,
        )


if __name__ == "__main__":
    unittest.main()
