"""Sync Football-Data CSV seasons into Oddsmith's training and match tables.

Example:
    uv run --active python scripts/sync_football_data.py \
      --from-season 2012 --to-season 2026 --write

The year arguments are season starting years, inclusive. The default five
divisions are E0, D1, SP1, I1, and F1. Without --write this command only prints
the download plan and performs no network or database writes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oddsmith.config import get_settings
from oddsmith.data.football_data import (
    MAJOR_DIVISIONS,
    FootballDataCsvProvider,
    import_observations,
    season_code,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-season", type=int, default=2012)
    parser.add_argument("--to-season", type=int, default=2026)
    parser.add_argument(
        "--divisions",
        default=",".join(MAJOR_DIVISIONS),
        help="comma-separated Football-Data division codes",
    )
    parser.add_argument("--database-url", help="defaults to DATABASE_URL from .env")
    parser.add_argument(
        "--ca-bundle",
        help="additional trusted PEM root; defaults to FOOTBALL_DATA_CA_BUNDLE",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="download and persist data; otherwise only display the request plan",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.from_season > args.to_season:
        print("ERROR: --from-season must not be after --to-season", file=sys.stderr)
        return 2
    try:
        seasons = [season_code(year) for year in range(args.from_season, args.to_season + 1)]
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    divisions = [item.strip().upper() for item in args.divisions.split(",") if item.strip()]
    unsupported = [item for item in divisions if item not in MAJOR_DIVISIONS]
    if not divisions or unsupported:
        detail = f" unsupported: {', '.join(unsupported)}" if unsupported else ""
        print(f"ERROR: choose at least one supported division;{detail}", file=sys.stderr)
        return 2

    requests = len(seasons) * len(divisions)
    if not args.write:
        print(
            f"Plan only: {requests} CSV downloads for seasons {seasons[0]}–{seasons[-1]} "
            f"and divisions {', '.join(divisions)}. Add --write to synchronize."
        )
        return 0

    settings = get_settings()
    engine = create_engine(args.database_url or settings.database_url)
    SQLModel.metadata.create_all(engine)
    provider = FootballDataCsvProvider(
        ca_bundle=args.ca_bundle or settings.football_data_ca_bundle
    )
    totals = {
        "documents": 0,
        "observations_inserted": 0,
        "observations_existing": 0,
        "baseline_inserted": 0,
        "rejected": 0,
    }
    with Session(engine) as session:
        for code in seasons:
            for division in divisions:
                document = provider.fetch(season_code=code, division=division)
                observations = import_observations(
                    session,
                    document.observations,
                    rejected=document.rejected,
                )
                totals["documents"] += 1
                totals["observations_inserted"] += observations.inserted
                totals["observations_existing"] += observations.existing
                totals["baseline_inserted"] += observations.baseline_inserted
                totals["rejected"] += observations.rejected
                print(
                    f"{code}/{division}: parsed={observations.parsed} "
                    f"inserted={observations.inserted} "
                    f"existing={observations.existing} rejected={observations.rejected}"
                )
    print("Totals: " + " ".join(f"{key}={value}" for key, value in totals.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
