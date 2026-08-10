"""Poisson goals model for computing our own fair odds from match results.

The classic approach: model each team's goals as Poisson-distributed. A team's
expected goals in a match depend on its ATTACK strength, the opponent's DEFENCE
strength, and home advantage.

    lambda_home = league_avg_home_goals * attack[home] * defence[away]
    lambda_away = league_avg_away_goals * attack[away] * defence[home]

Strengths are fit from historical results by iterative averaging (a lightweight,
dependency-free alternative to full maximum-likelihood — good enough for a
baseline and fully explainable). From the two lambdas we build the scoreline
probability grid and read off 1X2, Over/Under, and BTTS probabilities, then
convert probability -> fair decimal odds (odds = 1 / probability).

Everything here is pure and dependency-free so it is trivially unit-testable and
can be swapped for an ML engine later behind the OddsModel protocol.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import exp, factorial

MAX_GOALS = 10  # scoreline grid ceiling; P(>10 goals) is negligible


@dataclass(frozen=True)
class MatchResult:
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int


@dataclass
class TeamStrengths:
    attack: dict[str, float] = field(default_factory=dict)
    defence: dict[str, float] = field(default_factory=dict)
    league_home_avg: float = 1.35
    league_away_avg: float = 1.10

    def has(self, team: str) -> bool:
        return team in self.attack and team in self.defence


def poisson_pmf(k: int, lam: float) -> float:
    """P(X = k) for a Poisson with mean ``lam``."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return exp(-lam) * lam**k / factorial(k)


def dixon_coles_tau(h: int, a: int, home_lambda: float, away_lambda: float, rho: float) -> float:
    """Dixon-Coles low-score dependency correction.

    Plain Poisson treats home and away goals as independent, which understates
    the frequency of 0-0/1-1 and overstates 1-0/0-1. The tau factor re-weights
    the four low-score cells; ``rho`` (typically negative, ~-0.1) controls the
    strength. Cells other than the four lowest are unchanged (tau = 1).
    """
    if h == 0 and a == 0:
        return 1.0 - home_lambda * away_lambda * rho
    if h == 0 and a == 1:
        return 1.0 + home_lambda * rho
    if h == 1 and a == 0:
        return 1.0 + away_lambda * rho
    if h == 1 and a == 1:
        return 1.0 - rho
    return 1.0



def fit_strengths(
    results: list[MatchResult], iterations: int = 12, decay: float = 0.0
) -> TeamStrengths:
    """Estimate per-team attack/defence multipliers from historical results.

    Attack ~ how many more/fewer goals than average a team scores; defence ~ how
    many it concedes (lower is better). Both are ratios centred on 1.0. Fit by
    repeatedly re-estimating each team against the current opponent strengths.

    ``results`` are assumed chronological. With ``decay`` > 0 an exponential
    recency weight is applied so recent matches count more: the oldest match has
    weight exp(-decay * (n-1)) and the newest has weight 1. ``decay = 0`` weights
    all matches equally.
    """
    teams = sorted({r.home_team for r in results} | {r.away_team for r in results})
    if not results or not teams:
        return TeamStrengths()

    n = len(results)
    weights = [exp(-decay * (n - 1 - i)) for i in range(n)]
    wsum = sum(weights)
    league_home_avg = sum(r.home_goals * w for r, w in zip(results, weights, strict=True)) / wsum
    league_away_avg = sum(r.away_goals * w for r, w in zip(results, weights, strict=True)) / wsum

    attack = dict.fromkeys(teams, 1.0)
    defence = dict.fromkeys(teams, 1.0)

    for _ in range(iterations):
        scored: dict[str, float] = {t: 0.0 for t in teams}
        conceded: dict[str, float] = {t: 0.0 for t in teams}
        exp_scored: dict[str, float] = {t: 0.0 for t in teams}
        exp_conceded: dict[str, float] = {t: 0.0 for t in teams}

        for r, w in zip(results, weights, strict=True):
            scored[r.home_team] += r.home_goals * w
            conceded[r.home_team] += r.away_goals * w
            scored[r.away_team] += r.away_goals * w
            conceded[r.away_team] += r.home_goals * w

            exp_scored[r.home_team] += league_home_avg * defence[r.away_team] * w
            exp_conceded[r.home_team] += league_away_avg * attack[r.away_team] * w
            exp_scored[r.away_team] += league_away_avg * defence[r.home_team] * w
            exp_conceded[r.away_team] += league_home_avg * attack[r.home_team] * w

        for t in teams:
            if exp_scored[t] > 0:
                attack[t] = _clamp(scored[t] / exp_scored[t])
            if exp_conceded[t] > 0:
                defence[t] = _clamp(conceded[t] / exp_conceded[t])

    return TeamStrengths(
        attack=attack,
        defence=defence,
        league_home_avg=league_home_avg,
        league_away_avg=league_away_avg,
    )


