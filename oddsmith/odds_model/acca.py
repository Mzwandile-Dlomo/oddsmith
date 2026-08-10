"""Build a multi-leg accumulator from the highest-value selections.

Given per-fixture value picks, choose the strongest positive-EV legs subject to
diversification: at most one leg per fixture (you cannot combine two outcomes of
the same match on an acca). Legs are ranked by expected value, then by edge.

The combined odds and combined model probability are exposed so the UI can show
both the price AND the honest model-estimated chance the whole slip lands — which
for a 5-leg soccer acca is realistically single-digit percent.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import prod

from oddsmith.odds_model.value import ValuePick


@dataclass(frozen=True)
class AccaLeg:
    fixture_id: str
    home_team: str
    away_team: str
    market_type: str
    pick: ValuePick
    point: float | None = None


@dataclass(frozen=True)
class Acca:
    legs: list[AccaLeg]

    @property
    def combined_odds(self) -> float:
        if not self.legs:
            return 0.0
        return round(prod(leg.pick.offered_odds for leg in self.legs), 2)

    @property
    def combined_model_prob(self) -> float:
        """Model-estimated probability that EVERY leg wins (independence assumed)."""
        if not self.legs:
            return 0.0
        return round(prod(leg.pick.model_prob for leg in self.legs), 4)

    @property
    def combined_expected_value(self) -> float:
        # An empty acca has no EV. Without this guard the formula returns -1.0,
        # which reads as "a guaranteed total loss" rather than "no bet".
        if not self.legs:
            return 0.0
        return round(self.combined_model_prob * self.combined_odds - 1.0, 4)


@dataclass(frozen=True)
class Candidate:
    fixture_id: str
    home_team: str
    away_team: str
    market_type: str
    pick: ValuePick
    point: float | None = None


def build_acca(candidates: list[Candidate], legs: int = 5) -> Acca:
    """Pick the top ``legs`` value candidates, at most one per fixture."""
    value_only = [c for c in candidates if c.pick.is_value]
    value_only.sort(key=lambda c: (c.pick.expected_value, c.pick.edge), reverse=True)

    chosen: list[AccaLeg] = []
    used_fixtures: set[str] = set()
    for c in value_only:
        if c.fixture_id in used_fixtures:
            continue
        chosen.append(
            AccaLeg(
                fixture_id=c.fixture_id,
                home_team=c.home_team,
                away_team=c.away_team,
                market_type=c.market_type,
                pick=c.pick,
                point=c.point,
            )
        )
        used_fixtures.add(c.fixture_id)
        if len(chosen) == legs:
            break

    return Acca(legs=chosen)
