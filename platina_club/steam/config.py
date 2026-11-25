from flask import current_app


class SteamAPIConfigurationError(RuntimeError):
    pass


def get_steam_api_key():
    api_key = current_app.config.get("STEAM_API_KEY")
    if not api_key or not api_key.strip():
        raise SteamAPIConfigurationError(
            "Configure STEAM_API_KEY in the local environment to use the Steam Web API."
        )
    return api_key.strip()
