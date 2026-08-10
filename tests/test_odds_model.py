from math import isclose

from oddsmith.odds_model.acca import Candidate, build_acca
from oddsmith.odds_model.backtest import backtest_1x2
from oddsmith.odds_model.poisson import MatchResult
from oddsmith.odds_model.value import (
    assess_value,
    expected_value,
    implied_probabilities,
)


def test_implied_probabilities_remove_margin_and_sum_to_one():
    # 1X2 book with an overround; de-margined probs must sum to 1.
    probs = implied_probabilities([2.0, 3.5, 4.0])
    assert isclose(sum(probs), 1.0, abs_tol=1e-9)


def test_expected_value_positive_when_model_beats_price():
    # Model says 55% but odds imply less -> EV positive.
    assert expected_value(0.55, 2.0) > 0
    # Model says 40% at evens -> EV negative.
    assert expected_value(0.40, 2.0) < 0


def test_assess_value_flags_positive_edge():
    pick = assess_value("home", model_prob=0.60, offered_odds=2.0, fair_implied_prob=0.50)
    assert pick.edge > 0
    assert pick.expected_value > 0
    assert pick.is_value


def test_assess_value_rejects_negative_edge():
    pick = assess_value("home", model_prob=0.40, offered_odds=1.8, fair_implied_prob=0.55)
    assert pick.edge < 0
    assert not pick.is_value


def _cand(fid, ev, edge, odds=2.0):
    pick = assess_value("home", model_prob=0.5 + edge, offered_odds=odds, fair_implied_prob=0.5)
    # Force deterministic ev/edge for ranking assertions.
    from dataclasses import replace

    pick = replace(pick, expected_value=ev, edge=edge)
    return Candidate(fid, f"H{fid}", f"A{fid}", "match_winner", pick)


def test_build_acca_picks_top_value_one_per_fixture():
    candidates = [
        _cand("1", ev=0.10, edge=0.05),
        _cand("1", ev=0.20, edge=0.06),  # same fixture, higher EV — only one allowed
        _cand("2", ev=0.15, edge=0.04),
        _cand("3", ev=0.05, edge=0.02),
    ]
    acca = build_acca(candidates, legs=5)
    fixture_ids = [leg.fixture_id for leg in acca.legs]
    assert len(fixture_ids) == len(set(fixture_ids))  # no duplicate fixtures
    assert fixture_ids[0] == "1"  # highest EV first


def test_build_acca_excludes_non_value_legs():
    neg = _cand("9", ev=-0.10, edge=-0.05)
    pos = _cand("1", ev=0.10, edge=0.05)
    acca = build_acca([neg, pos], legs=5)
    assert [leg.fixture_id for leg in acca.legs] == ["1"]


def test_acca_combined_odds_and_prob():
    a = _cand("1", ev=0.1, edge=0.05, odds=2.0)
    b = _cand("2", ev=0.1, edge=0.05, odds=3.0)
    from dataclasses import replace

    a = Candidate("1", "H", "A", "match_winner", replace(a.pick, model_prob=0.5))
    b = Candidate("2", "H", "A", "match_winner", replace(b.pick, model_prob=0.4))
    acca = build_acca([a, b], legs=5)
    assert isclose(acca.combined_odds, 6.0, abs_tol=1e-9)
    assert isclose(acca.combined_model_prob, 0.20, abs_tol=1e-9)


def test_backtest_produces_sane_metrics():
    # Strong beats weak consistently; model should predict home wins well.
    results = []
    for _ in range(10):
        results.append(MatchResult("Strong", "Weak", 3, 0))
        results.append(MatchResult("Mid", "Weak", 2, 0))
        results.append(MatchResult("Strong", "Mid", 2, 1))
    bt = backtest_1x2(results, train_fraction=0.7)
    assert bt.matches_scored > 0
    assert 0.0 <= bt.hit_rate <= 1.0
    assert bt.brier >= 0.0


def test_backtest_empty_is_safe():
    bt = backtest_1x2([], train_fraction=0.7)
    assert bt.matches_scored == 0
    assert bt.roi is None


def test_empty_acca_has_no_expected_value():
    # -1.0 would read as "guaranteed total loss" rather than "no bet".
    assert build_acca([], legs=5).combined_expected_value == 0.0
