from datetime import UTC, datetime, timedelta

from oddsmith.odds_model.evaluation import EvaluationMatch, evaluate_expanding_window


def _dataset(seasons: int = 5, matches_per_season: int = 8) -> list[EvaluationMatch]:
    rows = []
    kickoff = datetime(2020, 8, 1, tzinfo=UTC)
    teams = ("A", "B", "C", "D")
    for season in range(2020, 2020 + seasons):
        for index in range(matches_per_season):
            home = teams[index % len(teams)]
            away = teams[(index + 1) % len(teams)]
            home_goals = 2 if index % 3 else 0
            away_goals = 0 if index % 2 else 1
            rows.append(
                EvaluationMatch(
                    league="Test League",
                    season=season,
                    kickoff_utc=kickoff,
                    home_team=home,
                    away_team=away,
                    home_goals=home_goals,
                    away_goals=away_goals,
                    odds_home=2.1,
                    odds_draw=3.4,
                    odds_away=3.8,
                )
            )
            kickoff += timedelta(days=7)
    return rows


def test_expanding_window_uses_only_complete_earlier_seasons():
    report = evaluate_expanding_window(
        _dataset(), min_train_seasons=2, bootstrap_samples=20
    )

    league = report.leagues[0]
    assert [fold.test_season for fold in league.folds] == [2022, 2023, 2024]
    assert [fold.train_matches for fold in league.folds] == [16, 24, 32]
    assert all(fold.test_matches == 8 for fold in league.folds)


def test_a_future_season_cannot_change_an_earlier_fold():
    original = _dataset()
    changed = list(original)
    last = changed[-1]
    changed[-1] = EvaluationMatch(
        **{
            **last.__dict__,
            "home_goals": 20,
            "away_goals": 20,
        }
    )

    first = evaluate_expanding_window(original, min_train_seasons=2, bootstrap_samples=0)
    second = evaluate_expanding_window(changed, min_train_seasons=2, bootstrap_samples=0)

    assert first.leagues[0].folds[0] == second.leagues[0].folds[0]


def test_metrics_and_one_pick_policy_are_sane():
    report = evaluate_expanding_window(
        _dataset(), min_train_seasons=2, min_edge=0.0, bootstrap_samples=50
    )
    summary = report.overall

    assert summary.model.matches == 24
    assert summary.market.matches == 24
    assert 0.0 <= summary.model.accuracy <= 1.0
    assert summary.model.log_loss >= 0.0
    assert summary.model.brier >= 0.0
    assert summary.strategy.bets <= summary.market.matches
    if summary.strategy.bets:
        assert summary.strategy.roi_ci_low is not None
        assert summary.strategy.roi_ci_high is not None
        assert summary.strategy.roi_ci_low <= summary.strategy.roi_ci_high


def test_missing_prices_still_scores_model_but_not_market_or_roi():
    rows = [
        EvaluationMatch(
            **{
                **match.__dict__,
                "odds_home": None,
                "odds_draw": None,
                "odds_away": None,
            }
        )
        for match in _dataset(seasons=3)
    ]
    report = evaluate_expanding_window(rows, min_train_seasons=2, bootstrap_samples=0)

    assert report.overall.model.matches == 8
    assert report.overall.market.matches == 0
    assert report.overall.strategy.bets == 0
    assert report.overall.strategy.roi is None


def test_invalid_evaluation_configuration_is_rejected():
    try:
        evaluate_expanding_window([], min_train_seasons=0)
    except ValueError as exc:
        assert "min_train_seasons" in str(exc)
    else:
        raise AssertionError("expected ValueError")
