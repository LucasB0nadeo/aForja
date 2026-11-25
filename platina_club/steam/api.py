import json
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from .config import get_steam_api_key


OWNED_GAMES_ENDPOINT = (
    "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
)
GAME_SCHEMA_ENDPOINT = (
    "https://api.steampowered.com/ISteamUserStats/GetSchemaForGame/v2/"
)
PLAYER_ACHIEVEMENTS_ENDPOINT = (
    "https://api.steampowered.com/ISteamUserStats/GetPlayerAchievements/v1/"
)
GLOBAL_ACHIEVEMENTS_ENDPOINT = (
    "https://api.steampowered.com/ISteamUserStats/"
    "GetGlobalAchievementPercentagesForApp/v2/"
)
STORE_APP_DETAILS_ENDPOINT = "https://store.steampowered.com/api/appdetails"
STORE_SEARCH_ENDPOINT = "https://store.steampowered.com/api/storesearch/"
PLAYER_SUMMARIES_ENDPOINT = (
    "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"
)
MAX_RESPONSE_BYTES = 16 * 1024 * 1024


class SteamAPIError(RuntimeError):
    pass


def fetch_game_achievements(steam_id, app_id):
    api_key = get_steam_api_key()
    schema_payload = _request_json(
        GAME_SCHEMA_ENDPOINT,
        {"key": api_key, "appid": app_id},
    )
    definitions = parse_achievement_schema(schema_payload)
    if not definitions:
        return []

    player_payload = _request_json(
        PLAYER_ACHIEVEMENTS_ENDPOINT,
        {
            "key": api_key,
            "steamid": steam_id,
            "appid": app_id,
            "l": "english",
        },
    )
    try:
        global_payload = _request_json(
            GLOBAL_ACHIEVEMENTS_ENDPOINT,
            {"gameid": app_id, "format": "json"},
        )
    except SteamAPIError:
        global_payload = None
    return merge_player_achievements(
        definitions,
        player_payload,
        global_payload,
    )


def fetch_store_game(app_id):
    if type(app_id) is not int or app_id <= 0:
        raise SteamAPIError("Steam returned an invalid game AppID.")

    payload = _request_json(
        STORE_APP_DETAILS_ENDPOINT,
        {"appids": app_id, "l": "english"},
    )
    return parse_store_game(payload, app_id)


def search_store_games(query):
    query = query.strip() if isinstance(query, str) else ""
    if len(query) < 2 or len(query) > 100:
        raise SteamAPIError(
            "A busca deve conter entre 2 e 100 caracteres."
        )

    payload = _request_json(
        STORE_SEARCH_ENDPOINT,
        {"term": query, "l": "brazilian", "cc": "br"},
    )
    return parse_store_search(payload)


def fetch_steam_profile(steam_id):
    payload = _request_json(
        PLAYER_SUMMARIES_ENDPOINT,
        {
            "key": get_steam_api_key(),
            "steamids": steam_id,
        },
    )
    return parse_steam_profile(payload, steam_id)


def fetch_owned_games(steam_id):
    params = {
        "key": get_steam_api_key(),
        "steamid": steam_id,
        "include_appinfo": "1",
        "include_played_free_games": "1",
    }
    return parse_owned_games(_request_json(OWNED_GAMES_ENDPOINT, params))


def parse_steam_profile(payload, steam_id):
    response = payload.get("response")
    players = response.get("players") if isinstance(response, dict) else None
    if not isinstance(players, list):
        raise SteamAPIError("Steam returned an invalid player profile.")

    player = next(
        (
            item
            for item in players
            if isinstance(item, dict) and item.get("steamid") == steam_id
        ),
        None,
    )
    if player is None:
        raise SteamAPIError("Steam did not make this profile available.")

    avatar_url = player.get("avatarfull")
    persona_name = player.get("personaname", "")
    if not isinstance(persona_name, str) or (
        avatar_url is not None and not isinstance(avatar_url, str)
    ):
        raise SteamAPIError("Steam returned invalid player profile details.")

    if avatar_url:
        parsed_url = urlsplit(avatar_url)
        if parsed_url.scheme != "https" or not parsed_url.netloc:
            raise SteamAPIError("Steam returned an invalid profile image URL.")
    else:
        avatar_url = None

    return {"steam_id": steam_id, "persona_name": persona_name, "avatar_url": avatar_url}


