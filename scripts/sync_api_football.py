"""Synchronize selected API-Football competition seasons into PostgreSQL."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlmodel import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oddsmith.competitions import COMPETITIONS, resolve_competition
from oddsmith.db import get_engine, init_db
from oddsmith.match_sync import sync_competition
from oddsmith.providers.api_football import ApiFootballProvider


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--season",
        type=int,
        default=2026,
        help="season starting year (default: 2026 for 2026/27)",
    )
    parser.add_argument(
        "--league",
        action="append",
        default=[],
        help="competition alias; repeat to sync a subset (default: all)",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="make provider requests and write matches; otherwise show the request plan",
    )
    return parser


async def _run() -> int:
    args = _parser().parse_args()
    try:
        competitions = (
            [resolve_competition(value) for value in args.league]
            if args.league
            else list(COMPETITIONS)
        )
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    if not args.write:
        aliases = ", ".join(item.key for item in competitions)
        print(
            f"Plan only: {len(competitions)} API requests for season {args.season}: "
            f"{aliases}. Add --write to synchronize."
        )
        return 0

    init_db()
    provider = ApiFootballProvider()
    total_received = total_inserted = total_updated = 0
    remaining = None
    with Session(get_engine()) as session:
        for competition in competitions:
            result = await sync_competition(session, provider, competition, args.season)
            total_received += result.received
            total_inserted += result.inserted
            total_updated += result.updated
            remaining = result.requests_remaining
            print(
                f"{result.competition}: received {result.received}, "
                f"inserted {result.inserted}, updated {result.updated}"
            )
    print(
        f"Done: {total_received} received, {total_inserted} inserted, "
        f"{total_updated} updated; daily requests remaining "
        f"{remaining if remaining is not None else 'unknown'}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
