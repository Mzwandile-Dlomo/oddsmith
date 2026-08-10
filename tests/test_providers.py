from datetime import UTC, datetime

import httpx
import pytest
import respx

from oddsmith.config import Settings
from oddsmith.models import MarketType
from oddsmith.providers.api_football import ApiFootballProvider
from oddsmith.providers.the_odds_api import TheOddsApiProvider


@pytest.fixture
def odds_settings():
    return Settings(
        the_odds_api_key="test-key",
        the_odds_api_base_url="https://api.the-odds-api.com/v4",
        api_football_key="test-key",
        api_football_base_url="https://v3.football.api-sports.io",
        database_url="sqlite:///:memory:",
    )


@respx.mock
async def test_the_odds_api_parses_h2h_and_totals(odds_settings):
    event = {
        "id": "abc123",
        "commence_time": "2026-07-25T15:00:00Z",
        "home_team": "Arsenal",
        "away_team": "Chelsea",
        "sport_title": "EPL",
        "bookmakers": [
            {
                "key": "bk1",
                "title": "Book One",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Arsenal", "price": 2.1},
                            {"name": "Chelsea", "price": 3.4},
                            {"name": "Draw", "price": 3.2},
                        ],
                    },
                    {
                        "key": "totals",
                        "outcomes": [
                            {"name": "Over", "price": 1.9, "point": 2.5},
                            {"name": "Under", "price": 1.9, "point": 2.5},
                        ],
                    },
                ],
            }
        ],
    }
    respx.get(url__regex=r".*/sports/.*/odds").mock(
        side_effect=lambda request: httpx.Response(200, json=[event])
        if "soccer_epl" in str(request.url)
        else httpx.Response(200, json=[])
    )

    async with httpx.AsyncClient(base_url=odds_settings.the_odds_api_base_url) as client:
        provider = TheOddsApiProvider(settings=odds_settings, client=client)
        fixtures = await provider.list_fixtures(
            date_from=datetime(2026, 7, 25, tzinfo=UTC),
            date_to=datetime(2026, 7, 26, tzinfo=UTC),
        )

    assert len(fixtures) == 1
    fx = fixtures[0]
    assert fx.id == "the_odds_api:abc123"
    assert fx.home_team == "Arsenal"
    types = {m.type for m in fx.markets}
    assert MarketType.MATCH_WINNER in types
    assert MarketType.OVER_UNDER in types
    mw = next(m for m in fx.markets if m.type is MarketType.MATCH_WINNER)
    names = {o.name for o in mw.outcomes}
    assert names == {"Home", "Away", "Draw"}
    ou = next(m for m in fx.markets if m.type is MarketType.OVER_UNDER)
    assert all(o.point == 2.5 for o in ou.outcomes)


@respx.mock
async def test_api_football_parses_fixtures_and_bets(odds_settings):
    fixtures_payload = {
        "response": [
            {
                "fixture": {"id": 555, "date": "2026-07-25T15:00:00+00:00"},
                "teams": {"home": {"name": "Arsenal"}, "away": {"name": "Chelsea"}},
                "league": {"name": "Premier League"},
            }
        ]
    }
    odds_payload = {
        "response": [
            {
                "bookmakers": [
                    {
                        "name": "Book One",
                        "bets": [
                            {
                                "id": 1,
                                "name": "Match Winner",
                                "values": [
                                    {"value": "Home", "odd": "2.10"},
                                    {"value": "Draw", "odd": "3.20"},
                                    {"value": "Away", "odd": "3.40"},
                                ],
                            },
                            {
                                "id": 8,
                                "name": "Both Teams Score",
                                "values": [
                                    {"value": "Yes", "odd": "1.80"},
                                    {"value": "No", "odd": "1.95"},
                                ],
                            },
                            {
                                "id": 5,
                                "name": "Goals Over/Under",
                                "values": [
                                    {"value": "Over 2.5", "odd": "1.90"},
                                    {"value": "Under 2.5", "odd": "1.90"},
                                ],
                            },
                        ],
                    }
                ]
            }
        ]
    }
    fixtures_route = respx.get(url__regex=r".*/fixtures(\?.*)?$").mock(
        return_value=httpx.Response(200, json=fixtures_payload)
    )
    respx.get(url__regex=r".*/odds(\?.*)?$").mock(return_value=httpx.Response(200, json=odds_payload))

    async with httpx.AsyncClient(base_url=odds_settings.api_football_base_url) as client:
        provider = ApiFootballProvider(settings=odds_settings, client=client)
        fixtures = await provider.list_fixtures(
            date_from=datetime(2026, 7, 25, tzinfo=UTC),
            date_to=datetime(2026, 7, 25, tzinfo=UTC),
        )

    # Free-plan compatible: fixtures are queried per-day via `date=`, not from/to.
    called_url = str(fixtures_route.calls.last.request.url)
    assert "date=2026-07-25" in called_url
    assert "from=" not in called_url

    assert len(fixtures) == 1
    fx = fixtures[0]
    assert fx.id == "api_football:555"
    assert fx.league == "Premier League"
    types = {m.type for m in fx.markets}
    assert types == {MarketType.MATCH_WINNER, MarketType.BTTS, MarketType.OVER_UNDER}
    btts = next(m for m in fx.markets if m.type is MarketType.BTTS)
    assert {o.name for o in btts.outcomes} == {"Yes", "No"}
    ou = next(m for m in fx.markets if m.type is MarketType.OVER_UNDER)
    assert all(o.point == 2.5 for o in ou.outcomes)


async def test_provider_missing_key_raises():
    from oddsmith.providers.base import ProviderError

    provider = TheOddsApiProvider(settings=Settings(the_odds_api_key=None))
    with pytest.raises(ProviderError):
        await provider.list_fixtures(
            date_from=datetime(2026, 7, 25, tzinfo=UTC),
            date_to=datetime(2026, 7, 26, tzinfo=UTC),
        )
