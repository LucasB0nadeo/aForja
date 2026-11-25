from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from .auth import login_required
from .db import get_db
from .howlongtobeat import HowLongToBeatUnavailable, search_hltb_games
from .rankings import refresh_achievement_ranking_records
from .steam.achievements import (
    BADGE_LABELS,
    BADGE_THRESHOLDS,
    sync_game_achievements,
)
from .steam.api import SteamAPIError, fetch_store_game
from .steam.catalog import cache_store_game
from .steam.config import SteamAPIConfigurationError, get_steam_api_key
from .steam.library import (
    SteamLinkRequiredError,
    sync_owned_games,
    upsert_steam_game,
)


library = Blueprint("library", __name__, url_prefix="/games")


def _parse_game_form(form):
    name = form.get("name", "").strip()
    platform = form.get("platform", "").strip()
    developer = form.get("developer", "").strip()
    year_text = form.get("release_year", "").strip()

    errors = []
    if not name:
        errors.append("Informe o nome do jogo.")
    if not platform:
        errors.append("Informe a plataforma.")
    if not developer:
        errors.append("Informe a desenvolvedora.")

    try:
        release_year = int(year_text)
        if release_year <= 0:
            raise ValueError
    except ValueError:
        errors.append("O ano de lançamento deve ser um inteiro positivo.")
        release_year = None

    return {
        "name": name,
        "platform": platform,
        "developer": developer,
        "release_year": release_year,
    }, errors


def _parse_achievement_form(form):
    name = form.get("name", "").strip()
    description = form.get("description", "").strip()
    rarity = form.get("rarity", "").strip()
    unlocked_value = form.get("unlocked", "0")

    errors = []
    if not name:
        errors.append("Informe o nome da conquista.")
    if not description:
        errors.append("Informe a descrição da conquista.")
    if not rarity:
        errors.append("Informe a raridade da conquista.")
    if unlocked_value not in ("0", "1"):
        errors.append("O estado de desbloqueio é inválido.")

    return {
        "name": name,
        "description": description,
        "rarity": rarity,
        "unlocked": unlocked_value == "1",
    }, errors


def _get_game(game_id):
    game = get_db().execute(
        "SELECT * FROM games WHERE id = ? AND user_id = ?",
        (game_id, g.user["id"]),
    ).fetchone()
    if game is None:
        abort(404)
    return game


def _require_manual_game(game):
    if game["source"] != "manual":
        abort(404)


def _get_manual_achievement(game_id, achievement_id):
    achievement = get_db().execute(
        """
        SELECT *
        FROM achievements
        WHERE id = ? AND game_id = ? AND user_id = ? AND source = 'manual'
        """,
        (achievement_id, game_id, g.user["id"]),
    ).fetchone()
    if achievement is None:
        abort(404)
    return achievement


