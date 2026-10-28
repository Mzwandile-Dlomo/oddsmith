"""Correct Football-Data kickoffs stored before times were read as UK local.

Football-Data publishes UK local times, and earlier imports stored them as UTC,
so every summer kickoff sits an hour late. This recomputes each row from the
Date and Time kept in its raw payload, renames source keys whose UTC date moved,
and carries the fix into the Poisson baseline and settled fixture results that
copied the old values.

Example:
    uv run --active python scripts/fix_football_data_kickoffs.py --write

Without --write it only reports what would change. Safe to re-run.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, update
from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oddsmith.data.football_data import _kickoff, _source_key
from oddsmith.db import HistoricalMatch, MatchObservation, OddsFixtureResult, get_engine


def _naive_utc(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="apply the corrections")
    args = parser.parse_args()

    with Session(get_engine()) as session:
        # Narrow columns only: hydrating every raw payload outlasts the pooler.
        rows = session.exec(
            select(
                MatchObservation.id,
                MatchObservation.source_key,
                MatchObservation.source_league_code,
                MatchObservation.league,
                MatchObservation.season,
                MatchObservation.kickoff_utc,
                MatchObservation.home_team,
                MatchObservation.away_team,
                MatchObservation.raw_payload["Date"].as_string(),
                MatchObservation.raw_payload["Time"].as_string(),
            ).where(MatchObservation.source == "football_data")
        ).all()
        keys = {row[1] for row in rows}
        baseline = {
            (league, season, _naive_utc(kickoff), home, away): match_id
            for match_id, league, season, kickoff, home, away in session.exec(
                select(
                    HistoricalMatch.id,
                    HistoricalMatch.league,
                    HistoricalMatch.season,
                    HistoricalMatch.kickoff_utc,
                    HistoricalMatch.home_team,
                    HistoricalMatch.away_team,
                )
            )
        }
        results: dict[str, list[tuple[int, datetime]]] = {}
        for result_id, source_key, kickoff in session.exec(
            select(
                OddsFixtureResult.id, OddsFixtureResult.source_key, OddsFixtureResult.kickoff_utc
            ).where(OddsFixtureResult.source == "football_data")
        ):
            results.setdefault(source_key, []).append((result_id, kickoff))

        shifted: Counter[str] = Counter()
        observation_updates, stale_ids, baseline_updates, result_updates = [], [], [], []
        renamed = 0
        for row_id, key, code, league, season, kickoff, home, away, raw_date, raw_time in rows:
            corrected = _kickoff({"Date": raw_date or "", "Time": raw_time or ""})
            if corrected is None:
                continue
            old, new = _naive_utc(kickoff), _naive_utc(corrected)
            if old == new:
                continue
            shifted[league] += 1
            new_key = _source_key(code or "unknown", season, corrected, home, away)

            match_id = baseline.get((league, season, old, home, away))
            if match_id is not None:
                baseline_updates.append({"id": match_id, "kickoff_utc": new})
            for result_id, result_kickoff in results.get(key, []):
                result_updates.append(
                    {
                        "id": result_id,
                        "source_key": new_key,
                        "kickoff_utc": new if _naive_utc(result_kickoff) == old else result_kickoff,
                    }
                )

            if new_key != key and new_key in keys:
                # A sync with the fixed parser already stored the corrected row.
                stale_ids.append(row_id)
                continue
            if new_key != key:
                keys.discard(key)
                keys.add(new_key)
                renamed += 1
            observation_updates.append({"id": row_id, "kickoff_utc": new, "source_key": new_key})

        print(f"Observations to shift: {sum(shifted.values())} of {len(rows)}")
        for league, count in shifted.most_common():
            print(f"  {league}: {count}")
        print(f"Source keys renamed (UTC date moved): {renamed}")
        print(f"Stale duplicates removed: {len(stale_ids)}")
        print(f"Baseline rows shifted: {len(baseline_updates)}")
        print(f"Settled fixture results updated: {len(result_updates)}")

        if not args.write:
            print("Plan only. Add --write to apply.")
            return 0
        if stale_ids:
            session.exec(delete(MatchObservation).where(MatchObservation.id.in_(stale_ids)))
        for model, updates in (
            (MatchObservation, observation_updates),
            (HistoricalMatch, baseline_updates),
            (OddsFixtureResult, result_updates),
        ):
            if updates:
                session.exec(update(model), params=updates)
        session.commit()
    print("Applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
