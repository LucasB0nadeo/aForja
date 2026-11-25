from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .auth import login_required
from .db import get_db
from .steam.api import SteamAPIError, fetch_store_game
from .steam.catalog import cache_store_game


wishlist = Blueprint("wishlist", __name__, url_prefix="/wishlist")


def _get_entry(entry_id):
    entry = get_db().execute(
        "SELECT * FROM wishlist_entries WHERE id = ? AND user_id = ?",
        (entry_id, g.user["id"]),
    ).fetchone()
    if entry is None:
        abort(404)
    return entry


def _parse_app_id(form):
    raw_app_id = form.get("steam_app_id", "").strip()
    try:
        app_id = int(raw_app_id)
        if app_id <= 0:
            raise ValueError
    except ValueError:
        app_id = None
    return raw_app_id, app_id


def _parse_personal_fields(form):
    priority_value = form.get("priority", "").strip()
    notes = form.get("notes", "").strip()
    errors = []
    try:
        priority = int(priority_value)
        if priority < 1 or priority > 5:
            raise ValueError
    except ValueError:
        priority = None
        errors.append("A prioridade deve ser um inteiro entre 1 e 5.")
    return {"priority": priority_value, "notes": notes, "parsed_priority": priority}, errors


def _render_form(entry, errors, editing, status=200):
    return (
        render_template(
            "wishlist/form.html",
            entry=entry,
            errors=errors,
            editing=editing,
        ),
        status,
    )


@wishlist.get("")
@login_required
def list_entries():
    entries = get_db().execute(
        """
        SELECT w.id, w.steam_app_id, w.priority, w.notes,
               c.name AS game_name, c.developer, c.release_date, c.platforms
        FROM wishlist_entries AS w
        LEFT JOIN steam_catalog AS c ON c.steam_app_id = w.steam_app_id
        WHERE w.user_id = ?
        ORDER BY w.priority DESC, COALESCE(c.name, '') COLLATE NOCASE
        """,
        (g.user["id"],),
    ).fetchall()
    return render_template("wishlist/list.html", entries=entries)


@wishlist.route("/new", methods=("GET", "POST"))
@login_required
def create_entry():
    entry = {"steam_app_id": "", "priority": "3", "notes": ""}
    if request.method == "POST":
        raw_app_id, app_id = _parse_app_id(request.form)
        personal_fields, errors = _parse_personal_fields(request.form)
        entry = {
            "steam_app_id": raw_app_id,
            "game_name": request.form.get("game_name", "").strip(),
            "priority": personal_fields["priority"],
            "notes": personal_fields["notes"],
        }
        if app_id is None:
            errors.append("Busque e selecione um jogo Steam válido.")

        if not errors:
            existing = get_db().execute(
                """
                SELECT id FROM wishlist_entries
                WHERE user_id = ? AND steam_app_id = ?
                """,
                (g.user["id"], app_id),
            ).fetchone()
            if existing is not None:
                flash("Esse jogo já está na sua lista de desejos.", "info")
                return redirect(url_for("wishlist.list_entries"))

            try:
                game = fetch_store_game(app_id)
            except SteamAPIError as error:
                errors.append(str(error))
            else:
                with get_db() as db:
                    cache_store_game(db, game)
                    cursor = db.execute(
                        """
                        INSERT INTO wishlist_entries (
                            user_id, steam_app_id, priority, notes
                        ) VALUES (?, ?, ?, ?)
                        ON CONFLICT(user_id, steam_app_id) DO NOTHING
                        """,
                        (g.user["id"], app_id, personal_fields["parsed_priority"], entry["notes"]),
                    )
                if cursor.rowcount == 0:
                    flash("Esse jogo já está na sua lista de desejos.", "info")
                    return redirect(url_for("wishlist.list_entries"))

        if errors:
            return _render_form(entry, errors, editing=False, status=400)
        flash("Jogo adicionado à lista de desejos.", "success")
        return redirect(url_for("wishlist.list_entries"))

    return _render_form(entry, [], editing=False)


@wishlist.route("/<int:entry_id>/edit", methods=("GET", "POST"))
@login_required
def edit_entry(entry_id):
    entry = _get_entry(entry_id)
    game = get_db().execute(
        "SELECT name FROM steam_catalog WHERE steam_app_id = ?",
        (entry["steam_app_id"],),
    ).fetchone()
    if request.method == "POST":
        personal_fields, errors = _parse_personal_fields(request.form)
        updated_entry = {
            "steam_app_id": entry["steam_app_id"],
            "game_name": game["name"] if game else f"AppID {entry['steam_app_id']}",
            "priority": personal_fields["priority"],
            "notes": personal_fields["notes"],
        }
        if errors:
            return _render_form(updated_entry, errors, editing=True, status=400)

        with get_db() as db:
            db.execute(
                """
                UPDATE wishlist_entries
                SET priority = ?, notes = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND user_id = ?
                """,
                (
                    personal_fields["parsed_priority"],
                    personal_fields["notes"],
                    entry_id,
                    g.user["id"],
                ),
            )
        flash("Item da lista de desejos atualizado.", "success")
        return redirect(url_for("wishlist.list_entries"))

    return _render_form(
        {
            **dict(entry),
            "game_name": game["name"] if game else f"AppID {entry['steam_app_id']}",
        },
        [],
        editing=True,
    )


@wishlist.route("/<int:entry_id>/delete", methods=("GET", "POST"))
@login_required
def delete_entry(entry_id):
    entry = _get_entry(entry_id)
    if request.method == "POST":
        if request.form.get("confirm") != "delete":
            abort(400)
        with get_db() as db:
            db.execute(
                "DELETE FROM wishlist_entries WHERE id = ? AND user_id = ?",
                (entry_id, g.user["id"]),
            )
        flash("Jogo removido da lista de desejos.", "success")
        return redirect(url_for("wishlist.list_entries"))

    game = get_db().execute(
        "SELECT name FROM steam_catalog WHERE steam_app_id = ?",
        (entry["steam_app_id"],),
    ).fetchone()
    return render_template(
        "wishlist/delete.html",
        entry=entry,
        game_name=game["name"] if game else f"AppID {entry['steam_app_id']}",
    )
