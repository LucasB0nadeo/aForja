import secrets
from urllib.parse import urlencode

from flask import (
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    request,
    session,
    url_for,
)

from ..auth import login_required
from ..db import get_db
from .api import SteamAPIError, search_store_games
from .config import SteamAPIConfigurationError
from . import steam
from .library import SteamLinkRequiredError, sync_owned_games
from .openid import (
    OPENID_ENDPOINT,
    OPENID_NAMESPACE,
    SteamOpenIDError,
    build_realm,
    build_return_to,
    verify_steam_openid_response,
)
from .profile import sync_steam_avatar


def _configured_return_url():
    return current_app.config["STEAM_OPENID_RETURN_URL"]


def _single_query_values():
    values = {}
    for key in request.args:
        items = request.args.getlist(key)
        if len(items) != 1:
            raise SteamOpenIDError("Steam OpenID response contains duplicate fields.")
        values[key] = items[0]
    return values


@steam.get("/search")
@login_required
def search_games():
    query = request.args.get("q", "").strip()
    if len(query) < 2 or len(query) > 100:
        return jsonify(error="A busca deve conter entre 2 e 100 caracteres."), 400

    try:
        results = search_store_games(query)
    except SteamAPIError as error:
        current_app.logger.warning("Steam game search failed: %s", error)
        return jsonify(error=str(error)), 502

    return jsonify(results=results)


@steam.get("/link")
@login_required
def link():
    existing_link = get_db().execute(
        "SELECT steam_id FROM steam_links WHERE user_id = ?",
        (g.user["id"],),
    ).fetchone()
    if existing_link is not None:
        flash("Desvincule a conta Steam atual antes de vincular outra.", "error")
        return redirect(url_for("auth.dashboard"))

    state = secrets.token_urlsafe(32)
    session["_steam_openid_state"] = state
    return_to = build_return_to(_configured_return_url(), state)
    realm = build_realm(_configured_return_url())
    query = urlencode(
        {
            "openid.ns": OPENID_NAMESPACE,
            "openid.mode": "checkid_setup",
            "openid.return_to": return_to,
            "openid.realm": realm,
            "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
            "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
        }
    )
    return redirect(f"{OPENID_ENDPOINT}?{query}")


@steam.get("/callback")
@login_required
def callback():
    expected_state = session.pop("_steam_openid_state", None)
    try:
        params = _single_query_values()
        state = params.get("state", "")
        if (
            not expected_state
            or not state
            or not secrets.compare_digest(expected_state, state)
        ):
            raise SteamOpenIDError("Steam OpenID login state did not match.")

        return_to = build_return_to(_configured_return_url(), state)
        steam_id = verify_steam_openid_response(params, return_to)
    except SteamOpenIDError as error:
        current_app.logger.warning("Steam account link verification failed: %s", error)
        flash("Não foi possível confirmar a identidade Steam. Tente novamente.", "error")
        return redirect(url_for("auth.dashboard"))

    db = get_db()
    existing_user_link = db.execute(
        "SELECT steam_id FROM steam_links WHERE user_id = ?",
        (g.user["id"],),
    ).fetchone()
    if existing_user_link is not None:
        if existing_user_link["steam_id"] == steam_id:
            flash("Esta conta Steam já está vinculada.", "success")
        else:
            flash("Desvincule a conta Steam atual antes de vincular outra.", "error")
        return redirect(url_for("auth.dashboard"))

    with db:
        cursor = db.execute(
            """
            INSERT INTO steam_links (user_id, steam_id)
            VALUES (?, ?)
            ON CONFLICT DO NOTHING
            """,
            (g.user["id"], steam_id),
        )
        if cursor.rowcount == 0:
            flash("Não foi possível vincular esta conta Steam.", "error")
            return redirect(url_for("auth.dashboard"))

    flash("Conta Steam vinculada.", "success")
    try:
        sync_steam_avatar(g.user["id"], steam_id)
    except (SteamAPIConfigurationError, SteamAPIError) as error:
        current_app.logger.warning("Steam profile sync failed: %s", error)
        flash("A foto Steam não pôde ser carregada neste momento.", "error")

    try:
        imported_count = sync_owned_games(g.user["id"])
    except (SteamAPIConfigurationError, SteamAPIError, SteamLinkRequiredError) as error:
        current_app.logger.warning("Initial Steam library sync failed: %s", error)
        flash(
            f"O vínculo foi concluído, mas a biblioteca não pôde ser sincronizada: {error}",
            "error",
        )
    else:
        flash(f"Biblioteca Steam sincronizada: {imported_count} jogo(s).", "success")
    return redirect(url_for("auth.dashboard"))


@steam.post("/unlink")
@login_required
def unlink():
    with get_db() as db:
        db.execute(
            "DELETE FROM steam_links WHERE user_id = ?",
            (g.user["id"],),
        )

    session.pop("_steam_openid_state", None)
    flash(
        "Conta Steam desvinculada. Jogos, conquistas e recompensas locais foram preservados.",
        "success",
    )
    return redirect(url_for("auth.dashboard"))


@steam.post("/library/sync")
@login_required
def sync_library():
    try:
        imported_count = sync_owned_games(g.user["id"])
    except (SteamAPIConfigurationError, SteamAPIError, SteamLinkRequiredError) as error:
        current_app.logger.warning("Steam library sync failed: %s", error)
        flash(str(error), "error")
    else:
        flash(f"Biblioteca Steam sincronizada: {imported_count} jogo(s).", "success")
    return redirect(url_for("library.list_games"))
