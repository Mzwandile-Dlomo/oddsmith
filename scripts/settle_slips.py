"""Settle saved slip legs from fixture results already stored in the database.

The companion to settle_odds_snapshots.py, which stops at OddsFixtureResult and
never propagates to the tickets. Neither script calls a provider, so this is
safe to run often — it only settles what previous ingest runs already fetched.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlmodel import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oddsmith.data.settlement import settle_pending_slips
from oddsmith.db import get_engine, init_db


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    init_db()
    with Session(get_engine()) as session:
        run = settle_pending_slips(session)
    print(
        f"Settled {run.legs_settled} pending legs across "
        f"{run.slips_settled} newly decided slips."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
