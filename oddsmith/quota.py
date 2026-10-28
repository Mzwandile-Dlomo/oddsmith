"""Hard spend limits for the metered odds providers.

Both upstreams are metered and both of our previous keys ran dry: API-Football's
free plan allows 100 requests a day, The Odds API's 500 credits a month. Every
metered call therefore reserves its cost here *before* it is sent.

The ledger lives in the DB (``ProviderUsage``, one row per provider per UTC day)
so the web app, the scripts and the scheduled GitHub jobs all draw on the same
budget. A reservation is refused when either

* today's spend plus the cost would pass the daily budget, or
* the provider's own last reported remaining count, minus the cost, would fall
  below the floor — the backstop for spend we did not see (another machine,
  another DB, the provider's dashboard).

Reservations are counted even when the request then fails; overcounting only
makes us stop early, undercounting is how keys get exhausted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from oddsmith.config import Settings, get_settings
from oddsmith.db import ProviderUsage, get_engine
from oddsmith.providers.base import ProviderError


class QuotaExceeded(ProviderError):
    """Raised instead of sending a call the budget cannot afford."""


@dataclass(frozen=True)
class QuotaPolicy:
    provider: str
    daily_budget: int
    floor: int
    # API-Football's remaining count resets every UTC day; The Odds API's is a
    # monthly balance, so yesterday's reading still applies today.
    remaining_resets_daily: bool


def api_football_policy(settings: Settings) -> QuotaPolicy:
    return QuotaPolicy(
        provider="api_football",
        daily_budget=settings.api_football_daily_budget,
        floor=settings.api_football_floor,
        remaining_resets_daily=True,
    )


def the_odds_api_policy(settings: Settings) -> QuotaPolicy:
    return QuotaPolicy(
        provider="the_odds_api",
        daily_budget=settings.the_odds_api_daily_budget,
        floor=settings.the_odds_api_floor,
        remaining_resets_daily=False,
    )


_engines: dict[str, object] = {}


def _engine_for(database_url: str):
    """Reuse the app engine for the app's DB; isolate anything else (tests)."""
    if database_url == get_settings().database_url:
        return get_engine()
    if database_url in {"sqlite://", "sqlite:///:memory:"}:
        # A fresh in-memory ledger per guard, shared across its connections.
        return create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    if database_url not in _engines:
        _engines[database_url] = create_engine(database_url)
    return _engines[database_url]


class QuotaGuard:
    def __init__(self, policy: QuotaPolicy, *, database_url: str | None = None, engine=None):
        self.policy = policy
        self._engine = engine if engine is not None else _engine_for(
            database_url or get_settings().database_url
        )
        ProviderUsage.__table__.create(self._engine, checkfirst=True)

    @staticmethod
    def _today() -> date:
        return datetime.now(UTC).date()

    def _row(self, session: Session, day: date) -> ProviderUsage:
        query = select(ProviderUsage).where(
            ProviderUsage.provider == self.policy.provider, ProviderUsage.day == day
        )
        row = session.exec(query).first()
        if row is not None:
            return row
        try:
            session.add(ProviderUsage(provider=self.policy.provider, day=day))
            session.commit()
        except IntegrityError:  # another process created it first
            session.rollback()
        return session.exec(query).one()

    def _provider_remaining(self, session: Session, today: ProviderUsage) -> int | None:
        if self.policy.remaining_resets_daily:
            return today.provider_remaining
        latest = session.exec(
            select(ProviderUsage)
            .where(
                ProviderUsage.provider == self.policy.provider,
                ProviderUsage.provider_remaining.is_not(None),
            )
            .order_by(ProviderUsage.day.desc())
        ).first()
        return latest.provider_remaining if latest else None

    def reserve(self, cost: int) -> bool:
        """Atomically claim ``cost`` from today's budget; False if it would overspend."""
        if cost <= 0:
            return True
        with Session(self._engine) as session:
            row = self._row(session, self._today())
            remaining = self._provider_remaining(session, row)
            if remaining is not None and remaining - cost < self.policy.floor:
                return False
            claimed = session.execute(
                update(ProviderUsage)
                .where(
                    ProviderUsage.id == row.id,
                    ProviderUsage.used + cost <= self.policy.daily_budget,
                )
                .values(used=ProviderUsage.used + cost, updated_at=datetime.now(UTC))
            )
            session.commit()
            return claimed.rowcount == 1

    def require(self, cost: int) -> None:
        if not self.reserve(cost):
            raise QuotaExceeded(
                f"{self.policy.provider}: daily budget reached "
                f"({self.policy.daily_budget}/day, floor {self.policy.floor}); "
                "serving stored data only"
            )

    def observe(self, provider_remaining: int | None) -> None:
        """Record the provider's own remaining count from a response header."""
        if provider_remaining is None:
            return
        with Session(self._engine) as session:
            row = self._row(session, self._today())
            row.provider_remaining = provider_remaining
            row.updated_at = datetime.now(UTC)
            session.add(row)
            session.commit()

    def used_today(self) -> int:
        with Session(self._engine) as session:
            return self._row(session, self._today()).used