def _request_json(endpoint, params):
    url = f"{endpoint}?{urlencode(params)}"
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=15) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except (HTTPError, URLError, TimeoutError) as error:
        raise SteamAPIError("Steam Web API is unavailable. Try again later.") from error

    if len(body) > MAX_RESPONSE_BYTES:
        raise SteamAPIError("Steam Web API returned an oversized response.")

    try:
        payload = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise SteamAPIError("Steam Web API returned invalid JSON.") from error

    if not isinstance(payload, dict):
        raise SteamAPIError("Steam Web API returned an invalid response.")
    return payload


def parse_store_game(payload, app_id):
    result = payload.get(str(app_id))
    if not isinstance(result, dict) or result.get("success") is not True:
        raise SteamAPIError("Steam does not recognize this game AppID.")

    game = result.get("data")
    if not isinstance(game, dict) or game.get("type") != "game":
        raise SteamAPIError("Steam does not recognize this game AppID.")

    name = game.get("name")
    developers = game.get("developers", [])
    release_info = game.get("release_date", {})
    platforms = game.get("platforms", {})
    icon_url = game.get("header_image")
    if (
        not isinstance(name, str)
        or not name.strip()
        or not isinstance(developers, list)
        or any(not isinstance(value, str) or not value.strip() for value in developers)
        or not isinstance(release_info, dict)
        or not isinstance(release_info.get("date", ""), str)
        or not isinstance(platforms, dict)
        or any(type(enabled) is not bool for enabled in platforms.values())
        or (icon_url is not None and not isinstance(icon_url, str))
    ):
        raise SteamAPIError("Steam returned invalid game details.")

    release_date = release_info.get("date", "").strip()
    return {
        "steam_app_id": app_id,
        "name": name.strip(),
        "developer": ", ".join(value.strip() for value in developers),
        "release_date": release_date.strip(),
        "platforms": ", ".join(
            name.title() for name, enabled in platforms.items() if enabled
        ),
        "icon_url": icon_url,
    }


def parse_store_search(payload):
    items = payload.get("items")
    if not isinstance(items, list):
        raise SteamAPIError("Steam returned an invalid game search response.")

    results = []
    app_ids = set()
    for item in items:
        if not isinstance(item, dict):
            raise SteamAPIError("Steam returned an invalid game search result.")
        if item.get("type") != "app":
            continue

        app_id = item.get("id")
        name = item.get("name")
        if (
            type(app_id) is not int
            or app_id <= 0
            or not isinstance(name, str)
            or not name.strip()
        ):
            raise SteamAPIError("Steam returned an invalid game search result.")
        if app_id in app_ids:
            continue

        app_ids.add(app_id)
        results.append({"steam_app_id": app_id, "name": name.strip()})
        if len(results) == 10:
            break

    return results


def parse_achievement_schema(payload):
    game = payload.get("game")
    if not isinstance(game, dict):
        raise SteamAPIError("Steam returned an invalid game achievement schema.")

    game_stats = game.get("availableGameStats")
    if game_stats is None:
        return []
    if not isinstance(game_stats, dict):
        raise SteamAPIError("Steam returned an invalid game achievement schema.")

    achievements = game_stats.get("achievements", [])
    if not isinstance(achievements, list):
        raise SteamAPIError("Steam returned an invalid game achievement schema.")

    definitions = []
    api_names = set()
    for achievement in achievements:
        if not isinstance(achievement, dict):
            raise SteamAPIError("Steam returned an invalid achievement definition.")

        api_name = achievement.get("name")
        display_name = achievement.get("displayName", "")
        description = achievement.get("description", "")
        icon_url = achievement.get("icon")
        icon_gray_url = achievement.get("icongray")
        if (
            not isinstance(api_name, str)
            or not api_name.strip()
            or api_name in api_names
            or not isinstance(display_name, str)
            or not isinstance(description, str)
            or (icon_url is not None and not isinstance(icon_url, str))
            or (icon_gray_url is not None and not isinstance(icon_gray_url, str))
        ):
            raise SteamAPIError("Steam returned an invalid achievement definition.")

        icon_url = icon_url.strip() if isinstance(icon_url, str) else None
        icon_gray_url = icon_gray_url.strip() if isinstance(icon_gray_url, str) else None
        if icon_url:
            if urlsplit(icon_url).scheme != "https" or not urlsplit(icon_url).netloc:
                raise SteamAPIError("Steam returned an invalid achievement icon URL.")
        else:
            icon_url = None
        if icon_gray_url:
            if urlsplit(icon_gray_url).scheme != "https" or not urlsplit(icon_gray_url).netloc:
                raise SteamAPIError("Steam returned an invalid achievement icon URL.")
        else:
            icon_gray_url = None

        api_names.add(api_name)
        definitions.append(
            {
                "steam_api_name": api_name,
                "name": display_name.strip() or api_name,
                "description": description,
                "icon_url": icon_url,
                "icon_gray_url": icon_gray_url,
            }
        )

    return definitions


