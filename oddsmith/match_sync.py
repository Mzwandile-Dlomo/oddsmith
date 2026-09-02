"""Idempotent API-Football fixture synchronization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlmodel import Session, select

from oddsmith.competitions import Competition
from oddsmith.db import FootballMatch
from oddsmith.providers.api_football import ApiFootballProvider


@dataclass(frozen=True)
class SyncResult:
    competition: str
    received: int
    inserted: int
    updated: int
    requests_remaining: int | None


def _as_utc_naive(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).replace(tzinfo=None)


def _values(payload: dict) -> dict:
    fixture = payload.get("fixture") or {}
    league = payload.get("league") or {}
    teams = payload.get("teams") or {}
    home = teams.get("home") or {}
    away = teams.get("away") or {}
    goals = payload.get("goals") or {}
    status = fixture.get("status") or {}
    return {
        "provider_fixture_id": int(fixture["id"]),
        "league_id": int(league["id"]),
        "league_name": str(league.get("name") or "Unknown"),
        "league_type": league.get("type"),
        "country": league.get("country"),
        "season": int(league["season"]),
        "round": league.get("round"),
        "kickoff_utc": _as_utc_naive(fixture["date"]),
        "status_long": str(status.get("long") or "Unknown"),
        "status_short": str(status.get("short") or "TBD"),
        "elapsed": status.get("elapsed"),
        "home_team_id": int(home["id"]),
        "home_team": str(home.get("name") or "Unknown"),
        "away_team_id": int(away["id"]),
        "away_team": str(away.get("name") or "Unknown"),
        "home_goals": goals.get("home"),
        "away_goals": goals.get("away"),
        "venue": fixture.get("venue"),
        "score": payload.get("score") or {},
        "raw_payload": payload,
        "updated_at": datetime.now(UTC).replace(tzinfo=None),
    }


def upsert_fixtures(session: Session, payloads: list[dict]) -> tuple[int, int]:
    """Insert new fixtures and update mutable score/status data in place."""
    ids = [int(item["fixture"]["id"]) for item in payloads]
    existing = {
        match.provider_fixture_id: match
        for match in session.exec(
            select(FootballMatch).where(FootballMatch.provider_fixture_id.in_(ids))
        )
    } if ids else {}
    inserted = updated = 0
    for payload in payloads:
        values = _values(payload)
        match = existing.get(values["provider_fixture_id"])
        if match is None:
            session.add(FootballMatch(**values))
            inserted += 1
            continue
        for key, value in values.items():
            setattr(match, key, value)
        session.add(match)
        updated += 1
    session.commit()
    return inserted, updated


async def sync_competition(
    session: Session,
    provider: ApiFootballProvider,
    competition: Competition,
    season: int,
) -> SyncResult:
    payload, quota = await provider.league_fixtures(
        league_id=competition.api_football_id, season=season
    )
    if not isinstance(payload, list):
        raise ValueError("API-Football returned a non-list fixtures response")
    inserted, updated = upsert_fixtures(session, payload)
    return SyncResult(
        competition=competition.key,
        received=len(payload),
        inserted=inserted,
        updated=updated,
        requests_remaining=quota.requests_remaining,
    )
