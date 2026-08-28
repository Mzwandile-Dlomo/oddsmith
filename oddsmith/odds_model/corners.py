"""Expanding-window total-corners count-model evaluation.

This benchmark measures count accuracy only. Without historical corner lines
and prices it cannot estimate betting ROI, and the report makes that limitation
explicit instead of inventing a synthetic market.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import log, nan, sqrt
from random import Random

from sklearn.ensemble import HistGradientBoostingRegressor

from oddsmith.data.features import TrainingExample


@dataclass(frozen=True)
class CornerMetrics:
    matches: int
    mean_actual: float
    mean_prediction: float
    mae: float
    rmse: float
    poisson_deviance: float


@dataclass(frozen=True)
class CornerSummary:
    model: CornerMetrics
    baseline: CornerMetrics
    mae_improvement: float
    improvement_ci_low: float | None
    improvement_ci_high: float | None


@dataclass(frozen=True)
class CornerFoldEvaluation:
    league: str
    test_season: int
    train_matches: int
    test_matches: int
    summary: CornerSummary


@dataclass(frozen=True)
class CornerLeagueEvaluation:
    league: str
    seasons: int
    folds: list[CornerFoldEvaluation]
    summary: CornerSummary


@dataclass(frozen=True)
class CornerEvaluationReport:
    generated_at: datetime
    model_name: str
    min_train_seasons: int
    leagues: list[CornerLeagueEvaluation]
    overall: CornerSummary
    odds_rows: int
    roi_validated: bool
    limitation: str


@dataclass
class _Predictions:
    actuals: list[float]
    model: list[float]
    baseline: list[float]

    @classmethod
    def empty(cls) -> _Predictions:
        return cls([], [], [])

    def extend(self, other: _Predictions) -> None:
        self.actuals.extend(other.actuals)
        self.model.extend(other.model)
        self.baseline.extend(other.baseline)


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


def _metrics(actuals: list[float], predictions: list[float]) -> CornerMetrics:
    if not actuals:
        return CornerMetrics(0, 0.0, 0.0, 0.0, 0.0, 0.0)
    squared_error = 0.0
    absolute_error = 0.0
    deviance = 0.0
    for actual, raw_prediction in zip(actuals, predictions, strict=True):
        prediction = max(raw_prediction, 1e-9)
        error = actual - prediction
        squared_error += error**2
        absolute_error += abs(error)
        deviance += 2.0 * (
            actual * log(actual / prediction) - (actual - prediction)
            if actual > 0
            else prediction
        )
    count = len(actuals)
    return CornerMetrics(
        matches=count,
        mean_actual=round(sum(actuals) / count, 4),
        mean_prediction=round(sum(predictions) / count, 4),
        mae=round(absolute_error / count, 4),
        rmse=round(sqrt(squared_error / count), 4),
        poisson_deviance=round(deviance / count, 4),
    )


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * quantile)]


def _summary(
    predictions: _Predictions, *, bootstrap_samples: int, seed: int
) -> CornerSummary:
    model = _metrics(predictions.actuals, predictions.model)
    baseline = _metrics(predictions.actuals, predictions.baseline)
    paired = [
        abs(actual - baseline_prediction) - abs(actual - model_prediction)
        for actual, model_prediction, baseline_prediction in zip(
            predictions.actuals,
            predictions.model,
            predictions.baseline,
            strict=True,
        )
    ]
    improvement = sum(paired) / len(paired) if paired else 0.0
    low = high = None
    if paired and bootstrap_samples > 0:
        rng = Random(seed)
        samples = [
            sum(rng.choices(paired, k=len(paired))) / len(paired)
            for _ in range(bootstrap_samples)
        ]
        low = round(_percentile(samples, 0.025), 4)
        high = round(_percentile(samples, 0.975), 4)
    return CornerSummary(
        model=model,
        baseline=baseline,
        mae_improvement=round(improvement, 4),
        improvement_ci_low=low,
        improvement_ci_high=high,
    )


def evaluate_corner_counts(
    examples: list[TrainingExample],
    *,
    min_train_seasons: int = 4,
    bootstrap_samples: int = 1000,
    seed: int = 42,
    generated_at: datetime | None = None,
) -> CornerEvaluationReport:
    """Compare a pooled Poisson boosted regressor with prior league means."""
    if min_train_seasons < 1:
        raise ValueError("min_train_seasons must be >= 1")

    usable = sorted(
        (example for example in examples if example.total_corners_label is not None),
        key=lambda example: example.kickoff_utc,
    )
    seasons = sorted({example.season for example in usable})
    leagues = sorted({example.league for example in usable})
    feature_names = sorted({name for example in usable for name in example.features})
    league_folds: dict[str, list[CornerFoldEvaluation]] = {
        league: [] for league in leagues
    }
    league_totals = {league: _Predictions.empty() for league in leagues}
    overall = _Predictions.empty()

    for season_index in range(min_train_seasons, len(seasons)):
        test_season = seasons[season_index]
        training_seasons = set(seasons[:season_index])
        train = [example for example in usable if example.season in training_seasons]
        test = [example for example in usable if example.season == test_season]
        if not train or not test:
            continue

        model = HistGradientBoostingRegressor(
            loss="poisson",
            learning_rate=0.05,
            max_iter=200,
            max_leaf_nodes=15,
            min_samples_leaf=30,
            l2_regularization=1.0,
            random_state=seed + season_index,
        )
        model.fit(
            _matrix(train, feature_names=feature_names, leagues=leagues),
            [float(example.total_corners_label) for example in train],
        )
        model_predictions = model.predict(
            _matrix(test, feature_names=feature_names, leagues=leagues)
        )
        league_means = {
            league: sum(
                float(example.total_corners_label)
                for example in train
                if example.league == league
            )
            / sum(example.league == league for example in train)
            for league in leagues
            if any(example.league == league for example in train)
        }
        for league in leagues:
            league_rows = [
                (example, float(prediction))
                for example, prediction in zip(test, model_predictions, strict=True)
                if example.league == league and league in league_means
            ]
            if not league_rows:
                continue
            scored = _Predictions(
                actuals=[float(row.total_corners_label) for row, _ in league_rows],
                model=[max(prediction, 1e-9) for _, prediction in league_rows],
                baseline=[league_means[league]] * len(league_rows),
            )
            league_totals[league].extend(scored)
            overall.extend(scored)
            league_folds[league].append(
                CornerFoldEvaluation(
                    league=league,
                    test_season=test_season,
                    train_matches=len(train),
                    test_matches=len(league_rows),
                    summary=_summary(
                        scored,
                        bootstrap_samples=bootstrap_samples,
                        seed=seed + season_index,
                    ),
                )
            )

    reports = [
        CornerLeagueEvaluation(
            league=league,
            seasons=len({row.season for row in usable if row.league == league}),
            folds=league_folds[league],
            summary=_summary(
                league_totals[league],
                bootstrap_samples=bootstrap_samples,
                seed=seed + index * 100,
            ),
        )
        for index, league in enumerate(leagues)
    ]
    return CornerEvaluationReport(
        generated_at=generated_at or datetime.now().astimezone(),
        model_name="Poisson HistGradientBoosting total corners",
        min_train_seasons=min_train_seasons,
        leagues=reports,
        overall=_summary(overall, bootstrap_samples=bootstrap_samples, seed=seed),
        odds_rows=0,
        roi_validated=False,
        limitation="Historical corner lines and prices are unavailable; ROI is not estimable.",
    )
