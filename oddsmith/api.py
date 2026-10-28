"""FastAPI application: fixtures discovery + slip building/tracking.

Routes:
  GET   /health                     - liveness probe
  GET   /fixtures                   - list soccer fixtures in a date window (merged providers)
  GET   /fixtures/{fixture_id}/markets - markets for one fixture
  GET   /fixtures/{fixture_id}/insights - recent form, head-to-head, line hit rates
  GET   /acca/weekend               - auto-built value acca (long price, low strike rate)
  GET   /acca/daily                 - short-priced "banker" slip + Kelly stake sizing
  GET   /calendar                   - per-day fixture/slip/model summary (cache-only)
  POST  /slips                      - create a slip with legs (locks odds)
  GET   /slips                      - list slips for the default user
  GET   /slips/{slip_id}            - one slip with legs + computed odds/returns
  PATCH /slips/{slip_id}            - set stake/name and/or per-leg results, then re-settle
"""

from __future__ import annotations

import time as time_module
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, date as date_type, datetime, time, timedelta

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlmodel import Session, select

from oddsmith.config import get_settings
from oddsmith.db import (
    CachedFixture,
    CornerEvaluationSnapshot,
    DEFAULT_USER_ID,
    HistoricalMatch,
    MatchObservation,
    ModelEvaluationSnapshot,
    OddsSnapshot,
    OddsFixtureResult,
    PersonalPoolEntry,
    ScheduledFixture,
    Slip,
    SlipLeg,
    get_session,
    init_db,
)
from oddsmith.models import Fixture, MarketType
from oddsmith.providers.api_football import ApiFootballProvider
from oddsmith.providers.base import OddsProvider
from oddsmith.cache import find_cached_fixture, get_cached_fixtures, read_cached_fixtures
from oddsmith.data.schedules import read_scheduled_fixtures
from oddsmith.data.settlement import team_key
from oddsmith.providers.the_odds_api import TheOddsApiProvider
from oddsmith.odds_model.acca import Acca, Candidate, build_acca
from oddsmith.odds_model.backtest import backtest_1x2
from oddsmith.odds_model.poisson import MatchResult
from oddsmith.odds_model.service import (
    PoissonModelService,
    build_model_markets,
    train_from_db,
)
from oddsmith.odds_model.staking import build_staking_plan
from oddsmith.odds_model.target_acca import (
    MAX_PLAUSIBLE_EDGE,
    TargetAcca,
    build_target_acca,
)
from oddsmith.odds_model.value import ValuePick
from oddsmith.history import team_stats
from oddsmith.insights import MatchInsights, build_insights, club_key, load_insight_rows
from oddsmith.match_read import MatchReadView, get_match_read
from oddsmith.research import ResearchDay, research_card
from oddsmith.matches import router as matches_router
from oddsmith.slips import (
    LegInput,
    LegResult,
    SlipResult,
    combined_odds,
    potential_profit,
    potential_return,
    profit_loss,
    settle,
    settled_return,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Oddsmith", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(matches_router)


def get_providers() -> list[OddsProvider]:
    return [TheOddsApiProvider(), ApiFootballProvider()]


_model_service: PoissonModelService | None = None
_model_history_version: tuple[int, int | None] | None = None
_model_checked_at = 0.0
# The version check is a DB round trip (~200ms to Supabase), so a trained model
# is trusted for this long before we look for newly synced results.
MODEL_VERSION_CHECK_SECONDS = 300


def _history_version(session: Session) -> tuple[int, int | None]:
    """Changes whenever the sync jobs add results; one cheap query."""
    count, max_id = session.exec(
        select(func.count(HistoricalMatch.id), func.max(HistoricalMatch.id))
    ).one()
    return int(count), max_id


def get_model_service(session: Session = Depends(get_session)) -> PoissonModelService:
    """Train the odds model from stored history; retrain once the sync adds results."""
    global _model_service, _model_history_version, _model_checked_at
    now = time_module.monotonic()
    if _model_service is not None and now - _model_checked_at < MODEL_VERSION_CHECK_SECONDS:
        return _model_service
    version = _history_version(session)
    _model_checked_at = now
    if _model_service is None or version != _model_history_version:
        _model_service = train_from_db(session)
        _model_history_version = version
    return _model_service


def _enrich_with_model(fixtures: list[Fixture], service: PoissonModelService) -> None:
    if not service.is_trained():
        return
    for fixture in fixtures:
        fixture.model_markets = build_model_markets(fixture, service)


def _same_fixture(left: Fixture, right: Fixture) -> bool:
    """Match schedule and odds rows while tolerating common provider name noise."""
    left_time = left.kickoff_utc if left.kickoff_utc.tzinfo else left.kickoff_utc.replace(tzinfo=UTC)
    right_time = right.kickoff_utc if right.kickoff_utc.tzinfo else right.kickoff_utc.replace(tzinfo=UTC)
    if abs((left_time - right_time).total_seconds()) > 3 * 60 * 60:
        return False

    def compatible(first: str, second: str) -> bool:
        first_key, second_key = team_key(first), team_key(second)
        return first_key == second_key or first_key in second_key or second_key in first_key

    return compatible(left.home_team, right.home_team) and compatible(
        left.away_team, right.away_team
    )


def _merge_with_schedule(
    priced: list[Fixture], scheduled: list[Fixture]
) -> list[Fixture]:
    """Prefer priced provider rows and fill uncovered matches from the schedule."""
    merged = list(priced)
    for fixture in scheduled:
        if not any(_same_fixture(fixture, existing) for existing in priced):
            merged.append(fixture)
    return sorted(merged, key=lambda fixture: fixture.kickoff_utc)


# --------------------------------------------------------------------------- #
# Request / response schemas
# --------------------------------------------------------------------------- #


class LegCreate(BaseModel):
    fixture_id: str
    home_team: str
    away_team: str
    kickoff_utc: datetime
    league: str | None = None
    provider: str
    market_type: MarketType
    selection: str
    point: float | None = None
    price: float = Field(gt=1.0)


class SlipCreate(BaseModel):
    name: str | None = None
    stake: float = Field(default=0.0, ge=0.0)
    currency: str | None = None
    legs: list[LegCreate] = Field(min_length=1)


class LegUpdate(BaseModel):
    leg_id: int
    result: LegResult


class SlipUpdate(BaseModel):
    name: str | None = None
    stake: float | None = Field(default=None, ge=0.0)
    legs: list[LegUpdate] | None = None


class LegView(BaseModel):
    id: int
    fixture_id: str
    home_team: str
    away_team: str
    kickoff_utc: datetime
    league: str | None
    provider: str
    market_type: str
    selection: str
    point: float | None
    price: float
    result: LegResult


class SlipView(BaseModel):
    id: int
    name: str | None
    stake: float
    currency: str
    result: SlipResult
    created_at: datetime
    settled_at: datetime | None
    legs: list[LegView]
    combined_odds: float
    potential_return: float
    potential_profit: float
    payout: float
    profit_loss: float


class PersonalPoolEntryCreate(LegCreate):
    """A manual favourite. The category is derived from its market."""


class PersonalPoolEntryUpdate(BaseModel):
    result: LegResult


class PersonalPoolEntryView(LegView):
    pool: str
    created_at: datetime
    settled_at: datetime | None


class PersonalPoolSummaryView(BaseModel):
    pool: str
    label: str
    total: int
    pending: int
    won: int
    lost: int
    void: int
    win_rate: float | None


class PersonalPoolView(BaseModel):
    entries: list[PersonalPoolEntryView]
    summaries: list[PersonalPoolSummaryView]
    note: str


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/fixtures", response_model=list[Fixture])
async def list_fixtures(
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    markets: list[MarketType] | None = Query(default=None),
    refresh: bool = Query(default=False),
    model: bool = Query(default=False),
    providers: list[OddsProvider] = Depends(get_providers),
    session: Session = Depends(get_session),
) -> list[Fixture]:
    """Stored fixtures for the window. The scheduled sync jobs fill the DB.

    Browsing never spends provider quota; only an explicit ``refresh=true`` does.
    """
    start = date_from or datetime.now(UTC)
    end = date_to or (start + timedelta(days=3))
    if end < start:
        raise HTTPException(status_code=400, detail="date_to must be after date_from")
    if refresh:
        fixtures = await get_cached_fixtures(
            session,
            providers,
            date_from=start,
            date_to=end,
            markets=markets,
            force_refresh=True,
        )
    else:
        fixtures = read_cached_fixtures(session, date_from=start, date_to=end)
    scheduled = read_scheduled_fixtures(session, date_from=start, date_to=end)
    fixtures = _merge_with_schedule(fixtures, scheduled)
    if model:
        _enrich_with_model(fixtures, get_model_service(session))
    return fixtures


@app.get("/fixtures/{fixture_id}/markets", response_model=Fixture)
def fixture_markets(fixture_id: str, session: Session = Depends(get_session)) -> Fixture:
    """Stored markets for one fixture; never a provider call."""
    cached = find_cached_fixture(session, fixture_id)
    if cached is None:
        raise HTTPException(status_code=404, detail="fixture not found")
    return cached


def _stored_fixture(session: Session, fixture_id: str) -> Fixture:
    """A fixture from the odds cache, else the schedule; never a provider call."""
    fixture = find_cached_fixture(session, fixture_id)
    if fixture is not None:
        return fixture
    scheduled = session.exec(
        select(ScheduledFixture).where(ScheduledFixture.source_key == fixture_id)
    ).first()
    if scheduled is None:
        raise HTTPException(status_code=404, detail="fixture not found")
    return Fixture(
        id=scheduled.source_key,
        home_team=scheduled.home_team,
        away_team=scheduled.away_team,
        kickoff_utc=scheduled.kickoff_utc,
        league=scheduled.league_name,
        provider=scheduled.source,
    )


@app.get("/fixtures/{fixture_id}/insights", response_model=MatchInsights)
def fixture_insights(
    fixture_id: str,
    last: int = Query(default=5, ge=3, le=20),
    h2h: int = Query(default=10, ge=1, le=30),
    session: Session = Depends(get_session),
) -> MatchInsights:
    """Recent form, head-to-head and totals-line hit rates for one fixture.

    Cache/schedule reads only — this never spends provider quota.
    """
    fixture = _stored_fixture(session, fixture_id)
    rows = load_insight_rows(session, [fixture.home_team, fixture.away_team])
    return build_insights(
        fixture_id=fixture.id,
        home_team=fixture.home_team,
        away_team=fixture.away_team,
        kickoff_utc=fixture.kickoff_utc,
        rows=rows,
        markets=fixture.markets,
        last=last,
        h2h_limit=h2h,
    )


# Stored fixtures and results change only when the sync jobs run (every few
# hours), so a day's research is served from memory for a few minutes.
RESEARCH_CACHE_SECONDS = 300
_research_cache: dict[tuple[str, str], tuple[float, ResearchDay]] = {}


def _aware_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


@app.get("/research/day", response_model=ResearchDay)
def research_day(
    date_from: datetime = Query(...),
    date_to: datetime = Query(...),
    session: Session = Depends(get_session),
) -> ResearchDay:
    """Every stored fixture in the window with its form and graded angles.

    Reads the odds cache and the schedule only, so browsing days never spends
    provider quota. History for all clubs playing is loaded in one pass.
    """
    if date_to < date_from:
        raise HTTPException(status_code=400, detail="date_to must be after date_from")
    cache_key = (date_from.isoformat(), date_to.isoformat())
    cached = _research_cache.get(cache_key)
    if cached and time_module.monotonic() - cached[0] < RESEARCH_CACHE_SECONDS:
        return cached[1]

    fixtures = _merge_with_schedule(
        read_cached_fixtures(session, date_from=date_from, date_to=date_to),
        read_scheduled_fixtures(session, date_from=date_from, date_to=date_to),
    )
    # Both reads return whole UTC days; keep only the requested instants, so a
    # local day (e.g. SAST) does not pick up the previous UTC evening's matches.
    window_from, window_to = _aware_utc(date_from), _aware_utc(date_to)
    fixtures = [f for f in fixtures if window_from <= _aware_utc(f.kickoff_utc) <= window_to]
    rows = load_insight_rows(
        session, {name for f in fixtures for name in (f.home_team, f.away_team)}
    )
    # Each fixture only needs its two clubs' rows. Club resolution is exact-key,
    # so this subset yields the same insights as all rows at ~1/N of the work.
    by_club: dict[str, list[MatchObservation]] = defaultdict(list)
    for row in rows:
        by_club[club_key(row.home_team)].append(row)
        by_club[club_key(row.away_team)].append(row)
    cards = [
        research_card(
            fixture_id=f.id,
            league=f.league,
            kickoff_utc=f.kickoff_utc,
            priced=bool(f.markets),
            provider=f.provider,
            insights=build_insights(
                fixture_id=f.id,
                home_team=f.home_team,
                away_team=f.away_team,
                kickoff_utc=f.kickoff_utc,
                rows=by_club[club_key(f.home_team)] + by_club[club_key(f.away_team)],
                markets=f.markets,
            ),
        )
        for f in sorted(fixtures, key=lambda f: f.kickoff_utc)
    ]
    day = ResearchDay(
        date_from=date_from,
        date_to=date_to,
        leagues=sorted({c.league for c in cards if c.league}),
        cards=cards,
    )
    _research_cache[cache_key] = (time_module.monotonic(), day)
    return day


@app.get("/fixtures/{fixture_id}/read", response_model=MatchReadView)
async def fixture_read(
    fixture_id: str,
    session: Session = Depends(get_session),
) -> MatchReadView:
    """Computed angles plus Claude's cached written read of them."""
    fixture = _stored_fixture(session, fixture_id)
    insights = build_insights(
        fixture_id=fixture.id,
        home_team=fixture.home_team,
        away_team=fixture.away_team,
        kickoff_utc=fixture.kickoff_utc,
        rows=load_insight_rows(session, [fixture.home_team, fixture.away_team]),
        markets=fixture.markets,
    )
    settings = get_settings()
    return await get_match_read(
        session,
        fixture_id=fixture.id,
        league=fixture.league,
        kickoff_utc=fixture.kickoff_utc,
        insights=insights,
        api_key=settings.anthropic_api_key,
        model=settings.match_read_model,
    )


# --------------------------------------------------------------------------- #
# Model: value accas + honest backtest metrics
# --------------------------------------------------------------------------- #


class AccaLegView(BaseModel):
    fixture_id: str
    home_team: str
    away_team: str
    kickoff_utc: datetime | None = None
    league: str | None = None
    provider: str = ""
    market_type: str
    selection: str
    point: float | None = None
    offered_odds: float
    model_prob: float
    edge: float
    expected_value: float


class AccaView(BaseModel):
    legs: list[AccaLegView]
    combined_odds: float
    combined_model_prob: float
    combined_expected_value: float


class BacktestView(BaseModel):
    matches_scored: int
    hit_rate: float
    brier: float
    roi: float | None
    value_bets: int
    note: str


class DataCoverageView(BaseModel):
    key: str
    label: str
    records: int
    percent: float


class LeagueCoverageView(BaseModel):
    league: str
    matches: int
    date_from: datetime
    date_to: datetime


class MarketReadinessView(BaseModel):
    key: str
    label: str
    stage: str
    prediction_ready: bool
    roi_validated: bool
    training_rows: int
    odds_rows: int
    settled_rows: int
    note: str


class ModelReadinessView(BaseModel):
    model_name: str
    model_stage: str
    model_trained: bool
    dataset_matches: int
    baseline_matches: int
    leagues: int
    seasons: int
    date_from: datetime | None
    date_to: datetime | None
    freshness_days: int | None
    price_snapshots: int
    coverage: list[DataCoverageView]
    league_coverage: list[LeagueCoverageView]
    markets: list[MarketReadinessView]
    next_priorities: list[str]


class PaperPerformanceView(BaseModel):
    generated_tickets: int
    pending_tickets: int
    settled_tickets: int
    won_tickets: int
    lost_tickets: int
    win_rate: float | None
    average_odds: float | None
    unit_staked: float
    unit_returned: float
    unit_profit: float
    unit_roi: float | None
    tracking_target: int
    note: str


class ProbabilityMetricsView(BaseModel):
    matches: int
    accuracy: float
    log_loss: float
    brier: float
    calibration_error: float


class StrategyMetricsView(BaseModel):
    bets: int
    wins: int
    profit: float
    roi: float | None
    roi_ci_low: float | None
    roi_ci_high: float | None


class EvaluationSummaryView(BaseModel):
    model: ProbabilityMetricsView
    market: ProbabilityMetricsView
    strategy: StrategyMetricsView


class FoldEvaluationView(BaseModel):
    league: str
    test_season: int
    train_matches: int
    test_matches: int
    summary: EvaluationSummaryView


class LeagueEvaluationView(BaseModel):
    league: str
    seasons: int
    folds: list[FoldEvaluationView]
    summary: EvaluationSummaryView


class EvaluationReportView(BaseModel):
    generated_at: datetime
    model_name: str
    min_train_seasons: int
    min_edge: float
    max_edge: float
    leagues: list[LeagueEvaluationView]
    overall: EvaluationSummaryView


class CornerMetricsView(BaseModel):
    matches: int
    mean_actual: float
    mean_prediction: float
    mae: float
    rmse: float
    poisson_deviance: float


class CornerSummaryView(BaseModel):
    model: CornerMetricsView
    baseline: CornerMetricsView
    mae_improvement: float
    improvement_ci_low: float | None
    improvement_ci_high: float | None


class CornerFoldEvaluationView(BaseModel):
    league: str
    test_season: int
    train_matches: int
    test_matches: int
    summary: CornerSummaryView


class CornerLeagueEvaluationView(BaseModel):
    league: str
    seasons: int
    folds: list[CornerFoldEvaluationView]
    summary: CornerSummaryView


class CornerEvaluationReportView(BaseModel):
    generated_at: datetime
    model_name: str
    min_train_seasons: int
    leagues: list[CornerLeagueEvaluationView]
    overall: CornerSummaryView
    odds_rows: int
    roi_validated: bool
    limitation: str


class StakingView(BaseModel):
    bankroll: float
    full_kelly_fraction: float
    recommended_fraction: float
    recommended_stake: float
    growth_per_bet: float
    bets_to_double: float | None
    horizon_bets: int
    projected_bankroll: float
    prob_all_win_over_horizon: float
    expected_losses_over_horizon: float
    let_it_ride_bankroll: float
    note: str


class DailyAccaView(BaseModel):
    legs: list[AccaLegView]
    combined_odds: float
    combined_model_prob: float
    combined_expected_value: float
    target_odds: float
    target_met: bool
    pool_size: int
    model_trained: bool
    fixtures_scanned: int
    candidates_scanned: int
    markets_used: list[MarketType]
    execution_mode: str
    validation_model: str | None
    validation_status: str
    auto_tracked: bool = False
    staking: StakingView
    note: str


def _acca_to_view(acca: Acca, fixtures_by_id: dict[str, Fixture] | None = None) -> AccaView:
    lookup = fixtures_by_id or {}
    legs = []
    for leg in acca.legs:
        fixture = lookup.get(leg.fixture_id)
        legs.append(
            AccaLegView(
                fixture_id=leg.fixture_id,
                home_team=leg.home_team,
                away_team=leg.away_team,
                kickoff_utc=fixture.kickoff_utc if fixture else None,
                league=fixture.league if fixture else None,
                provider=fixture.provider if fixture else "",
                market_type=leg.market_type,
                selection=leg.pick.selection,
                point=leg.point,
                offered_odds=leg.pick.offered_odds,
                model_prob=leg.pick.model_prob,
                edge=leg.pick.edge,
                expected_value=leg.pick.expected_value,
            )
        )
    return AccaView(
        legs=legs,
        combined_odds=acca.combined_odds,
        combined_model_prob=acca.combined_model_prob,
        combined_expected_value=acca.combined_expected_value,
    )


@app.get("/acca/weekend", response_model=AccaView)
def weekend_acca(
    legs: int = Query(default=5, ge=1, le=10),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    session: Session = Depends(get_session),
) -> AccaView:
    """Auto-build an accumulator from the highest positive-EV model picks.

    Legs are the outcomes where our model's probability most exceeds the
    bookmaker's, one per fixture. This chases VALUE, not a guaranteed win — a
    multi-leg soccer acca still lands only single-digit percent of the time.
    """
    start = date_from or datetime.now(UTC)
    end = date_to or (start + timedelta(days=4))
    fixtures = read_cached_fixtures(session, date_from=start, date_to=end)
    service = get_model_service(session)
    _enrich_with_model(fixtures, service)

    candidates = _collect_candidates(fixtures)
    fixtures_by_id = {f.id: f for f in fixtures}
    return _acca_to_view(build_acca(candidates, legs=legs), fixtures_by_id)


def _collect_candidates(
    fixtures: list[Fixture],
    value_only: bool = True,
    markets: set[MarketType] | None = None,
) -> list[Candidate]:
    """Flatten model-priced fixtures into acca candidates, one per outcome.

    Only outcomes the model has both priced and compared against a bookmaker are
    usable, so anything missing an edge/EV is skipped regardless of ``value_only``.
    """
    candidates: list[Candidate] = []
    for fixture in fixtures:
        for mm in fixture.model_markets:
            if markets is not None and mm.type not in markets:
                continue
            for o in mm.outcomes:
                if o.edge is None or o.expected_value is None or not o.bookmaker_odds:
                    continue
                if value_only and not o.is_value:
                    continue
                pick = ValuePick(
                    selection=o.name,
                    offered_odds=o.bookmaker_odds,
                    model_prob=o.model_prob,
                    implied_prob=0.0,
                    edge=o.edge,
                    expected_value=o.expected_value,
                )
                candidates.append(
                    Candidate(
                        fixture_id=fixture.id,
                        home_team=fixture.home_team,
                        away_team=fixture.away_team,
                        market_type=mm.type.value,
                        pick=pick,
                        point=o.point,
                    )
                )
    return candidates


@app.get("/acca/daily", response_model=DailyAccaView)
def daily_acca(
    target_odds: float = Query(default=1.5, gt=1.0, le=20.0),
    max_legs: int = Query(default=4, ge=1, le=8),
    min_leg_prob: float = Query(default=0.55, ge=0.0, lt=1.0),
    require_value: bool = Query(default=True),
    max_edge: float = Query(default=MAX_PLAUSIBLE_EDGE, gt=0.0, le=1.0),
    bankroll: float = Query(default=100.0, gt=0.0),
    horizon_bets: int = Query(default=30, ge=1, le=365),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    markets: list[MarketType] | None = Query(default=None),
    auto_track: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> DailyAccaView:
    """Build today's short-priced "banker" slip and size the stake for it.

    Where ``/acca/weekend`` maximises value and accepts a long price, this builds
    the slip MOST LIKELY to land that still clears ``target_odds`` (1.5 by
    default) — the daily-compounding shape.

    The returned staking plan is the important half. Repeating a 1.5 slip while
    staking the whole bankroll goes to zero with probability 1; the plan sizes
    the bet by half-Kelly so the edge actually compounds instead.
    """
    start = date_from or datetime.now(UTC)
    end = date_to or (start + timedelta(days=1))
    if end < start:
        raise HTTPException(status_code=400, detail="date_to must be after date_from")

    supported_markets = {
        MarketType.MATCH_WINNER,
        MarketType.OVER_UNDER,
        MarketType.BTTS,
    }
    requested_markets = set(markets) if markets else supported_markets
    unsupported = requested_markets - supported_markets
    if unsupported:
        names = ", ".join(sorted(m.value for m in unsupported))
        raise HTTPException(
            status_code=422,
            detail=f"Markets not modelled for daily slips: {names}",
        )

    # Reads the board the sync jobs stored; the home page loads this on every
    # visit, so it must never spend provider quota.
    fixtures = read_cached_fixtures(session, date_from=start, date_to=end)
    service = get_model_service(session)
    _enrich_with_model(fixtures, service)
    candidates = _collect_candidates(
        fixtures,
        value_only=require_value,
        markets=requested_markets,
    )

    acca = build_target_acca(
        candidates,
        target_odds=target_odds,
        max_legs=max_legs,
        min_leg_prob=min_leg_prob,
        require_value=require_value,
        max_edge=max_edge,
    )

    plan = build_staking_plan(
        acca.combined_model_prob,
        acca.combined_odds,
        bankroll=bankroll,
        horizon_bets=horizon_bets,
    )
    promoted, validation_model, validation_status = _model_validation_gate(session)
    if not promoted:
        plan = replace(
            plan,
            recommended_fraction=0.0,
            recommended_stake=0.0,
            growth_per_bet=0.0,
            bets_to_double=None,
            projected_bankroll=round(bankroll, 2),
            note=(
                "Paper mode: automated staking is locked until an unseen-season model "
                "beats the bookmaker baseline and its 95% ROI lower bound is positive."
            ),
        )

    fixtures_by_id = {f.id: f for f in fixtures}
    view = _acca_to_view(acca, fixtures_by_id)
    daily_view = DailyAccaView(
        legs=view.legs,
        combined_odds=view.combined_odds,
        combined_model_prob=view.combined_model_prob,
        combined_expected_value=view.combined_expected_value,
        target_odds=target_odds,
        target_met=acca.target_met,
        pool_size=acca.pool_size,
        model_trained=service.is_trained(),
        fixtures_scanned=len(fixtures),
        candidates_scanned=len(candidates),
        markets_used=sorted(requested_markets, key=lambda m: m.value),
        execution_mode="live" if promoted else "paper",
        validation_model=validation_model,
        validation_status=validation_status,
        staking=StakingView(
            bankroll=plan.bankroll,
            full_kelly_fraction=plan.full_kelly_fraction,
            recommended_fraction=plan.recommended_fraction,
            recommended_stake=plan.recommended_stake,
            growth_per_bet=plan.growth_per_bet,
            bets_to_double=plan.bets_to_double,
            horizon_bets=plan.horizon_bets,
            projected_bankroll=plan.projected_bankroll,
            prob_all_win_over_horizon=plan.prob_all_win_over_horizon,
            expected_losses_over_horizon=plan.expected_losses_over_horizon,
            let_it_ride_bankroll=plan.let_it_ride_bankroll,
            note=plan.note,
        ),
        note=_daily_note(acca, model_trained=service.is_trained(), fixtures=len(fixtures)),
    )
    # The Today page requests this only for the untouched 1.50 daily strategy.
    # Its first valid prediction becomes an immutable paper observation; later
    # page loads retain that original price rather than replacing it with hindsight.
    if auto_track and _is_canonical_daily_request(
        target_odds=target_odds,
        max_legs=max_legs,
        min_leg_prob=min_leg_prob,
        require_value=require_value,
        max_edge=max_edge,
        markets=requested_markets,
    ):
        daily_view.auto_tracked = _archive_daily_paper_prediction(
            session, daily_view, prediction_day=start.date()
        )
    return daily_view


def _is_canonical_daily_request(
    *,
    target_odds: float,
    max_legs: int,
    min_leg_prob: float,
    require_value: bool,
    max_edge: float,
    markets: set[MarketType],
) -> bool:
    return (
        target_odds == 1.5
        and max_legs == 4
        and min_leg_prob == 0.55
        and require_value
        and max_edge == MAX_PLAUSIBLE_EDGE
        and markets == {MarketType.MATCH_WINNER, MarketType.OVER_UNDER, MarketType.BTTS}
    )


def _archive_daily_paper_prediction(
    session: Session, view: DailyAccaView, *, prediction_day: date_type
) -> bool:
    """Persist the first valid canonical daily prediction, once per UTC day."""
    if not view.legs or any(leg.kickoff_utc is None for leg in view.legs):
        return False
    name = f"Paper daily 1.50 · {prediction_day.isoformat()}"
    existing = session.exec(
        select(Slip).where(Slip.user_id == DEFAULT_USER_ID, Slip.name == name)
    ).first()
    if existing is not None:
        return True

    settings = get_settings()
    slip = Slip(
        user_id=DEFAULT_USER_ID,
        name=name,
        stake=0.0,
        currency=settings.default_currency,
        result=SlipResult.PENDING,
    )
    session.add(slip)
    session.commit()
    session.refresh(slip)
    session.add_all(
        [
            SlipLeg(
                slip_id=slip.id,
                fixture_id=leg.fixture_id,
                home_team=leg.home_team,
                away_team=leg.away_team,
                kickoff_utc=leg.kickoff_utc,
                league=leg.league,
                provider=leg.provider,
                market_type=leg.market_type,
                selection=leg.selection,
                point=leg.point,
                price=leg.offered_odds,
            )
            for leg in view.legs
        ]
    )
    session.commit()
    return True


def _model_validation_gate(session: Session) -> tuple[bool, str | None, str]:
    snapshot = session.exec(
        select(ModelEvaluationSnapshot).order_by(
            ModelEvaluationSnapshot.generated_at.desc()
        )
    ).first()
    if snapshot is None:
        return False, None, "No unseen-season validation has been published."
    try:
        overall = snapshot.payload["overall"]
        model = overall["model"]
        market = overall["market"]
        strategy = overall["strategy"]
        promoted = (
            model["log_loss"] < market["log_loss"]
            and model["brier"] < market["brier"]
            and model["calibration_error"] <= market["calibration_error"]
            and strategy["roi_ci_low"] is not None
            and strategy["roi_ci_low"] > 0
        )
    except (KeyError, TypeError):
        return False, snapshot.model_name, "Published validation payload is incomplete."
    if promoted:
        return True, snapshot.model_name, "Promotion gates passed on unseen seasons."
    return (
        False,
        snapshot.model_name,
        "Latest validation remains below the bookmaker baseline or lacks a positive ROI bound.",
    )


def _daily_note(acca: TargetAcca, *, model_trained: bool = True, fixtures: int = 1) -> str:
    if not model_trained:
        return (
            "The prediction model has no historical match data. Import training data "
            "before generating tickets; bookmaker odds alone are not a prediction model."
        )
    if fixtures == 0:
        return "No fixtures with bookmaker odds were found in today's window."
    if not acca.legs:
        return (
            "No selections today clear the model's value and confidence filters. "
            "An empty slip is a real answer — some days there is no bet worth making."
        )
    if not acca.target_met:
        return (
            f"Today's card could only reach {acca.combined_odds:.2f}, short of the "
            f"{acca.target_odds:.2f} target. Shown rather than padded with legs the "
            "model does not rate."
        )
    return (
        f"{len(acca.legs)} legs at {acca.combined_odds:.2f}, which the model rates at "
        f"{acca.combined_model_prob:.0%} to land. Stake the recommended fraction, not "
        "the whole bankroll."
    )


# The walk-forward refit takes ~40s and depends only on stored history, so the
# result is kept until the sync jobs add results (the history version changes).
_backtest_cache: dict[tuple[float, tuple[int, int | None]], BacktestView] = {}


@app.get("/model/backtest", response_model=BacktestView)
def model_backtest(
    train_fraction: float = Query(default=0.7, gt=0.0, lt=1.0),
    session: Session = Depends(get_session),
) -> BacktestView:
    """Honest walk-forward accuracy on stored history. Not a promise of 80%."""
    cache_key = (train_fraction, _history_version(session))
    cached = _backtest_cache.get(cache_key)
    if cached is not None:
        return cached
    settings = get_settings()
    rows = list(session.exec(select(HistoricalMatch).order_by(HistoricalMatch.kickoff_utc)))
    results = [MatchResult(r.home_team, r.away_team, r.home_goals, r.away_goals) for r in rows]
    bt = backtest_1x2(
        results,
        train_fraction=train_fraction,
        rho=settings.model_rho,
        decay=settings.model_decay,
        shrinkage=settings.model_shrinkage,
    )
    view = BacktestView(
        matches_scored=bt.matches_scored,
        hit_rate=bt.hit_rate,
        brier=bt.brier,
        roi=bt.roi,
        value_bets=bt.value_bets,
        note="1X2 walk-forward on historical results. ~54% is competitive; not 80%.",
    )
    _backtest_cache.clear()  # results for an older history version are never asked for again
    _backtest_cache[cache_key] = view
    return view


def _observation_count(session: Session, *conditions: object) -> int:
    query = select(func.count()).select_from(MatchObservation)
    if conditions:
        query = query.where(*conditions)
    return int(session.exec(query).one())


def _coverage(key: str, label: str, records: int, total: int) -> DataCoverageView:
    return DataCoverageView(
        key=key,
        label=label,
        records=records,
        percent=round(records / total * 100, 1) if total else 0.0,
    )


def _snapshot_fixture_count(session: Session, market_type: MarketType) -> int:
    return int(
        session.exec(
            select(func.count(func.distinct(OddsSnapshot.fixture_id))).where(
                OddsSnapshot.market_type == market_type.value
            )
        ).one()
    )


def _settled_snapshot_fixture_count(session: Session, market_type: MarketType) -> int:
    return int(
        session.exec(
            select(func.count(func.distinct(OddsSnapshot.fixture_id)))
            .join(
                OddsFixtureResult,
                OddsFixtureResult.fixture_id == OddsSnapshot.fixture_id,
            )
            .where(OddsSnapshot.market_type == market_type.value)
        ).one()
    )


# Readiness is ~17 aggregate queries (~10s over the Supabase link) and its inputs
# change only when the sync jobs run, so it is served from memory for a while.
READINESS_CACHE_SECONDS = 300
_readiness_cache: dict[str, tuple[float, ModelReadinessView]] = {}


@app.get("/model/readiness", response_model=ModelReadinessView)
def model_readiness(session: Session = Depends(get_session)) -> ModelReadinessView:
    """Expose evidence and gaps behind the model, not a cosmetic "AI ready" flag."""
    cached = _readiness_cache.get("latest")
    if cached and time_module.monotonic() - cached[0] < READINESS_CACHE_SECONDS:
        return cached[1]
    view = _build_model_readiness(session)
    _readiness_cache["latest"] = (time_module.monotonic(), view)
    return view


def _build_model_readiness(session: Session) -> ModelReadinessView:
    total = _observation_count(session)
    baseline_total = int(session.exec(select(func.count()).select_from(HistoricalMatch)).one())
    summary = session.exec(
        select(
            func.count(func.distinct(MatchObservation.league)),
            func.count(func.distinct(MatchObservation.season)),
            func.min(MatchObservation.kickoff_utc),
            func.max(MatchObservation.kickoff_utc),
        )
    ).one()
    league_count, season_count, date_from, date_to = summary

    corners = _observation_count(
        session,
        MatchObservation.home_corners.is_not(None),
        MatchObservation.away_corners.is_not(None),
    )
    shots = _observation_count(
        session,
        MatchObservation.home_shots.is_not(None),
        MatchObservation.away_shots.is_not(None),
    )
    odds_1x2 = _observation_count(
        session,
        MatchObservation.close_home_odds.is_not(None),
        MatchObservation.close_draw_odds.is_not(None),
        MatchObservation.close_away_odds.is_not(None),
    )
    odds_goals = _observation_count(
        session,
        MatchObservation.close_over_2_5_odds.is_not(None),
        MatchObservation.close_under_2_5_odds.is_not(None),
    )
    cards = _observation_count(
        session,
        MatchObservation.home_yellow_cards.is_not(None),
        MatchObservation.away_yellow_cards.is_not(None),
    )
    price_snapshots = int(
        session.exec(select(func.count()).select_from(OddsSnapshot)).one()
    )
    btts_price_fixtures = _snapshot_fixture_count(session, MarketType.BTTS)
    corner_price_fixtures = _snapshot_fixture_count(
        session, MarketType.CORNER_TOTALS
    )
    settled_1x2 = _settled_snapshot_fixture_count(session, MarketType.MATCH_WINNER)
    settled_goals = _settled_snapshot_fixture_count(session, MarketType.OVER_UNDER)
    settled_btts = _settled_snapshot_fixture_count(session, MarketType.BTTS)
    settled_corners = _settled_snapshot_fixture_count(
        session, MarketType.CORNER_TOTALS
    )
    corner_evaluation = session.exec(
        select(CornerEvaluationSnapshot).order_by(
            CornerEvaluationSnapshot.generated_at.desc()
        )
    ).first()

    league_rows = session.exec(
        select(
            MatchObservation.league,
            func.count(MatchObservation.id),
            func.min(MatchObservation.kickoff_utc),
            func.max(MatchObservation.kickoff_utc),
        )
        .group_by(MatchObservation.league)
        .order_by(MatchObservation.league)
    ).all()
    league_coverage = [
        LeagueCoverageView(
            league=league,
            matches=int(matches),
            date_from=first,
            date_to=last,
        )
        for league, matches, first, last in league_rows
    ]

    latest = date_to
    if latest is not None and latest.tzinfo is None:
        latest = latest.replace(tzinfo=UTC)
    freshness_days = max((datetime.now(UTC) - latest).days, 0) if latest else None

    return ModelReadinessView(
        model_name="Dixon-Coles Poisson",
        model_stage="research_baseline",
        model_trained=baseline_total > 0,
        dataset_matches=total,
        baseline_matches=baseline_total,
        leagues=int(league_count or 0),
        seasons=int(season_count or 0),
        date_from=date_from,
        date_to=date_to,
        freshness_days=freshness_days,
        price_snapshots=price_snapshots,
        coverage=[
            _coverage("results", "Match results", total, total),
            _coverage("corners", "Corner outcomes", corners, total),
            _coverage("shots", "Shot statistics", shots, total),
            _coverage("cards", "Card statistics", cards, total),
            _coverage("odds_1x2", "Closing 1X2 prices", odds_1x2, total),
            _coverage("odds_goals", "Closing O/U 2.5 prices", odds_goals, total),
            _coverage(
                "odds_btts", "Captured BTTS price fixtures", btts_price_fixtures, total
            ),
            _coverage(
                "odds_corners",
                "Captured corner-price fixtures",
                corner_price_fixtures,
                total,
            ),
        ],
        league_coverage=league_coverage,
        markets=[
            MarketReadinessView(
                key="match_winner",
                label="Match winner (1X2)",
                stage="baseline",
                prediction_ready=baseline_total > 0,
                roi_validated=False,
                training_rows=total,
                odds_rows=odds_1x2,
                settled_rows=settled_1x2,
                note=(
                    "Poisson is live; the calibrated challenger improved it but remains below "
                    "the closing-market baseline."
                ),
            ),
            MarketReadinessView(
                key="over_under",
                label="Goals O/U 2.5",
                stage="baseline",
                prediction_ready=baseline_total > 0,
                roi_validated=False,
                training_rows=total,
                odds_rows=odds_goals,
                settled_rows=settled_goals,
                note="Outcome coverage is complete, but historical price coverage is partial.",
            ),
            MarketReadinessView(
                key="btts",
                label="Both teams to score",
                stage="research",
                prediction_ready=baseline_total > 0,
                roi_validated=False,
                training_rows=total,
                odds_rows=btts_price_fixtures,
                settled_rows=settled_btts,
                note=(
                    f"BTTS snapshots are accumulating; {settled_btts} priced fixtures are "
                    "settled, and ROI remains blocked until the sample is meaningful."
                    if btts_price_fixtures
                    else "Probabilities can be modelled; historical BTTS prices are missing "
                    "for ROI."
                ),
            ),
            MarketReadinessView(
                key="corners",
                label="Corner totals",
                stage="research" if corner_evaluation is not None else "blocked",
                prediction_ready=corner_evaluation is not None,
                roi_validated=False,
                training_rows=corners,
                odds_rows=corner_price_fixtures,
                settled_rows=settled_corners,
                note=(
                    f"Count accuracy is walk-forward tested; {settled_corners} priced fixtures "
                    "are settled, and ROI needs a meaningful sample."
                    if corner_price_fixtures
                    else "Count accuracy is walk-forward tested; historical corner prices are "
                    "still missing, so ROI cannot be estimated."
                    if corner_evaluation is not None
                    else "Outcome data is strong; a count model and historical corner prices "
                    "are missing."
                ),
            ),
        ],
        next_priorities=[
            "Develop a market-residual 1X2 challenger without tuning on the final test fold.",
            "Schedule the capped BTTS/corner collector and accumulate settled price history.",
            "Ingest 2026/27 fixtures, lineups, injuries, and timestamped prices continuously.",
            "Run 1X2 and corner models in shadow mode before promotion or automated staking.",
        ],
    )


@app.get("/model/paper-performance", response_model=PaperPerformanceView)
def paper_performance(session: Session = Depends(get_session)) -> PaperPerformanceView:
    """Report generated paper tickets at a comparable one-unit stake."""
    paper_slips = list(
        session.exec(
            select(Slip)
            .where(Slip.name.like("Paper %"))
            .order_by(Slip.created_at)
        )
    )
    settled = [slip for slip in paper_slips if slip.result is not SlipResult.PENDING]
    won = [slip for slip in settled if slip.result is SlipResult.WON]
    returned = 0.0
    settled_odds: list[float] = []
    legs_by_slip = _load_legs_by_slip(session, settled)
    for slip in settled:
        legs = legs_by_slip.get(slip.id or 0, [])
        inputs = _leg_inputs(legs)
        returned += settled_return(1.0, inputs)
        settled_odds.append(combined_odds([leg.price for leg in legs]))

    staked = float(len(settled))
    profit = returned - staked
    target = 100
    return PaperPerformanceView(
        generated_tickets=len(paper_slips),
        pending_tickets=len(paper_slips) - len(settled),
        settled_tickets=len(settled),
        won_tickets=len(won),
        lost_tickets=len(settled) - len(won),
        win_rate=round(len(won) / len(settled), 4) if settled else None,
        average_odds=(
            round(sum(settled_odds) / len(settled_odds), 4)
            if settled_odds
            else None
        ),
        unit_staked=staked,
        unit_returned=round(returned, 4),
        unit_profit=round(profit, 4),
        unit_roi=round(profit / staked, 4) if staked else None,
        tracking_target=target,
        note=(
            "No generated paper tickets are settled yet. Save the daily paper ticket and "
            "let result ingestion settle it automatically."
            if not settled
            else f"Tracking only: {len(settled)} of {target} standardized one-unit paper "
            "tickets are settled. This sample does not unlock real-money staking."
        ),
    )


@app.get("/model/evaluation/latest", response_model=EvaluationReportView)
def latest_model_evaluation(
    session: Session = Depends(get_session),
) -> EvaluationReportView:
    snapshot = session.exec(
        select(ModelEvaluationSnapshot).order_by(
            ModelEvaluationSnapshot.generated_at.desc()
        )
    ).first()
    if snapshot is None:
        raise HTTPException(status_code=404, detail="no published model evaluation")
    return EvaluationReportView.model_validate(snapshot.payload)


@app.get("/model/corners/evaluation/latest", response_model=CornerEvaluationReportView)
def latest_corner_evaluation(
    session: Session = Depends(get_session),
) -> CornerEvaluationReportView:
    snapshot = session.exec(
        select(CornerEvaluationSnapshot).order_by(
            CornerEvaluationSnapshot.generated_at.desc()
        )
    ).first()
    if snapshot is None:
        raise HTTPException(status_code=404, detail="no published corner evaluation")
    return CornerEvaluationReportView.model_validate(snapshot.payload)


# --------------------------------------------------------------------------- #
# History: past results + derived team stats
# --------------------------------------------------------------------------- #


class HistoryMatchView(BaseModel):
    id: int
    league: str
    season: int
    kickoff_utc: datetime
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int


def _history_match_rows(
    session: Session,
    *,
    league: str | None = None,
    season: int | None = None,
    team: str | None = None,
    newest: int | None = None,
) -> list[HistoryMatchView]:
    """Combine long-run CSV history with recently ingested cup/live results.

    Football-Data supplies the five domestic leagues, while Champions League and
    Europa League results arrive through ``MatchObservation``.  The Results UI
    must see both sources.  Prefer an observation when both describe the same
    fixture because it is the newer, richer source row.
    """
    # Filters run in SQL, and only the columns the view needs are selected:
    # MatchObservation carries a large raw_payload per row, and hydrating ~50k
    # full rows over the Supabase link took minutes.
    def _query(table):
        query = select(
            table.id,
            table.league,
            table.season,
            table.kickoff_utc,
            table.home_team,
            table.away_team,
            table.home_goals,
            table.away_goals,
        )
        if league is not None:
            query = query.where(table.league == league)
        if season is not None:
            query = query.where(table.season == season)
        if team is not None:
            query = query.where(or_(table.home_team == team, table.away_team == team))
        if newest is not None:
            # De-duplication only removes rows, so the newest N of the merged
            # result always lie within the newest N of each source.
            query = query.order_by(table.kickoff_utc.desc()).limit(newest)
        return query

    rows: dict[tuple[str, datetime, str, str], HistoryMatchView] = {}
    for match in session.exec(_query(HistoricalMatch)):
        key = (match.league, match.kickoff_utc, match.home_team, match.away_team)
        rows[key] = HistoryMatchView(
            id=match.id or 0,
            league=match.league,
            season=match.season,
            kickoff_utc=match.kickoff_utc,
            home_team=match.home_team,
            away_team=match.away_team,
            home_goals=match.home_goals,
            away_goals=match.away_goals,
        )
    for match in session.exec(_query(MatchObservation)):
        key = (match.league, match.kickoff_utc, match.home_team, match.away_team)
        rows[key] = HistoryMatchView(
            # Keep IDs unambiguous when a browser renders mixed source rows.
            id=-(match.id or 1),
            league=match.league,
            season=match.season,
            kickoff_utc=match.kickoff_utc,
            home_team=match.home_team,
            away_team=match.away_team,
            home_goals=match.home_goals,
            away_goals=match.away_goals,
        )
    return sorted(rows.values(), key=lambda match: match.kickoff_utc, reverse=True)


class TeamStatsView(BaseModel):
    team: str
    played: int
    won: int
    drawn: int
    lost: int
    points: int
    goals_for: int
    goals_against: int
    goal_difference: int
    home_record: str
    away_record: str
    form: list[str]


@app.get("/history/leagues", response_model=list[str])
def history_leagues(session: Session = Depends(get_session)) -> list[str]:
    return sorted(
        set(session.exec(select(HistoricalMatch.league).distinct()))
        | set(session.exec(select(MatchObservation.league).distinct()))
    )


@app.get("/history/matches", response_model=list[HistoryMatchView])
def history_matches(
    league: str | None = Query(default=None),
    team: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> list[HistoryMatchView]:
    rows = _history_match_rows(
        session, league=league or None, team=team or None, newest=offset + limit
    )
    return rows[offset : offset + limit]


@app.get("/history/teams/{team}/stats", response_model=TeamStatsView)
def history_team_stats(
    team: str,
    league: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> TeamStatsView:
    rows = _history_match_rows(session, league=league, team=team)
    rows.sort(key=lambda row: row.kickoff_utc)
    if not rows:
        raise HTTPException(status_code=404, detail="team not found in history")

    results = [
        MatchResult(r.home_team, r.away_team, r.home_goals, r.away_goals) for r in rows
    ]
    s = team_stats(team, results)
    return TeamStatsView(
        team=s.team,
        played=s.played,
        won=s.won,
        drawn=s.drawn,
        lost=s.lost,
        points=s.points,
        goals_for=s.goals_for,
        goals_against=s.goals_against,
        goal_difference=s.goal_difference,
        home_record=f"{s.home_won}-{s.home_drawn}-{s.home_lost}",
        away_record=f"{s.away_won}-{s.away_drawn}-{s.away_lost}",
        form=s.form,
    )


class LeagueTableView(BaseModel):
    league: str
    season: int
    seasons: list[int]  # newest first, for a season picker
    rows: list[TeamStatsView]  # ranked by points, goal difference, goals for


@app.get("/history/table", response_model=LeagueTableView)
def history_table(
    league: str = Query(...),
    season: int | None = Query(default=None),
    session: Session = Depends(get_session),
) -> LeagueTableView:
    """Standings computed from stored results; defaults to the league's latest season."""
    seasons = sorted(
        set(session.exec(select(HistoricalMatch.season).where(HistoricalMatch.league == league)))
        | set(
            session.exec(select(MatchObservation.season).where(MatchObservation.league == league))
        ),
        reverse=True,
    )
    if not seasons:
        raise HTTPException(status_code=404, detail="league not found in history")
    chosen = seasons[0] if season is None else season
    if chosen not in seasons:
        raise HTTPException(status_code=404, detail="season not found for league")

    rows = _history_match_rows(session, league=league, season=chosen)
    rows.sort(key=lambda row: row.kickoff_utc)
    results = [
        MatchResult(r.home_team, r.away_team, r.home_goals, r.away_goals) for r in rows
    ]
    teams = {r.home_team for r in rows} | {r.away_team for r in rows}
    table = []
    for team in teams:
        s = team_stats(team, results)
        table.append(
            TeamStatsView(
                team=s.team,
                played=s.played,
                won=s.won,
                drawn=s.drawn,
                lost=s.lost,
                points=s.points,
                goals_for=s.goals_for,
                goals_against=s.goals_against,
                goal_difference=s.goal_difference,
                home_record=f"{s.home_won}-{s.home_drawn}-{s.home_lost}",
                away_record=f"{s.away_won}-{s.away_drawn}-{s.away_lost}",
                form=s.form,
            )
        )
    table.sort(key=lambda t: (-t.points, -t.goal_difference, -t.goals_for, t.team))
    return LeagueTableView(league=league, season=chosen, seasons=seasons, rows=table)


# --------------------------------------------------------------------------- #
# Slips
# --------------------------------------------------------------------------- #


def _leg_inputs(legs: list[SlipLeg]) -> list[LegInput]:
    return [LegInput(price=leg.price, result=leg.result) for leg in legs]


def _to_slip_view(slip: Slip, legs: list[SlipLeg]) -> SlipView:
    inputs = _leg_inputs(legs)
    prices = [leg.price for leg in legs]
    return SlipView(
        id=slip.id or 0,
        name=slip.name,
        stake=slip.stake,
        currency=slip.currency,
        result=slip.result,
        created_at=slip.created_at,
        settled_at=slip.settled_at,
        legs=[LegView(**leg.model_dump()) for leg in legs],
        combined_odds=round(combined_odds(prices), 4),
        potential_return=potential_return(slip.stake, prices),
        potential_profit=potential_profit(slip.stake, prices),
        payout=settled_return(slip.stake, inputs),
        profit_loss=profit_loss(slip.stake, inputs),
    )


def _load_legs(session: Session, slip_id: int) -> list[SlipLeg]:
    return list(session.exec(select(SlipLeg).where(SlipLeg.slip_id == slip_id)))


def _load_legs_by_slip(session: Session, slips: list[Slip]) -> dict[int, list[SlipLeg]]:
    """Every leg for many slips in one query; a query per slip costs a round trip each."""
    ids = [slip.id for slip in slips if slip.id is not None]
    legs: dict[int, list[SlipLeg]] = {slip_id: [] for slip_id in ids}
    if ids:
        for leg in session.exec(select(SlipLeg).where(SlipLeg.slip_id.in_(ids))):
            legs[leg.slip_id].append(leg)
    return legs


@app.post("/slips", response_model=SlipView, status_code=201)
def create_slip(payload: SlipCreate, session: Session = Depends(get_session)) -> SlipView:
    settings = get_settings()
    slip = Slip(
        user_id=DEFAULT_USER_ID,
        name=payload.name,
        stake=payload.stake,
        currency=payload.currency or settings.default_currency,
        result=SlipResult.PENDING,
    )
    session.add(slip)
    session.commit()
    session.refresh(slip)

    legs = [
        SlipLeg(
            slip_id=slip.id,
            fixture_id=leg.fixture_id,
            home_team=leg.home_team,
            away_team=leg.away_team,
            kickoff_utc=leg.kickoff_utc,
            league=leg.league,
            provider=leg.provider,
            market_type=leg.market_type.value,
            selection=leg.selection,
            point=leg.point,
            price=leg.price,
        )
        for leg in payload.legs
    ]
    session.add_all(legs)
    session.commit()
    for leg in legs:
        session.refresh(leg)

    return _to_slip_view(slip, legs)


@app.get("/slips", response_model=list[SlipView])
def list_slips(session: Session = Depends(get_session)) -> list[SlipView]:
    slips = list(
        session.exec(
            select(Slip).where(Slip.user_id == DEFAULT_USER_ID).order_by(Slip.created_at.desc())
        )
    )
    legs = _load_legs_by_slip(session, slips)
    return [_to_slip_view(slip, legs.get(slip.id or 0, [])) for slip in slips]


@app.get("/slips/{slip_id}", response_model=SlipView)
def get_slip(slip_id: int, session: Session = Depends(get_session)) -> SlipView:
    slip = session.get(Slip, slip_id)
    if slip is None:
        raise HTTPException(status_code=404, detail="slip not found")
    return _to_slip_view(slip, _load_legs(session, slip_id))


@app.patch("/slips/{slip_id}", response_model=SlipView)
def update_slip(
    slip_id: int, payload: SlipUpdate, session: Session = Depends(get_session)
) -> SlipView:
    slip = session.get(Slip, slip_id)
    if slip is None:
        raise HTTPException(status_code=404, detail="slip not found")

    if payload.name is not None:
        slip.name = payload.name
    if payload.stake is not None:
        slip.stake = payload.stake

    legs = _load_legs(session, slip_id)
    if payload.legs:
        by_id = {leg.id: leg for leg in legs}
        for update in payload.legs:
            leg = by_id.get(update.leg_id)
            if leg is None:
                raise HTTPException(
                    status_code=404, detail=f"leg {update.leg_id} not on this slip"
                )
            leg.result = update.result
            session.add(leg)

    slip.result = settle(_leg_inputs(legs))
    # settled_at records when the slip *first* became decided. Legs can still be
    # filled in afterwards (an acca is LOST from one lost leg while its other
    # legs wait on a result), and recording those must not rewrite the date.
    if slip.result is SlipResult.PENDING:
        slip.settled_at = None
    elif slip.settled_at is None:
        slip.settled_at = datetime.now(UTC)
    session.add(slip)
    session.commit()

    legs = _load_legs(session, slip_id)
    session.refresh(slip)
    return _to_slip_view(slip, legs)


# --------------------------------------------------------------------------- #
# Personal favourable pools
# --------------------------------------------------------------------------- #


def _personal_pool_for(leg: PersonalPoolEntryCreate) -> str:
    """Keep personal buckets narrowly scoped and unambiguous."""
    if leg.market_type is MarketType.MATCH_WINNER and leg.selection in {"Home", "Away"}:
        return "straight_win"
    if leg.market_type is MarketType.CORNER_TOTALS:
        return "corners"
    raise HTTPException(
        status_code=422,
        detail="Personal pools support only a Home/Away straight win or a corner total.",
    )


def _to_personal_pool_entry_view(entry: PersonalPoolEntry) -> PersonalPoolEntryView:
    return PersonalPoolEntryView(
        id=entry.id or 0,
        fixture_id=entry.fixture_id,
        home_team=entry.home_team,
        away_team=entry.away_team,
        kickoff_utc=entry.kickoff_utc,
        league=entry.league,
        provider=entry.provider,
        market_type=entry.market_type,
        selection=entry.selection,
        point=entry.point,
        price=entry.price,
        result=entry.result,
        pool=entry.pool,
        created_at=entry.created_at,
        settled_at=entry.settled_at,
    )


def _personal_pool_summary(entries: list[PersonalPoolEntry], pool: str) -> PersonalPoolSummaryView:
    scoped = [entry for entry in entries if entry.pool == pool]
    settled = [entry for entry in scoped if entry.result is not LegResult.PENDING]
    won = sum(entry.result is LegResult.WON for entry in settled)
    return PersonalPoolSummaryView(
        pool=pool,
        label="Straight wins" if pool == "straight_win" else "Corners",
        total=len(scoped),
        pending=sum(entry.result is LegResult.PENDING for entry in scoped),
        won=won,
        lost=sum(entry.result is LegResult.LOST for entry in settled),
        void=sum(entry.result is LegResult.VOID for entry in settled),
        win_rate=round(won / len(settled), 4) if settled else None,
    )


@app.get("/personal-pool", response_model=PersonalPoolView)
def personal_pool(session: Session = Depends(get_session)) -> PersonalPoolView:
    entries = list(
        session.exec(
            select(PersonalPoolEntry)
            .where(PersonalPoolEntry.user_id == DEFAULT_USER_ID)
            .order_by(PersonalPoolEntry.kickoff_utc, PersonalPoolEntry.created_at.desc())
        )
    )
    return PersonalPoolView(
        entries=[_to_personal_pool_entry_view(entry) for entry in entries],
        summaries=[
            _personal_pool_summary(entries, "straight_win"),
            _personal_pool_summary(entries, "corners"),
        ],
        note=(
            "A personal shortlist for review. Its results are tracked separately and do not "
            "alter model probabilities, value labels, or automated stake limits."
        ),
    )


@app.post("/personal-pool", response_model=PersonalPoolEntryView, status_code=201)
def add_personal_pool_entry(
    payload: PersonalPoolEntryCreate, session: Session = Depends(get_session)
) -> PersonalPoolEntryView:
    pool = _personal_pool_for(payload)
    duplicate = session.exec(
        select(PersonalPoolEntry).where(
            PersonalPoolEntry.user_id == DEFAULT_USER_ID,
            PersonalPoolEntry.fixture_id == payload.fixture_id,
            PersonalPoolEntry.market_type == payload.market_type.value,
            PersonalPoolEntry.selection == payload.selection,
        )
    ).first()
    if duplicate is not None:
        return _to_personal_pool_entry_view(duplicate)
    entry = PersonalPoolEntry(
        user_id=DEFAULT_USER_ID,
        pool=pool,
        fixture_id=payload.fixture_id,
        home_team=payload.home_team,
        away_team=payload.away_team,
        kickoff_utc=payload.kickoff_utc,
        league=payload.league,
        provider=payload.provider,
        market_type=payload.market_type.value,
        selection=payload.selection,
        point=payload.point,
        price=payload.price,
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return _to_personal_pool_entry_view(entry)


@app.patch("/personal-pool/{entry_id}", response_model=PersonalPoolEntryView)
def update_personal_pool_entry(
    entry_id: int,
    payload: PersonalPoolEntryUpdate,
    session: Session = Depends(get_session),
) -> PersonalPoolEntryView:
    entry = session.get(PersonalPoolEntry, entry_id)
    if entry is None or entry.user_id != DEFAULT_USER_ID:
        raise HTTPException(status_code=404, detail="personal pool entry not found")
    entry.result = payload.result
    entry.settled_at = (
        None if payload.result is LegResult.PENDING else entry.settled_at or datetime.now(UTC)
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return _to_personal_pool_entry_view(entry)


# --------------------------------------------------------------------------- #
# Calendar
# --------------------------------------------------------------------------- #


class CalendarDayModelView(BaseModel):
    """What the model could build for one day, if anything."""

    candidate_count: int
    target_met: bool
    combined_odds: float
    combined_model_prob: float
    leg_count: int


class CalendarDayView(BaseModel):
    date: date_type
    fixture_count: int
    priced_fixture_count: int
    leagues: list[str]
    slip_count: int
    pending_count: int
    won_count: int
    lost_count: int
    staked: float
    profit_loss: float
    model: CalendarDayModelView | None = None


class CalendarView(BaseModel):
    date_from: date_type
    date_to: date_type
    days: list[CalendarDayView]
    model_trained: bool
    fixture_count: int
    profit_loss: float
    staked: float
    settled_slip_count: int


# A month view plus its overflow weeks; also bounds the per-day model searches.
MAX_CALENDAR_DAYS = 62


def _day_bounds(day: date_type) -> tuple[datetime, datetime]:
    return (
        datetime.combine(day, time.min, tzinfo=UTC),
        datetime.combine(day, time.max, tzinfo=UTC),
    )


def _slip_match_day(legs: list[SlipLeg], slip: Slip) -> date_type:
    """The day a slip belongs to: its earliest kickoff, not when it was created.

    A slip built the night before is a bet on the next day's card, and that is
    the day it should appear on in the calendar.
    """
    if legs:
        earliest = min(leg.kickoff_utc for leg in legs)
        aware = earliest if earliest.tzinfo else earliest.replace(tzinfo=UTC)
        return aware.astimezone(UTC).date()
    created = slip.created_at
    aware = created if created.tzinfo else created.replace(tzinfo=UTC)
    return aware.astimezone(UTC).date()


@app.get("/calendar", response_model=CalendarView)
def calendar(
    date_from: date_type = Query(...),
    date_to: date_type = Query(...),
    include_model: bool = Query(default=True),
    target_odds: float = Query(default=1.5, gt=1.0, le=20.0),
    max_legs: int = Query(default=4, ge=1, le=8),
    min_leg_prob: float = Query(default=0.55, ge=0.0, lt=1.0),
    session: Session = Depends(get_session),
) -> CalendarView:
    """Summarise each day in a window: fixtures, slips settled, and model shape.

    Deliberately database-only. Unlike ``/fixtures``, this never calls a provider —
    a month view would otherwise fan out into a fetch per uncovered day and
    exhaust the odds-API quota every time someone paged the calendar. The
    full-season schedule fills days that do not have priced fixtures yet.
    """
    if date_to < date_from:
        raise HTTPException(status_code=400, detail="date_to must be after date_from")
    span = (date_to - date_from).days + 1
    if span > MAX_CALENDAR_DAYS:
        raise HTTPException(
            status_code=422,
            detail=f"window too wide: {span} days (max {MAX_CALENDAR_DAYS})",
        )

    window_start, _ = _day_bounds(date_from)
    _, window_end = _day_bounds(date_to)

    rows = session.exec(
        select(CachedFixture).where(
            CachedFixture.kickoff_utc >= window_start.replace(tzinfo=None),
            CachedFixture.kickoff_utc <= window_end.replace(tzinfo=None),
        )
    )
    fixtures_by_day: dict[date_type, list[Fixture]] = {}
    for row in rows:
        fixture = Fixture.model_validate(row.payload)
        kickoff = fixture.kickoff_utc
        aware = kickoff if kickoff.tzinfo else kickoff.replace(tzinfo=UTC)
        fixtures_by_day.setdefault(aware.astimezone(UTC).date(), []).append(fixture)

    scheduled = read_scheduled_fixtures(
        session, date_from=window_start, date_to=window_end
    )
    scheduled_by_day: dict[date_type, list[Fixture]] = {}
    for fixture in scheduled:
        aware = (
            fixture.kickoff_utc
            if fixture.kickoff_utc.tzinfo
            else fixture.kickoff_utc.replace(tzinfo=UTC)
        )
        scheduled_by_day.setdefault(aware.astimezone(UTC).date(), []).append(fixture)

    slips = list(session.exec(select(Slip).where(Slip.user_id == DEFAULT_USER_ID)))
    slip_legs = _load_legs_by_slip(session, slips)
    slips_by_day: dict[date_type, list[Slip]] = {}
    for slip in slips:
        day = _slip_match_day(slip_legs.get(slip.id, []), slip)
        if date_from <= day <= date_to:
            slips_by_day.setdefault(day, []).append(slip)

    service = get_model_service(session)
    model_trained = service.is_trained()

    days: list[CalendarDayView] = []
    cursor = date_from
    while cursor <= date_to:
        priced_fixtures = fixtures_by_day.get(cursor, [])
        day_fixtures = _merge_with_schedule(
            priced_fixtures, scheduled_by_day.get(cursor, [])
        )
        day_slips = slips_by_day.get(cursor, [])

        staked = sum(s.stake for s in day_slips)
        pnl = 0.0
        for slip in day_slips:
            if slip.result == SlipResult.PENDING:
                continue
            pnl += profit_loss(slip.stake, _leg_inputs(slip_legs.get(slip.id, [])))

        model_view: CalendarDayModelView | None = None
        if include_model and model_trained and priced_fixtures:
            _enrich_with_model(priced_fixtures, service)
            candidates = _collect_candidates(priced_fixtures)
            acca = build_target_acca(
                candidates,
                target_odds=target_odds,
                max_legs=max_legs,
                min_leg_prob=min_leg_prob,
            )
            model_view = CalendarDayModelView(
                candidate_count=acca.pool_size,
                target_met=acca.target_met,
                combined_odds=acca.combined_odds,
                combined_model_prob=acca.combined_model_prob,
                leg_count=len(acca.legs),
            )

        days.append(
            CalendarDayView(
                date=cursor,
                fixture_count=len(day_fixtures),
                priced_fixture_count=len(priced_fixtures),
                leagues=sorted({f.league for f in day_fixtures if f.league}),
                slip_count=len(day_slips),
                pending_count=sum(
                    1 for s in day_slips if s.result == SlipResult.PENDING
                ),
                won_count=sum(1 for s in day_slips if s.result == SlipResult.WON),
                lost_count=sum(1 for s in day_slips if s.result == SlipResult.LOST),
                staked=round(staked, 2),
                profit_loss=round(pnl, 2),
                model=model_view,
            )
        )
        cursor += timedelta(days=1)

    return CalendarView(
        date_from=date_from,
        date_to=date_to,
        days=days,
        model_trained=model_trained,
        fixture_count=sum(d.fixture_count for d in days),
        profit_loss=round(sum(d.profit_loss for d in days), 2),
        staked=round(sum(d.staked for d in days), 2),
        settled_slip_count=sum(d.won_count + d.lost_count for d in days),
    )
