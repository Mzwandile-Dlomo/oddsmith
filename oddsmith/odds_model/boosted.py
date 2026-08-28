"""Calibrated gradient-boosted 1X2 challenger with temporal evaluation.

The base model is fit on older complete seasons. The immediately preceding
season is reserved for probability calibration, and the following season is
the unseen test fold. A pooled model learns from every configured league while
league one-hot features preserve competition-specific effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import nan

from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.frozen import FrozenEstimator

from oddsmith.data.features import TrainingExample
from oddsmith.odds_model.evaluation import (
    EvaluationReport,
    EvaluationSummary,
    FoldEvaluation,
    LeagueEvaluation,
    select_bet_profit,
    summarize_predictions,
)
from oddsmith.odds_model.value import implied_probabilities


@dataclass
class _Predictions:
    model_probs: list[tuple[float, float, float]]
    actuals: list[int]
    market_probs: list[tuple[float, float, float]]
    profits: list[float]

    @classmethod
    def empty(cls) -> _Predictions:
        return cls([], [], [], [])

    def extend(self, other: _Predictions) -> None:
        self.model_probs.extend(other.model_probs)
        self.actuals.extend(other.actuals)
        self.market_probs.extend(other.market_probs)
        self.profits.extend(other.profits)

    def summary(self, *, bootstrap_samples: int, seed: int) -> EvaluationSummary:
        return summarize_predictions(
            model_probs=self.model_probs,
            model_actuals=self.actuals,
            market_probs=self.market_probs,
            market_actuals=self.actuals,
            bet_profits=self.profits,
            bootstrap_samples=bootstrap_samples,
            seed=seed,
        )


def _complete_odds(example: TrainingExample) -> tuple[float, float, float] | None:
    values = (
        example.close_home_odds,
        example.close_draw_odds,
        example.close_away_odds,
    )
    if any(value is None or value <= 1.0 for value in values):
        return None
    return values  # type: ignore[return-value]


def _matrix(
    examples: list[TrainingExample],
    *,
    feature_names: list[str],
    leagues: list[str],
) -> list[list[float]]:
    return [
        [
            nan if example.features.get(name) is None else float(example.features[name])
            for name in feature_names
        ]
        + [float(example.league == league) for league in leagues]
        for example in examples
    ]


def _fit_fold(
    base_examples: list[TrainingExample],
    calibration_examples: list[TrainingExample],
    test_examples: list[TrainingExample],
    *,
    feature_names: list[str],
    leagues: list[str],
    min_edge: float,
    max_edge: float,
    seed: int,
) -> dict[str, _Predictions]:
    base = HistGradientBoostingClassifier(
        learning_rate=0.05,
        max_iter=200,
        max_leaf_nodes=15,
        min_samples_leaf=30,
        l2_regularization=1.0,
        random_state=seed,
    )
    base.fit(
        _matrix(base_examples, feature_names=feature_names, leagues=leagues),
        [example.result_label for example in base_examples],
    )
    model = CalibratedClassifierCV(FrozenEstimator(base), method="sigmoid")
    model.fit(
        _matrix(calibration_examples, feature_names=feature_names, leagues=leagues),
        [example.result_label for example in calibration_examples],
    )

    probabilities = model.predict_proba(
        _matrix(test_examples, feature_names=feature_names, leagues=leagues)
    )
    class_positions = {int(label): index for index, label in enumerate(model.classes_)}
    scored = {league: _Predictions.empty() for league in leagues}
    for example, row in zip(test_examples, probabilities, strict=True):
        model_probs = tuple(float(row[class_positions[label]]) for label in range(3))
        odds = _complete_odds(example)
        if odds is None:
            continue
        market_values = implied_probabilities(list(odds))
        market_probs = (market_values[0], market_values[1], market_values[2])
        league_scored = scored[example.league]
        league_scored.model_probs.append(model_probs)
        league_scored.actuals.append(example.result_label)
        league_scored.market_probs.append(market_probs)
        profit = select_bet_profit(
            model_probs=model_probs,
            market_probs=market_probs,
            odds=odds,
            actual=example.result_label,
            min_edge=min_edge,
            max_edge=max_edge,
        )
        if profit is not None:
            league_scored.profits.append(profit)
    return scored


def evaluate_calibrated_boosted(
    examples: list[TrainingExample],
    *,
    min_train_seasons: int = 4,
    min_edge: float = 0.03,
    max_edge: float = 0.15,
    bootstrap_samples: int = 1000,
    seed: int = 42,
    generated_at: datetime | None = None,
) -> EvaluationReport:
    """Run pooled expanding-window folds with a held-out calibration season."""
    if min_train_seasons < 2:
        raise ValueError("min_train_seasons must be >= 2 to reserve calibration data")
    if not 0.0 <= min_edge <= max_edge <= 1.0:
        raise ValueError("edges must satisfy 0 <= min_edge <= max_edge <= 1")

    usable = sorted(
        (example for example in examples if _complete_odds(example) is not None),
        key=lambda example: example.kickoff_utc,
    )
    seasons = sorted({example.season for example in usable})
    leagues = sorted({example.league for example in usable})
    feature_names = sorted(
        {name for example in usable for name in example.features}
    )
    overall = _Predictions.empty()
    league_totals = {league: _Predictions.empty() for league in leagues}
    league_folds: dict[str, list[FoldEvaluation]] = {league: [] for league in leagues}

    for season_index in range(min_train_seasons, len(seasons)):
        test_season = seasons[season_index]
        calibration_season = seasons[season_index - 1]
        base_seasons = set(seasons[: season_index - 1])
        base_examples = [example for example in usable if example.season in base_seasons]
        calibration_examples = [
            example for example in usable if example.season == calibration_season
        ]
        test_examples = [example for example in usable if example.season == test_season]
        if not base_examples or not calibration_examples or not test_examples:
            continue
        if set(range(3)) - {example.result_label for example in base_examples}:
            continue
        if set(range(3)) - {example.result_label for example in calibration_examples}:
            continue

        fold_results = _fit_fold(
            base_examples,
            calibration_examples,
            test_examples,
            feature_names=feature_names,
            leagues=leagues,
            min_edge=min_edge,
            max_edge=max_edge,
            seed=seed + season_index,
        )
        for league, scored in fold_results.items():
            if not scored.actuals:
                continue
            league_totals[league].extend(scored)
            overall.extend(scored)
            league_folds[league].append(
                FoldEvaluation(
                    league=league,
                    test_season=test_season,
                    train_matches=len(base_examples) + len(calibration_examples),
                    test_matches=len(scored.actuals),
                    summary=scored.summary(
                        bootstrap_samples=bootstrap_samples,
                        seed=seed + season_index,
                    ),
                )
            )

    league_reports = [
        LeagueEvaluation(
            league=league,
            seasons=len({example.season for example in usable if example.league == league}),
            folds=league_folds[league],
            summary=league_totals[league].summary(
                bootstrap_samples=bootstrap_samples,
                seed=seed + index * 100,
            ),
        )
        for index, league in enumerate(leagues)
    ]
    return EvaluationReport(
        generated_at=generated_at or datetime.now().astimezone(),
        model_name="Calibrated HistGradientBoosting 1X2",
        min_train_seasons=min_train_seasons,
        min_edge=min_edge,
        max_edge=max_edge,
        leagues=league_reports,
        overall=overall.summary(bootstrap_samples=bootstrap_samples, seed=seed),
    )
