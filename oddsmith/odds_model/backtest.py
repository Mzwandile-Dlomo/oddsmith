"""Walk-forward backtest: honest metrics for the model, no inflated claims.

We split historical results chronologically, fit team strengths on the training
portion, predict the held-out portion, and score predictions against reality:

* hit_rate   — how often the model's most-likely 1X2 pick was correct.
* brier      — mean squared error of the 1X2 probability vector (calibration;
               lower is better, 0 is perfect).
* roi        — simulated return staking 1 unit on every positive-EV pick at the
               bookmaker's offered odds, settled on the real outcome.

These are the numbers to trust. For soccer 1X2, a well-calibrated model lands
around 0.50-0.55 hit rate — nowhere near 80%, and that is expected.
"""

from __future__ import annotations

from dataclasses import dataclass

from oddsmith.odds_model.poisson import (
    MatchResult,
    expected_goals,
    fit_strengths,
    match_probabilities,
)
from oddsmith.odds_model.value import expected_value


@dataclass(frozen=True)
class BacktestResult:
    matches_scored: int
    hit_rate: float
    brier: float
    roi: float | None
    value_bets: int


def _outcome(result: MatchResult) -> str:
    if result.home_goals > result.away_goals:
        return "home"
    if result.home_goals == result.away_goals:
        return "draw"
    return "away"


def backtest_1x2(
    results: list[MatchResult],
    *,
    train_fraction: float = 0.7,
    rho: float = 0.0,
    decay: float = 0.0,
    shrinkage: float = 0.0,
    offered_odds: dict[int, tuple[float, float, float]] | None = None,
) -> BacktestResult:
    """Chronological walk-forward backtest on 1X2.

    ``results`` must already be in chronological order. ``rho`` applies the
    Dixon-Coles low-score correction, ``decay`` applies recency weighting when
    fitting, and ``shrinkage`` blends the 1X2 vector toward uniform to curb
    overconfidence. ``offered_odds`` optionally maps a held-out match's index to
    its (home, draw, away) bookmaker decimal odds so ROI can be simulated;
    without it ROI is None.
    """
    n = len(results)
    split = int(n * train_fraction)
    train, test = results[:split], results[split:]
    if not train or not test:
        return BacktestResult(0, 0.0, 0.0, None, 0)

    strengths = fit_strengths(train, decay=decay)

    hits = 0
    brier_sum = 0.0
    staked = 0.0
    returned = 0.0
    value_bets = 0

    for offset, match in enumerate(test):
        hl, al = expected_goals(strengths, match.home_team, match.away_team)
        probs = match_probabilities(hl, al, rho=rho, shrinkage=shrinkage)
        p = {"home": probs.home_win, "draw": probs.draw, "away": probs.away_win}

        predicted = max(p, key=p.get)
        actual = _outcome(match)
        if predicted == actual:
            hits += 1

        for key in ("home", "draw", "away"):
            y = 1.0 if actual == key else 0.0
            brier_sum += (p[key] - y) ** 2

        if offered_odds is not None:
            idx = split + offset
            book = offered_odds.get(idx)
            if book is not None:
                book_map = dict(zip(("home", "draw", "away"), book, strict=True))
                for key, odds in book_map.items():
                    if expected_value(p[key], odds) > 0:
                        value_bets += 1
                        staked += 1.0
                        if actual == key:
                            returned += odds

    hit_rate = round(hits / len(test), 4)
    brier = round(brier_sum / len(test), 4)
    roi = round((returned - staked) / staked, 4) if staked > 0 else None
    return BacktestResult(
        matches_scored=len(test),
        hit_rate=hit_rate,
        brier=brier,
        roi=roi,
        value_bets=value_bets,
    )
