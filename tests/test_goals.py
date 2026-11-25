import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from platina_club import create_app
from platina_club.db import get_db, init_db


STORE_GAMES = {
    12345: {
        "steam_app_id": 12345,
        "name": "Example Game",
        "developer": "Example Studio",
        "release_date": "2024",
        "platforms": "Windows",
        "icon_url": "https://cdn.example/game.jpg",
    },
    54321: {
        "steam_app_id": 54321,
        "name": "Another Example Game",
        "developer": "Another Studio",
        "release_date": "2025",
        "platforms": "Windows",
        "icon_url": "https://cdn.example/another-game.jpg",
    },
}


class GoalRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = str(Path(self.temp_dir.name) / "goals.sqlite3")
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
        with client.session_transaction() as flask_session:
            user_id = flask_session["user_id"]
        return client, user_id

    def token(self, client, path="/goals/new"):
        response = client.get(path)
        self.assertEqual(response.status_code, 200)
        with client.session_transaction() as flask_session:
            return flask_session["_csrf_token"]

    def goal_data(self, csrf_token, **overrides):
        values = {
            "csrf_token": csrf_token,
            "objective": "Conseguir 100% em Example Game",
            "due_date": "2026-12-31",
            "steam_app_id": "12345",
        }
        values.update(overrides)
        return values

    def test_goal_crud_keeps_achievement_progress_unchanged(self):
        client, user_id = self.create_client("goal-player@example.com")
        game_id = get_db().execute(
            """
            INSERT INTO games (user_id, source, name, steam_app_id)
            VALUES (?, 'steam', 'Example Game', 12345)
            """,
            (user_id,),
        ).lastrowid
        get_db().execute(
            """
            INSERT INTO achievements (
                user_id, game_id, source, steam_api_name, name,
                unlocked, unlocked_at
            ) VALUES (?, ?, 'steam', 'ACH_ONE', 'First', 1, CURRENT_TIMESTAMP)
            """,
            (user_id, game_id),
        )
        get_db().commit()
        achievement_before = tuple(
            get_db().execute(
                "SELECT unlocked, unlocked_at FROM achievements WHERE game_id = ?",
                (game_id,),
            ).fetchone()
        )

        with patch(
            "platina_club.goals.fetch_store_game",
            side_effect=[STORE_GAMES[12345], STORE_GAMES[54321]],
        ) as fetch:
            response = client.post(
                "/goals/new",
                data=self.goal_data(self.token(client)),
            )
            self.assertEqual(response.status_code, 302)
            goal = get_db().execute(
                "SELECT id, objective, due_date, steam_app_id, status FROM personal_goals"
            ).fetchone()
            goal_id = goal["id"]
            self.assertEqual(
                tuple(goal),
                (
                    goal_id,
                    "Conseguir 100% em Example Game",
                    "2026-12-31",
                    12345,
                    "in_progress",
                ),
            )

            response = client.get("/goals")
            self.assertIn(b"Conseguir 100% em Example Game", response.data)
            self.assertIn(b"Example Game", response.data)
            response = client.post(
                f"/goals/{goal_id}/edit",
                data=self.goal_data(
                    self.token(client, f"/goals/{goal_id}/edit"),
                    objective="Terminar a campanha",
                    due_date="2027-01-15",
                    steam_app_id="54321",
                    status="completed",
                ),
            )
            self.assertEqual(response.status_code, 302)
            self.assertEqual(
                [call.args[0] for call in fetch.call_args_list],
                [12345, 54321],
            )
        updated_goal = get_db().execute(
            """
            SELECT objective, due_date, steam_app_id, status
            FROM personal_goals WHERE id = ?
            """,
            (goal_id,),
        ).fetchone()
        self.assertEqual(
            tuple(updated_goal),
            ("Terminar a campanha", "2027-01-15", 54321, "completed"),
        )
        self.assertEqual(
            tuple(
                get_db().execute(
                    "SELECT unlocked, unlocked_at FROM achievements WHERE game_id = ?",
                    (game_id,),
                ).fetchone()
            ),
            achievement_before,
        )

        response = client.post(
            f"/goals/{goal_id}/delete",
            data={
                "csrf_token": self.token(client, f"/goals/{goal_id}/delete"),
                "confirm": "delete",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            get_db().execute("SELECT COUNT(*) FROM personal_goals").fetchone()[0],
            0,
        )
        self.assertEqual(
            get_db().execute("SELECT COUNT(*) FROM achievements").fetchone()[0],
            1,
        )

    def test_invalid_goal_inputs_are_rejected(self):
        client, _ = self.create_client("goal-validation@example.com")
        for overrides in (
            {"objective": "   "},
            {"due_date": "2026-02-30"},
            {"due_date": "20260101"},
            {"steam_app_id": "0"},
            {"steam_app_id": "abc"},
        ):
            response = client.post(
                "/goals/new",
                data=self.goal_data(self.token(client), **overrides),
            )
            self.assertEqual(response.status_code, 400)
        self.assertEqual(
            get_db().execute("SELECT COUNT(*) FROM personal_goals").fetchone()[0],
            0,
        )

        goal_id = get_db().execute(
            """
            INSERT INTO personal_goals (user_id, objective)
            VALUES ((SELECT id FROM users WHERE email = ?), 'Valid')
            """,
            ("goal-validation@example.com",),
        ).lastrowid
        get_db().commit()
        response = client.post(
            f"/goals/{goal_id}/edit",
            data=self.goal_data(
                self.token(client, f"/goals/{goal_id}/edit"),
                status="invalid",
            ),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            get_db().execute(
                "SELECT status FROM personal_goals WHERE id = ?",
                (goal_id,),
            ).fetchone()[0],
            "in_progress",
        )

    def test_goals_are_private_and_cannot_be_changed_by_another_user(self):
        owner, owner_id = self.create_client("goal-owner@example.com")
        other, _ = self.create_client("goal-other@example.com")
        goal_id = get_db().execute(
            """
            INSERT INTO personal_goals (user_id, objective)
            VALUES (?, 'Private objective')
            """,
            (owner_id,),
        ).lastrowid
        get_db().commit()

        response = other.get("/goals")
        self.assertNotIn(b"Private objective", response.data)
        self.assertEqual(other.get(f"/goals/{goal_id}/edit").status_code, 404)
        self.assertEqual(other.get(f"/goals/{goal_id}/delete").status_code, 404)
        response = other.post(
            f"/goals/{goal_id}/edit",
            data=self.goal_data(
                self.token(other),
                objective="Alterado",
            ),
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            get_db().execute(
                "SELECT objective FROM personal_goals WHERE id = ?",
                (goal_id,),
            ).fetchone()[0],
            "Private objective",
        )

    def test_goal_games_support_add_edit_remove_and_privacy(self):
        owner, owner_id = self.create_client("goal-games-owner@example.com")
        other, _ = self.create_client("goal-games-other@example.com")

        with patch(
            "platina_club.goals.fetch_store_game",
            side_effect=[
            STORE_GAMES[12345],
            STORE_GAMES[54321],
            STORE_GAMES[54321],
            ],
        ):
            create = owner.post(
            "/goals/new",
            data=self.goal_data(
                self.token(owner),
                objective="Concluir dois jogos",
                steam_app_id="12345",
                game_name="Example Game",
            ),
            )
            self.assertEqual(create.status_code, 302)
            goal_id = get_db().execute(
            "SELECT id FROM personal_goals WHERE user_id = ?",
            (owner_id,),
            ).fetchone()["id"]

            add = owner.post(
            f"/goals/{goal_id}/games/new",
            data={
                "csrf_token": self.token(owner, f"/goals/{goal_id}/edit"),
                "steam_app_id": "54321",
                "game_name": "Another Example Game",
            },
            )
            self.assertEqual(add.status_code, 302)

            relation_id = get_db().execute(
            """
            SELECT id FROM goal_games
            WHERE goal_id = ? AND steam_app_id = 54321
            """,
            (goal_id,),
            ).fetchone()["id"]

            edit = owner.post(
            f"/goals/{goal_id}/games/{relation_id}/edit",
            data={
                "csrf_token": self.token(
                    owner,
                    f"/goals/{goal_id}/games/{relation_id}/edit",
                ),
                "steam_app_id": "54321",
                "game_name": "Another Example Game",
            },
            )
            self.assertEqual(edit.status_code, 302)

        self.assertEqual(
            get_db().execute(
            """
            SELECT COUNT(*) FROM goal_games WHERE goal_id = ?
            """,
            (goal_id,),
            ).fetchone()[0],
            2,
        )
        self.assertEqual(
            other.get(f"/goals/{goal_id}/games/{relation_id}/edit").status_code,
            404,
        )
        response = other.post(
            f"/goals/{goal_id}/games/{relation_id}/delete",
            data={
            "csrf_token": self.token(other),
            "confirm": "delete",
            },
        )
        self.assertEqual(response.status_code, 404)

        delete = owner.post(
            f"/goals/{goal_id}/games/{relation_id}/delete",
            data={
            "csrf_token": self.token(
                owner,
                f"/goals/{goal_id}/edit",
            ),
            "confirm": "delete",
            },
        )
        self.assertEqual(delete.status_code, 302)
        self.assertEqual(
            get_db().execute(
            """
            SELECT COUNT(*) FROM goal_games WHERE goal_id = ?
            """,
            (goal_id,),
            ).fetchone()[0],
            1,
        )


if __name__ == "__main__":
    unittest.main()
