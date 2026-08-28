from datetime import UTC, datetime, timedelta

from oddsmith.data.features import TrainingExample
from oddsmith.odds_model.corners import evaluate_corner_counts


def _examples() -> list[TrainingExample]:
    examples: list[TrainingExample] = []
    kickoff = datetime(2020, 8, 1, tzinfo=UTC)
    for season in range(2020, 2025):
        for league in ("EPL", "LaLiga"):
            for match_index in range(36):
                total = 7 + match_index % 6
                examples.append(
                    TrainingExample(
                        source_key=f"{league}:{season}:{match_index}",
                        league=league,
                        season=season,
                        kickoff_utc=kickoff
                        + timedelta(days=(season - 2020) * 365 + match_index),
                        home_team="Home",
                        away_team="Away",
                        features={
                            "home_corners_for_avg": float(total - 4),
                            "away_corners_for_avg": 4.0,
                        },
                        result_label=0,
                        over_2_5_label=0,
                        btts_label=0,
                        total_corners_label=total,
                        close_home_odds=None,
                        close_draw_odds=None,
                        close_away_odds=None,
                    )
                )
    return examples


def test_corner_count_model_uses_unseen_season_and_reports_no_roi():
    report = evaluate_corner_counts(
        _examples(), min_train_seasons=4, bootstrap_samples=20
    )

    assert report.overall.model.matches == 72
    assert report.overall.baseline.matches == 72
    assert report.roi_validated is False
    assert report.odds_rows == 0
    assert all(len(league.folds) == 1 for league in report.leagues)
    assert all(league.folds[0].test_season == 2024 for league in report.leagues)


def test_corner_count_model_rejects_invalid_window():
    try:
        evaluate_corner_counts([], min_train_seasons=0)
    except ValueError as exc:
        assert "min_train_seasons" in str(exc)
    else:
        raise AssertionError("expected ValueError")
