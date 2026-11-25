import sqlite3
import tempfile
import unittest
from pathlib import Path

from platina_club import create_app
from platina_club.db import get_db, init_db


class DatabaseSchemaTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = str(Path(self.temp_dir.name) / "test.sqlite3")
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
        self.db = get_db()

    def tearDown(self):
        self.app_context.pop()
        self.temp_dir.cleanup()

    def test_initial_migration_creates_schema_and_is_idempotent(self):
        init_db()

        tables = {
            row["name"]
            for row in self.db.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

        self.assertEqual(self.db.execute("PRAGMA user_version").fetchone()[0], 11)
        self.assertTrue(
            {
                "users",
                "profiles",
                "steam_links",
                "games",
                "achievements",
                "badge_awards",
                "forja_slots",
                "collections",
                "collection_games",
                "game_reviews",
                "wishlist_entries",
                "personal_goals",
                "goal_games",
                "friendships",
                "ember_ranking_records",
                "achievement_ranking_records",
                "steam_catalog",
            }.issubset(tables)
        )
        profile_columns = {
            row["name"] for row in self.db.execute("PRAGMA table_info(profiles)")
        }
        self.assertIn("show_ranking_position", profile_columns)
        self.assertEqual(self.db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_unique_and_foreign_key_constraints_are_enforced(self):
        self.assertEqual(
            self.db.execute("PRAGMA foreign_keys").fetchone()[0],
            1,
        )
        first_user_id = self.db.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            ("player@example.com", "hash"),
        ).lastrowid
        self.db.commit()

        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                ("PLAYER@example.com", "hash"),
            )
        self.db.rollback()

        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                """
                INSERT INTO games (
                    user_id, source, name, steam_app_id
                ) VALUES (?, 'steam', ?, ?)
                """,
                (99999, "A Steam Game", 12345),
            )
        self.db.rollback()

        self.db.execute(
            "INSERT INTO steam_links (user_id, steam_id) VALUES (?, ?)",
            (first_user_id, "76561198000000001"),
        )
        second_user_id = self.db.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            ("second-player@example.com", "hash"),
        ).lastrowid
        self.db.execute(
            "INSERT INTO steam_links (user_id, steam_id) VALUES (?, ?)",
            (second_user_id, "76561198000000001"),
        )
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "INSERT INTO steam_links (user_id, steam_id) VALUES (?, ?)",
                (second_user_id, "76561198000000002"),
            )
        self.db.rollback()

        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "INSERT INTO steam_links (user_id, steam_id) VALUES (?, ?)",
                (99999, "76561198000000002"),
            )

    def test_shared_steam_migration_preserves_existing_links(self):
        legacy_path = str(Path(self.temp_dir.name) / "legacy.sqlite3")
        connection = sqlite3.connect(legacy_path)
        migration_dir = Path(__file__).parent.parent / "platina_club" / "migrations"
        for migration_path in sorted(migration_dir.glob("[0-9][0-9][0-9]_*.sql")):
            version = int(migration_path.name.split("_", 1)[0])
            if version > 3:
                break
            connection.executescript(
                migration_path.read_text(encoding="utf-8")
            )
            connection.execute(f"PRAGMA user_version = {version}")

        user_id = connection.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            ("legacy@example.com", "hash"),
        ).lastrowid
        connection.execute(
            """
            INSERT INTO steam_links (
                user_id, steam_id, games_sync_status, games_synced_at,
                games_sync_error, avatar_url
            ) VALUES (?, ?, 'stale', ?, ?, ?)
            """,
            (
                user_id,
                "76561198000000001",
                "2026-01-02 03:04:05",
                "temporary error",
                "https://avatars.steamstatic.com/avatar.jpg",
            ),
        )
        connection.commit()
        connection.close()

        legacy_app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret-key",
                "DATABASE": legacy_path,
            }
        )
        with legacy_app.app_context():
            init_db()
            migrated = get_db().execute(
                """
                SELECT steam_id, games_sync_status, games_synced_at,
                       games_sync_error, avatar_url
                FROM steam_links
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
            self.assertEqual(
                tuple(migrated),
                (
                    "76561198000000001",
                    "stale",
                    "2026-01-02 03:04:05",
                    "temporary error",
                    "https://avatars.steamstatic.com/avatar.jpg",
                ),
            )
            self.assertEqual(
                get_db().execute("PRAGMA user_version").fetchone()[0],
                11,
            )

    def test_badge_and_forja_constraints_preserve_awards_without_game_snapshot(self):
        user_id = self.db.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            ("smith@example.com", "hash"),
        ).lastrowid
        game_id = self.db.execute(
            """
            INSERT INTO games (
                user_id, source, name, steam_app_id
            ) VALUES (?, 'steam', ?, ?)
            """,
            (user_id, "Completed Game", 54321),
        ).lastrowid
        award_id = self.db.execute(
            """
            INSERT INTO badge_awards (
                user_id, game_id, steam_app_id, game_name_snapshot, badge_type
            ) VALUES (?, ?, ?, ?, 'ember')
            """,
            (user_id, game_id, 54321, "Completed Game"),
        ).lastrowid
        self.db.execute(
            """
            INSERT INTO forja_slots (user_id, slot, badge_award_id)
            VALUES (?, 1, ?)
            """,
            (user_id, award_id),
        )
        self.db.commit()

        self.db.execute("DELETE FROM games WHERE id = ?", (game_id,))

        award = self.db.execute(
            "SELECT game_id, game_name_snapshot FROM badge_awards WHERE id = ?",
            (award_id,),
        ).fetchone()
        slot = self.db.execute(
            "SELECT badge_award_id FROM forja_slots WHERE user_id = ? AND slot = 1",
            (user_id,),
        ).fetchone()

        self.assertIsNone(award["game_id"])
        self.assertEqual(award["game_name_snapshot"], "Completed Game")
        self.assertEqual(slot["badge_award_id"], award_id)

        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "INSERT INTO forja_slots (user_id, slot, badge_award_id) VALUES (?, 10, ?)",
                (user_id, award_id),
            )


if __name__ == "__main__":
    unittest.main()
