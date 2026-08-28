"""Capture a fresh window of bookmaker prices into append-only snapshots.

Run this on a schedule (for example every six hours). Provider calls may consume
paid quota, so the default uses only The Odds API and limits the date window.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import func
from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oddsmith.cache import get_cached_fixtures
from oddsmith.db import OddsSnapshot, get_engine, init_db
from oddsmith.models import MarketType
from oddsmith.providers.api_football import ApiFootballProvider
from oddsmith.providers.base import OddsProvider
from oddsmith.providers.the_odds_api import TheOddsApiProvider


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=3, choices=range(1, 8))
    parser.add_argument(
        "--provider",
        choices=("the_odds_api", "api_football", "all"),
        default="the_odds_api",
        help="API-Football can make one odds request per fixture and consume more quota",
    )
    parser.add_argument(
        "--markets",
        nargs="+",
        choices=("match_winner", "over_under", "btts"),
        default=("match_winner", "over_under"),
    )
    return parser


def _providers(choice: str) -> list[OddsProvider]:
    providers: list[OddsProvider] = []
    if choice in {"the_odds_api", "all"}:
        providers.append(TheOddsApiProvider())
    if choice in {"api_football", "all"}:
        providers.append(ApiFootballProvider())
    return providers


def _snapshot_count(session: Session) -> int:
    return int(session.exec(select(func.count()).select_from(OddsSnapshot)).one())


async def _run() -> int:
    args = _parser().parse_args()
    init_db()
    now = datetime.now(UTC)
    end = now + timedelta(days=args.days)
    markets = [MarketType(value) for value in args.markets]
    with Session(get_engine()) as session:
        before = _snapshot_count(session)
        fixtures = await get_cached_fixtures(
            session,
            _providers(args.provider),
            date_from=now,
            date_to=end,
            markets=markets,
            force_refresh=True,
        )
        after = _snapshot_count(session)
    print(
        f"Captured {after - before} new price outcomes across {len(fixtures)} fixtures "
        f"({after} total snapshots)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