def merge_player_achievements(definitions, payload, global_payload=None):
    player_stats = payload.get("playerstats")
    if not isinstance(player_stats, dict) or player_stats.get("success") is False:
        raise SteamAPIError("Steam did not make this game's achievement data available.")

    achievements = player_stats.get("achievements")
    if not isinstance(achievements, list):
        raise SteamAPIError("Steam returned an incomplete achievement response.")

    states = {}
    for achievement in achievements:
        if not isinstance(achievement, dict):
            raise SteamAPIError("Steam returned an invalid achievement state.")

        api_name = achievement.get("apiname")
        unlocked = achievement.get("achieved")
        unlock_time = achievement.get("unlocktime", 0)
        if (
            not isinstance(api_name, str)
            or not api_name
            or api_name in states
            or type(unlocked) is not int
            or unlocked not in (0, 1)
            or type(unlock_time) is not int
            or unlock_time < 0
        ):
            raise SteamAPIError("Steam returned an invalid achievement state.")

        states[api_name] = (unlocked, unlock_time)

    definition_names = {item["steam_api_name"] for item in definitions}
    if definition_names != states.keys():
        raise SteamAPIError("Steam returned an incomplete achievement response.")

    global_percentages = {}
    if global_payload is not None:
        achievement_percentages = (
            global_payload.get("achievementpercentages")
            if isinstance(global_payload, dict)
            else None
        )
        entries = (
            achievement_percentages.get("achievements")
            if isinstance(achievement_percentages, dict)
            else None
        )
        if isinstance(entries, list):
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                api_name = entry.get("name")
                percent = entry.get("percent")
                if not isinstance(api_name, str) or not api_name:
                    continue
                try:
                    parsed_percent = float(percent)
                except (TypeError, ValueError):
                    continue
                if (
                    parsed_percent < 0
                    or parsed_percent > 100
                    or api_name in global_percentages
                ):
                    continue
                global_percentages[api_name] = round(parsed_percent, 2)

    merged = []
    for definition in definitions:
        unlocked, unlock_time = states[definition["steam_api_name"]]
        try:
            unlocked_at = (
                datetime.fromtimestamp(unlock_time, timezone.utc).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                if unlocked and unlock_time
                else None
            )
        except (OverflowError, OSError, ValueError) as error:
            raise SteamAPIError("Steam returned an invalid unlock time.") from error

        merged.append(
            {
                **definition,
                "rarity": None,
                "global_percent": global_percentages.get(
                    definition["steam_api_name"]
                ),
                "unlocked": unlocked,
                "unlocked_at": unlocked_at,
            }
        )
    return merged


def parse_owned_games(payload):
    response = payload.get("response")
    if not isinstance(response, dict):
        raise SteamAPIError("Steam did not make this library available.")

    game_count = response.get("game_count")
    games = response.get("games")
    if type(game_count) is not int or game_count < 0:
        raise SteamAPIError("Steam returned an invalid library response.")
    if games is None and game_count == 0:
        games = []
    if not isinstance(games, list) or game_count != len(games):
        raise SteamAPIError("Steam returned an incomplete library response.")

    validated_games = []
    app_ids = set()
    for game in games:
        if not isinstance(game, dict):
            raise SteamAPIError("Steam returned an invalid game record.")

        app_id = game.get("appid")
        name = game.get("name")
        playtime = game.get("playtime_forever", 0)
        if (
            type(app_id) is not int
            or app_id <= 0
            or not isinstance(name, str)
            or not name.strip()
            or type(playtime) is not int
            or playtime < 0
            or app_id in app_ids
        ):
            raise SteamAPIError("Steam returned invalid or duplicate game data.")

        app_ids.add(app_id)
        validated_games.append(
            {
                "steam_app_id": app_id,
                "name": name.strip(),
                "playtime_minutes": playtime,
            }
        )

    return validated_games
