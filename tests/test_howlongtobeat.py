import unittest
from types import SimpleNamespace
from unittest.mock import patch

from platina_club.howlongtobeat import (
    HowLongToBeatUnavailable,
    search_hltb_games,
)


class HowLongToBeatSearchTests(unittest.TestCase):
    def test_search_maps_and_orders_results(self):
        entries = [
            SimpleNamespace(
                game_name="Lower match",
                game_id="123",
                similarity=0.6,
                main_story=4.5,
                main_extra=None,
                completionist=12,
                all_styles=7,
                coop_time=None,
                mp_time=None,
            ),
            SimpleNamespace(
                game_name="Best match",
                game_id=456,
                similarity=0.95,
                main_story=8,
                main_extra=13,
                completionist=20,
                all_styles=10,
                coop_time=2,
                mp_time=3,
            ),
        ]
        with patch(
            "platina_club.howlongtobeat.HowLongToBeat"
        ) as howlongtobeat:
            howlongtobeat.return_value.search.return_value = entries

            results = search_hltb_games("Example game")

        howlongtobeat.return_value.search.assert_called_once_with(
            "Example game",
            similarity_case_sensitive=False,
        )
        self.assertEqual([result.game_name for result in results], [
            "Best match",
            "Lower match",
        ])
        self.assertEqual(results[0].game_url, "https://howlongtobeat.com/game/456")
        self.assertEqual(results[1].game_url, "https://howlongtobeat.com/game/123")
        self.assertEqual(results[0].main_story, 8.0)

    def test_search_raises_when_service_fails_or_returns_none(self):
        for outcome in (
            {"side_effect": OSError("network unavailable")},
            {"return_value": None},
        ):
            with self.subTest(outcome=outcome):
                with patch(
                    "platina_club.howlongtobeat.HowLongToBeat"
                ) as howlongtobeat:
                    howlongtobeat.return_value.search.configure_mock(**outcome)

                    with self.assertRaises(HowLongToBeatUnavailable):
                        search_hltb_games("Example game")


if __name__ == "__main__":
    unittest.main()
