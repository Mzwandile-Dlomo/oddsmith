from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import Session, SQLModel, create_engine

from oddsmith import cache as cache_module
from oddsmith.config import Settings
from oddsmith.models import Fixture, Market, MarketType, Outcome
from oddsmith.providers.base import OddsProvider


class CountingProvider(OddsProvider):
    name = "counting"

    def __init__(self, fixture_count: int = 1) -> None:
        self.calls = 0
        self._fixture_count = fixture_count

    async def list_fixtures(self, *, date_from, date_to, markets=None):
        self.calls += 1
        return [
            Fixture(
                id=f"counting:{i}",
                home_team=f"Home {i}",
                away_team=f"Away {i}",
                kickoff_utc=datetime(2026, 7, 25, 15, 0, tzinfo=UTC) + timedelta(minutes=i),
                league="Test League",
                provider="counting",
                markets=[
                    Market(
                        type=MarketType.MATCH_WINNER,
                        outcomes=[Outcome(name="Home", price=2.0)],
                    )
                ],
            )
            for i in range(self._fixture_count)
        ]

    async def get_markets(self, fixture_id):
        return []


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def settings():
    return Settings(
        database_url="sqlite://",
        fixtures_cache_ttl_seconds=3600,
        max_fixtures_per_refresh=40,
    )


def _patch_settings(monkeypatch, settings):
    monkeypatch.setattr(cache_module, "get_settings", lambda: settings)


WINDOW = {
    "date_from": datetime(2026, 7, 25, 0, 0, tzinfo=UTC),
    "date_to": datetime(2026, 7, 26, 0, 0, tzinfo=UTC),
}


async def test_miss_fetches_and_stores(session, settings, monkeypatch):
    _patch_settings(monkeypatch, settings)
    provider = CountingProvider(fixture_count=2)

    fixtures = await cache_module.get_cached_fixtures(session, [provider], **WINDOW)

    assert provider.calls == 1
    assert len(fixtures) == 2


async def test_hit_does_not_call_provider(session, settings, monkeypatch):
    _patch_settings(monkeypatch, settings)
    provider = CountingProvider(fixture_count=2)

    await cache_module.get_cached_fixtures(session, [provider], **WINDOW)
    assert provider.calls == 1

    # Second identical request within TTL must be served from the DB.
    fixtures = await cache_module.get_cached_fixtures(session, [provider], **WINDOW)
    assert provider.calls == 1
    assert len(fixtures) == 2


async def test_stale_cache_refetches(session, settings, monkeypatch):
    settings.fixtures_cache_ttl_seconds = 0
    _patch_settings(monkeypatch, settings)
    provider = CountingProvider(fixture_count=1)

    await cache_module.get_cached_fixtures(session, [provider], **WINDOW)
    await cache_module.get_cached_fixtures(session, [provider], **WINDOW)

    assert provider.calls == 2


async def test_force_refresh_bypasses_fresh_cache(session, settings, monkeypatch):
    _patch_settings(monkeypatch, settings)
    provider = CountingProvider(fixture_count=1)

    await cache_module.get_cached_fixtures(session, [provider], **WINDOW)
    await cache_module.get_cached_fixtures(
        session, [provider], **WINDOW, force_refresh=True
    )

    assert provider.calls == 2


async def test_cap_limits_stored_fixtures(session, settings, monkeypatch):
    settings.max_fixtures_per_refresh = 5
    _patch_settings(monkeypatch, settings)
    provider = CountingProvider(fixture_count=20)

    fixtures = await cache_module.get_cached_fixtures(session, [provider], **WINDOW)

    assert len(fixtures) == 5


async def test_find_cached_fixture(session, settings, monkeypatch):
    _patch_settings(monkeypatch, settings)
    provider = CountingProvider(fixture_count=3)
    await cache_module.get_cached_fixtures(session, [provider], **WINDOW)

    found = cache_module.find_cached_fixture(session, "counting:1")
    assert found is not None
    assert found.id == "counting:1"

    missing = cache_module.find_cached_fixture(session, "counting:999")
    assert missing is None


