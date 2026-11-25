import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from platina_club import create_app
from platina_club.db import get_db, init_db
from platina_club.steam.api import SteamAPIError
from platina_club.steam.config import SteamAPIConfigurationError


class GameLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = str(Path(self.temp_dir.name) / "library.sqlite3")
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
        with client.session_transaction() as flask_session:
            user_id = flask_session["user_id"]
        return client, user_id

    def csrf_token(self, client, path):
        response = client.get(path)
        self.assertEqual(response.status_code, 200)
        with client.session_transaction() as flask_session:
            return flask_session["_csrf_token"]

    def game_data(self, csrf, **overrides):
        data = {
            "csrf_token": csrf,
            "name": "Hollow Knight",
            "platform": "PC",
            "developer": "Team Cherry",
            "release_year": "2017",
        }
        data.update(overrides)
        return data

    def create_game(self, client, **overrides):
        token = self.csrf_token(client, "/games/new")
        response = client.post(
            "/games/new",
            data=self.game_data(token, **overrides),
        )
        self.assertEqual(response.status_code, 302)
        return get_db().execute(
            "SELECT id FROM games ORDER BY id DESC LIMIT 1"
        ).fetchone()["id"]

    def test_manual_game_crud_and_validation(self):
        client, user_id = self.create_client("player@example.com")
        token = self.csrf_token(client, "/games/new")
        response = client.post(
            "/games/new",
            data=self.game_data(token, name="   ", release_year="0"),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            get_db().execute("SELECT COUNT(*) FROM games").fetchone()[0],
            0,
        )

        game_id = self.create_game(client)
        response = client.get("/games")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Hollow Knight", response.data)

        token = self.csrf_token(client, f"/games/{game_id}/edit")
        response = client.post(
            f"/games/{game_id}/edit",
            data=self.game_data(token, name="Hollow Knight: Silksong", release_year="2025"),
        )
        self.assertEqual(response.status_code, 302)
        game = get_db().execute(
            "SELECT name, release_year, user_id FROM games WHERE id = ?",
            (game_id,),
        ).fetchone()
        self.assertEqual(game["name"], "Hollow Knight: Silksong")
        self.assertEqual(game["release_year"], 2025)
        self.assertEqual(game["user_id"], user_id)

        response = client.get(f"/games/{game_id}/delete")
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(
            get_db().execute("SELECT id FROM games WHERE id = ?", (game_id,)).fetchone()
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

    def test_library_displays_game_covers_in_a_card_grid(self):
        client, user_id = self.create_client("cover-grid@example.com")
        db = get_db()
        db.execute(
            """
            INSERT INTO games (user_id, source, name, steam_app_id)
            VALUES (?, 'steam', 'Steam Game', 12345)
            """,
            (user_id,),
        )
        db.execute(
            """
            INSERT INTO games (
                user_id, source, name, platform, developer, release_year
            ) VALUES (?, 'manual', 'Manual Game', 'PC', 'Studio', 2024)
            """,
            (user_id,),
        )
        db.commit()

        response = client.get("/games")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'class="game-grid"', response.data)
        self.assertIn(b"Steam Game", response.data)
        self.assertIn(
            b"https://cdn.akamai.steamstatic.com/steam/apps/12345/header.jpg",
            response.data,
        )
        self.assertIn(b"Manual Game", response.data)
        self.assertIn(b"Sem capa dispon\xc3\xadvel", response.data)
        self.assertIn(b"Ainda n\xc3\xa3o sincronizado", response.data)
        self.assertNotIn(b"0% 0/0", response.data)

    def test_library_sort_controls_order_games_by_name_progress_and_latest(self):
        client, user_id = self.create_client("library-sort@example.com")
        db = get_db()
        low_id = db.execute(
            """
            INSERT INTO games (user_id, source, name, steam_app_id)
            VALUES (?, 'steam', 'Alpha Game', 12345)
            """,
            (user_id,),
        ).lastrowid
        high_id = db.execute(
            """
            INSERT INTO games (user_id, source, name, steam_app_id)
            VALUES (?, 'steam', 'Beta Game', 54321)
            """,
            (user_id,),
        ).lastrowid
        db.executemany(
            """
            INSERT INTO achievements (
                user_id, game_id, source, steam_api_name, name,
                unlocked, unlocked_at
            ) VALUES (?, ?, 'steam', ?, ?, ?, ?)
            """,
            [
                (user_id, low_id, "LOW_1", "Low 1", 1, "2026-11-20 10:00:00"),
                (user_id, low_id, "LOW_2", "Low 2", 0, None),
                (user_id, high_id, "HIGH_1", "High 1", 1, "2026-11-21 10:00:00"),
                (user_id, high_id, "HIGH_2", "High 2", 1, "2026-11-21 11:00:00"),
            ],
        )
        db.commit()

        progress = client.get("/games?sort=progress&direction=desc").get_data(as_text=True)
        self.assertLess(progress.index("Beta Game"), progress.index("Alpha Game"))

        latest = client.get("/games?sort=latest&direction=desc").get_data(as_text=True)
        self.assertLess(latest.index("Beta Game"), latest.index("Alpha Game"))

        descending_name = client.get("/games?sort=name&direction=desc").get_data(as_text=True)
        self.assertLess(descending_name.index("Beta Game"), descending_name.index("Alpha Game"))

        page = client.get("/games").get_data(as_text=True)
        self.assertIn("Porcentagem de conclusão", page)
        self.assertIn("Última conquista", page)
        self.assertIn("Crescente", page)
        self.assertIn("Decrescente", page)

    def test_library_search_status_summary_and_pagination(self):
        client, user_id = self.create_client("library-tools@example.com")
        db = get_db()
        completed_id = db.execute(
            """
            INSERT INTO games (user_id, source, name, steam_app_id)
            VALUES (?, 'steam', 'Completed Search Game', 12345)
            """,
            (user_id,),
        ).lastrowid
        for index in range(21):
            db.execute(
                """
                INSERT INTO games (user_id, source, name, steam_app_id)
                VALUES (?, 'steam', ?, ?)
                """,
                (user_id, f"Paged Game {index:02}", 20000 + index),
            )
        db.execute(
            """
            INSERT INTO achievements (
                user_id, game_id, source, steam_api_name, name, unlocked,
                unlocked_at
            ) VALUES (?, ?, 'steam', 'DONE', 'Done', 1, CURRENT_TIMESTAMP)
            """,
            (user_id, completed_id),
        )
        db.commit()

        page = client.get(
            "/games?q=Completed&status=completed&page_size=10"
        ).get_data(as_text=True)
        self.assertIn("Completed Search Game", page)
        self.assertIn("Conclu\u00eddos", page)
        self.assertIn("1 conquista", page)

        paged = client.get("/games?q=&status=all&page_size=10&page=2").get_data(as_text=True)
        self.assertIn("jogo(s)", paged)
        self.assertIn("Anterior", paged)
        no_matches = client.get(
            "/games?q=Nome-Inexistente"
        ).get_data(as_text=True)
        self.assertIn("Nenhum jogo corresponde", no_matches)

    def test_library_progress_bar_shows_unlocked_and_total_achievements(self):
        client, user_id = self.create_client("progress-grid@example.com")
        db = get_db()
        game_id = db.execute(
            """
            INSERT INTO games (
                user_id, source, name, steam_app_id,
                achievements_sync_status, achievements_synced_at
            ) VALUES (?, 'steam', 'Progress Game', 12345, 'success', CURRENT_TIMESTAMP)
            """,
            (user_id,),
        ).lastrowid
        zero_progress_game_id = db.execute(
            """
            INSERT INTO games (
                user_id, source, name, steam_app_id,
                achievements_sync_status, achievements_synced_at
            ) VALUES (?, 'steam', 'Zero Progress Game', 54321, 'success', CURRENT_TIMESTAMP)
            """,
            (user_id,),
        ).lastrowid
        for current_game_id, unlocked_count in (
            (game_id, 13),
            (zero_progress_game_id, 0),
        ):
            db.executemany(
                """
                INSERT INTO achievements (
                    user_id, game_id, source, steam_api_name, name, unlocked
                ) VALUES (?, ?, 'steam', ?, ?, ?)
                """,
                [
                    (
                        user_id,
                        current_game_id,
                        f"ACH_{index}",
                        f"Achievement {index}",
                        int(index < unlocked_count),
                    )
                    for index in range(52)
                ],
            )
        db.commit()

        response = client.get("/games")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'value="13"', response.data)
        self.assertIn(b'max="52"', response.data)
        self.assertIn(b"25% 13/52", response.data)
        self.assertIn(b"0% 0/52", response.data)

    def test_bulk_achievement_sync_continues_and_reports_partial_failures(self):
        client, user_id = self.create_client("bulk-sync@example.com")
        db = get_db()
        db.execute(
            "INSERT INTO steam_links (user_id, steam_id) VALUES (?, ?)",
            (user_id, "76561198000000001"),
        )
        db.executemany(
            """
            INSERT INTO games (user_id, source, name, steam_app_id)
            VALUES (?, 'steam', ?, ?)
            """,
            [
                (user_id, "Alpha Steam Game", 12345),
                (user_id, "Beta Steam Game", 54321),
            ],
        )
        db.commit()

        page = client.get("/games").get_data(as_text=True)
        self.assertLess(page.index('class="game-grid"'), page.index('class="library-sync-actions"'))
        self.assertIn("Sincronizar Steam", page)

        with (
            patch("platina_club.library.get_steam_api_key", return_value="test-key"),
            patch(
                "platina_club.library.sync_game_achievements",
                side_effect=[3, SteamAPIError("Steam stats are private.")],
            ) as sync_game,
        ):
            response = client.post(
                "/games/achievements/sync-all",
                data={"csrf_token": self.csrf_token(client, "/games")},
                follow_redirects=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [call.args[1] for call in sync_game.call_args_list],
            [
                get_db().execute(
                    "SELECT id FROM games WHERE steam_app_id = 12345"
                ).fetchone()["id"],
                get_db().execute(
                    "SELECT id FROM games WHERE steam_app_id = 54321"
                ).fetchone()["id"],
            ],
        )
        self.assertIn("Sincronização parcial: 1 de 2 jogo(s) atualizados.", response.get_data(as_text=True))
        self.assertIn("Beta Steam Game: Steam stats are private.", response.get_data(as_text=True))

    def test_bulk_achievement_sync_reports_missing_api_key(self):
        client, user_id = self.create_client("bulk-sync-key@example.com")
        db = get_db()
        db.execute(
            "INSERT INTO steam_links (user_id, steam_id) VALUES (?, ?)",
            (user_id, "76561198000000002"),
        )
        db.execute(
            """
            INSERT INTO games (user_id, source, name, steam_app_id)
            VALUES (?, 'steam', 'Steam Game', 12345)
            """,
            (user_id,),
        )
        db.commit()

        with (
            patch(
                "platina_club.library.get_steam_api_key",
                side_effect=SteamAPIConfigurationError(
                    "Configure STEAM_API_KEY in the local environment."
                ),
            ),
            patch("platina_club.library.sync_game_achievements") as sync_game,
        ):
            response = client.post(
                "/games/achievements/sync-all",
                data={"csrf_token": self.csrf_token(client, "/games")},
                follow_redirects=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Configure STEAM_API_KEY", response.get_data(as_text=True))
        sync_game.assert_not_called()

    def test_combined_steam_sync_updates_library_then_all_achievements(self):
        client, user_id = self.create_client("combined-sync@example.com")
        db = get_db()
        db.execute(
            "INSERT INTO steam_links (user_id, steam_id) VALUES (?, ?)",
            (user_id, "76561198000000003"),
        )
        db.commit()

        page = client.get("/games").get_data(as_text=True)
        self.assertIn("Sincronizar Steam", page)
        self.assertNotIn("Sincronizar biblioteca Steam", page)
        self.assertNotIn("Sincronizar conquistas de todos os jogos", page)

        first_game_id = db.execute(
            """
            INSERT INTO games (user_id, source, name, steam_app_id)
            VALUES (?, 'steam', 'Combined One', 12345)
            """,
            (user_id,),
        ).lastrowid
        second_game_id = db.execute(
            """
            INSERT INTO games (user_id, source, name, steam_app_id)
            VALUES (?, 'steam', 'Combined Two', 54321)
            """,
            (user_id,),
        ).lastrowid
        db.commit()

        with (
            patch(
                "platina_club.library.sync_owned_games",
                return_value=2,
            ) as sync_library,
            patch("platina_club.library.get_steam_api_key", return_value="test-key"),
            patch(
                "platina_club.library.sync_game_achievements",
                side_effect=[10, 5],
            ) as sync_achievements,
        ):
            response = client.post(
                "/games/steam/sync",
                data={"csrf_token": self.csrf_token(client, "/games")},
                follow_redirects=True,
            )

        self.assertEqual(response.status_code, 200)
        sync_library.assert_called_once_with(user_id)
        self.assertEqual(
            [call.args[1] for call in sync_achievements.call_args_list],
            [first_game_id, second_game_id],
        )
        response_text = response.get_data(as_text=True)
        self.assertIn("Biblioteca Steam sincronizada: 2 jogo(s).", response_text)
        self.assertIn("Conquistas: todas as 2 sincronizadas.", response_text)

    def test_game_operations_cannot_access_another_users_game(self):
        owner, _ = self.create_client("owner@example.com")
        other, _ = self.create_client("other@example.com")
        game_id = self.create_game(owner)

        other_library = other.get("/games")
        self.assertEqual(other_library.status_code, 200)
        self.assertNotIn(b"Hollow Knight", other_library.data)
        self.assertEqual(other.get(f"/games/{game_id}/edit").status_code, 404)
        self.assertEqual(other.get(f"/games/{game_id}/delete").status_code, 404)
        token = self.csrf_token(other, "/games/new")
        response = other.post(
            f"/games/{game_id}/edit",
            data=self.game_data(token, name="Unauthorized change"),
        )
        self.assertEqual(response.status_code, 404)
        response = other.post(
            f"/games/{game_id}/delete",
            data={"csrf_token": token, "confirm": "delete"},
        )
        self.assertEqual(response.status_code, 404)

        game = get_db().execute(
            "SELECT name FROM games WHERE id = ?",
            (game_id,),
        ).fetchone()
        self.assertEqual(game["name"], "Hollow Knight")
        self.assertEqual(
            self.app.test_client().get("/games").location,
            "/login",
        )

    def test_steam_game_is_not_editable_or_deletable_while_linked(self):
        client, user_id = self.create_client("steam-owner@example.com")
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
            (user_id, "Imported Game", 12345),
        ).lastrowid
        db.commit()

        self.assertEqual(client.get(f"/games/{game_id}/edit").status_code, 404)
        self.assertEqual(client.get(f"/games/{game_id}/delete").status_code, 404)


if __name__ == "__main__":
    unittest.main()
