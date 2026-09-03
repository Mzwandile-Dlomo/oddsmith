"""Synchronize complete current-season schedules from Fixture Download."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlmodel import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oddsmith.config import get_settings
from oddsmith.data.schedules import upsert_scheduled_fixtures
from oddsmith.db import get_engine, init_db
from oddsmith.providers.fixture_download import BY_KEY, COMPETITIONS, FixtureDownloadProvider


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--league", action="append", default=[])
    parser.add_argument("--ca-bundle")
    parser.add_argument("--write", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    unknown = [key for key in args.league if key not in BY_KEY]
    if unknown:
        print(f"ERROR: unknown league(s): {', '.join(unknown)}", file=sys.stderr)
        return 2
    competitions = [BY_KEY[key] for key in args.league] if args.league else COMPETITIONS
    if not args.write:
        print(
            f"Plan only: {len(competitions)} schedule downloads for season {args.season}: "
            f"{', '.join(item.key for item in competitions)}. Add --write."
        )
        return 0

    settings = get_settings()
    provider = FixtureDownloadProvider(
        ca_bundle=args.ca_bundle or settings.football_data_ca_bundle
    )
    init_db()
    inserted = updated = received = 0
    with Session(get_engine()) as session:
        for competition in competitions:
            fixtures = provider.fetch(competition, args.season)
            new, refreshed = upsert_scheduled_fixtures(session, fixtures)
            received += len(fixtures)
            inserted += new
            updated += refreshed
            print(
                f"{competition.key}: received={len(fixtures)} "
                f"inserted={new} updated={refreshed}"
            )
    print(f"Totals: received={received} inserted={inserted} updated={updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
