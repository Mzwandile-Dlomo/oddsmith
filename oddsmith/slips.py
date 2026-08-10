"""Pure bet-slip math: combined odds, potential return, and settlement.

Everything here is side-effect free and independent of the web/DB layers so it
can be unit-tested in isolation and reused by a future mobile client's server.

Odds are DECIMAL throughout (e.g. 2.50 means stake x2.5 total return on a win).
"""

from __future__ import annotations

from enum import StrEnum
from math import prod

from pydantic import BaseModel, Field


class LegResult(StrEnum):
    PENDING = "pending"
    WON = "won"
    LOST = "lost"
    VOID = "void"  # e.g. match postponed; leg is removed from the accumulator


class SlipResult(StrEnum):
    PENDING = "pending"
    WON = "won"
    LOST = "lost"


class LegInput(BaseModel):
    """A single selection on a slip, for calculation purposes."""

    price: float = Field(gt=1.0, description="Decimal odds for this selection")
    result: LegResult = LegResult.PENDING


def combined_odds(prices: list[float]) -> float:
    """Accumulator odds = product of every leg's decimal price.

    An empty slip has no odds; callers should guard against that. We return 0.0
    for an empty list so it is never mistaken for a valid 1.0 (evens) multiplier.
    """
    if not prices:
        return 0.0
    return prod(prices)


def potential_return(stake: float, prices: list[float]) -> float:
    """Total return (stake + winnings) if every leg wins."""
    if stake < 0:
        raise ValueError("stake must be non-negative")
    return round(stake * combined_odds(prices), 2)


def potential_profit(stake: float, prices: list[float]) -> float:
    """Winnings only (return minus stake)."""
    return round(potential_return(stake, prices) - stake, 2)


def effective_prices(legs: list[LegInput]) -> list[float]:
    """Prices that still count toward the accumulator.

    VOID legs drop out (treated as odds 1.0 -> excluded from the product).
    """
    return [leg.price for leg in legs if leg.result is not LegResult.VOID]


def settle(legs: list[LegInput]) -> SlipResult:
    """Determine the overall slip result from its legs.

    Accumulator rules:
    * Any LOST leg  -> the whole slip is LOST.
    * Any PENDING leg (and none lost) -> still PENDING.
    * All remaining legs WON (VOID legs ignored) -> WON.
    * A slip whose every leg is VOID is treated as WON at odds 1.0 (stake back).
    """
    if any(leg.result is LegResult.LOST for leg in legs):
        return SlipResult.LOST
    if any(leg.result is LegResult.PENDING for leg in legs):
        return SlipResult.PENDING
    return SlipResult.WON


def settled_return(stake: float, legs: list[LegInput]) -> float:
    """Actual payout given the legs' current results.

    * LOST slip -> 0.0
    * PENDING slip -> 0.0 (nothing paid yet)
    * WON slip -> stake x product(effective prices); an all-void slip pays the
      stake back (product of an empty list is 1.0).
    """
    result = settle(legs)
    if result is not SlipResult.WON:
        return 0.0
    prices = effective_prices(legs)
    multiplier = prod(prices) if prices else 1.0
    return round(stake * multiplier, 2)


def profit_loss(stake: float, legs: list[LegInput]) -> float:
    """Net P&L for a settled slip (payout minus stake).

    PENDING slips return 0.0 (no realised P&L yet).
    """
    if settle(legs) is SlipResult.PENDING:
        return 0.0
    return round(settled_return(stake, legs) - stake, 2)
