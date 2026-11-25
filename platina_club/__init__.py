import os
from pathlib import Path

from flask import Flask, render_template, request

from .auth import auth
from .collections import collections as collections_blueprint
from .db import close_db, get_db, init_db
from .goals import goals as goals_blueprint
from .library import library
from .profiles import profiles as profiles_blueprint
from .rankings import (
    rankings as rankings_blueprint,
    refresh_achievement_ranking_records,
    refresh_ember_ranking_records,
)
from .reviews import reviews as reviews_blueprint
from .security import csrf_token, validate_csrf_token
from .steam import steam
from .wishlist import wishlist as wishlist_blueprint


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        DATABASE=os.environ.get(
            "PLATINA_DATABASE",
            str(Path(app.instance_path) / "platina-club.sqlite3"),
        ),
        MAX_CONTENT_LENGTH=3 * 1024 * 1024,
        PROFILE_AVATAR_FOLDER=str(Path(app.instance_path) / "profile-avatars"),
        STEAM_API_KEY=os.environ.get("STEAM_API_KEY"),
        STEAM_OPENID_RETURN_URL=os.environ.get(
            "STEAM_OPENID_RETURN_URL",
            "http://127.0.0.1:5000/steam/callback",
        ),
    )

    if test_config is not None:
        app.config.update(test_config)

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError(
            "Configure SECRET_KEY with a random value before starting the application."
        )

    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()
        with get_db() as db:
            refresh_ember_ranking_records(db)
            refresh_achievement_ranking_records(db)
    app.register_blueprint(auth)
    app.register_blueprint(collections_blueprint)
    app.register_blueprint(goals_blueprint)
    app.register_blueprint(library)
    app.register_blueprint(profiles_blueprint)
    app.register_blueprint(rankings_blueprint)
    app.register_blueprint(reviews_blueprint)
    app.register_blueprint(steam)
    app.register_blueprint(wishlist_blueprint)
    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def protect_post_requests():
        if request.method == "POST":
            validate_csrf_token()

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.cli.command("init-db")
    def init_db_command():
        init_db()
        print("SQLite schema initialized.")

    return app
