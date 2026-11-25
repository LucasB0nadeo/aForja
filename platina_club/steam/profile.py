from .api import fetch_steam_profile
from .library import SteamLinkRequiredError
from ..db import get_db


def sync_steam_avatar(user_id, steam_id, fetcher=None):
    fetch = fetcher or fetch_steam_profile
    profile = fetch(steam_id)
    with get_db() as db:
        cursor = db.execute(
            """
            UPDATE steam_links
            SET avatar_url = ?
            WHERE user_id = ? AND steam_id = ?
            """,
            (profile["avatar_url"], user_id, steam_id),
        )
        if cursor.rowcount == 0:
            raise SteamLinkRequiredError("Vincule uma conta Steam antes de sincronizar.")
    return profile
