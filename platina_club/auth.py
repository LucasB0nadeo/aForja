import re
from functools import wraps
from pathlib import Path

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db


auth = Blueprint("auth", __name__)
EMAIL_PATTERN = re.compile(
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z]{2,63}"
)


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        user_id = session.get("user_id")
        if user_id is None:
            return redirect(url_for("auth.login"))

        user = get_db().execute(
            "SELECT id, email FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if user is None:
            session.clear()
            return redirect(url_for("auth.login"))

        g.user = user
        return view(*args, **kwargs)

    return wrapped_view


def is_valid_email(email):
    return (
        len(email) <= 254
        and EMAIL_PATTERN.fullmatch(email) is not None
        and len(email.rsplit("@", 1)[0]) <= 64
    )


@auth.route("/register", methods=("GET", "POST"))
def register():
    if request.method == "POST":
        email = request.form.get("email", "").strip().casefold()
        password = request.form.get("password", "")

        if not is_valid_email(email):
            flash("Informe um endereço de e-mail válido.", "error")
            return render_template("auth/register.html"), 400
        if not password:
            flash("A senha não pode ficar vazia.", "error")
            return render_template("auth/register.html"), 400

        with get_db() as db:
            cursor = db.execute(
                """
                INSERT INTO users (email, password_hash)
                VALUES (?, ?)
                ON CONFLICT(email) DO NOTHING
                """,
                (email, generate_password_hash(password)),
            )
            if cursor.rowcount == 0:
                flash("Este e-mail já está cadastrado.", "error")
                return render_template("auth/register.html"), 409

            user_id = cursor.lastrowid
            db.execute(
                "INSERT INTO profiles (user_id, display_name) VALUES (?, ?)",
                (user_id, email.split("@", 1)[0]),
            )

        session.clear()
        session["user_id"] = user_id
        return redirect(url_for("auth.dashboard"))

    return render_template("auth/register.html")


@auth.route("/login", methods=("GET", "POST"))
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().casefold()
        password = request.form.get("password", "")
        user = get_db().execute(
            "SELECT id, password_hash FROM users WHERE email = ?",
            (email,),
        ).fetchone()

        if user is None or not password or not check_password_hash(
            user["password_hash"], password
        ):
            flash("E-mail ou senha inválidos.", "error")
            return render_template("auth/login.html"), 401

        session.clear()
        session["user_id"] = user["id"]
        return redirect(url_for("auth.dashboard"))

    return render_template("auth/login.html")


@auth.post("/logout")
@login_required
def logout():
    session.clear()
    flash("Sessão encerrada.", "success")
    return redirect(url_for("auth.login"))


@auth.route("/delete-account", methods=("GET", "POST"))
@login_required
def delete_account():
    if request.method == "POST":
        password = request.form.get("password", "")
        user = get_db().execute(
            "SELECT password_hash FROM users WHERE id = ?",
            (g.user["id"],),
        ).fetchone()
        if user is None or not password or not check_password_hash(
            user["password_hash"], password
        ):
            flash("Senha incorreta. Sua conta não foi excluída.", "error")
            return render_template("auth/delete_account.html", user=g.user), 401

        profile = get_db().execute(
            "SELECT custom_avatar_path FROM profiles WHERE user_id = ?",
            (g.user["id"],),
        ).fetchone()
        custom_avatar = profile["custom_avatar_path"] if profile else None

        with get_db() as db:
            db.execute("DELETE FROM users WHERE id = ?", (g.user["id"],))

        if custom_avatar:
            avatar_folder = Path(
                current_app.config["PROFILE_AVATAR_FOLDER"]
            ).resolve()
            avatar_path = (avatar_folder / custom_avatar).resolve()
            if avatar_path.parent == avatar_folder and avatar_path.is_file():
                avatar_path.unlink()

        session.clear()
        flash("Sua conta foi excluída permanentemente.", "success")
        return redirect(url_for("auth.register"))

    return render_template("auth/delete_account.html", user=g.user)


@auth.get("/dashboard")
@login_required
def dashboard():
    steam_link = get_db().execute(
        "SELECT steam_id FROM steam_links WHERE user_id = ?",
        (g.user["id"],),
    ).fetchone()
    return render_template(
        "auth/dashboard.html",
        user=g.user,
        steam_link=steam_link,
    )
