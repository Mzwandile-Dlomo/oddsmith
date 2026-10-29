from datetime import UTC, datetime

import pytest

from oddsmith.models import Fixture, Market, MarketType, Outcome
from oddsmith.providers.base import OddsProvider, ProviderError
from oddsmith.providers.merge import (
    AllProvidersFailed,
    _merge,
    _normalize_team,
    gather_fixtures,
)


def _fx(fid, home, away, provider, markets=None, hour=15):
    return Fixture(
        id=fid,
        home_team=home,
        away_team=away,
        kickoff_utc=datetime(2026, 7, 25, hour, 0, tzinfo=UTC),
        provider=provider,
        markets=markets or [],
    )


def test_normalize_strips_fc_noise():
    assert _normalize_team("Arsenal FC") == _normalize_team("Arsenal")
    assert _normalize_team("AFC Bournemouth") == "bournemouth"


def test_merge_dedupes_same_match_across_providers():
    f1 = _fx(
        "the_odds_api:1",
        "Arsenal FC",
        "Chelsea FC",
        "the_odds_api",
        [Market(type=MarketType.MATCH_WINNER, outcomes=[Outcome(name="Home", price=2.1)])],
    )
    f2 = _fx(
        "api_football:99",
        "Arsenal",
        "Chelsea",
        "api_football",
        [Market(type=MarketType.BTTS, outcomes=[Outcome(name="Yes", price=1.8)])],
    )
    f3 = _fx("the_odds_api:2", "Liverpool", "Everton", "the_odds_api", hour=12)

    merged = _merge([f1, f2, f3])
    assert len(merged) == 2
    arsenal = next(m for m in merged if "rsenal" in m.home_team)
    assert {mk.type for mk in arsenal.markets} == {MarketType.MATCH_WINNER, MarketType.BTTS}


def test_merge_sorts_by_kickoff():
    early = _fx("p:1", "A", "B", "p", hour=10)
    late = _fx("p:2", "C", "D", "p", hour=20)
    merged = _merge([late, early])
    assert [m.id for m in merged] == ["p:1", "p:2"]


class _OkProvider(OddsProvider):
    name = "ok"

    async def list_fixtures(self, *, date_from, date_to, markets=None):
        return [_fx("ok:1", "A", "B", "ok")]

    async def get_markets(self, fixture_id):
        return []


class _FailingProvider(OddsProvider):
    name = "boom"

    async def list_fixtures(self, *, date_from, date_to, markets=None):
        raise ProviderError("no key")

    async def get_markets(self, fixture_id):
        return []


async def test_gather_skips_failing_provider():
    fixtures = await gather_fixtures(
        [_OkProvider(), _FailingProvider()],
        date_from=datetime(2026, 7, 25, tzinfo=UTC),
        date_to=datetime(2026, 7, 26, tzinfo=UTC),
    )
    assert len(fixtures) == 1
    assert fixtures[0].id == "ok:1"


async def test_gather_reraises_unexpected_error():
    class _Crash(OddsProvider):
        name = "crash"

        async def list_fixtures(self, *, date_from, date_to, markets=None):
            raise RuntimeError("unexpected")

        async def get_markets(self, fixture_id):
            return []

    with pytest.raises(RuntimeError):
        await gather_fixtures(
            [_Crash()],
            date_from=datetime(2026, 7, 25, tzinfo=UTC),
            date_to=datetime(2026, 7, 26, tzinfo=UTC),
        )


async def test_gather_raises_when_every_provider_fails():
    """An empty list would read as "no matches", and get logged as fetched."""
    with pytest.raises(AllProvidersFailed, match="boom: no key"):
        await gather_fixtures(
            [_FailingProvider(), _FailingProvider()],
            date_from=datetime(2026, 7, 25, tzinfo=UTC),
            date_to=datetime(2026, 7, 26, tzinfo=UTC),
        )
