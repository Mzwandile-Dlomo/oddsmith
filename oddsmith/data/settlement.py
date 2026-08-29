"""Link immutable odds snapshots to final match facts and settle outcomes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, select

from oddsmith.db import MatchObservation, OddsFixtureResult, OddsSnapshot
from oddsmith.models import MarketType
from oddsmith.textnorm import fold_accents

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_TEAM_NOISE = {"fc", "afc", "cf", "sc"}


@dataclass(frozen=True)
class SettlementRun:
    fixtures_scanned: int
    matched: int
    already_settled: int
    unmatched: int


def _team_key(name: str) -> str:
    tokens = _NON_ALNUM.sub(" ", fold_accents(name).lower()).split()
    return " ".join(token for token in tokens if token not in _TEAM_NOISE)


def _naive_utc(value: datetime) -> datetime:
    aware = value if value.tzinfo else value.replace(tzinfo=UTC)
    return aware.astimezone(UTC).replace(tzinfo=None)


def settle_from_match_observations(
    session: Session,
    *,
    now: datetime | None = None,
    kickoff_tolerance_hours: float = 12.0,
) -> SettlementRun:
    """Match completed snapshot fixtures to stored observations by teams/time."""
    if kickoff_tolerance_hours <= 0:
        raise ValueError("kickoff_tolerance_hours must be > 0")
    cutoff = _naive_utc(now or datetime.now(UTC))
    snapshot_fixtures = list(
        session.exec(
            select(
                OddsSnapshot.fixture_id,
                OddsSnapshot.kickoff_utc,
                OddsSnapshot.home_team,
                OddsSnapshot.away_team,
            )
            .where(OddsSnapshot.kickoff_utc < cutoff)
            .distinct()
        )
    )
    existing = set(session.exec(select(OddsFixtureResult.fixture_id)))
    observations = list(
        session.exec(
            select(
                MatchObservation.source_key,
                MatchObservation.source,
                MatchObservation.kickoff_utc,
                MatchObservation.home_team,
                MatchObservation.away_team,
                MatchObservation.home_goals,
                MatchObservation.away_goals,
                MatchObservation.home_corners,
                MatchObservation.away_corners,
            )
        )
    )
    by_teams: dict[tuple[str, str], list[tuple]] = {}
    for observation in observations:
        key = (_team_key(observation[3]), _team_key(observation[4]))
        by_teams.setdefault(key, []).append(observation)

    matched = already = 0
    tolerance = timedelta(hours=kickoff_tolerance_hours)
    for fixture_id, kickoff, home_team, away_team in snapshot_fixtures:
        if fixture_id in existing:
            already += 1
            continue
        candidates = by_teams.get((_team_key(home_team), _team_key(away_team)), [])
        closest = min(
            candidates,
            key=lambda row: abs(_naive_utc(row[2]) - _naive_utc(kickoff)),
            default=None,
        )
        if closest is None or abs(
            _naive_utc(closest[2]) - _naive_utc(kickoff)
        ) > tolerance:
            continue
        session.add(
            OddsFixtureResult(
                fixture_id=fixture_id,
                source=closest[1],
                source_key=closest[0],
                kickoff_utc=_naive_utc(kickoff),
                home_team=home_team,
                away_team=away_team,
                home_goals=closest[5],
                away_goals=closest[6],
                home_corners=closest[7],
                away_corners=closest[8],
            )
        )
        existing.add(fixture_id)
        matched += 1
    session.commit()
    return SettlementRun(
        fixtures_scanned=len(snapshot_fixtures),
        matched=matched,
        already_settled=already,
        unmatched=len(snapshot_fixtures) - matched - already,
    )


def snapshot_result(snapshot: OddsSnapshot, result: OddsFixtureResult) -> str | None:
    """Return won/lost/void for supported selections, or None if facts are missing."""
    if snapshot.market_type == MarketType.MATCH_WINNER.value:
        actual = (
            "Home"
            if result.home_goals > result.away_goals
            else "Draw"
            if result.home_goals == result.away_goals
            else "Away"
        )
        return "won" if snapshot.selection == actual else "lost"
    if snapshot.market_type == MarketType.BTTS.value:
        actual = "Yes" if result.home_goals > 0 and result.away_goals > 0 else "No"
        return "won" if snapshot.selection == actual else "lost"
    if snapshot.market_type in {
        MarketType.OVER_UNDER.value,
        MarketType.CORNER_TOTALS.value,
    }:
        if snapshot.point is None:
            return None
        if snapshot.market_type == MarketType.CORNER_TOTALS.value:
            if result.home_corners is None or result.away_corners is None:
                return None
            total = result.home_corners + result.away_corners
        else:
            total = result.home_goals + result.away_goals
        if total == snapshot.point:
            return "void"
        actual = "Over" if total > snapshot.point else "Under"
        return "won" if snapshot.selection == actual else "lost"
    return None
