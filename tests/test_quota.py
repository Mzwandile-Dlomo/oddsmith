from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
import respx
from sqlmodel import Session

from oddsmith.config import Settings
from oddsmith.db import ProviderUsage
from oddsmith.providers.api_football import ApiFootballProvider
from oddsmith.providers.the_odds_api import TheOddsApiProvider
from oddsmith.quota import QuotaExceeded, QuotaGuard, QuotaPolicy

API_FOOTBALL = "https://v3.football.api-sports.io"
ODDS_API = "https://api.the-odds-api.com/v4"


def _guard(budget=10, floor=0, resets_daily=True) -> QuotaGuard:
    return QuotaGuard(
        QuotaPolicy("test", daily_budget=budget, floor=floor, remaining_resets_daily=resets_daily),
        database_url="sqlite://",
    )


def _settings(**overrides) -> Settings:
    return Settings(
        the_odds_api_key="test-key",
        the_odds_api_base_url=ODDS_API,
        the_odds_api_regions="uk,eu",
        api_football_key="test-key",
        api_football_base_url=API_FOOTBALL,
        database_url="sqlite://",
        **overrides,
    )


def test_guard_refuses_past_the_daily_budget():
    guard = _guard(budget=5)

    assert guard.reserve(3)
    assert guard.reserve(2)
    assert not guard.reserve(1)
    assert guard.used_today() == 5
    with pytest.raises(QuotaExceeded):
        guard.require(1)


def test_guard_refuses_below_the_provider_reported_floor():
    guard = _guard(budget=100, floor=5)
    guard.observe(7)

    assert guard.reserve(2)  # 7 - 2 = 5, still at the floor
    guard.observe(5)
    assert not guard.reserve(1)


def test_monthly_balance_carries_over_but_daily_count_resets():
    monthly = _guard(budget=100, floor=10, resets_daily=False)
    daily = QuotaGuard(
        QuotaPolicy("test", daily_budget=100, floor=10, remaining_resets_daily=True),
        engine=monthly._engine,
    )
    with Session(monthly._engine) as session:
        session.add(
            ProviderUsage(
                provider="test",
                day=date.today() - timedelta(days=1),
                provider_remaining=0,
            )
        )
        session.commit()

    # The Odds API's balance from yesterday still applies; API-Football's resets.
    assert not monthly.reserve(1)
    assert daily.reserve(1)


def _fixture(fixture_id: int, league_id: int, kickoff: datetime) -> dict:
    return {
        "fixture": {"id": fixture_id, "date": kickoff.isoformat()},
        "teams": {"home": {"name": f"Home {fixture_id}"}, "away": {"name": f"Away {fixture_id}"}},
        "league": {"id": league_id, "name": f"League {league_id}", "season": 2026},
    }


@respx.mock
async def test_api_football_prices_only_a_few_tracked_upcoming_fixtures():
    soon = datetime.now(UTC) + timedelta(hours=3)
    past = datetime.now(UTC) - timedelta(hours=3)
    entries = [
        _fixture(1, 39, soon + timedelta(hours=2)),  # EPL
        _fixture(2, 288, soon + timedelta(hours=5)),  # SA Premiership: odds first
        _fixture(3, 9999, soon),  # untracked league: dropped
        _fixture(4, 135, past),  # already kicked off: no odds call
        _fixture(5, 135, soon),
    ]
    respx.get(url__regex=r".*/fixtures(\?.*)?$").mock(
        return_value=httpx.Response(200, json={"response": entries})
    )
    odds_route = respx.get(url__regex=r".*/odds(\?.*)?$").mock(
        return_value=httpx.Response(200, json={"response": []})
    )
    guard = _guard(budget=90)

    async with httpx.AsyncClient(base_url=API_FOOTBALL) as client:
        provider = ApiFootballProvider(
            settings=_settings(api_football_odds_per_refresh=2), client=client, guard=guard
        )
        fixtures = await provider.list_fixtures(date_from=soon, date_to=soon)

    assert {f.id for f in fixtures} == {f"api_football:{i}" for i in (1, 2, 4, 5)}
    priced = [call.request.url.params["fixture"] for call in odds_route.calls]
    assert priced == ["2", "1"]
    assert guard.used_today() == 3  # one fixtures list + two odds


