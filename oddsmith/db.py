"""Persistence layer: SQLModel tables + engine/session helpers.

MVP uses SQLite and a single default user (auth is deferred). The ``user_id``
column exists now so real auth can be layered on without a migration of intent.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, Session, SQLModel, create_engine

from oddsmith.config import get_settings
from oddsmith.slips import LegResult, SlipResult

DEFAULT_USER_ID = "default"


def _now() -> datetime:
    return datetime.now(UTC)


class Slip(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: str = Field(default=DEFAULT_USER_ID, index=True)
    name: str | None = None
    stake: float = 0.0
    currency: str = "ZAR"
    result: SlipResult = Field(default=SlipResult.PENDING)
    created_at: datetime = Field(default_factory=_now)
    settled_at: datetime | None = None


class SlipLeg(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    slip_id: int = Field(foreign_key="slip.id", index=True)

    # Snapshot of the selection at add-time (odds move; we lock what the user saw).
    fixture_id: str
    home_team: str
    away_team: str
    kickoff_utc: datetime
    league: str | None = None
    provider: str

    market_type: str  # MarketType value
    selection: str  # outcome name, e.g. "Home", "Over", "Yes"
    point: float | None = None
    price: float  # decimal odds locked in when added

    result: LegResult = Field(default=LegResult.PENDING)


class PersonalPoolEntry(SQLModel, table=True):
    """A personally curated selection, tracked independently from model picks.

    Pools deliberately contain only the two user-requested market families.
    They are a review shortlist, not a training label or a model-promotion signal.
    """

    id: int | None = Field(default=None, primary_key=True)
    user_id: str = Field(default=DEFAULT_USER_ID, index=True)
    pool: str = Field(index=True)  # ``straight_win`` or ``corners``
    fixture_id: str = Field(index=True)
    home_team: str
    away_team: str
    kickoff_utc: datetime = Field(index=True)
    league: str | None = None
    provider: str
    market_type: str = Field(index=True)
    selection: str
    point: float | None = None
    price: float
    result: LegResult = Field(default=LegResult.PENDING, index=True)
    created_at: datetime = Field(default_factory=_now)
    settled_at: datetime | None = None


class CachedFixture(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    fixture_id: str = Field(index=True, unique=True)
    kickoff_utc: datetime = Field(index=True)
    fetched_at: datetime = Field(default_factory=_now, index=True)
    payload: dict = Field(sa_column=Column(JSON))


class FetchLog(SQLModel, table=True):
    """Records which calendar days we have already fetched from providers.

    A request only calls providers for days in the window that are absent here
    (or, for upcoming days, whose ``fetched_at`` is older than the refresh TTL),
    so we never re-fetch data we already have.
    """

    id: int | None = Field(default=None, primary_key=True)
    day: date = Field(index=True, unique=True)
    fetched_at: datetime = Field(default_factory=_now, index=True)
    fixture_count: int = 0


class FootballMatch(SQLModel, table=True):
    """Canonical API-Football fixture retained independently of provider caches."""

    id: int | None = Field(default=None, primary_key=True)
    provider_fixture_id: int = Field(index=True, unique=True)
    league_id: int = Field(index=True)
    league_name: str = Field(index=True)
    league_type: str | None = Field(default=None, index=True)
    country: str | None = Field(default=None, index=True)
    season: int = Field(index=True)
    round: str | None = Field(default=None, index=True)
    kickoff_utc: datetime = Field(index=True)
    status_long: str
    status_short: str = Field(index=True)
    elapsed: int | None = None
    home_team_id: int = Field(index=True)
    home_team: str = Field(index=True)
    away_team_id: int = Field(index=True)
    away_team: str = Field(index=True)
    home_goals: int | None = None
    away_goals: int | None = None
    venue: dict | None = Field(default=None, sa_column=Column(JSON))
    score: dict = Field(default_factory=dict, sa_column=Column(JSON))
    raw_payload: dict = Field(sa_column=Column(JSON))
    updated_at: datetime = Field(default_factory=_now, index=True)


class MatchResource(SQLModel, table=True):
    """A quota-expensive fixture resource cached by fixture and resource type."""

    id: int | None = Field(default=None, primary_key=True)
    resource_key: str = Field(index=True, unique=True)
    provider_fixture_id: int = Field(index=True)
    resource_type: str = Field(index=True)
    payload: list | dict = Field(sa_column=Column(JSON))
    fetched_at: datetime = Field(default_factory=_now, index=True)


class ScheduledFixture(SQLModel, table=True):
    """A full-season fixture keyed by the source's real competition match number."""

    id: int | None = Field(default=None, primary_key=True)
    source_key: str = Field(index=True, unique=True)
    source: str = Field(index=True)
    competition_key: str = Field(index=True)
    league_id: int = Field(index=True)
    league_name: str = Field(index=True)
    country: str
    season: int = Field(index=True)
    match_number: int
    round_number: int | None = Field(default=None, index=True)
    kickoff_utc: datetime = Field(index=True)
    location: str | None = None
    home_team: str = Field(index=True)
    away_team: str = Field(index=True)
    home_goals: int | None = None
    away_goals: int | None = None
    raw_payload: dict = Field(sa_column=Column(JSON))
    updated_at: datetime = Field(default_factory=_now, index=True)


