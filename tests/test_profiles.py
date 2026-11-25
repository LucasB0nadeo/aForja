import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from platina_club import create_app
from platina_club.db import get_db, init_db
from platina_club.steam.api import SteamAPIError, fetch_steam_profile, parse_steam_profile


STEAM_ID = "76561198000000001"
STEAM_AVATAR = "https://avatars.steamstatic.com/steam-avatar.jpg"


class SteamProfileAPITests(unittest.TestCase):
    def test_player_summary_returns_verified_avatar_url(self):
        payload = {
            "response": {
                "players": [
                    {
                        "steamid": STEAM_ID,
                        "personaname": "Player",
                        "avatarfull": STEAM_AVATAR,
                    }
                ]
            }
        }
        self.assertEqual(
            parse_steam_profile(payload, STEAM_ID),
            {
                "steam_id": STEAM_ID,
                "persona_name": "Player",
                "avatar_url": STEAM_AVATAR,
            },
        )
        with self.assertRaises(SteamAPIError):
            parse_steam_profile(
                {
                    "response": {
                        "players": [
                            {
                                "steamid": STEAM_ID,
                                "avatarfull": "javascript:alert(1)",
                            }
                        ]
                    }
                },
                STEAM_ID,
            )

    def test_player_summary_uses_server_web_api_key(self):
        payload = {"response": {"players": []}}
        with (
            patch(
                "platina_club.steam.api.get_steam_api_key",
                return_value="configured-key",
            ),
            patch(
                "platina_club.steam.api._request_json",
                return_value=payload,
            ) as request_json,
        ):
            with self.assertRaises(SteamAPIError):
                fetch_steam_profile(STEAM_ID)

        self.assertEqual(request_json.call_args.args[1], {
            "key": "configured-key",
            "steamids": STEAM_ID,
        })


class ProfileRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.avatar_dir = Path(self.temp_dir.name) / "avatars"
        database_path = str(Path(self.temp_dir.name) / "profiles.sqlite3")
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret-key",
                "DATABASE": database_path,
                "PROFILE_AVATAR_FOLDER": str(self.avatar_dir),
            }
        )
        self.app_context = self.app.app_context()
        self.app_context.push()
        init_db()
        self.client = self.app.test_client()
        self.client.get("/register")
        with self.client.session_transaction() as flask_session:
            csrf_token = flask_session["_csrf_token"]
        response = self.client.post(
            "/register",
            data={
                "csrf_token": csrf_token,
                "email": "profile@example.com",
                "password": "test-password",
            },
        )
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as flask_session:
            self.user_id = flask_session["user_id"]
        get_db().execute(
            "INSERT INTO steam_links (user_id, steam_id, avatar_url) VALUES (?, ?, ?)",
            (self.user_id, STEAM_ID, STEAM_AVATAR),
        )
        get_db().commit()

    def tearDown(self):
        self.app_context.pop()
        self.temp_dir.cleanup()

    @staticmethod
    def image_upload(color):
        output = io.BytesIO()
        Image.new("RGB", (4, 4), color=color).save(output, format="PNG")
        output.seek(0)
        return output

    def token(self):
        response = self.client.get("/profile/edit")
        self.assertEqual(response.status_code, 200)
        with self.client.session_transaction() as flask_session:
            return flask_session["_csrf_token"]

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
        with client.session_transaction() as flask_session:
            return client, flask_session["user_id"]

    def add_ember(self, user_id, app_id, name):
        award_id = get_db().execute(
            """
            INSERT INTO badge_awards (
                user_id, steam_app_id, game_name_snapshot, badge_type
            ) VALUES (?, ?, ?, 'ember')
            """,
            (user_id, app_id, name),
        ).lastrowid
        get_db().commit()
        return award_id

    def add_unlocked_achievements(self, user_id, app_id, count):
        db = get_db()
        game_id = db.execute(
            """
            INSERT INTO games (user_id, source, name, steam_app_id)
            VALUES (?, 'steam', ?, ?)
            """,
            (user_id, f"Achievement Game {app_id}", app_id),
        ).lastrowid
        with db:
            for index in range(count):
                db.execute(
                    """
                    INSERT INTO achievements (
                        user_id, game_id, source, steam_api_name, name,
                        unlocked, unlocked_at
                    ) VALUES (?, ?, 'steam', ?, ?, 1, CURRENT_TIMESTAMP)
                    """,
                    (
                        user_id,
                        game_id,
                        f"ACHIEVEMENT_{app_id}_{index}",
                        f"Achievement {index}",
                    ),
                )

    def test_profile_fields_and_custom_avatar_replace_steam_photo(self):
        initial = self.client.get("/profile/edit")
        self.assertIn(STEAM_AVATAR.encode(), initial.data)
        self.assertNotIn(b"profile@example.com", initial.data)

        response = self.client.post(
            "/profile/edit",
            data={
                "csrf_token": self.token(),
                "display_name": "Forge Master",
                "bio": "Minha jornada.",
                "avatar": (self.image_upload("red"), "profile.png"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 302)
        profile = get_db().execute(
            """
            SELECT display_name, bio, custom_avatar_path
            FROM profiles WHERE user_id = ?
            """,
            (self.user_id,),
        ).fetchone()
        self.assertEqual(profile["display_name"], "Forge Master")
        self.assertEqual(profile["bio"], "Minha jornada.")
        avatar_path = self.avatar_dir / profile["custom_avatar_path"]
        self.assertTrue(avatar_path.is_file())

        page = self.client.get("/profile/edit")
        self.assertIn(b"/profile/avatar/", page.data)
        self.assertNotIn(STEAM_AVATAR.encode(), page.data)
        avatar_response = self.client.get(
            f"/profile/avatar/{profile['custom_avatar_path']}"
        )
        self.assertEqual(avatar_response.status_code, 200)
        self.assertEqual(avatar_response.mimetype, "image/jpeg")
        avatar_response.close()

        response = self.client.post(
            "/profile/edit",
            data={
                "csrf_token": self.token(),
                "display_name": "Forge Master",
                "bio": "Atualizada.",
                "avatar": (self.image_upload("blue"), "new-photo.png"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 302)
        updated_path = get_db().execute(
            "SELECT custom_avatar_path FROM profiles WHERE user_id = ?",
            (self.user_id,),
        ).fetchone()[0]
        self.assertNotEqual(updated_path, profile["custom_avatar_path"])
        self.assertFalse(avatar_path.exists())

        response = self.client.post(
            "/profile/edit",
            data={
                "csrf_token": self.token(),
                "display_name": "Forge Master",
                "bio": "Atualizada.",
                "remove_avatar": "1",
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(
            get_db().execute(
                "SELECT custom_avatar_path FROM profiles WHERE user_id = ?",
                (self.user_id,),
            ).fetchone()[0]
        )
        self.assertIn(STEAM_AVATAR.encode(), self.client.get("/profile/edit").data)

    def test_invalid_images_and_empty_display_name_are_rejected(self):
        original = get_db().execute(
            "SELECT display_name, bio FROM profiles WHERE user_id = ?",
            (self.user_id,),
        ).fetchone()
        for data in (
            {
                "csrf_token": self.token(),
                "display_name": "Changed",
                "bio": "Changed",
                "avatar": (io.BytesIO(b"not an image"), "fake.png"),
            },
            {
                "csrf_token": self.token(),
                "display_name": "   ",
                "bio": "Changed",
            },
            {
                "csrf_token": self.token(),
                "display_name": "Too large",
                "bio": "",
                "avatar": (io.BytesIO(b"x" * (2 * 1024 * 1024 + 1)), "large.jpg"),
            },
            {
                "csrf_token": self.token(),
                "display_name": "x" * 41,
                "bio": "Changed",
            },
            {
                "csrf_token": self.token(),
                "display_name": "Valid",
                "bio": "x" * 241,
            },
            {
                "csrf_token": self.token(),
                "display_name": "Valid",
                "bio": "",
                "privacy": "everyone",
            },
        ):
            response = self.client.post(
                "/profile/edit",
                data=data,
                content_type="multipart/form-data",
            )
            self.assertEqual(response.status_code, 400)
        current = get_db().execute(
            "SELECT display_name, bio FROM profiles WHERE user_id = ?",
            (self.user_id,),
        ).fetchone()
        self.assertEqual(tuple(current), tuple(original))

    def test_profile_routes_require_authentication(self):
        anonymous = self.app.test_client()
        self.assertEqual(anonymous.get("/profile/edit").location, "/login")
        self.assertEqual(
            anonymous.get("/profile/avatar/00000000000000000000000000000000.jpg").location,
            "/login",
        )

    def test_public_profile_shows_only_public_fields_and_selected_embers(self):
        get_db().execute(
            """
            UPDATE profiles SET display_name = 'Public Smith', bio = 'A short bio'
            WHERE user_id = ?
            """,
            (self.user_id,),
        )
        first_ember = self.add_ember(self.user_id, 10001, "Featured Game")
        self.add_ember(self.user_id, 10002, "Private Game")
        get_db().execute(
            """
            INSERT INTO forja_slots (user_id, slot, badge_award_id)
            VALUES (?, 1, ?)
            """,
            (self.user_id, first_ember),
        )
        get_db().execute(
            """
            INSERT INTO personal_goals (user_id, objective)
            VALUES (?, 'Private objective')
            """,
            (self.user_id,),
        )
        get_db().execute(
            """
            INSERT INTO game_reviews (user_id, steam_app_id, review_text, rating)
            VALUES (?, 10003, 'Private review', 4)
            """,
            (self.user_id,),
        )
        get_db().execute(
            """
            INSERT INTO wishlist_entries (user_id, steam_app_id, priority, notes)
            VALUES (?, 10004, 3, 'Private wish')
            """,
            (self.user_id,),
        )
        get_db().execute(
            "INSERT INTO collections (user_id, name) VALUES (?, 'Private collection')",
            (self.user_id,),
        )
        get_db().commit()

        viewer, _ = self.create_client("profile-viewer@example.com")
        response = viewer.get(f"/profiles/{self.user_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Public Smith", response.data)
        self.assertIn(b"A short bio", response.data)
        self.assertIn(b"Featured Game", response.data)
        self.assertNotIn("Metas concluídas", response.get_data(as_text=True))
        self.assertNotIn(b"profile@example.com", response.data)
        self.assertNotIn(b"Private Game", response.data)
        self.assertNotIn(b"Private objective", response.data)
        self.assertNotIn(b"Private review", response.data)
        self.assertNotIn(b"Private wish", response.data)
        self.assertNotIn(b"Private collection", response.data)

        self.assertEqual(
            self.app.test_client().get(f"/profiles/{self.user_id}").location,
            "/login",
        )
        self.assertEqual(viewer.get("/profiles/99999").status_code, 404)

    def test_profile_navigation_opens_public_profile_above_dashboard(self):
        response = self.client.get(f"/profiles/{self.user_id}")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            f'<img class="profile-orb" src="{STEAM_AVATAR}" alt="">'.encode(),
            response.data,
        )
        self.assertIn(
            f'href="/profiles/{self.user_id}"'.encode(),
            response.data,
        )
        self.assertLess(
            response.data.index(b">Perfil e Forja</span>"),
            response.data.index(b">Painel</span>"),
        )

    def test_profile_shows_best_and_current_ember_ranking_positions(self):
        _, other_user_id = self.create_client("ranking-other@example.com")
        self.add_ember(self.user_id, 41001, "Owner Game One")
        self.add_ember(self.user_id, 41002, "Owner Game Two")
        self.add_ember(other_user_id, 42001, "Other Game One")

        response = self.client.get(f"/profiles/{self.user_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Melhor posi\xc3\xa7\xc3\xa3o", response.data)
        self.assertIn(b"Posi\xc3\xa7\xc3\xa3o atual", response.data)
        self.assertEqual(
            get_db().execute(
                """
                SELECT best_position
                FROM ember_ranking_records
                WHERE user_id = ?
                """,
                (self.user_id,),
            ).fetchone()["best_position"],
            1,
        )

        self.add_ember(other_user_id, 42002, "Other Game Two")
        self.add_ember(other_user_id, 42003, "Other Game Three")
        response = self.client.get(f"/profiles/{self.user_id}")
        page = response.get_data(as_text=True)
        ember_ranking = page.index(
            'aria-label="Posições no ranking mundial de Brasas"'
        )
        best_position = page.index("Melhor posição", ember_ranking)
        current_position = page.index("Posição atual", best_position)
        self.assertIn("#1", page[best_position:current_position])
        self.assertIn("#2", page[current_position:])
        self.assertEqual(
            get_db().execute(
                """
                SELECT best_position
                FROM ember_ranking_records
                WHERE user_id = ?
                """,
                (self.user_id,),
            ).fetchone()["best_position"],
            1,
        )

    def test_profile_shows_best_and_current_achievement_ranking_positions(self):
        _, other_user_id = self.create_client("achievement-ranking@example.com")
        self.add_unlocked_achievements(self.user_id, 51001, 3)
        self.add_unlocked_achievements(other_user_id, 52001, 1)

        response = self.client.get(f"/profiles/{self.user_id}")
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        achievement_ranking = page.index(
            'aria-label="Ranking mundial de conquistas"'
        )
        ember_ranking = page.index(
            'aria-label="Posições no ranking mundial de Brasas"'
        )
        self.assertIn("#1", page[achievement_ranking:ember_ranking])
        self.assertEqual(
            get_db().execute(
                """
                SELECT best_position
                FROM achievement_ranking_records
                WHERE user_id = ?
                """,
                (self.user_id,),
            ).fetchone()["best_position"],
            1,
        )

        self.add_unlocked_achievements(other_user_id, 52002, 3)
        response = self.client.get(f"/profiles/{self.user_id}")
        page = response.get_data(as_text=True)
        achievement_ranking = page.index(
            'aria-label="Ranking mundial de conquistas"'
        )
        ember_ranking = page.index(
            'aria-label="Posições no ranking mundial de Brasas"'
        )
        self.assertIn("#1", page[achievement_ranking:ember_ranking])
        self.assertIn("#2", page[achievement_ranking:ember_ranking])
        self.assertEqual(
            get_db().execute(
                """
                SELECT best_position
                FROM achievement_ranking_records
                WHERE user_id = ?
                """,
                (self.user_id,),
            ).fetchone()["best_position"],
            1,
        )

    def test_profile_ranking_visibility_setting_hides_user_from_public_ranking(self):
        other_client, other_user_id = self.create_client("ranking-viewer@example.com")
        self.add_ember(self.user_id, 43001, "Owner Brasa")
        self.add_ember(other_user_id, 43002, "Viewer Brasa")

        edit_page = self.client.get("/profile/edit")
        self.assertRegex(
            edit_page.get_data(as_text=True),
            r'name="show_ranking_position"\s+value="1"\s+checked',
        )

        response = self.client.post(
            "/profile/edit",
            data={
                "csrf_token": self.token(),
                "display_name": "Profile Owner",
                "bio": "A profile bio.",
                "privacy": "all",
                "show_ranking_position": "0",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            get_db().execute(
                "SELECT show_ranking_position FROM profiles WHERE user_id = ?",
                (self.user_id,),
            ).fetchone()["show_ranking_position"],
            0,
        )

        owner_profile = self.client.get(f"/profiles/{self.user_id}")
        viewer_profile = other_client.get(f"/profiles/{self.user_id}")
        self.assertIn(b"Posi\xc3\xa7\xc3\xa3o privada pelo jogador", owner_profile.data)
        self.assertIn(b"Posi\xc3\xa7\xc3\xa3o privada pelo jogador", viewer_profile.data)

        ranking_page = other_client.get("/rankings")
        self.assertNotIn(b"Profile Owner", ranking_page.data)
        self.assertIn(b"ranking-viewer", ranking_page.data)

    def test_forja_limits_selection_to_nine_earned_embers_and_keeps_awards(self):
        award_ids = [
            self.add_ember(self.user_id, 20000 + index, f"Game {index}")
            for index in range(10)
        ]
        other_client, other_user_id = self.create_client("forja-other@example.com")
        foreign_ember = self.add_ember(other_user_id, 30001, "Other User Game")
        gold_id = get_db().execute(
            """
            INSERT INTO badge_awards (
                user_id, steam_app_id, game_name_snapshot, badge_type
            ) VALUES (?, 30002, 'Not an Ember', 'gold_hammer')
            """,
            (self.user_id,),
        ).lastrowid
        get_db().commit()

        token = self.token_for_path("/profile/forja")
        response = self.client.post(
            "/profile/forja",
            data={
                "csrf_token": token,
                "badge_award_ids": [str(award_id) for award_id in award_ids[:9]],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            get_db().execute(
                "SELECT COUNT(*) FROM forja_slots WHERE user_id = ?",
                (self.user_id,),
            ).fetchone()[0],
            9,
        )
        saved_slots = get_db().execute(
            """
            SELECT slot, badge_award_id
            FROM forja_slots
            WHERE user_id = ?
            ORDER BY slot
            """,
            (self.user_id,),
        ).fetchall()
        self.assertEqual(
            [(row["slot"], row["badge_award_id"]) for row in saved_slots],
            list(enumerate(award_ids[:9], start=1)),
        )

        for invalid_selection in (
            [str(award_id) for award_id in award_ids],
            [str(gold_id)],
            [str(foreign_ember)],
        ):
            response = self.client.post(
                "/profile/forja",
                data={
                    "csrf_token": self.token_for_path("/profile/forja"),
                    "badge_award_ids": invalid_selection,
                },
            )
            self.assertEqual(response.status_code, 400)
            self.assertEqual(
                get_db().execute(
                    "SELECT COUNT(*) FROM forja_slots WHERE user_id = ?",
                    (self.user_id,),
                ).fetchone()[0],
                9,
            )

        response = self.client.post(
            "/profile/forja",
            data={"csrf_token": self.token_for_path("/profile/forja")},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            get_db().execute(
                "SELECT COUNT(*) FROM forja_slots WHERE user_id = ?",
                (self.user_id,),
            ).fetchone()[0],
            0,
        )
        self.assertEqual(
            get_db().execute(
                "SELECT COUNT(*) FROM badge_awards WHERE user_id = ? AND badge_type = 'ember'",
                (self.user_id,),
            ).fetchone()[0],
            10,
        )

    def token_for_path(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        with self.client.session_transaction() as flask_session:
            return flask_session["_csrf_token"]

    def token_for_client(self, client, path):
        response = client.get(path)
        self.assertEqual(response.status_code, 200)
        with client.session_transaction() as flask_session:
            return flask_session["_csrf_token"]

    def set_privacy(self, privacy):
        response = self.client.post(
            "/profile/edit",
            data={
                "csrf_token": self.token(),
                "display_name": "Profile Owner",
                "bio": "A profile bio.",
                "privacy": privacy,
            },
        )
        self.assertEqual(response.status_code, 302)

    def test_profile_privacy_hides_content_but_owner_keeps_access(self):
        viewer, _ = self.create_client("privacy-viewer@example.com")
        self.set_privacy("nobody")

        private_response = viewer.get(f"/profiles/{self.user_id}")
        self.assertEqual(private_response.status_code, 200)
        self.assertIn(b"Perfil privado", private_response.data)
        self.assertNotIn(b"Profile Owner", private_response.data)
        self.assertNotIn(b"A profile bio.", private_response.data)
        self.assertNotIn(b"Copiar link", private_response.data)

        owner_response = self.client.get(f"/profiles/{self.user_id}")
        self.assertEqual(owner_response.status_code, 200)
        self.assertIn(b"Profile Owner", owner_response.data)
        self.assertIn(b"Copiar link", owner_response.data)

        self.set_privacy("all")
        visible_response = viewer.get(f"/profiles/{self.user_id}")
        self.assertEqual(visible_response.status_code, 200)
        self.assertIn(b"Profile Owner", visible_response.data)

    def test_friend_requests_control_profile_and_avatar_visibility(self):
        viewer, viewer_id = self.create_client("friend-viewer@example.com")
        self.set_privacy("friends")
        avatar_name = "a" * 32 + ".jpg"
        self.avatar_dir.mkdir(parents=True, exist_ok=True)
        (self.avatar_dir / avatar_name).write_bytes(b"test avatar")
        get_db().execute(
            "UPDATE profiles SET custom_avatar_path = ? WHERE user_id = ?",
            (avatar_name, self.user_id),
        )
        get_db().commit()

        private_page = viewer.get(f"/profiles/{self.user_id}")
        self.assertEqual(private_page.status_code, 200)
        self.assertIn(b"Enviar pedido de amizade", private_page.data)
        self.assertNotIn(b"Profile Owner", private_page.data)
        self.assertEqual(
            viewer.get(f"/profile/avatar/{avatar_name}").status_code,
            404,
        )

        response = viewer.post(
            f"/profiles/{self.user_id}/friendship",
            data={
                "csrf_token": self.token_for_client(
                    viewer, f"/profiles/{self.user_id}"
                ),
                "action": "request",
            },
        )
        self.assertEqual(response.status_code, 302)
        pending_page = viewer.get(f"/profiles/{self.user_id}")
        self.assertIn(b"Pedido de amizade enviado.", pending_page.data)

        owner_page = self.client.get(f"/profiles/{self.user_id}")
        self.assertIn(b"friend-viewer", owner_page.data)
        self.assertIn(b"Pedidos de amizade", owner_page.data)
        response = viewer.post(
            f"/profiles/{self.user_id}/friendship",
            data={
                "csrf_token": self.token_for_client(
                    viewer, f"/profiles/{self.user_id}"
                ),
                "action": "accept",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            get_db().execute(
                """
                SELECT status FROM friendships
                WHERE user_low_id = ? AND user_high_id = ?
                """,
                tuple(sorted((self.user_id, viewer_id))),
            ).fetchone()["status"],
            "pending",
        )

        response = self.client.post(
            f"/profiles/{viewer_id}/friendship",
            data={
                "csrf_token": self.token_for_path(f"/profiles/{self.user_id}"),
                "action": "accept",
            },
        )
        self.assertEqual(response.status_code, 302)

        visible_page = viewer.get(f"/profiles/{self.user_id}")
        self.assertIn(b"Profile Owner", visible_page.data)
        avatar_response = viewer.get(f"/profile/avatar/{avatar_name}")
        self.assertEqual(avatar_response.status_code, 200)
        avatar_response.close()

        self.set_privacy("nobody")
        private_page = viewer.get(f"/profiles/{self.user_id}")
        self.assertIn(b"Perfil privado", private_page.data)
        owner_page = self.client.get(f"/profiles/{self.user_id}")
        self.assertIn(b"Amigos", owner_page.data)
        self.assertIn(b"friend-viewer", owner_page.data)
        response = self.client.post(
            f"/profiles/{viewer_id}/friendship",
            data={
                "csrf_token": self.token_for_path(f"/profiles/{self.user_id}"),
                "action": "remove",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(
            get_db().execute(
                "SELECT 1 FROM friendships WHERE requested_by_id = ?",
                (viewer_id,),
            ).fetchone()
        )

    def test_friend_requests_can_be_declined_or_cancelled(self):
        viewer, viewer_id = self.create_client("friendship-actions@example.com")

        response = viewer.post(
            f"/profiles/{self.user_id}/friendship",
            data={
                "csrf_token": self.token_for_client(
                    viewer, f"/profiles/{self.user_id}"
                ),
                "action": "request",
            },
        )
        self.assertEqual(response.status_code, 302)

        response = self.client.post(
            f"/profiles/{viewer_id}/friendship",
            data={
                "csrf_token": self.token_for_path(f"/profiles/{self.user_id}"),
                "action": "decline",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(
            get_db().execute(
                "SELECT 1 FROM friendships WHERE requested_by_id = ?",
                (viewer_id,),
            ).fetchone()
        )

        response = viewer.post(
            f"/profiles/{self.user_id}/friendship",
            data={
                "csrf_token": self.token_for_client(
                    viewer, f"/profiles/{self.user_id}"
                ),
                "action": "request",
            },
        )
        self.assertEqual(response.status_code, 302)
        response = viewer.post(
            f"/profiles/{self.user_id}/friendship",
            data={
                "csrf_token": self.token_for_client(
                    viewer, f"/profiles/{self.user_id}"
                ),
                "action": "cancel",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(
            get_db().execute(
                "SELECT 1 FROM friendships WHERE requested_by_id = ?",
                (viewer_id,),
            ).fetchone()
        )

    def test_friends_page_lists_profiles_and_respects_their_privacy(self):
        _, friend_id = self.create_client("friends-list@example.com")
        get_db().execute(
            "UPDATE profiles SET display_name = 'Private Friend', privacy = 'nobody' WHERE user_id = ?",
            (friend_id,),
        )
        get_db().execute(
            """
            INSERT INTO friendships (
                user_low_id, user_high_id, requested_by_id, status
            ) VALUES (?, ?, ?, 'accepted')
            """,
            (*sorted((self.user_id, friend_id)), self.user_id),
        )
        get_db().commit()

        response = self.client.get("/friends")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Amigos", response.data)
        self.assertIn(b"Private Friend", response.data)
        self.assertIn(f'href="/profiles/{friend_id}"'.encode(), response.data)
        self.assertIn(b"Adicionar amigo", response.data)
        private_profile = self.client.get(f"/profiles/{friend_id}")
        self.assertIn(b"Perfil privado", private_profile.data)
        self.assertNotIn(b"Private Friend", private_profile.data)

    def test_friends_page_search_sends_request_and_hides_non_addable_profiles(self):
        _, searchable_id = self.create_client("searchable@example.com")
        _, hidden_id = self.create_client("hidden-friend@example.com")
        get_db().execute(
            "UPDATE profiles SET display_name = 'Searchable Player' WHERE user_id = ?",
            (searchable_id,),
        )
        get_db().execute(
            "UPDATE profiles SET display_name = 'Hidden Player', privacy = 'nobody' WHERE user_id = ?",
            (hidden_id,),
        )
        get_db().commit()

        response = self.client.get("/friends?q=Searchable")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Searchable Player", response.data)
        self.assertNotIn(b"Hidden Player", response.data)

        response = self.client.post(
            f"/profiles/{searchable_id}/friendship",
            data={
                "csrf_token": self.token_for_path("/friends"),
                "action": "request",
                "next": "friends",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/friends")
        self.assertEqual(
            get_db().execute(
                """
                SELECT status FROM friendships
                WHERE user_low_id = ? AND user_high_id = ?
                """,
                tuple(sorted((self.user_id, searchable_id))),
            ).fetchone()["status"],
            "pending",
        )
        pending_page = self.client.get("/friends?q=Searchable")
        self.assertIn(b"Pedido enviado", pending_page.data)


if __name__ == "__main__":
    unittest.main()