@respx.mock
async def test_api_football_stops_spending_at_the_budget_but_keeps_fixtures():
    soon = datetime.now(UTC) + timedelta(hours=3)
    respx.get(url__regex=r".*/fixtures(\?.*)?$").mock(
        return_value=httpx.Response(
            200, json={"response": [_fixture(i, 39, soon) for i in range(1, 6)]}
        )
    )
    odds_route = respx.get(url__regex=r".*/odds(\?.*)?$").mock(
        return_value=httpx.Response(200, json={"response": []})
    )

    async with httpx.AsyncClient(base_url=API_FOOTBALL) as client:
        provider = ApiFootballProvider(settings=_settings(), client=client, guard=_guard(budget=3))
        fixtures = await provider.list_fixtures(date_from=soon, date_to=soon)

    assert len(fixtures) == 5
    assert odds_route.call_count == 2


@respx.mock
async def test_api_football_sends_nothing_once_the_budget_is_spent():
    route = respx.get(url__regex=r".*").mock(return_value=httpx.Response(200, json={}))
    guard = _guard(budget=1)
    guard.reserve(1)

    async with httpx.AsyncClient(base_url=API_FOOTBALL) as client:
        provider = ApiFootballProvider(settings=_settings(), client=client, guard=guard)
        with pytest.raises(QuotaExceeded):
            await provider.list_fixtures(
                date_from=datetime.now(UTC), date_to=datetime.now(UTC)
            )

    assert route.call_count == 0


@respx.mock
async def test_the_odds_api_pays_only_for_sports_with_events_within_budget():
    respx.get(url__regex=r".*/sports/[a-z_]+/events(\?.*)?$").mock(
        side_effect=lambda request: httpx.Response(200, json=[])
        if "soccer_c" in str(request.url)
        else httpx.Response(200, json=[{"id": "x"}])
    )
    odds_route = respx.get(url__regex=r".*/sports/[a-z_]+/odds(\?.*)?$").mock(
        return_value=httpx.Response(200, headers={"x-requests-remaining": "400"}, json=[])
    )
    # h2h + totals across uk,eu = 4 credits a sport; 9 credits buys two.
    guard = _guard(budget=9, resets_daily=False)

    async with httpx.AsyncClient(base_url=ODDS_API) as client:
        provider = TheOddsApiProvider(
            settings=_settings(),
            client=client,
            sports=("soccer_a", "soccer_b", "soccer_c", "soccer_d"),
            guard=guard,
        )
        await provider.list_fixtures(
            date_from=datetime.now(UTC), date_to=datetime.now(UTC) + timedelta(days=1)
        )

    paid = [str(call.request.url.path).split("/")[-2] for call in odds_route.calls]
    assert paid == ["soccer_a", "soccer_b"]  # soccer_c has no events; soccer_d is over budget
    assert guard.used_today() == 8


@respx.mock
async def test_the_odds_api_refuses_when_nothing_is_affordable():
    respx.get(url__regex=r".*/events(\?.*)?$").mock(
        return_value=httpx.Response(200, json=[{"id": "x"}])
    )
    odds_route = respx.get(url__regex=r".*/odds(\?.*)?$").mock(
        return_value=httpx.Response(200, json=[])
    )

    async with httpx.AsyncClient(base_url=ODDS_API) as client:
        provider = TheOddsApiProvider(
            settings=_settings(), client=client, sports=("soccer_a",), guard=_guard(budget=3)
        )
        with pytest.raises(QuotaExceeded):
            await provider.list_fixtures(
                date_from=datetime.now(UTC), date_to=datetime.now(UTC) + timedelta(days=1)
            )

    assert odds_route.call_count == 0
