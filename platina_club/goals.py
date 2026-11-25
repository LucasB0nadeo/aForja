from datetime import date

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .auth import login_required
from .db import get_db
from .steam.api import SteamAPIError, fetch_store_game
from .steam.catalog import cache_store_game


goals = Blueprint("goals", __name__, url_prefix="/goals")


def _get_goal(goal_id):
    goal = get_db().execute(
        "SELECT * FROM personal_goals WHERE id = ? AND user_id = ?",
        (goal_id, g.user["id"]),
    ).fetchone()
    if goal is None:
        abort(404)
    return goal


def _get_goal_games(goal_id):
    return get_db().execute(
        """
        SELECT gg.id, gg.steam_app_id, c.name AS game_name
        FROM goal_games AS gg
        LEFT JOIN steam_catalog AS c ON c.steam_app_id = gg.steam_app_id
        WHERE gg.goal_id = ? AND gg.user_id = ?
        ORDER BY gg.created_at, gg.id
        """,
        (goal_id, g.user["id"]),
    ).fetchall()


def _get_goal_game(goal_id, goal_game_id):
    goal = _get_goal(goal_id)
    game = get_db().execute(
        """
        SELECT * FROM goal_games
        WHERE id = ? AND goal_id = ? AND user_id = ?
        """,
        (goal_game_id, goal["id"], g.user["id"]),
    ).fetchone()
    if game is None:
        abort(404)
    return goal, game


def _sync_legacy_goal_game(db, goal_id, user_id):
    first_game = db.execute(
        """
        SELECT steam_app_id
        FROM goal_games
        WHERE goal_id = ? AND user_id = ?
        ORDER BY created_at, id
        LIMIT 1
        """,
        (goal_id, user_id),
    ).fetchone()
    db.execute(
        "UPDATE personal_goals SET steam_app_id = ? WHERE id = ? AND user_id = ?",
        (
            first_game["steam_app_id"] if first_game is not None else None,
            goal_id,
            user_id,
        ),
    )


def _parse_form(form, editing):
    objective = form.get("objective", "").strip()
    due_date = form.get("due_date", "").strip() or None
    app_id_value = form.get("steam_app_id", "").strip()
    game_name = form.get("game_name", "").strip()
    status = form.get("status", "in_progress").strip()
    errors = []

    if not objective:
        errors.append("Informe o objetivo da meta.")

    if due_date is not None:
        try:
            parsed_date = date.fromisoformat(due_date)
            if parsed_date.isoformat() != due_date:
                raise ValueError
        except ValueError:
            errors.append("Informe um prazo válido no formato AAAA-MM-DD.")

    steam_app_id = None
    if app_id_value:
        try:
            steam_app_id = int(app_id_value)
            if steam_app_id <= 0:
                raise ValueError
        except ValueError:
            errors.append("O AppID Steam deve ser um inteiro positivo.")
    if game_name and not app_id_value:
        errors.append("Selecione um jogo Steam nos resultados da busca.")

    if editing and status not in ("in_progress", "completed"):
        errors.append("O estado da meta é inválido.")
    if not editing:
        status = "in_progress"

    return {
        "objective": objective,
        "due_date": due_date or "",
        "steam_app_id": app_id_value,
        "game_name": game_name,
        "status": status,
        "parsed_steam_app_id": steam_app_id,
    }, errors


def _render_form(goal, errors, editing, status=200):
    return (
        render_template(
            "goals/form.html",
            goal=goal,
            errors=errors,
            editing=editing,
        ),
        status,
    )


@goals.get("")
@login_required
def list_goals():
    items = get_db().execute(
        """
        SELECT g.id, g.objective, g.due_date, g.steam_app_id, g.status,
               c.name AS game_name
        FROM personal_goals AS g
        LEFT JOIN steam_catalog AS c ON c.steam_app_id = g.steam_app_id
        WHERE g.user_id = ?
        ORDER BY g.created_at DESC, g.id DESC
        """,
        (g.user["id"],),
    ).fetchall()
    summary = {
        "total": len(items),
        "in_progress": sum(goal["status"] == "in_progress" for goal in items),
        "completed": sum(goal["status"] == "completed" for goal in items),
    }
    goal_games = {}
    for goal in items:
        goal_games[goal["id"]] = _get_goal_games(goal["id"])
    return render_template(
        "goals/list.html",
        goals=items,
        goal_games=goal_games,
        summary=summary,
    )


