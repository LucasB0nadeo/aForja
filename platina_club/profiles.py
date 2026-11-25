import re
import uuid
import warnings
from io import BytesIO
from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from PIL import Image, ImageOps, UnidentifiedImageError

from .auth import login_required
from .db import get_db
from .rankings import (
    get_achievement_ranking_positions,
    get_ember_ranking_positions,
    refresh_achievement_ranking_records,
    refresh_ember_ranking_records,
)
from .steam.api import SteamAPIError
from .steam.config import SteamAPIConfigurationError
from .steam.library import SteamLinkRequiredError
from .steam.profile import sync_steam_avatar


profiles = Blueprint("profiles", __name__)
MAX_AVATAR_BYTES = 2 * 1024 * 1024
MAX_AVATAR_PIXELS = 16_000_000
ALLOWED_AVATAR_FORMATS = {"JPEG", "PNG", "WEBP"}
AVATAR_FILENAME_PATTERN = re.compile(r"[a-f0-9]{32}\.jpg")


def _validate_avatar(upload):
    payload = upload.stream.read(MAX_AVATAR_BYTES + 1)
    if len(payload) > MAX_AVATAR_BYTES:
        return None, "A imagem de perfil deve ter no máximo 2 MB."

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(payload)) as image:
                if image.format not in ALLOWED_AVATAR_FORMATS:
                    return None, "Use uma imagem PNG, JPEG ou WebP."
                if image.width * image.height > MAX_AVATAR_PIXELS:
                    return None, "A imagem de perfil excede o limite de resolução."
                image.verify()

            with Image.open(BytesIO(payload)) as image:
                image.load()
                image = ImageOps.exif_transpose(image)
                image.thumbnail((512, 512))
                output = BytesIO()
                image.convert("RGB").save(
                    output,
                    format="JPEG",
                    optimize=True,
                    quality=85,
                )
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        UnidentifiedImageError,
        ValueError,
    ):
        return None, "O arquivo enviado não é uma imagem válida."

    return output.getvalue(), None


def _avatar_url(profile):
    if profile["custom_avatar_path"]:
        return url_for(
            "profiles.avatar_file",
            filename=profile["custom_avatar_path"],
        )
    if profile.get("avatar_url"):
        return profile["avatar_url"]
    return url_for("static", filename="avatar-default.svg")


@profiles.app_context_processor
def inject_current_user_avatar():
    default_avatar_url = url_for("static", filename="avatar-default.svg")
    user_id = session.get("user_id")
    if user_id is None:
        return {"current_user_avatar_url": default_avatar_url}

    profile = get_db().execute(
        """
        SELECT p.custom_avatar_path, s.avatar_url
        FROM profiles AS p
        LEFT JOIN steam_links AS s ON s.user_id = p.user_id
        WHERE p.user_id = ?
        """,
        (user_id,),
    ).fetchone()
    if profile is None:
        return {"current_user_avatar_url": default_avatar_url}
    return {"current_user_avatar_url": _avatar_url(dict(profile))}


def _get_profile(user_id):
    profile = get_db().execute(
        """
        SELECT p.user_id, p.display_name, p.bio, p.custom_avatar_path,
               p.privacy, p.show_ranking_position, s.avatar_url
        FROM profiles AS p
        LEFT JOIN steam_links AS s ON s.user_id = p.user_id
        WHERE p.user_id = ?
        """,
        (user_id,),
    ).fetchone()
    if profile is None:
        abort(404)
    result = dict(profile)
    result["avatar_display_url"] = _avatar_url(result)
    return result


def _friendship_pair(first_user_id, second_user_id):
    return tuple(sorted((first_user_id, second_user_id)))


def _friendship(first_user_id, second_user_id):
    low_id, high_id = _friendship_pair(first_user_id, second_user_id)
    return get_db().execute(
        """
        SELECT requested_by_id, status
        FROM friendships
        WHERE user_low_id = ? AND user_high_id = ?
        """,
        (low_id, high_id),
    ).fetchone()


def _friendship_status(viewer_id, profile_id):
    friendship = _friendship(viewer_id, profile_id)
    if friendship is None:
        return "none"
    if friendship["status"] == "accepted":
        return "friends"
    if friendship["requested_by_id"] == viewer_id:
        return "pending_sent"
    return "pending_received"