class OddsSnapshot(SQLModel, table=True):
    """One bookmaker outcome price observed at a specific pre-match instant."""

    id: int | None = Field(default=None, primary_key=True)
    snapshot_key: str = Field(index=True, unique=True)
    fixture_id: str = Field(index=True)
    provider: str = Field(index=True)
    bookmaker: str = Field(index=True)
    league: str | None = Field(default=None, index=True)
    kickoff_utc: datetime = Field(index=True)
    captured_at: datetime = Field(index=True)
    hours_to_kickoff: float
    home_team: str
    away_team: str
    market_type: str = Field(index=True)
    selection: str = Field(index=True)
    point: float | None = Field(default=None, index=True)
    price: float


class OddsFixtureResult(SQLModel, table=True):
    """Final match facts linked to a provider fixture's immutable price history."""

    id: int | None = Field(default=None, primary_key=True)
    fixture_id: str = Field(index=True, unique=True)
    source: str = Field(index=True)
    source_key: str = Field(index=True)
    kickoff_utc: datetime = Field(index=True)
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int
    home_corners: int | None = None
    away_corners: int | None = None
    settled_at: datetime = Field(default_factory=_now, index=True)


class HistoricalMatch(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    league: str = Field(index=True)
    season: int = Field(index=True)
    kickoff_utc: datetime = Field(index=True)
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int


class MatchObservation(SQLModel, table=True):
    """Enriched, source-traceable row used to build leakage-safe ML features.

    ``HistoricalMatch`` remains the compact input to the Poisson baseline. This
    table keeps the wider evidence needed for goals, corners, cards, and 1X2 ML
    models without forcing a destructive migration of the existing table.
    Nullable fields are deliberate: historical providers and leagues have
    different coverage, and an unrecorded statistic must never be treated as 0.
    """

    id: int | None = Field(default=None, primary_key=True)
    source_key: str = Field(index=True, unique=True)
    source: str = Field(index=True)
    source_league_code: str | None = Field(default=None, index=True)
    league: str = Field(index=True)
    season: int = Field(index=True)
    kickoff_utc: datetime = Field(index=True)
    home_team: str = Field(index=True)
    away_team: str = Field(index=True)
    referee: str | None = None

    home_goals: int
    away_goals: int
    half_time_home_goals: int | None = None
    half_time_away_goals: int | None = None

    home_shots: int | None = None
    away_shots: int | None = None
    home_shots_on_target: int | None = None
    away_shots_on_target: int | None = None
    home_corners: int | None = None
    away_corners: int | None = None
    home_fouls: int | None = None
    away_fouls: int | None = None
    home_yellow_cards: int | None = None
    away_yellow_cards: int | None = None
    home_red_cards: int | None = None
    away_red_cards: int | None = None

    close_home_odds: float | None = None
    close_draw_odds: float | None = None
    close_away_odds: float | None = None
    close_over_2_5_odds: float | None = None
    close_under_2_5_odds: float | None = None

    imported_at: datetime = Field(default_factory=_now, index=True)
    raw_payload: dict = Field(sa_column=Column(JSON))


class ModelEvaluationSnapshot(SQLModel, table=True):
    """Immutable published evaluation artifact displayed by Model Lab."""

    id: int | None = Field(default=None, primary_key=True)
    model_name: str = Field(index=True)
    generated_at: datetime = Field(index=True)
    dataset_matches: int
    payload: dict = Field(sa_column=Column(JSON))


class MatchRead(SQLModel, table=True):
    """A cached written read for one fixture.

    ``data_key`` fingerprints the evidence the read was written from (latest
    stored match, prices, angles), so a read is rewritten only when new results
    or odds arrive, never on every page view.
    """

    id: int | None = Field(default=None, primary_key=True)
    fixture_id: str = Field(index=True)
    data_key: str = Field(index=True)
    model: str
    angle_key: str
    summary: str
    match_read: str
    created_at: datetime = Field(default_factory=_now)


class CornerEvaluationSnapshot(SQLModel, table=True):
    """Immutable corner count evaluation artifact displayed by Model Lab."""

    id: int | None = Field(default=None, primary_key=True)
    model_name: str = Field(index=True)
    generated_at: datetime = Field(index=True)
    dataset_matches: int
    payload: dict = Field(sa_column=Column(JSON))


class ProviderUsage(SQLModel, table=True):
    """Metered provider spend for one UTC day (see ``oddsmith.quota``).

    ``used`` is what we reserved before sending; ``provider_remaining`` is the
    last count the provider itself reported in its response headers.
    """

    __table_args__ = (UniqueConstraint("provider", "day"),)

    id: int | None = Field(default=None, primary_key=True)
    provider: str = Field(index=True)
    day: date = Field(index=True)
    used: int = 0
    provider_remaining: int | None = None
    updated_at: datetime = Field(default_factory=_now)


_engine = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        connect_args = (
            {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
        )
        _engine = create_engine(settings.database_url, connect_args=connect_args)
    return _engine


def init_db() -> None:
    SQLModel.metadata.create_all(get_engine())


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
