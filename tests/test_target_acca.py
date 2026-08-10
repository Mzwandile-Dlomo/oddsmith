from dataclasses import replace
from math import isclose, prod

from oddsmith.odds_model.acca import Candidate
from oddsmith.odds_model.target_acca import build_target_acca
from oddsmith.odds_model.value import assess_value


def _cand(fixture_id: str, model_prob: float, odds: float, *, value: bool = True) -> Candidate:
    """A candidate with an explicit model probability and price.

    ``fair_implied_prob`` is set below/above ``model_prob`` to control whether the
    pick reads as value, so tests can exercise the value filter directly.
    """
    fair = model_prob - 0.05 if value else model_prob + 0.05
    pick = assess_value("Home", model_prob=model_prob, offered_odds=odds, fair_implied_prob=fair)
    return Candidate(fixture_id, f"H{fixture_id}", f"A{fixture_id}", "match_winner", pick)


def test_clears_the_target_price():
    candidates = [
        _cand("1", 0.85, 1.25),
        _cand("2", 0.80, 1.30),
        _cand("3", 0.75, 1.35),
    ]
    acca = build_target_acca(candidates, target_odds=1.5, max_legs=4)

    assert acca.target_met
    assert acca.combined_odds >= 1.5


def test_prefers_the_likeliest_slip_that_clears_the_target():
    # Both routes clear 1.5, but the pair of short favourites is far likelier to
    # land than the single coin flip, so the builder must choose it.
    safe_a = _cand("1", 0.90, 1.25)
    safe_b = _cand("2", 0.88, 1.25)
    coin_flip = _cand("3", 0.52, 1.90)

    acca = build_target_acca(
        [coin_flip, safe_a, safe_b], target_odds=1.5, max_legs=4, min_leg_prob=0.5
    )

    assert acca.target_met
    assert {leg.fixture_id for leg in acca.legs} == {"1", "2"}
    assert acca.combined_model_prob > 0.75


def test_does_not_overshoot_the_target():
    # A single 3.0 leg clears 1.5 in one step but throws away probability. Two
    # short legs that land just past the target are the better slip.
    longshot = _cand("9", 0.40, 3.00)
    short_a = _cand("1", 0.92, 1.22)
    short_b = _cand("2", 0.91, 1.24)

    acca = build_target_acca(
        [longshot, short_a, short_b], target_odds=1.5, max_legs=4, min_leg_prob=0.3
    )

    assert acca.target_met
    assert "9" not in {leg.fixture_id for leg in acca.legs}
    assert acca.combined_model_prob > 0.80


def test_at_most_one_leg_per_fixture():
    # Same fixture offered three ways; only one may be used.
    candidates = [
        _cand("1", 0.85, 1.20),
        _cand("1", 0.84, 1.22),
        _cand("1", 0.83, 1.24),
        _cand("2", 0.86, 1.30),
    ]
    acca = build_target_acca(candidates, target_odds=1.5, max_legs=4)

    fixture_ids = [leg.fixture_id for leg in acca.legs]
    assert len(fixture_ids) == len(set(fixture_ids))


def test_respects_max_legs():
    candidates = [_cand(str(i), 0.95, 1.05) for i in range(20)]
    acca = build_target_acca(candidates, target_odds=1.5, max_legs=3, min_leg_prob=0.5)

    assert len(acca.legs) <= 3


def test_filters_out_low_probability_legs():
    candidates = [_cand("1", 0.35, 2.60), _cand("2", 0.30, 3.00)]
    acca = build_target_acca(candidates, target_odds=1.5, max_legs=4, min_leg_prob=0.60)

    assert acca.legs == []
    assert acca.pool_size == 0
    assert not acca.target_met


def test_value_filter_is_on_by_default():
    non_value = _cand("1", 0.85, 1.25, value=False)
    acca = build_target_acca([non_value], target_odds=1.5, max_legs=4)
    assert acca.legs == []

    # ...and can be relaxed deliberately.
    relaxed = build_target_acca([non_value], target_odds=1.5, max_legs=4, require_value=False)
    assert len(relaxed.legs) == 1


def test_unreachable_target_returns_best_effort_flagged():
    # Two short legs cannot reach 5.0; we still want the closest slip, marked.
    candidates = [_cand("1", 0.90, 1.20), _cand("2", 0.90, 1.20)]
    acca = build_target_acca(candidates, target_odds=5.0, max_legs=4)

    assert not acca.target_met
    assert len(acca.legs) == 2
    assert acca.combined_odds < 5.0


def test_empty_candidates_is_safe():
    acca = build_target_acca([], target_odds=1.5)
    assert acca.legs == []
    assert not acca.target_met
    assert acca.combined_odds == 0.0


def test_combined_figures_match_the_legs():
    candidates = [_cand("1", 0.80, 1.30), _cand("2", 0.75, 1.40)]
    acca = build_target_acca(candidates, target_odds=1.5, max_legs=4)

    expected_odds = prod(leg.pick.offered_odds for leg in acca.legs)
    expected_prob = prod(leg.pick.model_prob for leg in acca.legs)
    assert isclose(acca.combined_odds, round(expected_odds, 2), abs_tol=1e-9)
    assert isclose(acca.combined_model_prob, round(expected_prob, 4), abs_tol=1e-9)


def test_certain_leg_does_not_divide_by_zero():
    # A model probability of 1.0 would make efficiency infinite; it is capped.
    certain = _cand("1", 0.99, 1.10)
    certain = Candidate(
        "1", "H", "A", "match_winner", replace(certain.pick, model_prob=1.0)
    )
    acca = build_target_acca([certain, _cand("2", 0.90, 1.40)], target_odds=1.5, max_legs=4)

    assert acca.target_met


def test_implausible_edges_are_discarded():
    # Model says 92% on a line the book prices near 45%. That is a bad fit, not a
    # 100% edge — and stake sizing would bet it hardest, so it must be dropped.
    too_good = _cand("1", 0.92, 2.23)
    too_good = Candidate(
        "1", "H", "A", "over_under", replace(too_good.pick, edge=0.333)
    )
    sane = _cand("2", 0.80, 1.60)

    acca = build_target_acca([too_good, sane], target_odds=1.5, max_legs=4)

    assert "1" not in {leg.fixture_id for leg in acca.legs}
    assert acca.pool_size == 1


def test_max_edge_is_tunable():
    too_good = _cand("1", 0.92, 2.23)
    too_good = Candidate("1", "H", "A", "over_under", replace(too_good.pick, edge=0.333))

    # Raising the ceiling deliberately lets it back in.
    acca = build_target_acca([too_good], target_odds=1.5, max_legs=4, max_edge=0.5)
    assert len(acca.legs) == 1
