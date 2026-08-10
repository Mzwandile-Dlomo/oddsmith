"""Persistence layer: SQLModel tables + engine/session helpers.

MVP uses SQLite and a single default user (auth is deferred). The ``user_id``
column exists now so real auth can be layered on without a migration of intent.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime

from sqlalchemy import JSON, Column
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
    currency: str = "USD"
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


class HistoricalMatch(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    league: str = Field(index=True)
    season: int = Field(index=True)
    kickoff_utc: datetime = Field(index=True)
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int


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
