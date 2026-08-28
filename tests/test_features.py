from datetime import UTC, datetime, timedelta

from oddsmith.data.features import build_training_examples
from oddsmith.db import MatchObservation


def _match(
    day: int, home_goals: int, away_goals: int, *, league: str = "EPL"
) -> MatchObservation:
    return MatchObservation(
        source_key=f"match:{day}",
        source="test",
        league=league,
        season=2025,
        kickoff_utc=datetime(2025, 8, 1, tzinfo=UTC) + timedelta(days=day),
        home_team="Home",
        away_team="Away",
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
