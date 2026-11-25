import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from platina_club import create_app
from platina_club.db import get_db, init_db
from platina_club.howlongtobeat import HowLongToBeatUnavailable


STORE_GAME = {
    "steam_app_id": 620,
    "name": "Portal 2",
    "developer": "Valve",
    "release_date": "2011",
    "platforms": "Windows",
    "icon_url": "https://cdn.example/portal-2.jpg",
}


class GameStatisticsRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret-key",
                "DATABASE": str(Path(self.temp_dir.name) / "statistics.sqlite3"),
            }
        )
        self.app_context = self.app.app_context()
        self.app_context.push()
        init_db()
        self.client, self.user_id = self.create_client("stats@example.com")
        _, self.second_user_id = self.create_client("stats-second@example.com")

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
        with client.session_transaction() as flask_session:
            user_id = flask_session["user_id"]
        return client, user_id

    def add_synced_game(self, user_id):
        game_id = get_db().execute(
            """
            INSERT INTO games (
                user_id, source, name, steam_app_id,
                achievements_sync_status, achievements_synced_at
            ) VALUES (?, 'steam', 'Portal 2', 620, 'success', CURRENT_TIMESTAMP)
            """,
            (user_id,),
        ).lastrowid
        get_db().execute(
            """
            INSERT INTO achievements (
                user_id, game_id, source, steam_api_name,
                name, global_percent, unlocked
            ) VALUES (?, ?, 'steam', 'ACH_FIRST', 'Achievement One', 23.4, 1)
            """,
            (user_id, game_id),
        )
        return game_id

    def test_statistics_combine_forge_and_steam_data(self):
        first_game_id = self.add_synced_game(self.user_id)
        second_game_id = self.add_synced_game(self.second_user_id)
        get_db().execute(
            """
            UPDATE achievements SET updated_at = datetime('now', '-1 day')
            WHERE game_id = ?
            """,
            (first_game_id,),
        )
        get_db().execute(
            """
            INSERT INTO badge_awards (
                user_id, game_id, steam_app_id, game_name_snapshot, badge_type
            ) VALUES (?, ?, 620, 'Portal 2', 'copper_sparks')
            """,
            (self.user_id, first_game_id),
        )
        get_db().execute(
            """
            INSERT INTO game_reviews (user_id, steam_app_id, review_text, rating)
            VALUES (?, 620, 'Ótimo jogo.', 5), (?, 620, 'Muito bom.', 3)
            """,
            (self.user_id, self.second_user_id),
        )
        get_db().commit()

        with (
            patch(
                "platina_club.library.fetch_store_game",
                return_value=STORE_GAME,
            ) as fetch_game,
            patch("platina_club.library.search_hltb_games") as hltb_search,
        ):
            response = self.client.get("/games/statistics?steam_app_id=620")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Portal 2", response.data)
        self.assertIn(b"data-hltb-results", response.data)
        self.assertIn(b"/games/howlongtobeat?query=Portal+2&amp;fragment=1", response.data)
        self.assertIn(b"4.0 / 5", response.data)
        self.assertIn(b"https://store.steampowered.com/app/620/", response.data)
        self.assertIn(b"Fa\xc3\xadscas de Cobre", response.data)
        self.assertIn(b"50.0%", response.data)
        self.assertIn(b"Achievement One", response.data)
        self.assertIn(b"23.4%", response.data)
        fetch_game.assert_called_once_with(620)
        hltb_search.assert_not_called()
        self.assertEqual(
            get_db().execute(
                "SELECT name FROM steam_catalog WHERE steam_app_id = 620"
            ).fetchone()["name"],
            "Portal 2",
        )

    def test_statistics_automatically_loads_hltb_estimates(self):
        result = SimpleNamespace(
            game_name="Portal 2",
            game_id=6200,
            game_url="https://howlongtobeat.com/game/6200",
            similarity=1.0,
            main_story=8.0,
            main_extra=10.0,
            completionist=18.0,
            all_styles=9.0,
            coop_time=6.0,
            mp_time=None,
        )
        with (
            patch(
                "platina_club.library.fetch_store_game",
                return_value=STORE_GAME,
            ),
            patch(
                "platina_club.library.search_hltb_games",
            ) as hltb_search,
        ):
            response = self.client.get("/games/statistics?steam_app_id=620")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Buscando estimativas de conclus\xc3\xa3o", response.data)
        hltb_search.assert_not_called()

        with patch(
            "platina_club.library.search_hltb_games",
            return_value=[result],
        ) as hltb_search:
            response = self.client.get(
                "/games/howlongtobeat",
                query_string={"query": "Portal 2", "fragment": "1"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"8.0 h", response.data)
        self.assertIn(b"18.0 h", response.data)
        self.assertIn(b"https://howlongtobeat.com/game/6200", response.data)
        hltb_search.assert_called_once_with("Portal 2")

    def test_hltb_failure_does_not_hide_steam_game_statistics(self):
        with patch(
            "platina_club.library.fetch_store_game",
            return_value=STORE_GAME,
        ):
            response = self.client.get(
                "/games/statistics?steam_app_id=620"
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"data-hltb-results", response.data)
        self.assertIn(b"Portal 2", response.data)
        self.assertIn(b"Avalia\xc3\xa7\xc3\xb5es", response.data)

        with patch(
            "platina_club.library.search_hltb_games",
            side_effect=HowLongToBeatUnavailable,
        ):
            hltb_response = self.client.get(
                "/games/howlongtobeat",
                query_string={"query": "Portal 2", "fragment": "1"},
            )

        self.assertEqual(hltb_response.status_code, 503)
        self.assertIn(b"Servi\xc3\xa7o indispon\xc3\xadvel", hltb_response.data)

    def test_search_is_available_and_missing_selection_returns_to_search(self):
        search_page = self.client.get("/games/search")
        self.assertEqual(search_page.status_code, 200)
        self.assertIn(b"Pesquisar jogos", search_page.data)
        self.assertIn(b"/steam/search", search_page.data)
        self.assertNotIn(b"/games/howlongtobeat", search_page.data)

        response = self.client.get("/games/statistics")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/games/search")

    def test_howlongtobeat_search_shows_completion_estimates(self):
        result = SimpleNamespace(
            game_name="Hollow Knight",
            game_id=98765,
            game_url="https://howlongtobeat.com/game/98765",
            similarity=0.95,
            main_story=27.5,
            main_extra=41.0,
            completionist=63.0,
            all_styles=35.0,
            coop_time=None,
            mp_time=None,
        )
        with patch(
            "platina_club.library.search_hltb_games",
            return_value=[result],
        ) as search:
            response = self.client.get(
                "/games/howlongtobeat?query=Hollow+Knight"
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Hollow Knight", response.data)
        self.assertIn(b"27.5 h", response.data)
        self.assertIn(b"41.0 h", response.data)
        self.assertIn(b"https://howlongtobeat.com/game/98765", response.data)
        search.assert_called_once_with("Hollow Knight")

    def test_howlongtobeat_search_shows_empty_and_unavailable_states(self):
        with patch("platina_club.library.search_hltb_games", return_value=[]):
            empty_response = self.client.get(
                "/games/howlongtobeat?query=Missing+Game"
            )
        self.assertEqual(empty_response.status_code, 200)
        self.assertIn(b"Nenhum resultado", empty_response.data)

        with patch(
            "platina_club.library.search_hltb_games",
            side_effect=HowLongToBeatUnavailable,
        ):
            unavailable_response = self.client.get(
                "/games/howlongtobeat?query=Hollow+Knight"
            )
        self.assertEqual(unavailable_response.status_code, 503)
        self.assertIn(b"Servi\xc3\xa7o indispon\xc3\xadvel", unavailable_response.data)

    def test_howlongtobeat_rejects_invalid_query_without_calling_service(self):
        for query in ("x", "x" * 101):
            with self.subTest(query_length=len(query)):
                with patch("platina_club.library.search_hltb_games") as search:
                    response = self.client.get(
                        "/games/howlongtobeat",
                        query_string={"query": query},
                    )

                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.location, "/games/search")
                search.assert_not_called()

    def test_game_can_be_added_from_the_catalog_when_sync_omits_it(self):
        with patch(
            "platina_club.library.fetch_store_game",
            return_value=STORE_GAME,
        ) as fetch_game:
            statistics = self.client.get("/games/statistics?steam_app_id=620")

        self.assertIn(b"Adicionar \xc3\xa0 minha biblioteca", statistics.data)
        with self.client.session_transaction() as flask_session:
            csrf_token = flask_session["_csrf_token"]
        response = self.client.post(
            "/games/import",
            data={"csrf_token": csrf_token, "steam_app_id": "620"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/games/1")
        imported_game = get_db().execute(
            """
            SELECT id, source, name, playtime_minutes
            FROM games
            WHERE user_id = ? AND steam_app_id = 620
            """,
            (self.user_id,),
        ).fetchone()
        self.assertEqual(
            tuple(imported_game),
            (1, "steam", "Portal 2", 0),
        )
        fetch_game.assert_called_once_with(620)


if __name__ == "__main__":
    unittest.main()
