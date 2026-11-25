from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .auth import login_required
from .db import get_db
from .steam.api import SteamAPIError, fetch_store_game
from .steam.catalog import cache_store_game


reviews = Blueprint("reviews", __name__, url_prefix="/reviews")


def _get_review(review_id):
    review = get_db().execute(
        "SELECT * FROM game_reviews WHERE id = ? AND user_id = ?",
        (review_id, g.user["id"]),
    ).fetchone()
    if review is None:
        abort(404)
    return review


def _parse_review_form(form, include_app_id):
    review_text = form.get("review_text", "").strip()
    rating_value = form.get("rating", "").strip()
    app_id_value = form.get("steam_app_id", "").strip() if include_app_id else None
    game_name = form.get("game_name", "").strip() if include_app_id else ""
    errors = []

    if not review_text:
        errors.append("Escreva sua avaliação.")
    try:
        rating = int(rating_value)
        if rating < 1 or rating > 5:
            raise ValueError
    except ValueError:
        rating = None
        errors.append("A nota deve ser um inteiro entre 1 e 5.")

    app_id = None
    if include_app_id:
        try:
            app_id = int(app_id_value)
            if app_id <= 0:
                raise ValueError
        except ValueError:
            app_id = None
            errors.append("Busque e selecione um jogo Steam válido.")

    return {
        "steam_app_id": app_id_value if include_app_id else None,
        "game_name": game_name,
        "review_text": review_text,
        "rating": rating_value,
        "parsed_app_id": app_id,
        "parsed_rating": rating,
    }, errors


def _render_form(review, errors, editing, existing_review_id=None, status=200):
    return (
        render_template(
            "reviews/form.html",
            review=review,
            errors=errors,
            editing=editing,
            existing_review_id=existing_review_id,
        ),
        status,
    )


@reviews.get("")
@login_required
def list_reviews():
    items = get_db().execute(
        """
        SELECT r.id, r.steam_app_id, r.review_text, r.rating, r.updated_at,
               c.name AS game_name
        FROM game_reviews AS r
        LEFT JOIN steam_catalog AS c ON c.steam_app_id = r.steam_app_id
        WHERE r.user_id = ?
        ORDER BY r.updated_at DESC, r.id DESC
        """,
        (g.user["id"],),
    ).fetchall()
    return render_template("reviews/list.html", reviews=items)


@reviews.route("/new", methods=("GET", "POST"))
@login_required
def create_review():
    review = {
        "steam_app_id": "",
        "review_text": "",
        "rating": "",
    }
    if request.method == "POST":
        review, errors = _parse_review_form(request.form, include_app_id=True)
        existing_review_id = None
        if not errors:
            existing = get_db().execute(
                """
                SELECT id FROM game_reviews
                WHERE user_id = ? AND steam_app_id = ?
                """,
                (g.user["id"], review["parsed_app_id"]),
            ).fetchone()
            if existing is not None:
                existing_review_id = existing["id"]
                errors.append("Você já avaliou este jogo; edite a avaliação existente.")

        if not errors:
            try:
                game = fetch_store_game(review["parsed_app_id"])
            except SteamAPIError as error:
                errors.append(str(error))
            else:
                with get_db() as db:
                    cache_store_game(db, game)
                    cursor = db.execute(
                        """
                        INSERT INTO game_reviews (
                            user_id, steam_app_id, review_text, rating
                        ) VALUES (?, ?, ?, ?)
                        ON CONFLICT(user_id, steam_app_id) DO NOTHING
                        """,
                        (
                            g.user["id"],
                            review["parsed_app_id"],
                            review["review_text"],
                            review["parsed_rating"],
                        ),
                    )
                    if cursor.rowcount == 0:
                        existing = db.execute(
                            """
                            SELECT id FROM game_reviews
                            WHERE user_id = ? AND steam_app_id = ?
                            """,
                            (g.user["id"], review["parsed_app_id"]),
                        ).fetchone()
                        existing_review_id = existing["id"]
                        errors.append(
                            "Você já avaliou este jogo; edite a avaliação existente."
                        )

        if errors:
            return _render_form(
                review,
                errors,
                editing=False,
                existing_review_id=existing_review_id,
                status=400,
            )
        flash("Avaliação cadastrada.", "success")
        return redirect(url_for("reviews.list_reviews"))

    return _render_form(review, [], editing=False)


@reviews.route("/<int:review_id>/edit", methods=("GET", "POST"))
@login_required
def edit_review(review_id):
    review = _get_review(review_id)
    if request.method == "POST":
        updated_review, errors = _parse_review_form(
            request.form,
            include_app_id=False,
        )
        if errors:
            updated_review["steam_app_id"] = review["steam_app_id"]
            return _render_form(updated_review, errors, editing=True, status=400)

        with get_db() as db:
            db.execute(
                """
                UPDATE game_reviews
                SET review_text = ?, rating = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND user_id = ?
                """,
                (
                    updated_review["review_text"],
                    updated_review["parsed_rating"],
                    review_id,
                    g.user["id"],
                ),
            )
        flash("Avaliação atualizada.", "success")
        return redirect(url_for("reviews.list_reviews"))

    return _render_form(review, [], editing=True)


@reviews.route("/<int:review_id>/delete", methods=("GET", "POST"))
@login_required
def delete_review(review_id):
    review = _get_review(review_id)
    if request.method == "POST":
        if request.form.get("confirm") != "delete":
            abort(400)
        with get_db() as db:
            db.execute(
                "DELETE FROM game_reviews WHERE id = ? AND user_id = ?",
                (review_id, g.user["id"]),
            )
        flash("Avaliação removida.", "success")
        return redirect(url_for("reviews.list_reviews"))

    game = get_db().execute(
        "SELECT name FROM steam_catalog WHERE steam_app_id = ?",
        (review["steam_app_id"],),
    ).fetchone()
    return render_template(
        "reviews/delete.html",
        review=review,
        game_name=game["name"] if game else f"AppID {review['steam_app_id']}",
    )
