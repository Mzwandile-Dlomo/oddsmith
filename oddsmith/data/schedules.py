"""Persistence helpers for full-season schedules."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Session, select

from oddsmith.db import ScheduledFixture


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
