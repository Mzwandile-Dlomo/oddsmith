"""Give stored API-Football results the unambiguous league labels new ones get.

API-Football names both Italy's and Brazil's top flight "Serie A", and results
were stored under that bare name, so the Leagues page merged the two. New rows
are labelled by ``league_label``; rows stored before then kept only the fixture
ID, so this tells Brazil from Italy by the clubs involved, using the clubs in
the Football-Data files for each country. It also prefixes MLS with its country
so old and new MLS rows share one label.

Example:
    uv run --active python scripts/relabel_api_football_leagues.py --write

Without --write it only reports what would change. Safe to re-run.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from sqlalchemy import update
from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oddsmith.db import MatchObservation, get_engine
from oddsmith.insights import club_key

SOURCE = "api_football_result"
RENAMES = {"Major League Soccer": "USA Major League Soccer"}


def _clubs(session: Session, leagues: list[str]) -> set[str]:
    clubs: set[str] = set()
    for home, away in session.exec(
        select(MatchObservation.home_team, MatchObservation.away_team).where(
            MatchObservation.source == "football_data", MatchObservation.league.in_(leagues)
        )
    ):
        clubs |= {club_key(home), club_key(away)}
    return clubs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="apply the new labels")
    args = parser.parse_args()

    with Session(get_engine()) as session:
        brazil = _clubs(session, ["Brazil"])
        italy = _clubs(session, ["SerieA", "SerieB"])
        rows = session.exec(
            select(
                MatchObservation.id,
                MatchObservation.league,
                MatchObservation.home_team,
                MatchObservation.away_team,
            ).where(
                MatchObservation.source == SOURCE,
                MatchObservation.league.in_(["Serie A", *RENAMES]),
            )
        ).all()

        updates, unresolved = [], []
        changes: Counter[tuple[str, str]] = Counter()
        for row_id, league, home, away in rows:
            label = RENAMES.get(league)
            if league == "Serie A":
                clubs = {club_key(home), club_key(away)}
                if clubs <= italy:
                    continue
                if clubs & brazil and not clubs & italy:
                    label = "Brazil Serie A"
                else:
                    unresolved.append(f"{home} v {away}")
                    continue
            updates.append({"id": row_id, "league": label})
            changes[(league, label)] += 1

        for (old, new), count in changes.items():
            print(f"{old} -> {new}: {count}")
        print(f"Unchanged: {len(rows) - len(updates) - len(unresolved)}")
        for match in unresolved:
            print(f"  unresolved, left as Serie A: {match}")

        if not args.write:
            print("Plan only. Add --write to apply.")
            return 0
        if updates:
            session.exec(update(MatchObservation), params=updates)
        session.commit()
    print("Applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