def _can_view_profile(profile, viewer_id):
    if profile["user_id"] == viewer_id or profile["privacy"] == "all":
        return True
    if profile["privacy"] == "friends":
        return _friendship_status(viewer_id, profile["user_id"]) == "friends"
    return False


def _incoming_friend_requests(user_id):
    return get_db().execute(
        """
        SELECT p.user_id, p.display_name
        FROM friendships AS f
        JOIN profiles AS p
          ON p.user_id = CASE
              WHEN f.user_low_id = ? THEN f.user_high_id
              ELSE f.user_low_id
          END
        WHERE (f.user_low_id = ? OR f.user_high_id = ?)
          AND f.status = 'pending'
          AND f.requested_by_id != ?
        ORDER BY f.created_at, p.display_name
        """,
        (user_id, user_id, user_id, user_id),
    ).fetchall()


def _accepted_friends(user_id):
    return get_db().execute(
        """
        SELECT p.user_id, p.display_name
        FROM friendships AS f
        JOIN profiles AS p
          ON p.user_id = CASE
              WHEN f.user_low_id = ? THEN f.user_high_id
              ELSE f.user_low_id
          END
        WHERE (f.user_low_id = ? OR f.user_high_id = ?)
          AND f.status = 'accepted'
        ORDER BY p.display_name
        """,
        (user_id, user_id, user_id),
    ).fetchall()


def _render_edit(profile, errors, status=200, avatar_error=None):
    return (
        render_template(
            "profiles/edit.html",
            profile=profile,
            errors=errors,
            avatar_error=avatar_error,
        ),
        status,
    )


@profiles.route("/profile/edit", methods=("GET", "POST"))
@login_required
def edit_profile():
    profile = _get_profile(g.user["id"])
    avatar_error = None
    if request.method == "POST" and request.form.get("action") == "sync_steam_avatar":
        steam_link = get_db().execute(
            "SELECT steam_id FROM steam_links WHERE user_id = ?",
            (g.user["id"],),
        ).fetchone()
        if steam_link is None:
            flash("Vincule uma conta Steam antes de sincronizar a foto.", "error")
            return redirect(url_for("profiles.edit_profile"))
        try:
            sync_steam_avatar(g.user["id"], steam_link["steam_id"])
            with get_db() as db:
                db.execute(
                    """
                    UPDATE profiles
                    SET custom_avatar_path = NULL, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                    """,
                    (g.user["id"],),
                )
            flash("Foto Steam sincronizada.", "success")
        except (
            SteamAPIConfigurationError,
            SteamAPIError,
            SteamLinkRequiredError,
        ) as error:
            current_app.logger.warning(
                "Steam profile sync failed for user %s: %s",
                g.user["id"],
                error,
            )
            flash("A foto Steam não pôde ser sincronizada neste momento.", "error")
        return redirect(url_for("profiles.edit_profile"))

    if (
        request.method == "GET"
        and not profile["custom_avatar_path"]
        and not profile["avatar_url"]
    ):
        steam_link = get_db().execute(
            "SELECT steam_id FROM steam_links WHERE user_id = ?",
            (g.user["id"],),
        ).fetchone()
        if steam_link is not None:
            try:
                sync_steam_avatar(g.user["id"], steam_link["steam_id"])
            except (
                SteamAPIConfigurationError,
                SteamAPIError,
                SteamLinkRequiredError,
            ) as error:
                current_app.logger.warning(
                    "Steam profile sync failed for user %s: %s",
                    g.user["id"],
                    error,
                )
                avatar_error = "A foto Steam não pôde ser carregada neste momento."
            profile = _get_profile(g.user["id"])

    if request.method == "POST":
        display_name = request.form.get("display_name", "").strip()
        bio = request.form.get("bio", "").strip()
        errors = []
        if not display_name:
            errors.append("Informe um nome de exibição.")
        if len(display_name) > 40:
            errors.append("O nome de exibição deve ter no máximo 40 caracteres.")
        if len(bio) > 240:
            errors.append("A bio deve ter no máximo 240 caracteres.")
        privacy = request.form.get("privacy", profile["privacy"])
        if privacy not in {"all", "friends", "nobody"}:
            errors.append("Selecione uma opção de privacidade válida.")
        ranking_visibility_values = request.form.getlist(
            "show_ranking_position"
        )
        if any(value not in {"0", "1"} for value in ranking_visibility_values):
            errors.append("A opção de visibilidade do ranking é inválida.")
        show_ranking_position = (
            "1" in ranking_visibility_values
            if ranking_visibility_values
            else profile["show_ranking_position"]
        )

        upload = request.files.get("avatar")
        has_upload = upload is not None and bool(upload.filename)
        remove_avatar = request.form.get("remove_avatar") == "1"
        if has_upload and remove_avatar:
            errors.append("Envie uma imagem ou escolha a foto Steam, não ambos.")

        avatar_bytes = None
        if has_upload and not errors:
            avatar_bytes, avatar_error = _validate_avatar(upload)
            if avatar_error:
                errors.append(avatar_error)

        profile.update(
            {
                "display_name": display_name,
                "bio": bio,
                "privacy": privacy,
                "show_ranking_position": show_ranking_position,
                "avatar_display_url": _avatar_url(profile),
            }
        )
        if errors:
            return _render_edit(profile, errors, status=400)

        old_avatar = profile["custom_avatar_path"]
        new_avatar = old_avatar
        new_avatar_path = None
        if avatar_bytes is not None:
            new_avatar = f"{uuid.uuid4().hex}.jpg"
            avatar_folder = Path(current_app.config["PROFILE_AVATAR_FOLDER"])
            avatar_folder.mkdir(parents=True, exist_ok=True)
            new_avatar_path = avatar_folder / new_avatar
            new_avatar_path.write_bytes(avatar_bytes)
        elif remove_avatar:
            new_avatar = None

        with get_db() as db:
            db.execute(
                """
                UPDATE profiles
                SET display_name = ?, bio = ?, custom_avatar_path = ?,
                    privacy = ?, show_ranking_position = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                """,
                (
                    display_name,
                    bio,
                    new_avatar,
                    privacy,
                    int(show_ranking_position),
                    g.user["id"],
                ),
            )
            refresh_achievement_ranking_records(db)
            refresh_ember_ranking_records(db)

        if old_avatar and old_avatar != new_avatar:
            _delete_avatar_file(old_avatar)
        flash("Perfil atualizado.", "success")
        return redirect(url_for("profiles.edit_profile"))

    return _render_edit(profile, [], avatar_error=avatar_error)


