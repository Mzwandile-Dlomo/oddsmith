"""Capture a fresh window of bookmaker prices into append-only snapshots.

Run this on a schedule (for example every six hours). Provider calls may consume
paid quota, so the default uses only The Odds API and limits the date window.
Corner totals are supported as collection-only research data: they use the
provider's explicitly budgeted per-event endpoint and never enter the model or
ticket generator.
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
from oddsmith.data.odds_snapshots import capture_odds_snapshots
from oddsmith.db import OddsSnapshot, get_engine, init_db
from oddsmith.models import MarketType
from oddsmith.providers.api_football import ApiFootballProvider
from oddsmith.providers.base import OddsProvider, ProviderError
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
        choices=("match_winner", "over_under", "btts", "corner_totals"),
        default=("match_winner", "over_under"),
    )
    parser.add_argument(
        "--max-additional-events",
        type=int,
        default=5,
        choices=range(1, 41),
        help="maximum events for BTTS/corner per-event price collection",
    )
    parser.add_argument(
        "--max-additional-credits",
        type=int,
        default=10,
        help="hard credit ceiling for BTTS/corner per-event price collection",
    )
    parser.add_argument(
        "--additional-optional",
        action="store_true",
        help=(
            "report an unavailable BTTS/corner market and continue successfully; "
            "use only for scheduled research collection"
        ),
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
    additional_markets = [
        market
        for market in markets
        if market in {MarketType.BTTS, MarketType.CORNER_TOTALS}
    ]
    bulk_markets = [market for market in markets if market not in additional_markets]
    if additional_markets and args.provider != "the_odds_api":
        raise SystemExit(
            "BTTS and corner totals are collected through The Odds API's "
            "budgeted per-event endpoint; use --provider the_odds_api"
        )
    with Session(get_engine()) as session:
        before = _snapshot_count(session)
        fixtures = []
        if bulk_markets:
            fixtures = await get_cached_fixtures(
                session,
                _providers(args.provider),
                date_from=now,
                date_to=end,
                markets=bulk_markets,
                force_refresh=True,
            )
        if additional_markets:
            try:
                result = await TheOddsApiProvider().collect_additional_markets(
                    date_from=now,
                    date_to=end,
                    markets=additional_markets,
                    max_events=args.max_additional_events,
                    max_credits=args.max_additional_credits,
                )
            except ProviderError as exc:
                if not args.additional_optional:
                    raise
                print(
                    "WARNING: additional-market research was skipped; "
                    f"the configured account did not accept this request ({exc})."
                )
            else:
                capture_odds_snapshots(session, result.fixtures, captured_at=now)
                session.commit()
                fixtures.extend(result.fixtures)
        after = _snapshot_count(session)
    print(
        f"Captured {after - before} new price outcomes across {len(fixtures)} fixtures "
        f"({after} total snapshots)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
