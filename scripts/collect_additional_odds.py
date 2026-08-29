"""Collect quota-controlled BTTS and total-corner prices from The Odds API."""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlmodel import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oddsmith.config import get_settings
from oddsmith.data.odds_snapshots import capture_odds_snapshots
from oddsmith.db import get_engine, init_db
from oddsmith.models import MarketType
from oddsmith.providers.the_odds_api import TheOddsApiProvider


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-hours-to-kickoff", type=float, default=18.0)
    parser.add_argument("--max-hours-to-kickoff", type=float, default=36.0)
    parser.add_argument("--max-events", type=int, default=5, choices=range(1, 41))
    parser.add_argument("--max-credits", type=int, default=20)
    parser.add_argument(
        "--markets",
        nargs="+",
        choices=("btts", "corner_totals"),
        default=("btts", "corner_totals"),
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="make quota-consuming event-odds calls and persist returned prices",
    )
    return parser


async def _run() -> int:
    args = _parser().parse_args()
    if not 0 <= args.min_hours_to_kickoff < args.max_hours_to_kickoff <= 168:
        raise SystemExit(
            "kickoff horizon must satisfy 0 <= min < max <= 168 hours"
        )
    settings = get_settings()
    markets = list(dict.fromkeys(MarketType(value) for value in args.markets))
    region_count = max(
        len([region for region in settings.the_odds_api_regions.split(",") if region]),
        1,
    )
    worst_case = args.max_events * len(markets) * region_count
    capped_estimate = min(worst_case, args.max_credits)
    if not args.write:
        print(
            f"Plan only: up to {args.max_events} events, {len(markets)} markets, "
            f"{region_count} regions; configured ceiling {args.max_credits} credits "
            f"(at most {capped_estimate} usable under this cap); horizon "
            f"{args.min_hours_to_kickoff:g}-{args.max_hours_to_kickoff:g}h. "
            "Add --write to collect."
        )
        return 0

    init_db()
    now = datetime.now(UTC)
    result = await TheOddsApiProvider(settings=settings).collect_additional_markets(
        date_from=now + timedelta(hours=args.min_hours_to_kickoff),
        date_to=now + timedelta(hours=args.max_hours_to_kickoff),
        markets=markets,
        max_events=args.max_events,
        max_credits=args.max_credits,
    )
    with Session(get_engine()) as session:
        added = capture_odds_snapshots(session, result.fixtures, captured_at=now)
        session.commit()
    remaining = (
        str(result.credits_remaining)
        if result.credits_remaining is not None
        else "not reported"
    )
    print(
        f"Discovered {result.events_discovered} events; requested {result.event_requests}; "
        f"stored {added} outcomes. Credits used {result.credits_used} "
        f"(worst-case ceiling {result.estimated_max_credits}); remaining {remaining}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
