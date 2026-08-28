"""Download and import full Football-Data seasons into Oddsmith.

Example — five major European leagues, two seasons:
    uv run --active python scripts/import_football_data.py \
      --season-code 2425 --season-code 2526 --write

Season codes use Football-Data's YYZZ convention. Imports are idempotent and
also populate the compact HistoricalMatch table used by the Poisson baseline.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx
from sqlmodel import Session, SQLModel, create_engine

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oddsmith.config import get_settings
from oddsmith.data.football_data import import_observations, parse_csv

BASE_URL = "https://www.football-data.co.uk/mmz4281/{season}/{division}.csv"
DEFAULT_DIVISIONS = ("E0", "D1", "SP1", "I1", "F1")


def _season_start(code: str) -> int:
    if len(code) != 4 or not code.isdigit():
        raise argparse.ArgumentTypeError("season code must look like 2425")
    year = int(code[:2])
    return 1900 + year if year >= 90 else 2000 + year


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season-code", action="append", required=True)
    parser.add_argument(
        "--divisions",
        default=",".join(DEFAULT_DIVISIONS),
        help="comma-separated Football-Data division codes",
    )
    parser.add_argument("--database-url", help="defaults to DATABASE_URL from .env")
    parser.add_argument(
        "--write",
        action="store_true",
        help="write to the configured database; without this flag the command is a dry run",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    divisions = [item.strip().upper() for item in args.divisions.split(",") if item.strip()]
    if not divisions:
        print("ERROR: at least one division is required", file=sys.stderr)
        return 2

    engine = create_engine(args.database_url or get_settings().database_url)
    if args.write:
        SQLModel.metadata.create_all(engine)

    totals = {"parsed": 0, "inserted": 0, "existing": 0, "baseline": 0, "rejected": 0}
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        for season_code in args.season_code:
            season = _season_start(season_code)
            for division in divisions:
                url = BASE_URL.format(season=season_code, division=division)
                response = client.get(url)
                response.raise_for_status()
                rows, rejected = parse_csv(response.text, season=season)
                if not args.write:
                    print(f"{season_code}/{division}: parsed={len(rows)} rejected={rejected}")
                    totals["parsed"] += len(rows)
                    totals["rejected"] += rejected
                    continue
                with Session(engine) as session:
                    result = import_observations(session, rows, rejected=rejected)
                print(
                    f"{season_code}/{division}: parsed={result.parsed} "
                    f"inserted={result.inserted} existing={result.existing} "
                    f"baseline={result.baseline_inserted} rejected={result.rejected}"
                )
                totals["parsed"] += result.parsed
                totals["inserted"] += result.inserted
                totals["existing"] += result.existing
                totals["baseline"] += result.baseline_inserted
                totals["rejected"] += result.rejected

    print("Totals: " + " ".join(f"{key}={value}" for key, value in totals.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
