"""Backfill pre-match odds snapshots from already-cached fixture payloads."""

from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from sqlalchemy import func
from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oddsmith.data.odds_snapshots import capture_odds_snapshots
from oddsmith.db import CachedFixture, OddsSnapshot, get_engine, init_db
from oddsmith.models import Fixture


def main() -> int:
    init_db()
    with Session(get_engine()) as session:
        before = int(
            session.exec(select(func.count()).select_from(OddsSnapshot)).one()
        )
        grouped: dict[datetime, list[Fixture]] = defaultdict(list)
        for row in session.exec(select(CachedFixture)):
            grouped[row.fetched_at].append(Fixture.model_validate(row.payload))
        for captured_at, fixtures in grouped.items():
            capture_odds_snapshots(session, fixtures, captured_at=captured_at)
        session.commit()
        after = int(
            session.exec(select(func.count()).select_from(OddsSnapshot)).one()
        )
    print(f"Backfilled {after - before} price outcomes ({after} total snapshots).")
    with Session(get_engine()) as session:
        breakdown = session.exec(
            select(
                OddsSnapshot.market_type,
                func.count(OddsSnapshot.id),
                func.count(func.distinct(OddsSnapshot.fixture_id)),
                func.min(OddsSnapshot.hours_to_kickoff),
                func.max(OddsSnapshot.hours_to_kickoff),
            )
            .group_by(OddsSnapshot.market_type)
            .order_by(OddsSnapshot.market_type)
        ).all()
    for market, rows, fixtures, nearest, furthest in breakdown:
        print(
            f"{market}: {rows} outcomes, {fixtures} fixtures, "
            f"{nearest:.1f}h to {furthest:.1f}h before kickoff"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