@goals.route("/new", methods=("GET", "POST"))
@login_required
def create_goal():
    goal = {
        "objective": "",
        "due_date": "",
        "steam_app_id": "",
        "game_name": "",
    }
    if request.method == "POST":
        goal, errors = _parse_form(request.form, editing=False)
        if errors:
            return _render_form(goal, errors, editing=False, status=400)

        game = None
        if goal["parsed_steam_app_id"] is not None:
            try:
                game = fetch_store_game(goal["parsed_steam_app_id"])
            except SteamAPIError as error:
                errors.append(str(error))
        if errors:
            return _render_form(goal, errors, editing=False, status=400)

        with get_db() as db:
            if game is not None:
                cache_store_game(db, game)
            cursor = db.execute(
                """
                INSERT INTO personal_goals (
                    user_id, objective, due_date, steam_app_id
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    g.user["id"],
                    goal["objective"],
                    goal["due_date"] or None,
                    goal["parsed_steam_app_id"],
                ),
            )
            goal_id = cursor.lastrowid
            if goal["parsed_steam_app_id"] is not None:
                db.execute(
                    """
                    INSERT INTO goal_games (
                        goal_id, user_id, steam_app_id
                    ) VALUES (?, ?, ?)
                    """,
                    (
                        goal_id,
                        g.user["id"],
                        goal["parsed_steam_app_id"],
                    ),
                )
        flash("Meta criada.", "success")
        return redirect(url_for("goals.list_goals"))

    return _render_form(goal, [], editing=False)


@goals.route("/<int:goal_id>/edit", methods=("GET", "POST"))
@login_required
def edit_goal(goal_id):
    goal = _get_goal(goal_id)
    if request.method == "POST":
        updated_goal, errors = _parse_form(request.form, editing=True)
        updated_goal["id"] = goal_id
        if errors:
            return (
                render_template(
                    "goals/form.html",
                    goal=updated_goal,
                    errors=errors,
                    editing=True,
                    goal_games=_get_goal_games(goal_id),
                ),
                400,
            )

        game = None
        app_id = updated_goal["parsed_steam_app_id"]
        updated_steam_app_id = (
            app_id if app_id is not None else goal["steam_app_id"]
        )
        if app_id is not None:
            cached_game = get_db().execute(
                "SELECT 1 FROM steam_catalog WHERE steam_app_id = ?",
                (app_id,),
            ).fetchone()
            if app_id != goal["steam_app_id"] or (
                cached_game is None and updated_goal["game_name"]
            ):
                try:
                    game = fetch_store_game(app_id)
                except SteamAPIError as error:
                    errors.append(str(error))
        if errors:
            return (
                render_template(
                    "goals/form.html",
                    goal=updated_goal,
                    errors=errors,
                    editing=True,
                    goal_games=_get_goal_games(goal_id),
                ),
                400,
            )

        with get_db() as db:
            if game is not None:
                cache_store_game(db, game)
            db.execute(
                """
                UPDATE personal_goals
                SET objective = ?, due_date = ?, steam_app_id = ?, status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND user_id = ?
                """,
                (
                    updated_goal["objective"],
                    updated_goal["due_date"] or None,
                    updated_steam_app_id,
                    updated_goal["status"],
                    goal_id,
                    g.user["id"],
                ),
            )
            if app_id is not None:
                existing_relation = db.execute(
                    """
                    SELECT id FROM goal_games
                    WHERE goal_id = ? AND user_id = ? AND steam_app_id = ?
                    """,
                    (goal_id, g.user["id"], app_id),
                ).fetchone()
                if existing_relation is not None:
                    db.execute(
                        """
                        UPDATE personal_goals
                        SET steam_app_id = ?
                        WHERE id = ? AND user_id = ?
                        """,
                        (app_id, goal_id, g.user["id"]),
                    )
                else:
                    relation = db.execute(
                        """
                        SELECT id FROM goal_games
                        WHERE goal_id = ? AND user_id = ?
                        ORDER BY created_at, id
                        LIMIT 1
                        """,
                        (goal_id, g.user["id"]),
                    ).fetchone()
                    if relation is None:
                        db.execute(
                            """
                            INSERT INTO goal_games (goal_id, user_id, steam_app_id)
                            VALUES (?, ?, ?)
                            """,
                            (goal_id, g.user["id"], app_id),
                        )
                    else:
                        db.execute(
                            """
                            UPDATE goal_games
                            SET steam_app_id = ?
                            WHERE id = ? AND goal_id = ? AND user_id = ?
                            """,
                            (app_id, relation["id"], goal_id, g.user["id"]),
                        )
                    _sync_legacy_goal_game(db, goal_id, g.user["id"])
        flash("Meta atualizada.", "success")
        return redirect(url_for("goals.list_goals"))

    goal = dict(goal)
    if goal["steam_app_id"] is not None:
        game = get_db().execute(
            "SELECT name FROM steam_catalog WHERE steam_app_id = ?",
            (goal["steam_app_id"],),
        ).fetchone()
        goal["game_name"] = game["name"] if game is not None else ""
    else:
        goal["game_name"] = ""
    return render_template(
        "goals/form.html",
        goal=goal,
        errors=[],
        editing=True,
        goal_games=_get_goal_games(goal_id),
    )


@goals.route("/<int:goal_id>/delete", methods=("GET", "POST"))
@login_required
def delete_goal(goal_id):
    goal = _get_goal(goal_id)
    if request.method == "POST":
        if request.form.get("confirm") != "delete":
            abort(400)
        with get_db() as db:
            db.execute(
                "DELETE FROM personal_goals WHERE id = ? AND user_id = ?",
                (goal_id, g.user["id"]),
            )
        flash("Meta removida.", "success")
        return redirect(url_for("goals.list_goals"))

    return render_template("goals/delete.html", goal=goal)


@goals.route("/<int:goal_id>/games/new", methods=("POST",))
@login_required
def create_goal_game(goal_id):
    goal = _get_goal(goal_id)
    app_id_value = request.form.get("steam_app_id", "").strip()
    game_name = request.form.get("game_name", "").strip()
    errors = []

    try:
        app_id = int(app_id_value)
        if app_id <= 0:
            raise ValueError
    except ValueError:
        app_id = None
        errors.append("Selecione um jogo Steam valido nos resultados da busca.")
    if app_id is not None and not game_name:
        errors.append("Selecione um jogo Steam nos resultados da busca.")

    if not errors:
        duplicate = get_db().execute(
            """
            SELECT 1 FROM goal_games
            WHERE goal_id = ? AND user_id = ? AND steam_app_id = ?
            """,
            (goal["id"], g.user["id"], app_id),
        ).fetchone()
        if duplicate is not None:
            errors.append("Este jogo ja faz parte da meta.")

    if not errors:
        try:
            game = fetch_store_game(app_id)
        except SteamAPIError as error:
            errors.append(str(error))

    if errors:
        for error in errors:
            flash(error, "error")
        return redirect(url_for("goals.edit_goal", goal_id=goal_id))

    with get_db() as db:
        cache_store_game(db, game)
        db.execute(
            """
            INSERT INTO goal_games (goal_id, user_id, steam_app_id)
            VALUES (?, ?, ?)
            """,
            (goal["id"], g.user["id"], app_id),
        )
        _sync_legacy_goal_game(db, goal["id"], g.user["id"])
    flash("Jogo adicionado a meta.", "success")
    return redirect(url_for("goals.edit_goal", goal_id=goal_id))


@goals.route(
    "/<int:goal_id>/games/<int:goal_game_id>/edit",
    methods=("GET", "POST"),
)
@login_required
def edit_goal_game(goal_id, goal_game_id):
    goal, goal_game = _get_goal_game(goal_id, goal_game_id)
    game = get_db().execute(
        "SELECT name FROM steam_catalog WHERE steam_app_id = ?",
        (goal_game["steam_app_id"],),
    ).fetchone()
    goal_game = dict(goal_game)
    goal_game["game_name"] = game["name"] if game is not None else ""

    if request.method == "POST":
        app_id_value = request.form.get("steam_app_id", "").strip()
        game_name = request.form.get("game_name", "").strip()
        errors = []
        try:
            app_id = int(app_id_value)
            if app_id <= 0:
                raise ValueError
        except ValueError:
            app_id = None
            errors.append("Selecione um jogo Steam valido nos resultados da busca.")
        if app_id is not None and not game_name:
            errors.append("Selecione um jogo Steam nos resultados da busca.")

        if not errors:
            duplicate = get_db().execute(
                """
                SELECT 1 FROM goal_games
                WHERE goal_id = ? AND user_id = ? AND steam_app_id = ?
                  AND id != ?
                """,
                (goal["id"], g.user["id"], app_id, goal_game_id),
            ).fetchone()
            if duplicate is not None:
                errors.append("Este jogo ja faz parte da meta.")

        if not errors:
            try:
                fetched_game = fetch_store_game(app_id)
            except SteamAPIError as error:
                errors.append(str(error))

        if errors:
            for error in errors:
                flash(error, "error")
            goal_game["steam_app_id"] = app_id_value
            return render_template(
                "goals/game_form.html",
                goal=goal,
                goal_game=goal_game,
            ), 400

        with get_db() as db:
            cache_store_game(db, fetched_game)
            db.execute(
                """
                UPDATE goal_games
                SET steam_app_id = ?
                WHERE id = ? AND goal_id = ? AND user_id = ?
                """,
                (app_id, goal_game_id, goal["id"], g.user["id"]),
            )
            _sync_legacy_goal_game(db, goal["id"], g.user["id"])
        flash("Jogo atualizado na meta.", "success")
        return redirect(url_for("goals.edit_goal", goal_id=goal_id))

    return render_template(
        "goals/game_form.html",
        goal=goal,
        goal_game=goal_game,
    )


@goals.route(
    "/<int:goal_id>/games/<int:goal_game_id>/delete",
    methods=("POST",),
)
@login_required
def delete_goal_game(goal_id, goal_game_id):
    goal, goal_game = _get_goal_game(goal_id, goal_game_id)
    if request.form.get("confirm") != "delete":
        abort(400)
    with get_db() as db:
        db.execute(
            """
            DELETE FROM goal_games
            WHERE id = ? AND goal_id = ? AND user_id = ?
            """,
            (goal_game_id, goal["id"], g.user["id"]),
        )
        _sync_legacy_goal_game(db, goal["id"], g.user["id"])
    flash("Jogo removido da meta.", "success")
    return redirect(url_for("goals.edit_goal", goal_id=goal_id))