@profiles.get("/profiles/<int:user_id>")
@login_required
def public_profile(user_id):
    profile = get_db().execute(
        """
        SELECT p.user_id, p.display_name, p.bio, p.custom_avatar_path,
               p.privacy, p.show_ranking_position, s.avatar_url
        FROM profiles AS p
        LEFT JOIN steam_links AS s ON s.user_id = p.user_id
        WHERE p.user_id = ?
        """,
        (user_id,),
    ).fetchone()
    if profile is None:
        abort(404)
    profile = dict(profile)
    friendship_status = (
        "self"
        if profile["user_id"] == g.user["id"]
        else _friendship_status(g.user["id"], profile["user_id"])
    )
    if not _can_view_profile(profile, g.user["id"]):
        return render_template(
            "profiles/private.html",
            profile=profile,
            friendship_status=friendship_status,
        )

    profile["avatar_display_url"] = _avatar_url(profile)
    ranking_positions = (
        get_ember_ranking_positions(user_id)
        if profile["privacy"] == "all" and profile["show_ranking_position"]
        else None
    )
    achievement_ranking_positions = (
        get_achievement_ranking_positions(user_id)
        if profile["privacy"] == "all" and profile["show_ranking_position"]
        else None
    )
    forja = get_db().execute(
        """
        SELECT f.slot, b.game_name_snapshot, b.steam_app_id
        FROM forja_slots AS f
        JOIN badge_awards AS b
          ON b.id = f.badge_award_id
         AND b.user_id = f.user_id
         AND b.badge_type = 'ember'
        WHERE f.user_id = ?
        ORDER BY f.slot
        """,
        (user_id,),
    ).fetchall()
    stats = {
        "games": get_db().execute(
            "SELECT COUNT(*) FROM games WHERE user_id = ?",
            (user_id,),
        ).fetchone()[0],
        "achievements": get_db().execute(
            """
            SELECT COUNT(*) FROM achievements
            WHERE user_id = ? AND unlocked = 1
            """,
            (user_id,),
        ).fetchone()[0],
        "embers": get_db().execute(
            """
            SELECT COUNT(*) FROM badge_awards
            WHERE user_id = ? AND badge_type = 'ember'
            """,
            (user_id,),
        ).fetchone()[0],
    }
    return render_template(
        "profiles/public.html",
        profile=profile,
        forja=forja,
        stats=stats,
        ranking_positions=ranking_positions,
        achievement_ranking_positions=achievement_ranking_positions,
        friendship_status=friendship_status,
        incoming_friend_requests=(
            _incoming_friend_requests(g.user["id"])
            if profile["user_id"] == g.user["id"]
            else []
        ),
        friends=(
            _accepted_friends(g.user["id"])
            if profile["user_id"] == g.user["id"]
            else []
        ),
    )