def _clamp(value: float, low: float = 0.35, high: float = 2.2) -> float:
    return max(low, min(high, value))


def expected_goals(
    strengths: TeamStrengths, home_team: str, away_team: str
) -> tuple[float, float]:
    a = strengths
    home_lambda = a.league_home_avg * a.attack.get(home_team, 1.0) * a.defence.get(
        away_team, 1.0
    )
    away_lambda = a.league_away_avg * a.attack.get(away_team, 1.0) * a.defence.get(
        home_team, 1.0
    )
    return home_lambda, away_lambda


@dataclass(frozen=True)
class MatchProbabilities:
    home_win: float
    draw: float
    away_win: float
    over_2_5: float
    under_2_5: float
    btts_yes: float
    btts_no: float


def match_probabilities(
    home_lambda: float, away_lambda: float, rho: float = 0.0, shrinkage: float = 0.0
) -> MatchProbabilities:
    """Build the scoreline grid and read off market probabilities.

    With ``rho`` != 0 the Dixon-Coles low-score correction is applied and the
    grid is renormalised so probabilities still sum to 1. ``shrinkage`` (0..1)
    blends the 1X2 vector toward a uniform prior to curb overconfidence.
    """
    home_win = draw = away_win = 0.0
    over = under = 0.0
    btts_yes = btts_no = 0.0
    total = 0.0

    for h in range(MAX_GOALS + 1):
        ph = poisson_pmf(h, home_lambda)
        for a in range(MAX_GOALS + 1):
            p = ph * poisson_pmf(a, away_lambda)
            if rho != 0.0:
                p *= dixon_coles_tau(h, a, home_lambda, away_lambda, rho)
            total += p
            if h > a:
                home_win += p
            elif h == a:
                draw += p
            else:
                away_win += p

            if h + a > 2.5:
                over += p
            else:
                under += p

            if h > 0 and a > 0:
                btts_yes += p
            else:
                btts_no += p

    norm = total if total > 0 else 1.0
    hw, dw, aw = home_win / norm, draw / norm, away_win / norm

    # Calibration shrinkage: blend the 1X2 vector toward a uniform prior so a
    # dominant favourite never collapses to near-certainty (real matches carry
    # irreducible uncertainty — upsets, red cards, rotation). Bookmakers rarely
    # price a side above ~0.93; a small blend keeps us in that realistic range
    # and improves calibration without changing which outcome is favoured.
    if shrinkage > 0.0:
        u = 1.0 / 3.0
        hw = (1 - shrinkage) * hw + shrinkage * u
        dw = (1 - shrinkage) * dw + shrinkage * u
        aw = (1 - shrinkage) * aw + shrinkage * u

    return MatchProbabilities(
        home_win=hw,
        draw=dw,
        away_win=aw,
        over_2_5=over / norm,
        under_2_5=under / norm,
        btts_yes=btts_yes / norm,
        btts_no=btts_no / norm,
    )


def probability_to_odds(probability: float, margin: float = 0.0) -> float | None:
    """Fair decimal odds from a probability, optionally with a bookmaker margin.

    Returns ``None`` for a zero/negative probability (no sensible price).
    """
    if probability <= 0:
        return None
    fair = 1.0 / probability
    if margin <= 0:
        return round(fair, 2)
    return round(fair / (1 + margin), 2)
