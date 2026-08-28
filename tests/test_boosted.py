from datetime import UTC, datetime, timedelta

from oddsmith.data.features import TrainingExample
from oddsmith.odds_model.boosted import evaluate_calibrated_boosted


def _examples() -> list[TrainingExample]:
    examples: list[TrainingExample] = []
    kickoff = datetime(2020, 8, 1, tzinfo=UTC)
    for season in range(2020, 2025):
        for league_index, league in enumerate(("EPL", "LaLiga")):
            for match_index in range(18):
                label = match_index % 3
                market = (
                    (0.55, 0.25, 0.20)
                    if label == 0
                    else (0.30, 0.40, 0.30)
                    if label == 1
                    else (0.20, 0.25, 0.55)
                )
                examples.append(
                    TrainingExample(
                        source_key=f"{league}:{season}:{match_index}",
                        league=league,
                        season=season,
                        kickoff_utc=kickoff
                        + timedelta(days=(season - 2020) * 365 + match_index),
                        home_team=f"Home {league_index}",
                        away_team=f"Away {league_index}",
                        features={
                            "home_points_avg": float(label == 0),
                            "away_points_avg": float(label == 2),
                            "market_home_prob": market[0],
                            "market_draw_prob": market[1],
                            "market_away_prob": market[2],
                        },
                        result_label=label,
                        over_2_5_label=0,
                        btts_label=0,
                        total_corners_label=8,
                        close_home_odds=1.0 / market[0],
                        close_draw_odds=1.0 / market[1],
                        close_away_odds=1.0 / market[2],
                    )
                )
    return examples


def test_boosted_challenger_reserves_prior_season_for_calibration():
    report = evaluate_calibrated_boosted(
        _examples(), min_train_seasons=4, bootstrap_samples=20
    )

    assert report.model_name == "Calibrated HistGradientBoosting 1X2"
    assert report.overall.model.matches == 36
    assert report.overall.market.matches == 36
    assert {league.league for league in report.leagues} == {"EPL", "LaLiga"}
    assert all(len(league.folds) == 1 for league in report.leagues)
    assert all(league.folds[0].test_season == 2024 for league in report.leagues)
    assert all(league.folds[0].train_matches == 144 for league in report.leagues)


def test_boosted_challenger_rejects_missing_calibration_season():
    try:
        evaluate_calibrated_boosted([], min_train_seasons=1)
    except ValueError as exc:
        assert "calibration" in str(exc)
    else:
        raise AssertionError("expected ValueError")