@profiles.get("/friends")
@login_required
def friends_page():
    search_query = request.args.get("q", "").strip()
    search_results = []
    if search_query:
        escaped_query = (
            search_query.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        matching_profiles = get_db().execute(
            """
            SELECT user_id, display_name
            FROM profiles
            WHERE user_id != ?
              AND privacy != 'nobody'
              AND display_name LIKE ? ESCAPE '\\'
            ORDER BY display_name
            LIMIT 20
            """,
            (g.user["id"], f"%{escaped_query}%"),
        ).fetchall()
        search_results = [
            {
                **dict(profile),
                "friendship_status": _friendship_status(
                    g.user["id"], profile["user_id"]
                ),
            }
            for profile in matching_profiles
        ]

    return render_template(
        "profiles/friends.html",
        friends=_accepted_friends(g.user["id"]),
        incoming_friend_requests=_incoming_friend_requests(g.user["id"]),
        search_query=search_query,
        search_results=search_results,
    )


@profiles.post("/profiles/<int:user_id>/friendship")
@login_required
def manage_friendship(user_id):
    target_profile = get_db().execute(
        "SELECT user_id, privacy FROM profiles WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if target_profile is None:
        abort(404)
    if user_id == g.user["id"]:
        abort(400)

    action = request.form.get("action")
    low_id, high_id = _friendship_pair(g.user["id"], user_id)
    friendship = _friendship(g.user["id"], user_id)
    message = None
    category = "error"

    if action == "request":
        if target_profile["privacy"] == "nobody":
            message = "Este perfil não aceita pedidos de amizade."
        elif friendship is not None:
            message = "Já existe uma relação ou pedido de amizade com este jogador."
            category = "info"
        else:
            with get_db() as db:
                cursor = db.execute(
                    """
                    INSERT INTO friendships (
                        user_low_id, user_high_id, requested_by_id
                    ) VALUES (?, ?, ?)
                    ON CONFLICT (user_low_id, user_high_id) DO NOTHING
                    """,
                    (low_id, high_id, g.user["id"]),
                )
            if cursor.rowcount:
                message = "Pedido de amizade enviado."
                category = "success"
            else:
                message = "Já existe uma relação ou pedido de amizade com este jogador."
                category = "info"
    elif action in {"accept", "decline"}:
        if (
            friendship is not None
            and friendship["status"] == "pending"
            and friendship["requested_by_id"] != g.user["id"]
        ):
            if action == "accept":
                with get_db() as db:
                    db.execute(
                        """
                        UPDATE friendships
                        SET status = 'accepted', updated_at = CURRENT_TIMESTAMP
                        WHERE user_low_id = ? AND user_high_id = ?
                        """,
                        (low_id, high_id),
                    )
                message = "Pedido de amizade aceito."
                category = "success"
            else:
                with get_db() as db:
                    db.execute(
                        """
                        DELETE FROM friendships
                        WHERE user_low_id = ? AND user_high_id = ?
                        """,
                        (low_id, high_id),
                    )
                message = "Pedido de amizade recusado."
                category = "success"
        else:
            message = "Este pedido de amizade não está mais disponível."
    elif action == "cancel":
        if (
            friendship is not None
            and friendship["status"] == "pending"
            and friendship["requested_by_id"] == g.user["id"]
        ):
            with get_db() as db:
                db.execute(
                    """
                    DELETE FROM friendships
                    WHERE user_low_id = ? AND user_high_id = ?
                    """,
                    (low_id, high_id),
                )
            message = "Pedido de amizade cancelado."
            category = "success"
        else:
            message = "Este pedido de amizade não está mais disponível."
    elif action == "remove":
        if friendship is not None and friendship["status"] == "accepted":
            with get_db() as db:
                db.execute(
                    """
                    DELETE FROM friendships
                    WHERE user_low_id = ? AND user_high_id = ?
                    """,
                    (low_id, high_id),
                )
            message = "Amizade removida."
            category = "success"
        else:
            message = "Vocês não são amigos."
    else:
        abort(400)

    flash(message, category)
    if request.form.get("next") == "friends":
        return redirect(url_for("profiles.friends_page"))
    return redirect(url_for("profiles.public_profile", user_id=user_id))


def _earned_embers(user_id):
    return get_db().execute(
        """
        SELECT id, steam_app_id, game_name_snapshot, awarded_at
        FROM badge_awards
        WHERE user_id = ? AND badge_type = 'ember'
        ORDER BY awarded_at, id
        """,
        (user_id,),
    ).fetchall()


@profiles.route("/profile/forja", methods=("GET", "POST"))
@login_required
def edit_forja():
    earned_embers = _earned_embers(g.user["id"])
    slot_rows = get_db().execute(
        """
        SELECT slot, badge_award_id
        FROM forja_slots
        WHERE user_id = ?
        ORDER BY slot
        """,
        (g.user["id"],),
    ).fetchall()
    ember_slots = {row["slot"]: row["badge_award_id"] for row in slot_rows}
    selected_ids = set(ember_slots.values())
    errors = []

    if request.method == "POST":
        raw_ids = request.form.getlist("badge_award_ids")
        try:
            award_ids = [int(value) for value in raw_ids]
            if any(award_id <= 0 for award_id in award_ids):
                raise ValueError
        except ValueError:
            award_ids = []
            errors.append("A seleção de Brasas é inválida.")
        award_ids = list(dict.fromkeys(award_ids))
        if len(award_ids) > 9:
            errors.append("A Forja pode exibir no máximo nove Brasas.")
        if not errors and award_ids:
            placeholders = ", ".join("?" for _ in award_ids)
            owned_count = get_db().execute(
                f"""
                SELECT COUNT(*) FROM badge_awards
                WHERE user_id = ? AND badge_type = 'ember'
                    AND id IN ({placeholders})
                """,
                (g.user["id"], *award_ids),
            ).fetchone()[0]
            if owned_count != len(award_ids):
                errors.append("Selecione somente Brasas conquistadas pela sua conta.")

        if errors:
            selected_ids = set(award_ids)
            ember_slots = {
                slot: award_id
                for slot, award_id in enumerate(award_ids, start=1)
            }
            return render_template(
                "profiles/forja.html",
                earned_embers=earned_embers,
                selected_ids=selected_ids,
                ember_slots=ember_slots,
                errors=errors,
            ), 400

        with get_db() as db:
            db.execute("DELETE FROM forja_slots WHERE user_id = ?", (g.user["id"],))
            db.executemany(
                """
                INSERT INTO forja_slots (user_id, slot, badge_award_id)
                VALUES (?, ?, ?)
                """,
                (
                    (g.user["id"], slot, award_id)
                    for slot, award_id in enumerate(award_ids, start=1)
                ),
            )
        flash("Forja atualizada.", "success")
        return redirect(url_for("profiles.public_profile", user_id=g.user["id"]))

    return render_template(
        "profiles/forja.html",
        earned_embers=earned_embers,
        selected_ids=selected_ids,
        ember_slots=ember_slots,
        errors=errors,
    )


@profiles.get("/profile/avatar/<filename>")
@login_required
def avatar_file(filename):
    if AVATAR_FILENAME_PATTERN.fullmatch(filename) is None:
        abort(404)
    profile = get_db().execute(
        "SELECT user_id, privacy FROM profiles WHERE custom_avatar_path = ?",
        (filename,),
    ).fetchone()
    if profile is None or not _can_view_profile(profile, g.user["id"]):
        abort(404)
    return send_from_directory(
        current_app.config["PROFILE_AVATAR_FOLDER"],
        filename,
        mimetype="image/jpeg",
        max_age=3600,
    )


def _delete_avatar_file(filename):
    if AVATAR_FILENAME_PATTERN.fullmatch(filename) is None:
        return
    path = Path(current_app.config["PROFILE_AVATAR_FOLDER"]) / filename
    if path.is_file():
        path.unlink()
