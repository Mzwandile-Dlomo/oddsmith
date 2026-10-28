"""DB-backed fixtures cache that accumulates data instead of expiring it.

Goal: fetch each calendar day from the providers at most once (twice for
upcoming days whose odds may move), store everything permanently, and serve
from the growing DB. A ``FetchLog`` records which days we already have, so a
request only calls providers for the days in its window we are missing.

* Past days are frozen once fetched (results never change).
* Upcoming days may be re-fetched after ``fixtures_cache_ttl_seconds`` so odds
  stay current.
* Fixtures are UPSERTED, never deleted — the dataset only grows.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlmodel import Session, select

from oddsmith.config import get_settings
from oddsmith.data.odds_snapshots import capture_odds_snapshots
from oddsmith.db import CachedFixture, FetchLog
from oddsmith.models import Fixture, MarketType
from oddsmith.providers.base import OddsProvider
from oddsmith.providers.merge import gather_fixtures


def _now() -> datetime:
    return datetime.now(UTC)


def _naive_utc(dt: datetime) -> datetime:
    """Store/compare datetimes as naive-UTC so SQLite and Postgres agree.

    SQLite drops tzinfo on round-trip, which makes naive(from DB) vs aware
    comparisons raise. Normalising every boundary to naive-UTC sidesteps that
    while remaining correct on Postgres.
    """
    aware = dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    return aware.astimezone(UTC).replace(tzinfo=None)


def _days_in(date_from: datetime, date_to: datetime) -> list[date]:
    start = _naive_utc(date_from).date()
    end = _naive_utc(date_to).date()
    days: list[date] = []
    cur = start
    while cur <= end:
        days.append(cur)
        cur += timedelta(days=1)
    return days


def _needs_fetch(day: date, log: FetchLog | None, ttl_seconds: int, today: date, now: datetime) -> bool:
    """A day must be fetched if never fetched, or if it is upcoming and stale."""
    if log is None:
        return True
    if day < today:
        return False  # past results are frozen once fetched
    stamp = log.fetched_at if log.fetched_at.tzinfo else log.fetched_at.replace(tzinfo=UTC)
    return (_naive_utc(now) - _naive_utc(stamp)) > timedelta(seconds=ttl_seconds)


def _read_window(
    session: Session, *, date_from: datetime, date_to: datetime
) -> list[CachedFixture]:
    rows = session.exec(
        select(CachedFixture).where(
            CachedFixture.kickoff_utc >= _naive_utc(date_from),
            CachedFixture.kickoff_utc <= _naive_utc(date_to),
        )
    )
    return list(rows)


def read_cached_fixtures(
    session: Session, *, date_from: datetime, date_to: datetime
) -> list[Fixture]:
    """Serve the window from the DB only — never calls a provider.

    Review surfaces (the calendar, a past match day) must not spend odds-API
    quota re-fetching days the user is only looking back at.
    """
    days = _days_in(date_from, date_to)
    read_from = datetime.combine(days[0], datetime.min.time(), tzinfo=UTC)
    read_to = datetime.combine(days[-1], datetime.max.time(), tzinfo=UTC)
    rows = _read_window(session, date_from=read_from, date_to=read_to)
    fixtures = [Fixture.model_validate(row.payload) for row in rows]
    return sorted(fixtures, key=lambda f: f.kickoff_utc)


async def get_cached_fixtures(
    session: Session,
    providers: list[OddsProvider],
    *,
    date_from: datetime,
    date_to: datetime,
    markets: list[MarketType] | None = None,
    force_refresh: bool = False,
) -> list[Fixture]:
    """Serve fixtures for the window, fetching only the days we are missing.

    Days already fetched (per ``FetchLog``) are served from the DB. Only the
    uncovered/stale days trigger a provider call; their results are upserted and
    the day is logged. Nothing is ever deleted.
    """
    settings = get_settings()
    now = _now()
    today = _naive_utc(now).date()
    ttl = settings.fixtures_cache_ttl_seconds

    days = _days_in(date_from, date_to)
    logs = {
        log.day: log
        for log in session.exec(select(FetchLog).where(FetchLog.day.in_(days)))
    }

    to_fetch = [
        d for d in days if force_refresh or _needs_fetch(d, logs.get(d), ttl, today, now)
    ]

    if to_fetch:
        fetch_start = datetime.combine(min(to_fetch), datetime.min.time(), tzinfo=UTC)
        fetch_end = datetime.combine(max(to_fetch), datetime.max.time(), tzinfo=UTC)
        fetched = await gather_fixtures(
            providers, date_from=fetch_start, date_to=fetch_end, markets=markets
        )
        fetched = fetched[: settings.max_fixtures_per_refresh]
        _upsert_fixtures(session, fetched, now)
        _log_days(session, to_fetch, fetched, now)

    # Read by full-day bounds so a fixture kicking off earlier on the first day
    # (or later on the last) is still returned for the requested window.
    return read_cached_fixtures(session, date_from=date_from, date_to=date_to)


def _upsert_fixtures(session: Session, fixtures: list[Fixture], fetched_at: datetime) -> None:
    """Insert new fixtures and update existing ones by fixture_id. Never deletes."""
    existing = {
        row.fixture_id: row
        for row in session.exec(
            select(CachedFixture).where(
                CachedFixture.fixture_id.in_([f.id for f in fixtures])
            )
        )
    }
    stamp = _naive_utc(fetched_at)
    capture_odds_snapshots(session, fixtures, captured_at=stamp)
    for fixture in fixtures:
        payload = fixture.model_dump(mode="json")
        row = existing.get(fixture.id)
        if row is None:
            session.add(
                CachedFixture(
                    fixture_id=fixture.id,
                    kickoff_utc=_naive_utc(fixture.kickoff_utc),
                    fetched_at=stamp,
                    payload=payload,
                )
            )
        else:
            if not fixture.markets and row.payload.get("markets"):
                # The quota guard can skip a refresh's odds; keep the stored ones.
                payload["markets"] = row.payload["markets"]
            row.kickoff_utc = _naive_utc(fixture.kickoff_utc)
            row.fetched_at = stamp
            row.payload = payload
            session.add(row)
    session.commit()


def _log_days(
    session: Session, days: list[date], fetched: list[Fixture], fetched_at: datetime
) -> None:
    counts: dict[date, int] = {}
    for f in fetched:
        d = _naive_utc(f.kickoff_utc).date()
        counts[d] = counts.get(d, 0) + 1
    stamp = _naive_utc(fetched_at)
    existing = {
        log.day: log
        for log in session.exec(select(FetchLog).where(FetchLog.day.in_(days)))
    }
    for day in days:
        log = existing.get(day)
        if log is None:
            session.add(FetchLog(day=day, fetched_at=stamp, fixture_count=counts.get(day, 0)))
        else:
            log.fetched_at = stamp
            log.fixture_count = counts.get(day, 0)
            session.add(log)
    session.commit()


def find_cached_fixture(session: Session, fixture_id: str) -> Fixture | None:
    row = session.exec(
        select(CachedFixture)
        .where(CachedFixture.fixture_id == fixture_id)
        .order_by(CachedFixture.fetched_at.desc())
    ).first()
    return Fixture.model_validate(row.payload) if row else None
