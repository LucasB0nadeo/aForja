import sqlite3
from pathlib import Path

from flask import current_app, g


def get_db():
    if "db" not in g:
        database = current_app.config["DATABASE"]
        if database != ":memory:":
            Path(database).parent.mkdir(parents=True, exist_ok=True)

        connection = sqlite3.connect(database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        g.db = connection

    return g.db


def close_db(error=None):
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def init_db():
    connection = get_db()
    current_version = connection.execute("PRAGMA user_version").fetchone()[0]
    migration_dir = Path(__file__).parent / "migrations"

    for migration_path in sorted(migration_dir.glob("[0-9][0-9][0-9]_*.sql")):
        version = int(migration_path.name.split("_", 1)[0])
        if version <= current_version:
            continue

        migration_sql = migration_path.read_text(encoding="utf-8")
        try:
            connection.executescript(
                "BEGIN IMMEDIATE;\n"
                f"{migration_sql}\n"
                f"PRAGMA user_version = {version};\n"
                "COMMIT;"
            )
        except sqlite3.Error:
            if connection.in_transaction:
                connection.rollback()
            raise

        current_version = version
