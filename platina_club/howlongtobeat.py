import logging
import math
from dataclasses import dataclass
from typing import Optional

from fake_useragent.errors import FakeUserAgentError
from howlongtobeatpy import HowLongToBeat


logger = logging.getLogger(__name__)


class HowLongToBeatUnavailable(Exception):
    pass


@dataclass(frozen=True)
class HowLongToBeatResult:
    game_name: str
    game_id: Optional[int]
    similarity: float
    main_story: Optional[float]
    main_extra: Optional[float]
    completionist: Optional[float]
    all_styles: Optional[float]
    coop_time: Optional[float]
    mp_time: Optional[float]

    @property
    def game_url(self):
        if self.game_id is None:
            return None
        return f"https://howlongtobeat.com/game/{self.game_id}"


def _number_or_none(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        value = float(value)
    except OverflowError:
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return value


def _game_id_or_none(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        game_id = value
    elif (
        isinstance(value, str)
        and value.isascii()
        and value.isdigit()
        and len(value) <= 20
    ):
        game_id = int(value)
    else:
        return None
    return game_id if game_id > 0 else None


def search_hltb_games(query):
    try:
        entries = HowLongToBeat().search(
            query,
            similarity_case_sensitive=False,
        )
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        FakeUserAgentError,
    ) as error:
        logger.warning("HowLongToBeat search failed: %s", error)
        raise HowLongToBeatUnavailable from error

    if entries is None:
        logger.warning("HowLongToBeat search returned no response.")
        raise HowLongToBeatUnavailable
    if not isinstance(entries, list):
        logger.warning("HowLongToBeat search returned an unexpected response.")
        raise HowLongToBeatUnavailable

    results = []
    for entry in entries:
        game_name = getattr(entry, "game_name", None)
        if not isinstance(game_name, str) or not game_name.strip():
            continue

        similarity = _number_or_none(getattr(entry, "similarity", None))
        results.append(
            HowLongToBeatResult(
                game_name=game_name,
                game_id=_game_id_or_none(getattr(entry, "game_id", None)),
                similarity=max(0.0, min(similarity or 0.0, 1.0)),
                main_story=_number_or_none(getattr(entry, "main_story", None)),
                main_extra=_number_or_none(getattr(entry, "main_extra", None)),
                completionist=_number_or_none(
                    getattr(entry, "completionist", None)
                ),
                all_styles=_number_or_none(getattr(entry, "all_styles", None)),
                coop_time=_number_or_none(getattr(entry, "coop_time", None)),
                mp_time=_number_or_none(getattr(entry, "mp_time", None)),
            )
        )

    return sorted(results, key=lambda result: result.similarity, reverse=True)[:10]
