from datetime import UTC, datetime, timedelta

from oddsmith.data.features import build_training_examples
from oddsmith.db import MatchObservation


def _match(
    day: int,
    home_goals: int,
    away_goals: int,
    *,
    league: str = "EPL",
    home: str = "Home",
    away: str = "Away",
) -> MatchObservation:
    return MatchObservation(
        source_key=f"match:{day}",
        source="test",
        league=league,
        season=2025,
        kickoff_utc=datetime(2025, 8, 1, tzinfo=UTC) + timedelta(days=day),
        home_team=home,
        away_team=away,
        home_goals=home_goals,
        away_goals=away_goals,
        home_shots=10 + day,
        away_shots=5 + day,
        home_shots_on_target=5,
        away_shots_on_target=2,
        home_corners=6,
        away_corners=3,
        home_yellow_cards=1,
        away_yellow_cards=2,
        home_red_cards=0,
        away_red_cards=0,
        close_home_odds=2.0,
        close_draw_odds=3.5,
        close_away_odds=4.0,
        raw_payload={},
    )


def test_features_use_only_matches_before_kickoff():
    first = _match(0, 2, 0)
    second = _match(7, 9, 8)

    examples = build_training_examples([second, first], window=5, min_team_matches=1)

    assert len(examples) == 1
    example = examples[0]
    assert example.source_key == "match:7"
    assert example.features["home_goals_for_avg"] == 2.0
    assert example.features["away_goals_for_avg"] == 0.0
    assert example.features["home_shots_for_avg"] == 10.0
    assert example.features["home_rest_days"] == 7.0
    assert example.result_label == 0
    assert example.total_corners_label == 9


def test_market_probabilities_are_demargined():
    examples = build_training_examples([_match(0, 1, 0)], min_team_matches=0)
    features = examples[0].features

    total = sum(
        features[key]
        for key in ("market_home_prob", "market_draw_prob", "market_away_prob")
        if features[key] is not None
    )
    assert abs(total - 1.0) < 0.00001


def test_team_history_is_isolated_by_league():
    examples = build_training_examples(
        [
            _match(0, 2, 0, league="EPL"),
            _match(7, 1, 1, league="LaLiga"),
            _match(14, 3, 0, league="LaLiga"),
        ],
        min_team_matches=1,
    )

    assert len(examples) == 1
    assert examples[0].league == "LaLiga"
    assert examples[0].features["home_goals_for_avg"] == 1.0


def test_invalid_feature_window_is_rejected():
    try:
        build_training_examples([], window=0)
    except ValueError as exc:
        assert "window" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_extra_feature_groups_are_off_by_default():
    # The published boosted and corner benchmarks train on every feature key, so
    # the default output must not gain columns silently.
    examples = build_training_examples([_match(0, 1, 0), _match(7, 2, 2)], min_team_matches=1)

    keys = examples[0].features.keys()
    assert not any("venue" in key or key.startswith("h2h_") for key in keys)


def test_venue_features_use_only_same_venue_history():
    matches = [
        _match(0, 3, 0, home="A", away="B"),  # A at home
        _match(7, 0, 4, home="C", away="A"),  # A away: must not enter A's home form
        _match(14, 1, 1, home="A", away="C"),
    ]

    examples = build_training_examples(
        matches, min_team_matches=1, extra_features={"venue"}
    )
    last = next(example for example in examples if example.source_key == "match:14")

    assert last.features["home_venue_matches"] == 1.0
    assert last.features["home_venue_goals_for_avg"] == 3.0
    assert last.features["home_venue_points_avg"] == 3.0
    assert last.features["away_venue_matches"] == 0.0
    assert last.features["away_venue_goals_for_avg"] is None


def test_h2h_is_scored_from_current_home_team_side():
    matches = [
        _match(0, 2, 0, home="A", away="B"),
        _match(7, 1, 1, home="B", away="A"),
        _match(14, 0, 0, home="B", away="A"),
    ]

    examples = build_training_examples(matches, min_team_matches=1, extra_features={"h2h"})
    by_key = {example.source_key: example.features for example in examples}

    # Match 7: B hosts A; the only prior meeting was a 2-0 loss for B.
    assert by_key["match:7"]["h2h_matches"] == 1.0
    assert by_key["match:7"]["h2h_home_points_avg"] == 0.0
    assert by_key["match:7"]["h2h_home_goal_diff_avg"] == -2.0
    # Match 14 sees both earlier meetings but never its own result.
    assert by_key["match:14"]["h2h_matches"] == 2.0
    assert by_key["match:14"]["h2h_home_points_avg"] == 0.5
    assert by_key["match:14"]["h2h_home_goal_diff_avg"] == -1.0


def test_extra_features_keep_the_same_example_rows():
    matches = [
        _match(day, day % 3, day % 2, home=home, away=away)
        for day, (home, away) in enumerate(
            [("A", "B"), ("C", "D"), ("B", "C"), ("D", "A"), ("A", "C"), ("B", "D")]
        )
    ]

    baseline = build_training_examples(matches, min_team_matches=1)
    candidate = build_training_examples(
        matches, min_team_matches=1, extra_features={"venue", "h2h"}
    )

    assert [e.source_key for e in baseline] == [e.source_key for e in candidate]
    for base, cand in zip(baseline, candidate, strict=True):
        assert base.features.items() <= cand.features.items()


def test_unknown_feature_group_is_rejected():
    try:
        build_training_examples([], extra_features={"xgboost"})
    except ValueError as exc:
        assert "xgboost" in str(exc)
    else:
        raise AssertionError("expected ValueError")
