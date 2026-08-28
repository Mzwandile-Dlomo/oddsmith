"""Persist append-only, pre-match bookmaker price observations."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

from sqlmodel import Session, select

from oddsmith.db import OddsSnapshot
from oddsmith.models import Fixture


def _naive_utc(value: datetime) -> datetime:
    aware = value if value.tzinfo else value.replace(tzinfo=UTC)
    return aware.astimezone(UTC).replace(tzinfo=None)


def capture_odds_snapshots(
    session: Session,
    fixtures: list[Fixture],
    *,
    captured_at: datetime,
) -> int:
    """Stage idempotent snapshot rows and return the number added."""
    stamp = _naive_utc(captured_at)
    candidates: list[OddsSnapshot] = []
    for fixture in fixtures:
        kickoff = _naive_utc(fixture.kickoff_utc)
        if stamp >= kickoff:
            continue
        hours_to_kickoff = (kickoff - stamp).total_seconds() / 3600
        for market in fixture.markets:
            provider = market.provider or fixture.provider
            bookmaker = market.bookmaker or "unknown"
            for outcome in market.outcomes:
                identity = "|".join(
                    (
                        fixture.id,
                        provider,
                        bookmaker,
                        market.type.value,
                        outcome.name,
                        "" if outcome.point is None else f"{outcome.point:g}",
                        stamp.isoformat(timespec="microseconds"),
                    )
                )
                candidates.append(
                    OddsSnapshot(
                        snapshot_key=sha256(identity.encode()).hexdigest(),
                        fixture_id=fixture.id,
                        provider=provider,
                        bookmaker=bookmaker,
                        league=fixture.league,
                        kickoff_utc=kickoff,
                        captured_at=stamp,
                        hours_to_kickoff=round(hours_to_kickoff, 4),
                        home_team=fixture.home_team,
                        away_team=fixture.away_team,
                        market_type=market.type.value,
                        selection=outcome.name,
                        point=outcome.point,
                        price=outcome.price,
                    )
                )
    keys = [row.snapshot_key for row in candidates]
    existing: set[str] = set()
    for start in range(0, len(keys), 500):
        existing.update(
            session.exec(
                select(OddsSnapshot.snapshot_key).where(
                    OddsSnapshot.snapshot_key.in_(keys[start : start + 500])
                )
            )
        )
    added = 0
    for row in candidates:
        if row.snapshot_key in existing:
            continue
        session.add(row)
        existing.add(row.snapshot_key)
        added += 1
    return added
