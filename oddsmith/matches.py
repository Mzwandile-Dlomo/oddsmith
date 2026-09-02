"""Persistent match catalogue and quota-aware API-Football resources."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session, select

from oddsmith.competitions import Competition, resolve_competition
from oddsmith.db import FootballMatch, MatchResource, get_session
from oddsmith.providers.api_football import ApiFootballProvider
from oddsmith.providers.base import ProviderError

router = APIRouter(tags=["matches"])


class MatchView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(validation_alias="provider_fixture_id")
    league_id: int
    league_name: str
    league_type: str | None
    country: str | None
    season: int
    round: str | None
    kickoff_utc: datetime
    status_long: str
    status_short: str
    elapsed: int | None
    home_team_id: int
    home_team: str
    away_team_id: int
    away_team: str
    home_goals: int | None
    away_goals: int | None
    venue: dict | None
    score: dict
    updated_at: datetime


class MatchDetailView(MatchView):
    details: list | dict | None = None


def get_match_provider() -> ApiFootballProvider:
    return ApiFootballProvider()


def _utc_naive(value: datetime) -> datetime:
    aware = value if value.tzinfo else value.replace(tzinfo=UTC)
    return aware.astimezone(UTC).replace(tzinfo=None)


def _competition(value: str | None) -> Competition | None:
    if value is None:
        return None
    try:
        return resolve_competition(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _find_match(session: Session, match_id: int) -> FootballMatch:
    match = session.exec(
        select(FootballMatch).where(FootballMatch.provider_fixture_id == match_id)
    ).first()
    if match is None:
        raise HTTPException(status_code=404, detail="match not found; run the fixture sync first")
    return match


def _cached_resource(session: Session, match_id: int, resource: str) -> MatchResource | None:
    return session.exec(
        select(MatchResource).where(
            MatchResource.resource_key == f"api_football:{match_id}:{resource}"
        )
    ).first()


async def _resource(
    session: Session,
    provider: ApiFootballProvider,
    match_id: int,
    resource: str,
    refresh: bool,
) -> list | dict:
    _find_match(session, match_id)
    cached = _cached_resource(session, match_id, resource)
    if cached is not None and not refresh:
        return cached.payload
    try:
        payload, _ = await provider.fixture_resource(match_id, resource)
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if cached is None:
        cached = MatchResource(
            resource_key=f"api_football:{match_id}:{resource}",
            provider_fixture_id=match_id,
            resource_type=resource,
            payload=payload,
        )
    else:
        cached.payload = payload
        cached.fetched_at = datetime.now(UTC).replace(tzinfo=None)
    session.add(cached)
    session.commit()
    return payload


@router.get("/matches/today", response_model=list[MatchView])
def matches_today(
    league: str | None = None,
    session: Session = Depends(get_session),
) -> list[FootballMatch]:
    today = datetime.now(UTC).date()
    return _list_matches(session, league=league, date_from=today, date_to=today)


@router.get("/matches/upcoming", response_model=list[MatchView])
def upcoming_matches(
    league: str | None = None,
    days: Annotated[int, Query(ge=1, le=90)] = 14,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    session: Session = Depends(get_session),
) -> list[FootballMatch]:
    now = datetime.now(UTC).replace(tzinfo=None)
    statement = select(FootballMatch).where(
        FootballMatch.kickoff_utc >= now,
        FootballMatch.kickoff_utc < now + timedelta(days=days),
    )
    competition = _competition(league)
    if competition:
        statement = statement.where(FootballMatch.league_id == competition.api_football_id)
    return list(session.exec(statement.order_by(FootballMatch.kickoff_utc).limit(limit)))


@router.get("/matches", response_model=list[MatchView])
def list_matches(
    season: int | None = Query(default=None, ge=2000, le=2100),
    league: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    status: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
    session: Session = Depends(get_session),
) -> list[FootballMatch]:
    return _list_matches(
        session,
        season=season,
        league=league,
        date_from=date_from,
        date_to=date_to,
        status=status,
        limit=limit,
    )


def _list_matches(
    session: Session,
    *,
    season: int | None = None,
    league: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    status: str | None = None,
    limit: int = 500,
) -> list[FootballMatch]:
    statement = select(FootballMatch)
    competition = _competition(league)
    if competition:
        statement = statement.where(FootballMatch.league_id == competition.api_football_id)
    if season is not None:
        statement = statement.where(FootballMatch.season == season)
    if date_from is not None:
        statement = statement.where(
            FootballMatch.kickoff_utc >= datetime.combine(date_from, time.min)
        )
    if date_to is not None:
        statement = statement.where(
            FootballMatch.kickoff_utc < datetime.combine(date_to + timedelta(days=1), time.min)
        )
    if status:
        statement = statement.where(FootballMatch.status_short == status.upper())
    return list(session.exec(statement.order_by(FootballMatch.kickoff_utc).limit(limit)))


@router.get("/matches/{match_id}", response_model=MatchDetailView)
def match_detail(match_id: int, session: Session = Depends(get_session)) -> MatchDetailView:
    match = _find_match(session, match_id)
    cached = _cached_resource(session, match_id, "details")
    view = MatchDetailView.model_validate(match)
    view.details = cached.payload if cached else match.raw_payload
    return view


@router.get("/teams/{team_id}/matches", response_model=list[MatchView])
def team_matches(
    team_id: int,
    season: int | None = Query(default=None, ge=2000, le=2100),
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    session: Session = Depends(get_session),
) -> list[FootballMatch]:
    statement = select(FootballMatch).where(
        (FootballMatch.home_team_id == team_id) | (FootballMatch.away_team_id == team_id)
    )
    if season is not None:
        statement = statement.where(FootballMatch.season == season)
    return list(session.exec(statement.order_by(FootballMatch.kickoff_utc.desc()).limit(limit)))


@router.get("/matches/{match_id}/statistics")
async def match_statistics(
    match_id: int,
    refresh: bool = False,
    session: Session = Depends(get_session),
    provider: ApiFootballProvider = Depends(get_match_provider),
) -> list | dict:
    return await _resource(session, provider, match_id, "statistics", refresh)


@router.get("/matches/{match_id}/odds")
async def match_odds(
    match_id: int,
    refresh: bool = False,
    session: Session = Depends(get_session),
    provider: ApiFootballProvider = Depends(get_match_provider),
) -> list | dict:
    return await _resource(session, provider, match_id, "odds", refresh)


@router.get("/predictions/{match_id}")
async def match_predictions(
    match_id: int,
    refresh: bool = False,
    session: Session = Depends(get_session),
    provider: ApiFootballProvider = Depends(get_match_provider),
) -> list | dict:
    return await _resource(session, provider, match_id, "predictions", refresh)
