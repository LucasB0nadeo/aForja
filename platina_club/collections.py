from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .auth import login_required
from .db import get_db


collections = Blueprint("collections", __name__, url_prefix="/collections")


def _get_collection(collection_id):
    collection = get_db().execute(
        "SELECT * FROM collections WHERE id = ? AND user_id = ?",
        (collection_id, g.user["id"]),
    ).fetchone()
    if collection is None:
        abort(404)
    return collection


def _owned_games():
    return get_db().execute(
        """
        SELECT id, name, source
        FROM games
        WHERE user_id = ?
        ORDER BY name COLLATE NOCASE
        """,
        (g.user["id"],),
    ).fetchall()


def _parse_form(form):
    name = form.get("name", "").strip()
    description = form.get("description", "").strip()
    errors = []
    if not name:
        errors.append("Informe o nome da coleção.")

    game_ids = []
    for value in form.getlist("game_ids"):
        try:
            game_id = int(value)
            if game_id <= 0:
                raise ValueError
            game_ids.append(game_id)
        except ValueError:
            errors.append("A seleção de jogos é inválida.")
            break
    game_ids = list(dict.fromkeys(game_ids))
    if not errors and game_ids:
        placeholders = ", ".join("?" for _ in game_ids)
        owned_count = get_db().execute(
            f"""
            SELECT COUNT(*) FROM games
            WHERE user_id = ? AND id IN ({placeholders})
            """,
            (g.user["id"], *game_ids),
        ).fetchone()[0]
        if owned_count != len(game_ids):
            errors.append("Selecione apenas jogos da sua biblioteca.")

    return {"name": name, "description": description}, game_ids, errors


def _render_form(collection, selected_game_ids, errors, editing, status=200):
    return (
        render_template(
            "collections/form.html",
            collection=collection,
            games=_owned_games(),
            selected_game_ids=set(selected_game_ids),
            errors=errors,
            editing=editing,
        ),
        status,
    )


@collections.get("")
@login_required
def list_collections():
    items = get_db().execute(
        """
        SELECT c.id, c.name, c.description, COUNT(cg.game_id) AS game_count
        FROM collections AS c
        LEFT JOIN collection_games AS cg
            ON cg.collection_id = c.id AND cg.user_id = c.user_id
        WHERE c.user_id = ?
        GROUP BY c.id
        ORDER BY c.name COLLATE NOCASE
        """,
        (g.user["id"],),
    ).fetchall()
    return render_template("collections/list.html", collections=items)


@collections.route("/new", methods=("GET", "POST"))
@login_required
def create_collection():
    collection = {"name": "", "description": ""}
    if request.method == "POST":
        collection, game_ids, errors = _parse_form(request.form)
        if errors:
            return _render_form(collection, game_ids, errors, editing=False, status=400)

        with get_db() as db:
            collection_id = db.execute(
                """
                INSERT INTO collections (user_id, name, description)
                VALUES (?, ?, ?)
                """,
                (g.user["id"], collection["name"], collection["description"]),
            ).lastrowid
            db.executemany(
                """
                INSERT INTO collection_games (user_id, collection_id, game_id)
                VALUES (?, ?, ?)
                """,
                (
                    (g.user["id"], collection_id, game_id)
                    for game_id in game_ids
                ),
            )
        flash("Coleção criada.", "success")
        return redirect(url_for("collections.edit_collection", collection_id=collection_id))

    return _render_form(collection, [], [], editing=False)


@collections.route("/<int:collection_id>/edit", methods=("GET", "POST"))
@login_required
def edit_collection(collection_id):
    collection = _get_collection(collection_id)
    selected_game_ids = [
        row["game_id"]
        for row in get_db().execute(
            """
            SELECT game_id FROM collection_games
            WHERE collection_id = ? AND user_id = ?
            """,
            (collection_id, g.user["id"]),
        ).fetchall()
    ]

    if request.method == "POST":
        updated_collection, game_ids, errors = _parse_form(request.form)
        if errors:
            return _render_form(
                updated_collection,
                game_ids,
                errors,
                editing=True,
                status=400,
            )

        with get_db() as db:
            db.execute(
                """
                UPDATE collections
                SET name = ?, description = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND user_id = ?
                """,
                (
                    updated_collection["name"],
                    updated_collection["description"],
                    collection_id,
                    g.user["id"],
                ),
            )
            db.execute(
                """
                DELETE FROM collection_games
                WHERE collection_id = ? AND user_id = ?
                """,
                (collection_id, g.user["id"]),
            )
            db.executemany(
                """
                INSERT INTO collection_games (user_id, collection_id, game_id)
                VALUES (?, ?, ?)
                """,
                (
                    (g.user["id"], collection_id, game_id)
                    for game_id in game_ids
                ),
            )
        flash("Coleção atualizada.", "success")
        return redirect(url_for("collections.list_collections"))

    return _render_form(collection, selected_game_ids, [], editing=True)


@collections.route("/<int:collection_id>/delete", methods=("GET", "POST"))
@login_required
def delete_collection(collection_id):
    collection = _get_collection(collection_id)
    if request.method == "POST":
        if request.form.get("confirm") != "delete":
            abort(400)
        with get_db() as db:
            db.execute(
                "DELETE FROM collections WHERE id = ? AND user_id = ?",
                (collection_id, g.user["id"]),
            )
        flash("Coleção excluída.", "success")
        return redirect(url_for("collections.list_collections"))

    return render_template("collections/delete.html", collection=collection)
