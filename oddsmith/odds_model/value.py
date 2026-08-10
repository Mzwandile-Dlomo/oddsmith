"""Value detection: compare our model's probability to the bookmaker's.

A bookmaker's decimal odds imply a probability of 1/odds, but those implied
probabilities across a market sum to >1 — the excess is the bookmaker's margin
(the "overround"/"vig"). To compare fairly we de-margin the book's implied
probabilities so they sum to 1, then measure our edge:

    edge = model_prob - fair_implied_prob

A positive edge means our model thinks the outcome is more likely than the
(de-margined) market does — i.e. the offered price is potentially VALUE. Expected
value per unit stake at the offered odds is:

    ev = model_prob * offered_odds - 1
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValuePick:
    selection: str
    offered_odds: float
    model_prob: float
    implied_prob: float
    edge: float
    expected_value: float

    @property
    def is_value(self) -> bool:
        return self.edge > 0 and self.expected_value > 0


def implied_probabilities(odds: list[float]) -> list[float]:
    """De-margined (normalised) implied probabilities for a set of market odds.

    Raw implied prob is 1/odds; dividing by their sum removes the overround so
    the result is a fair probability distribution summing to 1.
    """
    raw = [1.0 / o for o in odds if o > 0]
    total = sum(raw)
    if total <= 0:
        return []
    return [r / total for r in raw]


def expected_value(model_prob: float, offered_odds: float) -> float:
    """EV per 1 unit staked: win (odds-1) with prob p, lose 1 with prob (1-p)."""
    return round(model_prob * offered_odds - 1.0, 4)


def assess_value(
    selection: str,
    model_prob: float,
    offered_odds: float,
    fair_implied_prob: float,
) -> ValuePick:
    edge = round(model_prob - fair_implied_prob, 4)
    return ValuePick(
        selection=selection,
        offered_odds=offered_odds,
        model_prob=round(model_prob, 4),
        implied_prob=round(fair_implied_prob, 4),
        edge=edge,
        expected_value=expected_value(model_prob, offered_odds),
    )
