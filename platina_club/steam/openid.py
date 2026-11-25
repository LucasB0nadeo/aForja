import ipaddress
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


OPENID_ENDPOINT = "https://steamcommunity.com/openid/login"
OPENID_NAMESPACE = "http://specs.openid.net/auth/2.0"
STEAM_ID_PREFIX = "https://steamcommunity.com/openid/id/"


class SteamOpenIDError(RuntimeError):
    pass


def build_return_to(return_url, state):
    parsed = urlsplit(return_url)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise SteamOpenIDError("STEAM_OPENID_RETURN_URL is not a valid callback URL.")

    if parsed.scheme != "https":
        try:
            is_loopback = ipaddress.ip_address(parsed.hostname).is_loopback
        except ValueError:
            is_loopback = parsed.hostname.lower() == "localhost"
        if not is_loopback:
            raise SteamOpenIDError(
                "Steam OpenID callback URLs must use HTTPS outside localhost."
            )

    return f"{return_url}?{urlencode({'state': state})}"


def build_realm(return_url):
    parsed = urlsplit(return_url)
    if not parsed.scheme or not parsed.netloc:
        raise SteamOpenIDError("STEAM_OPENID_RETURN_URL is not a valid callback URL.")
    return urlunsplit((parsed.scheme, parsed.netloc, "/", "", ""))


def verify_steam_openid_response(params, return_to, post_verification=None):
    if params.get("openid.ns") != OPENID_NAMESPACE:
        raise SteamOpenIDError("Steam OpenID response has an invalid namespace.")
    if params.get("openid.mode") != "id_res":
        raise SteamOpenIDError("Steam OpenID response was not a successful identity result.")
    if params.get("openid.op_endpoint") != OPENID_ENDPOINT:
        raise SteamOpenIDError("Steam OpenID response came from an unexpected endpoint.")
    if params.get("openid.return_to") != return_to:
        raise SteamOpenIDError("Steam OpenID response does not match the login request.")

    signed_fields = set(params.get("openid.signed", "").split(","))
    if not {
        "op_endpoint",
        "claimed_id",
        "identity",
        "return_to",
        "response_nonce",
    }.issubset(signed_fields):
        raise SteamOpenIDError("Steam OpenID response is missing signed identity fields.")

    claimed_id = params.get("openid.claimed_id", "")
    identity = params.get("openid.identity", "")
    if claimed_id != identity or not claimed_id.startswith(STEAM_ID_PREFIX):
        raise SteamOpenIDError("Steam OpenID response contains an invalid SteamID.")

    steam_id = claimed_id[len(STEAM_ID_PREFIX) :]
    if re.fullmatch(r"[0-9]{17}", steam_id) is None:
        raise SteamOpenIDError("Steam OpenID response contains an invalid SteamID.")

    verification_params = {
        key: value for key, value in params.items() if key.startswith("openid.")
    }
    verification_params["openid.mode"] = "check_authentication"
    verify = post_verification or _post_verification
    if not _is_valid_verification_response(verify(verification_params)):
        raise SteamOpenIDError("Steam could not verify the OpenID response.")

    return steam_id


def _post_verification(params):
    request = Request(
        OPENID_ENDPOINT,
        data=urlencode(params).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            return response.read(16384).decode("utf-8")
    except (HTTPError, URLError, TimeoutError) as error:
        raise SteamOpenIDError("Could not verify the Steam OpenID response.") from error


def _is_valid_verification_response(response_text):
    return any(
        line.strip() == "is_valid:true"
        for line in response_text.splitlines()
    )
