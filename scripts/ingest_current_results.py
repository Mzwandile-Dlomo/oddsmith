"""Ingest completed priced fixtures and statistics, then settle their snapshots."""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oddsmith.data.settlement import (
    settle_from_match_observations,
    settle_pending_slips,
    settle_personal_pool_entries,
    team_key,
)
from oddsmith.db import MatchObservation, OddsFixtureResult, OddsSnapshot, get_engine, init_db
from oddsmith.providers.api_football import ApiFootballProvider, ApiFootballResult


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lookback-days", type=int, default=3, choices=range(1, 8))
    parser.add_argument("--max-requests", type=int, default=15, choices=range(1, 51))
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="list unresolved priced fixtures in plan mode",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="make API-Football requests, store results, and run settlement",
    )
    return parser


def _observation(result: ApiFootballResult) -> MatchObservation:
    return MatchObservation(
        source_key=f"api_football_result:{result.fixture_id}",
        source="api_football_result",
        league=result.league,
        season=result.season,
        kickoff_utc=result.kickoff_utc,
        home_team=result.home_team,
        away_team=result.away_team,
        home_goals=result.home_goals,
        away_goals=result.away_goals,
        home_shots=result.home_shots,
        away_shots=result.away_shots,
        home_shots_on_target=result.home_shots_on_target,
        away_shots_on_target=result.away_shots_on_target,
        home_corners=result.home_corners,
        away_corners=result.away_corners,
        home_fouls=result.home_fouls,
        away_fouls=result.away_fouls,
        home_yellow_cards=result.home_yellow_cards,
        away_yellow_cards=result.away_yellow_cards,
        home_red_cards=result.home_red_cards,
        away_red_cards=result.away_red_cards,
        raw_payload={"fixture_id": result.fixture_id},
    )


def _naive_utc(value: datetime) -> datetime:
    aware = value if value.tzinfo else value.replace(tzinfo=UTC)
    return aware.astimezone(UTC).replace(tzinfo=None)


async def _run() -> int:
    args = _parser().parse_args()
    init_db()
    now = datetime.now(UTC).replace(tzinfo=None)
    earliest = now - timedelta(days=args.lookback_days)
    with Session(get_engine()) as session:
        settled = set(session.exec(select(OddsFixtureResult.fixture_id)))
        priced = [
            row
            for row in session.exec(
                select(
                    OddsSnapshot.fixture_id,
                    OddsSnapshot.kickoff_utc,
                    OddsSnapshot.home_team,
                    OddsSnapshot.away_team,
                )
                .where(
                    OddsSnapshot.kickoff_utc >= earliest,
                    OddsSnapshot.kickoff_utc < now,
                )
                .distinct()
            )
            if row[0] not in settled
        ]
    dates = sorted({row[1].date() for row in priced}, reverse=True)
    worst_case = min(len(dates) + len(priced), args.max_requests)
    if not args.write:
        print(
            f"Plan only: {len(priced)} unresolved priced fixtures across {len(dates)} days; "
            f"at most {worst_case} of {args.max_requests} allowed requests. Add --write."
        )
        if args.verbose:
            for fixture_id, kickoff, home_team, away_team in sorted(
                priced, key=lambda row: row[1]
            ):
                print(
                    f"  {kickoff.isoformat()} | {home_team} vs {away_team} | {fixture_id}"
                )
        return 0

    provider = ApiFootballProvider()
    requests = inserted = stats_requests = 0
    daily_remaining: int | None = None
    minute_remaining: int | None = None
    rate_limited = False
    wanted: dict[tuple[str, str], list[tuple]] = {}
    for row in priced:
        key = (team_key(row[2]), team_key(row[3]))
        wanted.setdefault(key, []).append(row)
    collected: dict[str, ApiFootballResult] = {}
    completed_returned = 0
    for day in dates:
        if requests >= args.max_requests:
            break
        requests += 1
        try:
            results, quota = await provider.completed_results(day)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 429:
                raise
            rate_limited = True
            break
        daily_remaining = quota.requests_remaining
        minute_remaining = quota.minute_remaining
        completed_returned += len(results)
        for result in results:
            key = (team_key(result.home_team), team_key(result.away_team))
            candidates = wanted.get(key, [])
            priced_row = min(
                candidates,
                key=lambda row: abs(
                    _naive_utc(result.kickoff_utc) - _naive_utc(row[1])
                ),
                default=None,
            )
            if priced_row is None:
                continue
            kickoff_delta = abs(
                _naive_utc(result.kickoff_utc) - _naive_utc(priced_row[1])
            )
            if kickoff_delta > timedelta(hours=12):
                continue
            collected[result.fixture_id] = result
            if (
                requests < args.max_requests
                and (minute_remaining is None or minute_remaining > 0)
            ):
                requests += 1
                stats_requests += 1
                try:
                    result, quota = await provider.add_result_statistics(result)
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code != 429:
                        raise
                    rate_limited = True
                    minute_remaining = 0
                else:
                    daily_remaining = quota.requests_remaining
                    minute_remaining = quota.minute_remaining
            collected[result.fixture_id] = result

    with Session(get_engine()) as session:
        existing = set(session.exec(select(MatchObservation.source_key)))
        for result in collected.values():
            observation = _observation(result)
            if observation.source_key in existing:
                continue
            session.add(observation)
            existing.add(observation.source_key)
            inserted += 1
        session.commit()
        settlement = settle_from_match_observations(session)
        slip_settlement = settle_pending_slips(session)
        pool_settled = settle_personal_pool_entries(session)
    print(
        f"Used {requests}/{args.max_requests} requests ({stats_requests} statistics); "
        f"provider returned {completed_returned} finals; matched {len(collected)} priced "
        f"fixtures; inserted {inserted} results; settled {settlement.matched}; "
        f"settled {slip_settlement.legs_settled} paper legs across "
        f"{slip_settlement.slips_settled} tickets; "
        f"settled {pool_settled} personal-pool selections; "
        f"rate limited {'yes' if rate_limited else 'no'}; "
        f"daily requests remaining {daily_remaining if daily_remaining is not None else 'unknown'}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