@library.get("")
@login_required
def list_games():
    db = get_db()
    allowed_sort = ("name", "progress", "latest")
    allowed_direction = ("asc", "desc")
    allowed_status = ("all", "completed", "in_progress", "not_started")
    allowed_page_size = ("10", "20", "30")

    sort_by = request.args.get("sort")
    direction = request.args.get("direction")
    status_filter = request.args.get("status")
    query = request.args.get("q")
    page_size_value = request.args.get("page_size")
    page_value = request.args.get("page")

    if sort_by is None:
        sort_by = session.get("library_sort", "name")
    if direction is None:
        direction = session.get("library_direction", "asc")
    if status_filter is None:
        status_filter = session.get("library_status", "all")
    if query is None:
        query = session.get("library_query", "")
    if page_size_value is None:
        page_size_value = session.get("library_page_size", "20")

    query = query.strip()[:100]
    sort_by = sort_by if sort_by in allowed_sort else "name"
    direction = direction if direction in allowed_direction else "asc"
    status_filter = (
        status_filter if status_filter in allowed_status else "all"
    )
    page_size_value = (
        page_size_value if page_size_value in allowed_page_size else "20"
    )
    page_size = int(page_size_value)
    try:
        page = max(1, int(page_value or "1"))
    except ValueError:
        page = 1

    session["library_sort"] = sort_by
    session["library_direction"] = direction
    session["library_status"] = status_filter
    session["library_query"] = query
    session["library_page_size"] = page_size_value
    if sort_by not in ("name", "progress", "latest"):
        sort_by = "name"
    if direction not in ("asc", "desc"):
        direction = "asc"

    games = db.execute(
        """
        SELECT g.id, g.source, g.name, g.platform, g.developer, g.release_year,
               g.steam_app_id, g.icon_url, g.achievements_sync_status,
               (
                   SELECT COUNT(*)
                   FROM achievements AS a
                   WHERE a.game_id = g.id AND a.user_id = g.user_id
               ) AS achievement_total,
               (
                   SELECT COALESCE(SUM(a.unlocked), 0)
                   FROM achievements AS a
                   WHERE a.game_id = g.id AND a.user_id = g.user_id
               ) AS achievement_unlocked,
               (
                   SELECT MAX(a.unlocked_at)
                   FROM achievements AS a
                   WHERE a.game_id = g.id
                     AND a.user_id = g.user_id
                     AND a.unlocked = 1
                     AND a.unlocked_at IS NOT NULL
               ) AS last_unlocked_at,
               (
                   SELECT COUNT(*)
                   FROM achievements AS a
                   WHERE a.game_id = g.id
                     AND a.user_id = g.user_id
                     AND a.unlocked = 1
                     AND a.unlocked_at >= datetime('now', '-7 days')
               ) AS recent_unlocked_count
        FROM games AS g
        WHERE g.user_id = ?
        """,
        (g.user["id"],),
    ).fetchall()
    games = [dict(game) for game in games]
    for game in games:
        total = game["achievement_total"]
        game["achievement_percent"] = (
            round(100 * game["achievement_unlocked"] / total, 2)
            if total
            else -1
        )
        if total and game["achievement_unlocked"] >= total:
            game["completion_status"] = "completed"
        elif game["achievement_unlocked"] > 0:
            game["completion_status"] = "in_progress"
        else:
            game["completion_status"] = "not_started"

    valid_progress = [
        game["achievement_percent"]
        for game in games
        if game["achievement_percent"] >= 0
    ]
    completed_count = sum(
        game["completion_status"] == "completed"
        for game in games
    )
    in_progress_count = sum(
        game["completion_status"] == "in_progress"
        for game in games
    )
    not_started_count = sum(
        game["completion_status"] == "not_started"
        for game in games
    )
    summary = {
        "total": len(games),
        "completed": completed_count,
        "in_progress": in_progress_count,
        "not_started": not_started_count,
        "average": (
            round(sum(valid_progress) / len(valid_progress), 1)
            if valid_progress
            else 0
        ),
    }

    if query:
        folded_query = query.casefold()
        games = [
            game
            for game in games
            if folded_query in game["name"].casefold()
        ]
    if status_filter != "all":
        games = [
            game
            for game in games
            if game["completion_status"] == status_filter
        ]

    if sort_by == "progress":
        if direction == "asc":
            games.sort(
                key=lambda game: (
                    game["achievement_percent"] < 0,
                    game["achievement_percent"],
                    game["name"].casefold(),
                ),
            )
        else:
            games.sort(
                key=lambda game: (
                    game["achievement_percent"] < 0,
                    -game["achievement_percent"]
                    if game["achievement_percent"] >= 0
                    else 0,
                    game["name"].casefold(),
                ),
            )
    elif sort_by == "latest":
        if direction == "asc":
            games.sort(
                key=lambda game: (
                    game["last_unlocked_at"] is None,
                    game["last_unlocked_at"] or "",
                    game["name"].casefold(),
                ),
            )
        else:
            dated = [game for game in games if game["last_unlocked_at"]]
            undated = [game for game in games if not game["last_unlocked_at"]]
            dated.sort(
                key=lambda game: (
                    game["last_unlocked_at"],
                    game["name"].casefold(),
                ),
                reverse=True,
            )
            undated.sort(key=lambda game: game["name"].casefold())
            games = dated + undated
    else:
        games.sort(
            key=lambda game: game["name"].casefold(),
            reverse=direction == "desc",
        )
    total_filtered = len(games)
    total_pages = max(1, (total_filtered + page_size - 1) // page_size)
    page = min(page, total_pages)
    start = (page - 1) * page_size
    page_games = games[start:start + page_size]
    steam_link = db.execute(
        """
        SELECT games_sync_status, games_synced_at, games_sync_error
        FROM steam_links
        WHERE user_id = ?
        """,
        (g.user["id"],),
    ).fetchone()
    return render_template(
        "games/list.html",
        games=page_games,
        steam_link=steam_link,
        steam_game_count=sum(game["source"] == "steam" for game in games),
        sort_by=sort_by,
        direction=direction,
        status_filter=status_filter,
        query=query,
        page_size=page_size,
        page=page,
        total_pages=total_pages,
        total_filtered=total_filtered,
        summary=summary,
    )


@library.get("/search")
@login_required
def search_game_statistics():
    return render_template("games/search_statistics.html")


@library.get("/howlongtobeat")
@login_required
def search_howlongtobeat():
    query = request.args.get("query", "").strip()
    fragment_requested = request.args.get("fragment") == "1"
    if len(query) < 2:
        if fragment_requested:
            return render_template(
                "games/_howlongtobeat_results.html",
                hltb_results=None,
            ), 400
        flash(
            "Digite pelo menos 2 caracteres para pesquisar no HowLongToBeat.",
            "error",
        )
        return redirect(url_for("library.search_game_statistics"))
    if len(query) > 100:
        if fragment_requested:
            return render_template(
                "games/_howlongtobeat_results.html",
                hltb_results=None,
            ), 400
        flash("A busca no HowLongToBeat deve ter até 100 caracteres.", "error")
        return redirect(url_for("library.search_game_statistics"))

    try:
        results = search_hltb_games(query)
    except HowLongToBeatUnavailable:
        if fragment_requested:
            return render_template(
                "games/_howlongtobeat_results.html",
                hltb_results=None,
            ), 503
        return render_template(
            "games/howlongtobeat.html",
            query=query,
            hltb_results=None,
        ), 503

    if fragment_requested:
        return render_template(
            "games/_howlongtobeat_results.html",
            hltb_results=results,
        )

    return render_template(
        "games/howlongtobeat.html",
        query=query,
        hltb_results=results,
    )


@library.get("/statistics")
@login_required
def game_statistics():
    try:
        steam_app_id = int(request.args.get("steam_app_id", ""))
        if steam_app_id <= 0:
            raise ValueError
    except (TypeError, ValueError):
        flash("Busque e selecione um jogo Steam.", "error")
        return redirect(url_for("library.search_game_statistics"))

    db = get_db()
    game = db.execute(
        "SELECT name, developer, icon_url FROM steam_catalog WHERE steam_app_id = ?",
        (steam_app_id,),
    ).fetchone()
    catalog_error = None
    if game is None:
        try:
            store_game = fetch_store_game(steam_app_id)
        except SteamAPIError as error:
            current_app.logger.warning(
                "Steam game details unavailable for AppID %s: %s",
                steam_app_id,
                error,
            )
            catalog_error = "Os detalhes do jogo não estão disponíveis no momento."
        else:
            with db:
                cache_store_game(db, store_game)
            game = store_game

    hltb_search_name = game["name"] if game else None
    game_name = hltb_search_name
    if game_name is None:
        local_game = db.execute(
            """
            SELECT name FROM games
            WHERE steam_app_id = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (steam_app_id,),
        ).fetchone()
        if local_game:
            hltb_search_name = local_game["name"]
        game_name = (
            local_game["name"]
            if local_game
            else f"Jogo Steam (AppID {steam_app_id})"
        )
    library_game = db.execute(
        """
        SELECT id FROM games
        WHERE user_id = ? AND steam_app_id = ? AND source = 'steam'
        """,
        (g.user["id"], steam_app_id),
    ).fetchone()

    review_stats = db.execute(
        """
        SELECT ROUND(AVG(rating), 1) AS average, COUNT(*) AS count
        FROM game_reviews
        WHERE steam_app_id = ?
        """,
        (steam_app_id,),
    ).fetchone()

    eligible_players = db.execute(
        """
        SELECT COUNT(DISTINCT g.user_id)
        FROM games AS g
        WHERE g.source = 'steam'
          AND g.steam_app_id = ?
          AND g.achievements_synced_at IS NOT NULL
          AND EXISTS (
              SELECT 1
              FROM achievements AS a
              WHERE a.game_id = g.id
                AND a.user_id = g.user_id
                AND a.source = 'steam'
          )
        """,
        (steam_app_id,),
    ).fetchone()[0]
    earned_badges = db.execute(
        """
        SELECT b.badge_type, COUNT(DISTINCT b.user_id) AS count
        FROM badge_awards AS b
        JOIN games AS g
          ON g.id = b.game_id
         AND g.user_id = b.user_id
         AND g.steam_app_id = b.steam_app_id
        WHERE g.source = 'steam'
          AND g.steam_app_id = ?
          AND g.achievements_synced_at IS NOT NULL
        GROUP BY b.badge_type
        """,
        (steam_app_id,),
    ).fetchall()
    badge_counts = {row["badge_type"]: row["count"] for row in earned_badges}
    badge_types = (*[badge_type for _, badge_type in BADGE_THRESHOLDS], "ember")
    badge_stats = [
        {
            "badge_type": badge_type,
            "label": BADGE_LABELS[badge_type],
            "count": badge_counts.get(badge_type, 0),
            "percent": (
                round(100 * badge_counts.get(badge_type, 0) / eligible_players, 1)
                if eligible_players
                else None
            ),
        }
        for badge_type in badge_types
    ]

    steam_achievements = db.execute(
        """
        WITH ranked_achievements AS (
            SELECT a.name, a.global_percent,
                   ROW_NUMBER() OVER (
                       PARTITION BY a.steam_api_name
                       ORDER BY a.updated_at DESC, a.id DESC
                   ) AS row_number
            FROM achievements AS a
            JOIN games AS g
              ON g.id = a.game_id
             AND g.user_id = a.user_id
            WHERE g.steam_app_id = ?
              AND g.source = 'steam'
              AND a.source = 'steam'
              AND a.global_percent IS NOT NULL
              AND a.steam_api_name IS NOT NULL
        )
        SELECT name, global_percent
        FROM ranked_achievements
        WHERE row_number = 1
        ORDER BY name COLLATE NOCASE
        """,
        (steam_app_id,),
    ).fetchall()

    return render_template(
        "games/statistics.html",
        steam_app_id=steam_app_id,
        game_name=game_name,
        hltb_search_name=hltb_search_name,
        game_icon_url=game["icon_url"] if game else None,
        catalog_error=catalog_error,
        catalog_game_available=game is not None,
        library_game_id=library_game["id"] if library_game else None,
        review_stats=review_stats,
        badge_stats=badge_stats,
        eligible_players=eligible_players,
        steam_achievements=steam_achievements,
    )


@library.post("/import")
@login_required
def import_steam_game():
    try:
        steam_app_id = int(request.form.get("steam_app_id", ""))
        if steam_app_id <= 0:
            raise ValueError
    except (TypeError, ValueError):
        flash("Selecione um jogo Steam válido para importar.", "error")
        return redirect(url_for("library.search_game_statistics"))

    db = get_db()
    existing_game = db.execute(
        """
        SELECT id FROM games
        WHERE user_id = ? AND steam_app_id = ? AND source = 'steam'
        """,
        (g.user["id"], steam_app_id),
    ).fetchone()
    if existing_game is not None:
        flash("Este jogo já está na sua biblioteca.", "info")
        return redirect(
            url_for("library.game_statistics", steam_app_id=steam_app_id)
        )

    game = db.execute(
        "SELECT steam_app_id, name FROM steam_catalog WHERE steam_app_id = ?",
        (steam_app_id,),
    ).fetchone()
    store_game = None
    if game is None:
        try:
            store_game = fetch_store_game(steam_app_id)
        except SteamAPIError as error:
            current_app.logger.warning(
                "Steam game import failed for AppID %s: %s",
                steam_app_id,
                error,
            )
            flash("Não foi possível validar este jogo no catálogo Steam.", "error")
            return redirect(
                url_for("library.game_statistics", steam_app_id=steam_app_id)
            )
        game = store_game

    with db:
        if store_game is not None:
            cache_store_game(db, store_game)
        game_id = upsert_steam_game(
            db,
            g.user["id"],
            {
                "steam_app_id": steam_app_id,
                "name": game["name"],
                "playtime_minutes": 0,
            },
            update_playtime=False,
        )

    flash("Jogo adicionado à sua biblioteca.", "success")
    return redirect(
        url_for("library.game_detail", game_id=game_id)
    )


@library.get("/<int:game_id>")
@login_required
def game_detail(game_id):
    game = _get_game(game_id)
    steam_linked = get_db().execute(
        "SELECT 1 FROM steam_links WHERE user_id = ?",
        (g.user["id"],),
    ).fetchone() is not None
    if game["source"] == "steam" and steam_linked:
        sync_state = get_db().execute(
            """
            SELECT achievements_sync_status,
                   achievements_synced_at IS NULL AS missing_snapshot,
                   achievements_synced_at <= datetime('now', '-15 minutes') AS expired
            FROM games
            WHERE id = ? AND user_id = ?
            """,
            (game_id, g.user["id"]),
        ).fetchone()
        if (
            sync_state["achievements_sync_status"] != "success"
            or sync_state["missing_snapshot"]
            or sync_state["expired"]
        ):
            try:
                sync_game_achievements(g.user["id"], game_id)
            except (
                SteamAPIConfigurationError,
                SteamAPIError,
                SteamLinkRequiredError,
            ) as error:
                current_app.logger.warning(
                    "Steam achievement sync failed for game %s: %s",
                    game_id,
                    error,
                )
            game = _get_game(game_id)

    achievements = get_db().execute(
        """
        SELECT id, source, name, description, rarity, global_percent,
               icon_url, icon_gray_url, unlocked, unlocked_at
        FROM achievements
        WHERE game_id = ? AND user_id = ?
        ORDER BY name COLLATE NOCASE
        """,
        (game_id, g.user["id"]),
    ).fetchall()
    progress = None
    badge_awards = []
    if game["source"] == "steam":
        if game["achievements_synced_at"] is not None:
            stats = get_db().execute(
                """
                SELECT COUNT(*) AS total, COALESCE(SUM(unlocked), 0) AS unlocked
                FROM achievements
                WHERE game_id = ? AND user_id = ? AND source = 'steam'
                """,
                (game_id, g.user["id"]),
            ).fetchone()
            if stats["total"]:
                progress = {
                    "total": stats["total"],
                    "unlocked": stats["unlocked"],
                    "percent": round(100 * stats["unlocked"] / stats["total"], 1),
                }
        badge_awards = get_db().execute(
            """
            SELECT badge_type, awarded_at
            FROM badge_awards
            WHERE user_id = ? AND game_id = ?
            ORDER BY awarded_at, id
            """,
            (g.user["id"], game_id),
        ).fetchall()
    return render_template(
        "games/detail.html",
        game=game,
        achievements=achievements,
        steam_linked=steam_linked,
        progress=progress,
        badge_awards=badge_awards,
        badge_labels=BADGE_LABELS,
    )


@library.post("/<int:game_id>/achievements/sync")
@login_required
def sync_achievements(game_id):
    game = _get_game(game_id)
    if game["source"] != "steam":
        abort(404)

    try:
        count = sync_game_achievements(g.user["id"], game_id)
    except (
        SteamAPIConfigurationError,
        SteamAPIError,
        SteamLinkRequiredError,
    ) as error:
        current_app.logger.warning(
            "Steam achievement sync failed for game %s: %s",
            game_id,
            error,
        )
        flash(f"As conquistas não puderam ser sincronizadas: {error}", "error")
    else:
        flash(f"Conquistas Steam sincronizadas: {count}.", "success")
    return redirect(url_for("library.game_detail", game_id=game_id))


@library.post("/achievements/sync-all")
@login_required
def sync_all_achievements():
    user_id = g.user["id"]
    steam_link = get_db().execute(
        "SELECT 1 FROM steam_links WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if steam_link is None:
        flash("Vincule uma conta Steam antes de sincronizar conquistas.", "error")
        return redirect(url_for("library.list_games"))

    games = get_db().execute(
        """
        SELECT id, name
        FROM games
        WHERE user_id = ? AND source = 'steam'
        ORDER BY name COLLATE NOCASE
        """,
        (user_id,),
    ).fetchall()
    if not games:
        flash("Não há jogos Steam na biblioteca para sincronizar.", "info")
        return redirect(url_for("library.list_games"))

    try:
        get_steam_api_key()
    except SteamAPIConfigurationError as error:
        current_app.logger.warning("Bulk Steam achievement sync failed: %s", error)
        flash(f"As conquistas não puderam ser sincronizadas: {error}", "error")
        return redirect(url_for("library.list_games"))

    succeeded = 0
    failures = []
    for game in games:
        try:
            sync_game_achievements(user_id, game["id"])
        except (
            SteamAPIConfigurationError,
            SteamAPIError,
            SteamLinkRequiredError,
        ) as error:
            current_app.logger.warning(
                "Bulk Steam achievement sync failed for game %s: %s",
                game["id"],
                error,
            )
            failures.append((game["name"], str(error)))
        else:
            succeeded += 1

    if failures:
        failure_details = "; ".join(
            f"{name}: {error}" for name, error in failures[:3]
        )
        remaining = len(failures) - 3
        if remaining > 0:
            failure_details += f"; mais {remaining} falha(s)"
        flash(
            f"Sincronização parcial: {succeeded} de {len(games)} jogo(s) "
            f"atualizados. {failure_details}",
            "error",
        )
    else:
        flash(
            f"Conquistas sincronizadas em todos os {succeeded} jogos Steam.",
            "success",
        )
    return redirect(url_for("library.list_games"))


@library.post("/steam/sync")
@login_required
def sync_steam():
    user_id = g.user["id"]
    steam_link = get_db().execute(
        "SELECT 1 FROM steam_links WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if steam_link is None:
        flash("Vincule uma conta Steam antes de sincronizar.", "error")
        return redirect(url_for("library.list_games"))

    library_updated = False
    imported_count = 0
    library_error = None
    try:
        imported_count = sync_owned_games(user_id)
        library_updated = True
    except (
        SteamAPIConfigurationError,
        SteamAPIError,
        SteamLinkRequiredError,
    ) as error:
        library_error = str(error)
        current_app.logger.warning(
            "Combined Steam library sync failed: %s",
            error,
        )

    games = get_db().execute(
        """
        SELECT id, name
        FROM games
        WHERE user_id = ? AND source = 'steam'
        ORDER BY name COLLATE NOCASE
        """,
        (user_id,),
    ).fetchall()

    succeeded = 0
    failures = []
    if library_updated:
        try:
            get_steam_api_key()
        except SteamAPIConfigurationError as error:
            library_error = str(error)
        else:
            for game in games:
                try:
                    sync_game_achievements(user_id, game["id"])
                except (
                    SteamAPIConfigurationError,
                    SteamAPIError,
                    SteamLinkRequiredError,
                ) as error:
                    current_app.logger.warning(
                        "Combined Steam achievement sync failed for game %s: %s",
                        game["id"],
                        error,
                    )
                    failures.append((game["name"], str(error)))
                else:
                    succeeded += 1

    if library_error:
        flash(
            f"Biblioteca Steam: {library_error}",
            "error",
        )
    elif library_updated:
        flash(
            f"Biblioteca Steam sincronizada: {imported_count} jogo(s).",
            "success",
        )

    if failures:
        failure_details = "; ".join(
            f"{name}: {error}" for name, error in failures[:3]
        )
        remaining = len(failures) - 3
        if remaining > 0:
            failure_details += f"; mais {remaining} falha(s)"
        flash(
            f"Conquistas: sincronização parcial, {succeeded} de "
            f"{len(games)} jogo(s). {failure_details}",
            "error",
        )
    elif library_updated and games:
        flash(
            f"Conquistas: todas as {succeeded} sincronizadas.",
            "success",
        )
    elif library_updated:
        flash("Conquistas: não há jogos Steam para sincronizar.", "info")

    return redirect(url_for("library.list_games"))


@library.route("/new", methods=("GET", "POST"))
@login_required
def create_game():
    game = {
        "name": "",
        "platform": "",
        "developer": "",
        "release_year": "",
    }

    if request.method == "POST":
        game, errors = _parse_game_form(request.form)
        if errors:
            return render_template(
                "games/form.html",
                game=game,
                errors=errors,
                editing=False,
            ), 400

        with get_db() as db:
            db.execute(
                """
                INSERT INTO games (
                    user_id, source, name, platform, developer, release_year
                ) VALUES (?, 'manual', ?, ?, ?, ?)
                """,
                (
                    g.user["id"],
                    game["name"],
                    game["platform"],
                    game["developer"],
                    game["release_year"],
                ),
            )
        flash("Jogo cadastrado.", "success")
        return redirect(url_for("library.list_games"))

    return render_template(
        "games/form.html",
        game=game,
        errors=[],
        editing=False,
    )


@library.route("/<int:game_id>/achievements/new", methods=("GET", "POST"))
@login_required
def create_achievement(game_id):
    game = _get_game(game_id)
    _require_manual_game(game)
    achievement = {
        "name": "",
        "description": "",
        "rarity": "",
        "unlocked": False,
    }

    if request.method == "POST":
        achievement, errors = _parse_achievement_form(request.form)
        if errors:
            return render_template(
                "achievements/form.html",
                game=game,
                achievement=achievement,
                errors=errors,
                editing=False,
            ), 400

        with get_db() as db:
            db.execute(
                """
                INSERT INTO achievements (
                    user_id, game_id, source, name, description, rarity,
                    unlocked, unlocked_at
                )
                VALUES (
                    ?, ?, 'manual', ?, ?, ?, ?,
                    CASE WHEN ? = 1 THEN CURRENT_TIMESTAMP ELSE NULL END
                )
                """,
                (
                    g.user["id"],
                    game_id,
                    achievement["name"],
                    achievement["description"],
                    achievement["rarity"],
                    int(achievement["unlocked"]),
                    int(achievement["unlocked"]),
                ),
            )
            refresh_achievement_ranking_records(db)
        flash("Conquista cadastrada.", "success")
        return redirect(url_for("library.game_detail", game_id=game_id))

    return render_template(
        "achievements/form.html",
        game=game,
        achievement=achievement,
        errors=[],
        editing=False,
    )


@library.route(
    "/<int:game_id>/achievements/<int:achievement_id>/edit",
    methods=("GET", "POST"),
)
@login_required
def edit_achievement(game_id, achievement_id):
    game = _get_game(game_id)
    _require_manual_game(game)
    achievement = _get_manual_achievement(game_id, achievement_id)

    if request.method == "POST":
        updated_achievement, errors = _parse_achievement_form(request.form)
        if errors:
            return render_template(
                "achievements/form.html",
                game=game,
                achievement=updated_achievement,
                errors=errors,
                editing=True,
            ), 400

        with get_db() as db:
            db.execute(
                """
                UPDATE achievements
                SET name = ?, description = ?, rarity = ?, unlocked = ?,
                    unlocked_at = CASE
                        WHEN ? = 1 THEN COALESCE(unlocked_at, CURRENT_TIMESTAMP)
                        ELSE NULL
                    END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND game_id = ? AND user_id = ? AND source = 'manual'
                """,
                (
                    updated_achievement["name"],
                    updated_achievement["description"],
                    updated_achievement["rarity"],
                    int(updated_achievement["unlocked"]),
                    int(updated_achievement["unlocked"]),
                    achievement_id,
                    game_id,
                    g.user["id"],
                ),
            )
            refresh_achievement_ranking_records(db)
        flash("Conquista atualizada.", "success")
        return redirect(url_for("library.game_detail", game_id=game_id))

    return render_template(
        "achievements/form.html",
        game=game,
        achievement=achievement,
        errors=[],
        editing=True,
    )


@library.route(
    "/<int:game_id>/achievements/<int:achievement_id>/delete",
    methods=("GET", "POST"),
)
@login_required
def delete_achievement(game_id, achievement_id):
    game = _get_game(game_id)
    _require_manual_game(game)
    achievement = _get_manual_achievement(game_id, achievement_id)

    if request.method == "POST":
        if request.form.get("confirm") != "delete":
            abort(400)
        with get_db() as db:
            db.execute(
                """
                DELETE FROM achievements
                WHERE id = ? AND game_id = ? AND user_id = ? AND source = 'manual'
                """,
                (achievement_id, game_id, g.user["id"]),
            )
            refresh_achievement_ranking_records(db)
        flash("Conquista removida.", "success")
        return redirect(url_for("library.game_detail", game_id=game_id))

    return render_template(
        "achievements/delete.html",
        game=game,
        achievement=achievement,
    )


@library.route("/<int:game_id>/edit", methods=("GET", "POST"))
@login_required
def edit_game(game_id):
    game = _get_game(game_id)
    _require_manual_game(game)

    if request.method == "POST":
        updated_game, errors = _parse_game_form(request.form)
        if errors:
            return render_template(
                "games/form.html",
                game=updated_game,
                errors=errors,
                editing=True,
            ), 400

        with get_db() as db:
            db.execute(
                """
                UPDATE games
                SET name = ?, platform = ?, developer = ?, release_year = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND user_id = ? AND source = 'manual'
                """,
                (
                    updated_game["name"],
                    updated_game["platform"],
                    updated_game["developer"],
                    updated_game["release_year"],
                    game_id,
                    g.user["id"],
                ),
            )
        flash("Jogo atualizado.", "success")
        return redirect(url_for("library.list_games"))

    return render_template(
        "games/form.html",
        game=game,
        errors=[],
        editing=True,
    )


@library.route("/<int:game_id>/delete", methods=("GET", "POST"))
@login_required
def delete_game(game_id):
    game = _get_game(game_id)
    if game["source"] == "steam":
        linked = get_db().execute(
            "SELECT 1 FROM steam_links WHERE user_id = ?",
            (g.user["id"],),
        ).fetchone()
        if linked is not None:
            abort(404)

    if request.method == "POST":
        if request.form.get("confirm") != "delete":
            abort(400)
        with get_db() as db:
            db.execute(
                "DELETE FROM games WHERE id = ? AND user_id = ?",
                (game_id, g.user["id"]),
            )
            refresh_achievement_ranking_records(db)
        flash("Jogo removido da biblioteca.", "success")
        return redirect(url_for("library.list_games"))

    achievement_count = get_db().execute(
        "SELECT COUNT(*) FROM achievements WHERE game_id = ? AND user_id = ?",
        (game_id, g.user["id"]),
    ).fetchone()[0]
    return render_template(
        "games/delete.html",
        game=game,
        achievement_count=achievement_count,
    )
