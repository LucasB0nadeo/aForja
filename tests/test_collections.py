import tempfile
import unittest
from pathlib import Path

from platina_club import create_app
from platina_club.db import get_db, init_db


class CollectionRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = str(Path(self.temp_dir.name) / "collections.sqlite3")
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

    def add_game(self, user_id, name):
        game_id = get_db().execute(
            """
            INSERT INTO games (
                user_id, source, name, platform, developer, release_year
            ) VALUES (?, 'manual', ?, 'PC', 'Developer', 2025)
            """,
            (user_id, name),
        ).lastrowid
        get_db().commit()
        return game_id

    def token(self, client, path):
        response = client.get(path)
        self.assertEqual(response.status_code, 200)
        with client.session_transaction() as flask_session:
            return flask_session["_csrf_token"]

    def test_collection_crud_supports_many_to_many_game_selection(self):
        client, user_id = self.create_client("collections@example.com")
        first_game = self.add_game(user_id, "First Game")
        second_game = self.add_game(user_id, "Second Game")

        response = client.post(
            "/collections/new",
            data={
                "csrf_token": self.token(client, "/collections/new"),
                "name": "Férias",
                "description": "Jogos para zerar.",
                "game_ids": [str(first_game), str(second_game)],
            },
        )
        self.assertEqual(response.status_code, 302)
        collection_id = get_db().execute(
            "SELECT id FROM collections WHERE user_id = ?",
            (user_id,),
        ).fetchone()["id"]

        response = client.get("/collections")
        self.assertIn(b"F\xc3\xa9rias", response.data)
        self.assertIn(b"2 jogo(s)", response.data)

        second_collection = client.post(
            "/collections/new",
            data={
                "csrf_token": self.token(client, "/collections/new"),
                "name": "Favoritos",
                "description": "",
                "game_ids": [str(first_game)],
            },
        )
        self.assertEqual(second_collection.status_code, 302)
        self.assertEqual(
            get_db().execute(
                "SELECT COUNT(*) FROM collection_games WHERE game_id = ?",
                (first_game,),
            ).fetchone()[0],
            2,
        )

        response = client.post(
            f"/collections/{collection_id}/edit",
            data={
                "csrf_token": self.token(
                    client, f"/collections/{collection_id}/edit"
                ),
                "name": "Férias atualizada",
                "description": "Só o segundo jogo.",
                "game_ids": [str(second_game)],
            },
        )
        self.assertEqual(response.status_code, 302)
        updated_collection = get_db().execute(
            "SELECT name, description FROM collections WHERE id = ?",
            (collection_id,),
        ).fetchone()
        self.assertEqual(
            tuple(updated_collection),
            ("Férias atualizada", "Só o segundo jogo."),
        )
        self.assertEqual(
            [
                row["game_id"]
                for row in get_db().execute(
                    "SELECT game_id FROM collection_games WHERE collection_id = ?",
                    (collection_id,),
                )
            ],
            [second_game],
        )

    def test_foreign_game_selection_is_rejected_without_changing_associations(self):
        owner, owner_id = self.create_client("owner-collections@example.com")
        _, other_id = self.create_client("other-collections@example.com")
        owned_game = self.add_game(owner_id, "Owned Game")
        foreign_game = self.add_game(other_id, "Private Game")

        owner.post(
            "/collections/new",
            data={
                "csrf_token": self.token(owner, "/collections/new"),
                "name": "My collection",
                "description": "",
                "game_ids": [str(owned_game)],
            },
        )
        collection_id = get_db().execute(
            "SELECT id FROM collections WHERE user_id = ?",
            (owner_id,),
        ).fetchone()["id"]

        response = owner.post(
            f"/collections/{collection_id}/edit",
            data={
                "csrf_token": self.token(
                    owner, f"/collections/{collection_id}/edit"
                ),
                "name": "My collection",
                "description": "",
                "game_ids": [str(foreign_game)],
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Selecione apenas jogos da sua biblioteca.", response.data)
        self.assertEqual(
            get_db().execute(
                "SELECT game_id FROM collection_games WHERE collection_id = ?",
                (collection_id,),
            ).fetchone()["game_id"],
            owned_game,
        )

    def test_collections_are_private_and_deletion_keeps_games(self):
        owner, owner_id = self.create_client("private-owner@example.com")
        other, _ = self.create_client("private-other@example.com")
        game_id = self.add_game(owner_id, "Still Here")
        owner.post(
            "/collections/new",
            data={
                "csrf_token": self.token(owner, "/collections/new"),
                "name": "Private",
                "description": "",
                "game_ids": [str(game_id)],
            },
        )
        collection_id = get_db().execute(
            "SELECT id FROM collections WHERE user_id = ?",
            (owner_id,),
        ).fetchone()["id"]

        response = other.get("/collections")
        self.assertNotIn(b"Private", response.data)
        self.assertEqual(
            other.get(f"/collections/{collection_id}/edit").status_code,
            404,
        )
        other_csrf_token = self.token(other, "/dashboard")
        self.assertEqual(
            other.post(
                f"/collections/{collection_id}/delete",
                data={"csrf_token": other_csrf_token},
            ).status_code,
            404,
        )

        response = owner.post(
            f"/collections/{collection_id}/delete",
            data={
                "csrf_token": self.token(
                    owner, f"/collections/{collection_id}/delete"
                ),
                "confirm": "delete",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(
            get_db().execute(
                "SELECT id FROM collections WHERE id = ?",
                (collection_id,),
            ).fetchone()
        )
        self.assertIsNotNone(
            get_db().execute("SELECT id FROM games WHERE id = ?", (game_id,)).fetchone()
        )


if __name__ == "__main__":
    unittest.main()
