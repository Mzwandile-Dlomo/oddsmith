"""How much to stake, and what compounding a daily slip actually does.

A positive-EV bet still ruins you if you stake it wrong. The intuition "hit 1.5
every day and let it ride" is a bankroll staked at fraction 1.0, and its expected
log-growth is:

    p * log(1 + 1.0 * b) + (1 - p) * log(1 - 1.0)  ->  log(0)  ->  -inf

One loss takes everything, and over enough days a loss is certain. So the naive
version of the plan goes to zero **with probability 1 no matter how good the
model is**. That is not a modelling problem, it is an arithmetic one.

The fix is the Kelly criterion: stake the fraction of the bankroll that maximises
expected LOG growth rather than expected profit.

    f* = (p * b - (1 - p)) / b        where b = offered_odds - 1

Kelly is the fastest possible long-run growth, but it is also brutal — it assumes
``p`` is exactly right, and drawdowns of 50%+ are routine. Our ``p`` is a model
estimate with real error, and overestimating ``p`` means overbetting, which is
the one mistake Kelly punishes without mercy. Halving the fraction gives ~75% of
the growth for ~half the volatility, so **half-Kelly is what this module
recommends**.

Pure functions, no I/O — same contract as the rest of ``odds_model``.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp, expm1, inf, log

# Kelly assumes a known probability. Ours is estimated, so we stake half of it.
KELLY_MULTIPLIER = 0.5

# Never risk more than this share of the bankroll on one slip, whatever Kelly
# says. A short-priced favourite can produce a huge f*, and model error at the
# top end is exactly where it hurts most.
MAX_STAKE_FRACTION = 0.25


def kelly_fraction(model_prob: float, offered_odds: float) -> float:
    """Fraction of bankroll maximising long-run growth. 0.0 when there is no edge."""
    b = offered_odds - 1.0
    if b <= 0 or not 0.0 < model_prob < 1.0:
        return 0.0
    f = (model_prob * b - (1.0 - model_prob)) / b
    return max(0.0, f)


def log_growth_rate(model_prob: float, offered_odds: float, fraction: float) -> float:
    """Expected log-growth of the bankroll per bet at a given stake fraction.

    Returns ``-inf`` at fraction 1.0: staking everything means one loss ends the
    sequence permanently.
    """
    b = offered_odds - 1.0
    if fraction <= 0.0:
        return 0.0
    if fraction >= 1.0:
        return -inf
    if not 0.0 < model_prob < 1.0:
        return -inf
    return model_prob * log(1.0 + fraction * b) + (1.0 - model_prob) * log(1.0 - fraction)


@dataclass(frozen=True)
class StakingPlan:
    """A stake recommendation plus the honest arithmetic behind it."""

    model_prob: float
    offered_odds: float
    bankroll: float

    full_kelly_fraction: float
    recommended_fraction: float
    recommended_stake: float

    # Geometric growth per bet at the recommended fraction, e.g. 0.031 = +3.1%.
    growth_per_bet: float
    bets_to_double: float | None
    horizon_bets: int
    projected_bankroll: float

    # Reality checks.
    prob_all_win_over_horizon: float
    expected_losses_over_horizon: float
    let_it_ride_bankroll: float

    note: str


def build_staking_plan(
    model_prob: float,
    offered_odds: float,
    *,
    bankroll: float = 100.0,
    horizon_bets: int = 30,
    kelly_multiplier: float = KELLY_MULTIPLIER,
    max_fraction: float = MAX_STAKE_FRACTION,
) -> StakingPlan:
    """Size a repeated bet and project what compounding it really does.

    ``horizon_bets`` is how many times the bet is repeated — for a daily slip
    that is a number of days.
    """
    full_kelly = kelly_fraction(model_prob, offered_odds)
    fraction = min(full_kelly * kelly_multiplier, max_fraction)

    growth_log = log_growth_rate(model_prob, offered_odds, fraction)
    growth_per_bet = _expm1(growth_log)
    projected = bankroll * _exp(growth_log * horizon_bets)
    doubling = (log(2.0) / growth_log) if growth_log > 0 else None

    prob_all_win = model_prob**horizon_bets if 0.0 <= model_prob <= 1.0 else 0.0

    return StakingPlan(
        model_prob=round(model_prob, 4),
        offered_odds=round(offered_odds, 4),
        bankroll=round(bankroll, 2),
        full_kelly_fraction=round(full_kelly, 4),
        recommended_fraction=round(fraction, 4),
        recommended_stake=round(bankroll * fraction, 2),
        growth_per_bet=round(growth_per_bet, 6),
        bets_to_double=round(doubling, 1) if doubling is not None else None,
        horizon_bets=horizon_bets,
        projected_bankroll=round(projected, 2),
        prob_all_win_over_horizon=round(prob_all_win, 6),
        expected_losses_over_horizon=round((1.0 - model_prob) * horizon_bets, 2),
        # Staking the whole bankroll every time: one loss ends it, and over any
        # real horizon a loss is near-certain.
        let_it_ride_bankroll=0.0,
        note=_note(full_kelly, fraction, growth_log, model_prob, horizon_bets),
    )


def _note(
    full_kelly: float, fraction: float, growth_log: float, model_prob: float, horizon: int
) -> str:
    if full_kelly <= 0.0:
        return (
            "No edge at this price — the model does not rate this slip above the "
            "bookmaker's margin. The correct stake is zero."
        )
    expected_losses = (1.0 - model_prob) * horizon
    base = (
        f"Half-Kelly staking. Expect roughly {expected_losses:.1f} losing slips in "
        f"{horizon}; the plan only works if you keep staking the same FRACTION after "
        f"each one rather than chasing."
    )
    if growth_log <= 0:
        return "Edge too thin to compound safely once stake sizing is applied. " + base
    return base


def _exp(x: float) -> float:
    """``exp`` that treats the ruin case (-inf) as a zero bankroll, not an error."""
    return 0.0 if x == -inf else exp(x)


def _expm1(x: float) -> float:
    return -1.0 if x == -inf else expm1(x)
