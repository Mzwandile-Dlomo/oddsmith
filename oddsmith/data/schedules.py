"""Persistence helpers for full-season schedules."""

from __future__ import annotations

from datetime import UTC, datetime, time

from sqlmodel import Session, select

from oddsmith.db import ScheduledFixture
from oddsmith.models import Fixture


def upsert_scheduled_fixtures(
    session: Session, fixtures: list[ScheduledFixture]
) -> tuple[int, int]:
    keys = [fixture.source_key for fixture in fixtures]
    existing = {
        fixture.source_key: fixture
        for fixture in session.exec(
            select(ScheduledFixture).where(ScheduledFixture.source_key.in_(keys))
        )
    } if keys else {}
    inserted = updated = 0
    for incoming in fixtures:
        stored = existing.get(incoming.source_key)
        if stored is None:
            session.add(incoming)
            inserted += 1
            continue
        for field in (
            "round_number",
            "kickoff_utc",
            "location",
            "home_team",
            "away_team",
            "home_goals",
            "away_goals",
            "raw_payload",
        ):
            setattr(stored, field, getattr(incoming, field))
        stored.updated_at = datetime.now(UTC)
        session.add(stored)
        updated += 1
    session.commit()
    return inserted, updated


def read_scheduled_fixtures(
    session: Session, *, date_from: datetime, date_to: datetime
) -> list[Fixture]:
    """Return persisted full-season fixtures without contacting a provider."""
    # Match the odds cache's API semantics: date-only query parameters arrive
    # as midnight, but represent the complete first and last calendar days.
    start = datetime.combine(_naive_utc(date_from).date(), time.min)
    end = datetime.combine(_naive_utc(date_to).date(), time.max)
    rows = session.exec(
        select(ScheduledFixture)
        .where(
            ScheduledFixture.kickoff_utc >= start,
            ScheduledFixture.kickoff_utc <= end,
        )
        .order_by(ScheduledFixture.kickoff_utc)
    )
    return [
        Fixture(
            id=row.source_key,
            home_team=row.home_team,
            away_team=row.away_team,
            kickoff_utc=row.kickoff_utc.replace(tzinfo=UTC),
            league=row.league_name,
            provider=row.source,
        )
        for row in rows
    ]


def _naive_utc(value: datetime) -> datetime:
    aware = value if value.tzinfo else value.replace(tzinfo=UTC)
    return aware.astimezone(UTC).replace(tzinfo=None)
