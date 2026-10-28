"""Sync Football-Data CSV seasons into Oddsmith's training and match tables.

Example:
    uv run --active python scripts/sync_football_data.py \
      --from-season 2012 --to-season 2026 --write

The year arguments are season starting years, inclusive. By default it syncs
the five major divisions (E0, D1, SP1, I1, F1), which also feed the Poisson
baseline, plus their second tiers and the calendar-year MLS, Brazil and
Argentina files, which only feed match observations (form, insights,
settlement). Calendar-year leagues are kept by kickoff date: season 2026 means
matches from 1 August 2026 to 31 July 2027. Without --write this command only
prints the download plan and performs no network or database writes.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oddsmith.config import get_settings
from oddsmith.data.football_data import (
    EXTRA_LEAGUES,
    MAJOR_DIVISIONS,
    SUPPORTED_DIVISIONS,
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
        default=",".join(SUPPORTED_DIVISIONS),
        help="comma-separated Football-Data division codes",
    )
    parser.add_argument(
        "--extra-leagues",
        default=",".join(EXTRA_LEAGUES),
        help="comma-separated calendar-year league files; empty to skip",
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
    unsupported = [item for item in divisions if item not in SUPPORTED_DIVISIONS]
    if not divisions or unsupported:
        detail = f" unsupported: {', '.join(unsupported)}" if unsupported else ""
        print(f"ERROR: choose at least one supported division;{detail}", file=sys.stderr)
        return 2
    extras = [item.strip().upper() for item in args.extra_leagues.split(",") if item.strip()]
    unsupported = [item for item in extras if item not in EXTRA_LEAGUES]
    if unsupported:
        print(f"ERROR: unsupported extra leagues: {', '.join(unsupported)}", file=sys.stderr)
        return 2
    kickoff_from = date(args.from_season, 8, 1)
    kickoff_to = date(args.to_season + 1, 7, 31)

    requests = len(seasons) * len(divisions) + len(extras)
    if not args.write:
        print(
            f"Plan only: {requests} CSV downloads for seasons {seasons[0]}–{seasons[-1]}, "
            f"divisions {', '.join(divisions)}"
            + (f" and {', '.join(extras)} from {kickoff_from} to {kickoff_to}" if extras else "")
            + ". Add --write to synchronize."
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
    documents = [
        (f"{code}/{division}", lambda c=code, d=division: provider.fetch(season_code=c, division=d))
        for code in seasons
        for division in divisions
    ] + [
        (
            code,
            lambda c=code: provider.fetch_extra(
                c, kickoff_from=kickoff_from, kickoff_to=kickoff_to
            ),
        )
        for code in extras
    ]
    with Session(engine) as session:
        for label, fetch in documents:
            document = fetch()
            observations = import_observations(
                session,
                document.observations,
                rejected=document.rejected,
                # Only the leagues the model was tuned on feed its training table.
                sync_poisson_baseline=document.division in MAJOR_DIVISIONS,
            )
            totals["documents"] += 1
            totals["observations_inserted"] += observations.inserted
            totals["observations_existing"] += observations.existing
            totals["baseline_inserted"] += observations.baseline_inserted
            totals["rejected"] += observations.rejected
            print(
                f"{label}: parsed={observations.parsed} "
                f"inserted={observations.inserted} "
                f"existing={observations.existing} rejected={observations.rejected}"
            )
    print("Totals: " + " ".join(f"{key}={value}" for key, value in totals.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