async def test_data_accumulates_across_windows(session, settings, monkeypatch):
    # Given fixtures cached for two separate day-windows, when a later fetch runs,
    # then both windows' fixtures remain in the DB (fetching one day preserves others).
    _patch_settings(monkeypatch, settings)

    class DayProvider(OddsProvider):
        name = "day"

        def __init__(self, day, n):
            self.day = day
            self.n = n
            self.calls = 0

        async def list_fixtures(self, *, date_from, date_to, markets=None):
            self.calls += 1
            return [
                Fixture(
                    id=f"day:{self.day.isoformat()}:{i}",
                    home_team=f"H{i}",
                    away_team=f"A{i}",
                    kickoff_utc=datetime.combine(self.day, datetime.min.time(), tzinfo=UTC)
                    + timedelta(hours=15, minutes=i),
                    league="L",
                    provider="day",
                    markets=[],
                )
                for i in range(self.n)
            ]

        async def get_markets(self, fixture_id):
            return []

    from datetime import date

    w1 = {
        "date_from": datetime(2026, 8, 1, 0, 0, tzinfo=UTC),
        "date_to": datetime(2026, 8, 1, 23, 0, tzinfo=UTC),
    }
    w2 = {
        "date_from": datetime(2026, 8, 2, 0, 0, tzinfo=UTC),
        "date_to": datetime(2026, 8, 2, 23, 0, tzinfo=UTC),
    }
    await cache_module.get_cached_fixtures(session, [DayProvider(date(2026, 8, 1), 3)], **w1)
    await cache_module.get_cached_fixtures(session, [DayProvider(date(2026, 8, 2), 2)], **w2)

    # A wide window spanning both days serves all 5 accumulated fixtures.
    wide = {
        "date_from": datetime(2026, 8, 1, 0, 0, tzinfo=UTC),
        "date_to": datetime(2026, 8, 2, 23, 0, tzinfo=UTC),
    }
    # Both days already logged & fresh -> no provider needed.
    silent = CountingProvider(fixture_count=99)
    all_fx = await cache_module.get_cached_fixtures(session, [silent], **wide)
    assert silent.calls == 0
    assert len(all_fx) == 5


async def test_only_missing_days_are_fetched(session, settings, monkeypatch):
    # Fetch day 1, then request days 1-2: only day 2 should hit the provider.
    _patch_settings(monkeypatch, settings)

    calls = {"n": 0}

    class RangeProvider(OddsProvider):
        name = "range"

        async def list_fixtures(self, *, date_from, date_to, markets=None):
            calls["n"] += 1
            out = []
            d = date_from.date()
            while d <= date_to.date():
                out.append(
                    Fixture(
                        id=f"range:{d.isoformat()}",
                        home_team="H",
                        away_team="A",
                        kickoff_utc=datetime.combine(d, datetime.min.time(), tzinfo=UTC)
                        + timedelta(hours=15),
                        league="L",
                        provider="range",
                        markets=[],
                    )
                )
                d += timedelta(days=1)
            return out

        async def get_markets(self, fixture_id):
            return []

    day1 = {
        "date_from": datetime(2026, 9, 1, 0, 0, tzinfo=UTC),
        "date_to": datetime(2026, 9, 1, 23, 0, tzinfo=UTC),
    }
    both = {
        "date_from": datetime(2026, 9, 1, 0, 0, tzinfo=UTC),
        "date_to": datetime(2026, 9, 2, 23, 0, tzinfo=UTC),
    }
    p = RangeProvider()
    await cache_module.get_cached_fixtures(session, [p], **day1)
    assert calls["n"] == 1

    # Second request overlaps day 1 (already have) + day 2 (missing).
    result = await cache_module.get_cached_fixtures(session, [p], **both)
    assert calls["n"] == 2  # one more fetch, for the missing day only
    # The fetch should have covered only day 2's range, so exactly 2 fixtures total.
    assert len(result) == 2
