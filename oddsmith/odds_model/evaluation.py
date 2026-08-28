"""League-by-league expanding-window evaluation for the 1X2 baseline.

This module is intentionally pure: database rows are converted to
``EvaluationMatch`` at the boundary. Each fold trains on complete earlier
seasons and evaluates the next season, so no future match can influence a past
prediction. The bookmaker comparison uses de-margined closing probabilities.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import log
from random import Random

from oddsmith.odds_model.poisson import (
    MatchResult,
    expected_goals,
    fit_strengths,
    match_probabilities,
)
from oddsmith.odds_model.value import implied_probabilities

OUTCOMES = ("home", "draw", "away")
EPSILON = 1e-12


@dataclass(frozen=True)
class EvaluationMatch:
    league: str
    season: int
    kickoff_utc: datetime
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int
    odds_home: float | None = None
    odds_draw: float | None = None
    odds_away: float | None = None

    @property
    def odds(self) -> tuple[float, float, float] | None:
        values = (self.odds_home, self.odds_draw, self.odds_away)
        if any(value is None or value <= 1.0 for value in values):
            return None
        return values  # type: ignore[return-value]


@dataclass(frozen=True)
class ProbabilityMetrics:
    matches: int
    accuracy: float
    log_loss: float
    brier: float
    calibration_error: float


@dataclass(frozen=True)
class StrategyMetrics:
    bets: int
    wins: int
    profit: float
    roi: float | None
    roi_ci_low: float | None
    roi_ci_high: float | None


@dataclass(frozen=True)
class EvaluationSummary:
    model: ProbabilityMetrics
    market: ProbabilityMetrics
    strategy: StrategyMetrics


@dataclass(frozen=True)
class FoldEvaluation:
    league: str
    test_season: int
    train_matches: int
    test_matches: int
    summary: EvaluationSummary


@dataclass(frozen=True)
class LeagueEvaluation:
    league: str
    seasons: int
    folds: list[FoldEvaluation]
    summary: EvaluationSummary


@dataclass(frozen=True)
class EvaluationReport:
    generated_at: datetime
    model_name: str
    min_train_seasons: int
    min_edge: float
    max_edge: float
    leagues: list[LeagueEvaluation]
    overall: EvaluationSummary


@dataclass
class _Scored:
    model_probs: list[tuple[float, float, float]]
    model_actuals: list[int]
    market_probs: list[tuple[float, float, float]]
    market_actuals: list[int]
    bet_profits: list[float]

    @classmethod
    def empty(cls) -> _Scored:
        return cls([], [], [], [], [])

    def extend(self, other: _Scored) -> None:
        self.model_probs.extend(other.model_probs)
        self.model_actuals.extend(other.model_actuals)
        self.market_probs.extend(other.market_probs)
        self.market_actuals.extend(other.market_actuals)
        self.bet_profits.extend(other.bet_profits)


def _actual(match: EvaluationMatch) -> int:
    if match.home_goals > match.away_goals:
        return 0
    if match.home_goals == match.away_goals:
        return 1
    return 2


def _probability_metrics(
    probabilities: list[tuple[float, float, float]], actuals: list[int]
) -> ProbabilityMetrics:
    if not probabilities:
        return ProbabilityMetrics(0, 0.0, 0.0, 0.0, 0.0)

    hits = 0
    log_loss_sum = 0.0
    brier_sum = 0.0
    bins: list[list[tuple[float, float]]] = [[] for _ in range(10)]
    for probs, actual in zip(probabilities, actuals, strict=True):
        predicted = max(range(3), key=lambda index: probs[index])
        correct = float(predicted == actual)
        hits += int(correct)
        log_loss_sum -= log(max(probs[actual], EPSILON))
        brier_sum += sum(
            (prob - (1.0 if index == actual else 0.0)) ** 2
            for index, prob in enumerate(probs)
        )
        confidence = probs[predicted]
        bin_index = min(int(confidence * 10), 9)
        bins[bin_index].append((confidence, correct))

    count = len(probabilities)
    calibration_error = 0.0
    for bucket in bins:
        if not bucket:
            continue
        mean_confidence = sum(item[0] for item in bucket) / len(bucket)
        mean_accuracy = sum(item[1] for item in bucket) / len(bucket)
        calibration_error += len(bucket) / count * abs(mean_confidence - mean_accuracy)

    return ProbabilityMetrics(
        matches=count,
        accuracy=round(hits / count, 4),
        log_loss=round(log_loss_sum / count, 4),
        brier=round(brier_sum / count, 4),
        calibration_error=round(calibration_error, 4),
    )


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * quantile)]


def _strategy_metrics(
    profits: list[float], *, bootstrap_samples: int, seed: int
) -> StrategyMetrics:
    if not profits:
        return StrategyMetrics(0, 0, 0.0, None, None, None)
    roi = sum(profits) / len(profits)
    interval_low = interval_high = None
    if bootstrap_samples > 0:
        rng = Random(seed)
        bootstrapped = [
            sum(rng.choices(profits, k=len(profits))) / len(profits)
            for _ in range(bootstrap_samples)
        ]
        interval_low = round(_percentile(bootstrapped, 0.025), 4)
        interval_high = round(_percentile(bootstrapped, 0.975), 4)
    return StrategyMetrics(
        bets=len(profits),
        wins=sum(profit > 0 for profit in profits),
        profit=round(sum(profits), 2),
        roi=round(roi, 4),
        roi_ci_low=interval_low,
        roi_ci_high=interval_high,
    )


def _summary(scored: _Scored, *, bootstrap_samples: int, seed: int) -> EvaluationSummary:
    return EvaluationSummary(
        model=_probability_metrics(scored.model_probs, scored.model_actuals),
        market=_probability_metrics(scored.market_probs, scored.market_actuals),
        strategy=_strategy_metrics(
            scored.bet_profits,
            bootstrap_samples=bootstrap_samples,
            seed=seed,
        ),
    )


def _score_fold(
    train: list[EvaluationMatch],
    test: list[EvaluationMatch],
    *,
    rho: float,
    decay: float,
    shrinkage: float,
    min_edge: float,
    max_edge: float,
) -> _Scored:
    train_results = [
        MatchResult(row.home_team, row.away_team, row.home_goals, row.away_goals)
        for row in train
    ]
    strengths = fit_strengths(train_results, decay=decay)
    scored = _Scored.empty()

    for match in test:
        home_lambda, away_lambda = expected_goals(
            strengths, match.home_team, match.away_team
        )
        prediction = match_probabilities(
            home_lambda,
            away_lambda,
            rho=rho,
            shrinkage=shrinkage,
        )
        model_probs = (prediction.home_win, prediction.draw, prediction.away_win)
        actual = _actual(match)
        scored.model_probs.append(model_probs)
        scored.model_actuals.append(actual)

        odds = match.odds
        if odds is None:
            continue
        market_values = implied_probabilities(list(odds))
        if len(market_values) != 3:
            continue
        market_probs = (market_values[0], market_values[1], market_values[2])
        scored.market_probs.append(market_probs)
        scored.market_actuals.append(actual)

        candidates: list[tuple[float, int]] = []
        for index, (probability, price, market_probability) in enumerate(
            zip(model_probs, odds, market_probs, strict=True)
        ):
            edge = probability - market_probability
            expected_profit = probability * price - 1.0
            if min_edge <= edge <= max_edge and expected_profit > 0:
                candidates.append((expected_profit, index))
        if candidates:
            _, selection = max(candidates)
            scored.bet_profits.append(odds[selection] - 1.0 if selection == actual else -1.0)
    return scored


def evaluate_expanding_window(
    matches: list[EvaluationMatch],
    *,
    min_train_seasons: int = 4,
    rho: float = -0.10,
    decay: float = 0.008,
    shrinkage: float = 0.06,
    min_edge: float = 0.03,
    max_edge: float = 0.15,
    bootstrap_samples: int = 1000,
    seed: int = 42,
    generated_at: datetime | None = None,
) -> EvaluationReport:
    """Evaluate each league on successive unseen seasons and aggregate results."""
    if min_train_seasons < 1:
        raise ValueError("min_train_seasons must be >= 1")
    if not 0.0 <= min_edge <= max_edge <= 1.0:
        raise ValueError("edges must satisfy 0 <= min_edge <= max_edge <= 1")

    by_league: dict[str, list[EvaluationMatch]] = {}
    for match in sorted(matches, key=lambda item: item.kickoff_utc):
        by_league.setdefault(match.league, []).append(match)

    overall_scored = _Scored.empty()
    league_reports: list[LeagueEvaluation] = []
    for league in sorted(by_league):
        league_matches = by_league[league]
        seasons = sorted({match.season for match in league_matches})
        league_scored = _Scored.empty()
        folds: list[FoldEvaluation] = []
        for season_index in range(min_train_seasons, len(seasons)):
            test_season = seasons[season_index]
            training_seasons = set(seasons[:season_index])
            train = [match for match in league_matches if match.season in training_seasons]
            test = [match for match in league_matches if match.season == test_season]
            if not train or not test:
                continue
            fold_scored = _score_fold(
                train,
                test,
                rho=rho,
                decay=decay,
                shrinkage=shrinkage,
                min_edge=min_edge,
                max_edge=max_edge,
            )
            league_scored.extend(fold_scored)
            folds.append(
                FoldEvaluation(
                    league=league,
                    test_season=test_season,
                    train_matches=len(train),
                    test_matches=len(test),
                    summary=_summary(
                        fold_scored,
                        bootstrap_samples=bootstrap_samples,
                        seed=seed + season_index,
                    ),
                )
            )
        overall_scored.extend(league_scored)
        league_reports.append(
            LeagueEvaluation(
                league=league,
                seasons=len(seasons),
                folds=folds,
                summary=_summary(
                    league_scored,
                    bootstrap_samples=bootstrap_samples,
                    seed=seed + len(league_reports) * 100,
                ),
            )
        )

    return EvaluationReport(
        generated_at=generated_at or datetime.now().astimezone(),
        model_name="Dixon-Coles Poisson",
        min_train_seasons=min_train_seasons,
        min_edge=min_edge,
        max_edge=max_edge,
        leagues=league_reports,
        overall=_summary(
            overall_scored,
            bootstrap_samples=bootstrap_samples,
            seed=seed,
        ),
    )
