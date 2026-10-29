"""Strong slip: an accumulator built from the research board's Strong angles.

A Strong angle is a line both sides' recent matches kept landing ("Over 1.5
goals — Strong, 9/10"). This module takes the best priced Strong angle from
each fixture in a window and stacks them, most consistent first, until the
slip clears a target price.

Form is not the model. A 9/10 is a frequency over a handful of matches, so the
slip reports each leg's record, the bookmaker's de-margined probability and,
where the scoreline model prices the same line, the model's probability. It
never turns the form counts into a "chance this slip wins".
"""

from __future__ import annotations

import math
from datetime import datetime

from pydantic import BaseModel

from oddsmith.insights import TOTAL_LINES, MatchInsights, wilson_lower_bound
from oddsmith.models import Fixture, MarketType
from oddsmith.research import rank_angles

# Corner prices are collection-only research data; they never enter generated
# tickets (see capture_odds.py), so a Strong corner angle is not slip material.
STRONG_SLIP_MARKETS = frozenset({MarketType.OVER_UNDER, MarketType.BTTS})
# An Over 1.5 at 1.05 adds almost nothing to the price but a whole match of risk.
DEFAULT_MIN_LEG_ODDS = 1.15
MAX_ALTERNATIVES = 20

_LINES = {key: (mtype, outcome, point) for key, _, _, mtype, outcome, point in TOTAL_LINES}


class StrongLeg(BaseModel):
    fixture_id: str
    home_team: str
    away_team: str
    kickoff_utc: datetime
    league: str | None
    provider: str
    market_type: MarketType
    selection: str
    point: float | None
    label: str
    # None when no bookmaker price was collected for this line.
    offered_odds: float | None
    hits: int
    sample: int
    h2h_hits: int
    h2h_sample: int
    # 95% Wilson lower bound on hits/sample: 18/20 outranks 9/10.
    support: float
    book_implied_prob: float | None
    model_prob: float | None


class StrongSlip(BaseModel):
    legs: list[StrongLeg]
    # Strong picks from other fixtures that the slip did not need.
    alternatives: list[StrongLeg]
    # Strong picks with no collected price (the bulk odds feed mostly carries
    # only the 2.5 goals line). Worth checking at the user's own bookmaker.
    unpriced: list[StrongLeg]
    combined_odds: float
    target_odds: float
    target_met: bool
    # Products over the legs, only when every leg has a value.
    combined_book_prob: float | None
    combined_model_prob: float | None
    fixtures_scanned: int
    priced_fixtures: int
    note: str


def strong_candidates(fixture: Fixture, insights: MatchInsights) -> list[StrongLeg]:
    """Every Strong goals/BTTS angle on one fixture, priced or not, best supported first."""
    model = {
        (mm.type, o.name, o.point): o.model_prob
        for mm in fixture.model_markets
        for o in mm.outcomes
    }
    legs: list[StrongLeg] = []
    for angle in rank_angles(insights, limit=len(TOTAL_LINES)):
        mtype, outcome, point = _LINES[angle.key]
        if angle.strength != "Strong" or mtype not in STRONG_SLIP_MARKETS:
            continue
        legs.append(
            StrongLeg(
                fixture_id=fixture.id,
                home_team=fixture.home_team,
                away_team=fixture.away_team,
                kickoff_utc=fixture.kickoff_utc,
                league=fixture.league,
                provider=fixture.provider,
                market_type=mtype,
                selection=outcome,
                point=point,
                label=angle.label,
                offered_odds=angle.book_price,
                hits=angle.hits,
                sample=angle.sample,
                h2h_hits=angle.h2h_hits,
                h2h_sample=angle.h2h_sample,
                support=round(wilson_lower_bound(angle.hits, angle.sample), 4),
                book_implied_prob=angle.book_implied_prob,
                model_prob=model.get((mtype, outcome, point)),
            )
        )
    legs.sort(key=lambda leg: leg.support, reverse=True)
    return legs


def _product(values: list[float | None]) -> float | None:
    if not values or any(v is None for v in values):
        return None
    return round(math.prod(v for v in values if v is not None), 4)


def _best_per_fixture(legs: list[list[StrongLeg]]) -> list[StrongLeg]:
    """Each fixture's first leg (lists are best first), strongest fixtures first.

    Ties go to the longer price, which reaches the target in fewer legs.
    """
    return sorted(
        (candidates[0] for candidates in legs if candidates),
        key=lambda leg: (leg.support, leg.offered_odds or 0.0),
        reverse=True,
    )


def build_strong_slip(
    per_fixture: list[list[StrongLeg]],
    *,
    target_odds: float,
    max_legs: int,
    min_leg_odds: float = DEFAULT_MIN_LEG_ODDS,
    fixtures_scanned: int,
    priced_fixtures: int,
) -> StrongSlip:
    """One leg per fixture, strongest first, until the target price is cleared.

    Two legs from the same match are correlated (Over 1.5 and BTTS mostly land
    together), so each fixture contributes only its best supported angle.
    """
    pool = _best_per_fixture(
        [
            [leg for leg in candidates if (leg.offered_odds or 0.0) >= min_leg_odds]
            for candidates in per_fixture
        ]
    )
    unpriced = _best_per_fixture(
        [[leg for leg in candidates if leg.offered_odds is None] for candidates in per_fixture]
    )
    legs: list[StrongLeg] = []
    combined = 1.0
    for leg in pool:
        if combined >= target_odds or len(legs) == max_legs:
            break
        legs.append(leg)
        combined *= leg.offered_odds or 1.0
    chosen = {leg.fixture_id for leg in legs}
    alternatives = [leg for leg in pool if leg.fixture_id not in chosen][:MAX_ALTERNATIVES]

    combined_odds = round(combined, 2) if legs else 0.0
    target_met = bool(legs) and combined >= target_odds
    return StrongSlip(
        legs=legs,
        alternatives=alternatives,
        unpriced=unpriced[:MAX_ALTERNATIVES],
        combined_odds=combined_odds,
        target_odds=target_odds,
        target_met=target_met,
        combined_book_prob=_product([leg.book_implied_prob for leg in legs]),
        combined_model_prob=_product([leg.model_prob for leg in legs]),
        fixtures_scanned=fixtures_scanned,
        priced_fixtures=priced_fixtures,
        note=_note(priced_fixtures, len(pool), target_met, legs, target_odds, max_legs),
    )


def _note(
    priced_fixtures: int,
    strong: int,
    target_met: bool,
    legs: list[StrongLeg],
    target_odds: float,
    max_legs: int,
) -> str:
    if priced_fixtures == 0:
        return "No priced fixtures still to kick off in this window."
    if strong == 0:
        return (
            f"None of the {priced_fixtures} priced fixtures has a Strong angle with a "
            "bookmaker price on a goals or BTTS line."
        )
    plural = "s" if len(legs) != 1 else ""
    if not target_met:
        return (
            f"Only {len(legs)} Strong leg{plural} available within {max_legs}; "
            f"together they don't reach {target_odds:.2f}."
        )
    return f"{len(legs)} Strong leg{plural} picked from {strong} fixtures with a priced Strong angle."
