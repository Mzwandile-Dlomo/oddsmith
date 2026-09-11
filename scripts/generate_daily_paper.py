"""Create one immutable, model-filtered daily paper ticket for the current UTC day.

This is deliberately a paper observation: it records what the model would have
selected before kickoff, then the normal result pipeline settles it. A day with
no qualifying value selection records no ticket rather than padding an acca.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, time
from pathlib import Path

from sqlmodel import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oddsmith.api import daily_acca, get_providers
from oddsmith.db import get_engine, init_db


async def _run() -> int:
    init_db()
    now = datetime.now(UTC)
    start = datetime.combine(now.date(), time.min, tzinfo=UTC)
    end = datetime.combine(now.date(), time.max, tzinfo=UTC)
    with Session(get_engine()) as session:
        ticket = await daily_acca(
            date_from=start,
            date_to=end,
            auto_track=True,
            providers=get_providers(),
            session=session,
        )
    if ticket.auto_tracked:
        print(
            f"Archived Paper daily 1.50 for {start.date().isoformat()}: "
            f"{len(ticket.legs)} legs at {ticket.combined_odds:.2f}."
        )
    else:
        print(
            f"No paper ticket for {start.date().isoformat()}: {ticket.note} "
            f"({ticket.fixtures_scanned} fixtures, {ticket.candidates_scanned} candidates)."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
