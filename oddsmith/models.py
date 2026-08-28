"""Domain models for Oddsmith.

Two layers live here:

* Provider-facing value objects (``Fixture``, ``Market``, ``Outcome``) that the
  odds adapters produce. These are plain Pydantic models, not persisted.
* Enums describing the market "takes" a user can pick.

Persisted SQLModel tables (slips/legs) live in ``db.py`` to keep the ORM engine
concerns separate from these transport/value objects.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class MarketType(StrEnum):
    """The kinds of bets ("takes") a user can add to a slip."""

    MATCH_WINNER = "match_winner"  # 1X2 / straight win (home / draw / away)
    BTTS = "btts"  # both teams to score (yes / no)
    OVER_UNDER = "over_under"  # total goals over/under a line
    CORNER_TOTALS = "corner_totals"  # total corners over/under
    DOUBLE_CHANCE = "double_chance"  # 1X / 12 / X2


class Outcome(BaseModel):
    """A single selectable price within a market.

    ``name`` is the human label (e.g. "Home", "Draw", "Over", "Yes").
    ``point`` is the line for markets that need one (e.g. 2.5 for over/under).
    ``price`` is the decimal odds (e.g. 1.85).
    """

    name: str
    price: float = Field(gt=1.0, description="Decimal odds; must be > 1.0")
    point: float | None = None


class Market(BaseModel):
    type: MarketType
    outcomes: list[Outcome]
    bookmaker: str | None = None
    provider: str | None = None


class ModelOutcome(BaseModel):
    """Our model's view of one outcome, alongside the bookmaker's price.

    ``model_odds`` is our fair price (1/model_prob). ``edge`` is model_prob minus
    the bookmaker's de-margined implied probability; positive means our model
    rates this outcome higher than the market — a value signal. ``is_value`` is
    true only when the edge and expected value are both positive.
    """

    name: str
    model_prob: float
    model_odds: float
    bookmaker_odds: float | None = None
    edge: float | None = None
    expected_value: float | None = None
    is_value: bool = False
    point: float | None = None


class ModelMarket(BaseModel):
    type: MarketType
    outcomes: list[ModelOutcome]


class Fixture(BaseModel):
    """A soccer match, provider-agnostic."""

    id: str
    home_team: str
    away_team: str
    kickoff_utc: datetime
    league: str | None = None
    provider: str
    # Present when the fixture was fetched together with its odds.
    markets: list[Market] = Field(default_factory=list)
    # Our model's computed odds + value flags, when available.
    model_markets: list[ModelMarket] = Field(default_factory=list)
