"""Settle captured odds against completed MatchObservation rows."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlmodel import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oddsmith.data.settlement import settle_from_match_observations
from oddsmith.db import get_engine, init_db


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kickoff-tolerance-hours", type=float, default=12.0)
    args = parser.parse_args()
    init_db()
    with Session(get_engine()) as session:
        result = settle_from_match_observations(
            session, kickoff_tolerance_hours=args.kickoff_tolerance_hours
        )
    print(
        f"Scanned {result.fixtures_scanned} completed priced fixtures: "
        f"matched {result.matched}, already settled {result.already_settled}, "
        f"unmatched {result.unmatched}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
