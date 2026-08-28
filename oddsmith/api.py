"""FastAPI application: fixtures discovery + slip building/tracking.

Routes:
  GET   /health                     - liveness probe
  GET   /fixtures                   - list soccer fixtures in a date window (merged providers)
  GET   /fixtures/{fixture_id}/markets - markets for one fixture
  GET   /acca/weekend               - auto-built value acca (long price, low strike rate)
  GET   /acca/daily                 - short-priced "banker" slip + Kelly stake sizing
  POST  /slips                      - create a slip with legs (locks odds)
  GET   /slips                      - list slips for the default user
  GET   /slips/{slip_id}            - one slip with legs + computed odds/returns
  PATCH /slips/{slip_id}            - set stake/name and/or per-leg results, then re-settle
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from oddsmith.config import get_settings
from oddsmith.db import (
    DEFAULT_USER_ID,
    Slip,
    SlipLeg,
    get_session,
    init_db,
)
from oddsmith.models import Fixture, MarketType
from oddsmith.providers.api_football import ApiFootballProvider
from oddsmith.providers.base import OddsProvider
from oddsmith.cache import find_cached_fixture, get_cached_fixtures
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
from oddsmith.db import HistoricalMatch
from oddsmith.history import team_stats
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


def get_providers() -> list[OddsProvider]:
    return [TheOddsApiProvider(), ApiFootballProvider()]


_model_service: PoissonModelService | None = None


def get_model_service(session: Session = Depends(get_session)) -> PoissonModelService:
    """Train the odds model once from stored history and reuse it across requests."""
    global _model_service
    if _model_service is None or not _model_service.is_trained():
        _model_service = train_from_db(session)
    return _model_service


def _enrich_with_model(fixtures: list[Fixture], service: PoissonModelService) -> None:
    if not service.is_trained():
        return
    for fixture in fixtures:
        fixture.model_markets = build_model_markets(fixture, service)


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
    start = date_from or datetime.now(UTC)
    end = date_to or (start + timedelta(days=3))
    if end < start:
        raise HTTPException(status_code=400, detail="date_to must be after date_from")
    fixtures = await get_cached_fixtures(
        session,
        providers,
        date_from=start,
        date_to=end,
        markets=markets,
        force_refresh=refresh,
    )
    if model:
        _enrich_with_model(fixtures, get_model_service(session))
    return fixtures


@app.get("/fixtures/{fixture_id}/markets", response_model=Fixture)
async def fixture_markets(
    fixture_id: str,
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    providers: list[OddsProvider] = Depends(get_providers),
    session: Session = Depends(get_session),
) -> Fixture:
    cached = find_cached_fixture(session, fixture_id)
    if cached is not None:
        return cached

    start = date_from or datetime.now(UTC)
    end = date_to or (start + timedelta(days=7))
    fixtures = await get_cached_fixtures(session, providers, date_from=start, date_to=end)
    for fixture in fixtures:
        if fixture.id == fixture_id:
            return fixture
    raise HTTPException(status_code=404, detail="fixture not found in window")


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
async def weekend_acca(
    legs: int = Query(default=5, ge=1, le=10),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    providers: list[OddsProvider] = Depends(get_providers),
    session: Session = Depends(get_session),
) -> AccaView:
    """Auto-build an accumulator from the highest positive-EV model picks.

    Legs are the outcomes where our model's probability most exceeds the
    bookmaker's, one per fixture. This chases VALUE, not a guaranteed win — a
    multi-leg soccer acca still lands only single-digit percent of the time.
    """
    start = date_from or datetime.now(UTC)
    end = date_to or (start + timedelta(days=4))
    fixtures = await get_cached_fixtures(session, providers, date_from=start, date_to=end)
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
async def daily_acca(
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
    providers: list[OddsProvider] = Depends(get_providers),
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

    fixtures = await get_cached_fixtures(
        session,
        providers,
        date_from=start,
        date_to=end,
        markets=list(requested_markets),
    )
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

    fixtures_by_id = {f.id: f for f in fixtures}
    view = _acca_to_view(acca, fixtures_by_id)
    return DailyAccaView(
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


@app.get("/model/backtest", response_model=BacktestView)
def model_backtest(
    train_fraction: float = Query(default=0.7, gt=0.0, lt=1.0),
    session: Session = Depends(get_session),
) -> BacktestView:
    """Honest walk-forward accuracy on stored history. Not a promise of 80%."""
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
    return BacktestView(
        matches_scored=bt.matches_scored,
        hit_rate=bt.hit_rate,
        brier=bt.brier,
        roi=bt.roi,
        value_bets=bt.value_bets,
        note="1X2 walk-forward on historical results. ~54% is competitive; not 80%.",
    )


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
    rows = session.exec(select(HistoricalMatch.league).distinct())
    return sorted(rows)


@app.get("/history/matches", response_model=list[HistoryMatchView])
def history_matches(
    league: str | None = Query(default=None),
    team: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> list[HistoryMatchView]:
    query = select(HistoricalMatch)
    if league:
        query = query.where(HistoricalMatch.league == league)
    if team:
        query = query.where(
            (HistoricalMatch.home_team == team) | (HistoricalMatch.away_team == team)
        )
    query = query.order_by(HistoricalMatch.kickoff_utc.desc()).offset(offset).limit(limit)
    rows = session.exec(query)
    return [
        HistoryMatchView(
            id=r.id or 0,
            league=r.league,
            season=r.season,
            kickoff_utc=r.kickoff_utc,
            home_team=r.home_team,
            away_team=r.away_team,
            home_goals=r.home_goals,
            away_goals=r.away_goals,
        )
        for r in rows
    ]


@app.get("/history/teams/{team}/stats", response_model=TeamStatsView)
def history_team_stats(
    team: str,
    league: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> TeamStatsView:
    query = select(HistoricalMatch).where(
        (HistoricalMatch.home_team == team) | (HistoricalMatch.away_team == team)
    )
    if league:
        query = query.where(HistoricalMatch.league == league)
    rows = list(session.exec(query.order_by(HistoricalMatch.kickoff_utc)))
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
    return [_to_slip_view(slip, _load_legs(session, slip.id or 0)) for slip in slips]


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
    slip.settled_at = datetime.now(UTC) if slip.result is not SlipResult.PENDING else None
    session.add(slip)
    session.commit()

    legs = _load_legs(session, slip_id)
    session.refresh(slip)
    return _to_slip_view(slip, legs)
