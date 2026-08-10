from math import isclose

from oddsmith.odds_model.poisson import (
    MatchResult,
    expected_goals,
    fit_strengths,
    match_probabilities,
    poisson_pmf,
    probability_to_odds,
)


def test_poisson_pmf_known_values():
    # Poisson(lambda=1): P(0)=P(1)=e^-1 ~= 0.3679
    assert isclose(poisson_pmf(0, 1.0), 0.36788, abs_tol=1e-4)
    assert isclose(poisson_pmf(1, 1.0), 0.36788, abs_tol=1e-4)
    assert isclose(poisson_pmf(2, 1.0), 0.18394, abs_tol=1e-4)


def test_poisson_pmf_zero_lambda():
    assert poisson_pmf(0, 0.0) == 1.0
    assert poisson_pmf(1, 0.0) == 0.0


def test_probabilities_sum_to_one():
    probs = match_probabilities(1.4, 1.1)
    assert isclose(probs.home_win + probs.draw + probs.away_win, 1.0, abs_tol=1e-6)
    assert isclose(probs.over_2_5 + probs.under_2_5, 1.0, abs_tol=1e-6)
    assert isclose(probs.btts_yes + probs.btts_no, 1.0, abs_tol=1e-6)


def test_higher_home_lambda_favours_home():
    probs = match_probabilities(2.5, 0.8)
    assert probs.home_win > probs.away_win
    assert probs.home_win > probs.draw


def test_equal_lambdas_symmetric():
    probs = match_probabilities(1.3, 1.3)
    assert isclose(probs.home_win, probs.away_win, abs_tol=1e-9)


def test_more_goals_expected_raises_over():
    low = match_probabilities(0.8, 0.7)
    high = match_probabilities(2.2, 2.0)
    assert high.over_2_5 > low.over_2_5


def test_probability_to_odds_is_inverse():
    assert probability_to_odds(0.5) == 2.0
    assert probability_to_odds(0.25) == 4.0
    assert probability_to_odds(0.0) is None


def test_probability_to_odds_applies_margin():
    fair = probability_to_odds(0.5)
    with_margin = probability_to_odds(0.5, margin=0.05)
    assert with_margin is not None and fair is not None
    assert with_margin < fair


def test_fit_strengths_recovers_dominant_team():
    # Alpha thrashes everyone; Zeta loses everything. Alpha's attack should
    # exceed Zeta's, and Alpha's defence number (goals conceded ratio) lower.
    results = [
        MatchResult("Alpha", "Zeta", 4, 0),
        MatchResult("Alpha", "Mid", 3, 1),
        MatchResult("Mid", "Zeta", 2, 0),
        MatchResult("Zeta", "Alpha", 0, 3),
        MatchResult("Mid", "Alpha", 1, 2),
        MatchResult("Zeta", "Mid", 0, 2),
    ]
    s = fit_strengths(results)
    assert s.attack["Alpha"] > s.attack["Zeta"]
    assert s.defence["Alpha"] < s.defence["Zeta"]


def test_fit_empty_results_is_neutral():
    s = fit_strengths([])
    assert s.attack == {}
    assert s.defence == {}


def test_dixon_coles_keeps_probabilities_normalised():
    probs = match_probabilities(1.4, 1.1, rho=-0.10)
    assert isclose(probs.home_win + probs.draw + probs.away_win, 1.0, abs_tol=1e-6)
    assert isclose(probs.over_2_5 + probs.under_2_5, 1.0, abs_tol=1e-6)
    assert isclose(probs.btts_yes + probs.btts_no, 1.0, abs_tol=1e-6)


def test_recency_decay_weights_recent_matches_more():
    early_weak = [MatchResult("Rise", "Foe", 0, 3) for _ in range(6)]
    late_strong = [MatchResult("Rise", "Foe", 3, 0) for _ in range(6)]
    chronological = early_weak + late_strong
    no_decay = fit_strengths(chronological, decay=0.0)
    with_decay = fit_strengths(chronological, decay=0.10)
    assert with_decay.attack["Rise"] > no_decay.attack["Rise"]


def test_shrinkage_curbs_overconfidence_without_flipping_favourite():
    # A lopsided match: raw model is very confident of a home win.
    raw = match_probabilities(3.0, 0.4)
    shrunk = match_probabilities(3.0, 0.4, shrinkage=0.06)
    # Shrinkage pulls the favourite down toward uniform...
    assert shrunk.home_win < raw.home_win
    # ...lifts the long shots up...
    assert shrunk.away_win > raw.away_win
    # ...but home is still clearly the favourite and probs still sum to 1.
    assert shrunk.home_win > shrunk.draw
    assert shrunk.home_win > shrunk.away_win
    assert isclose(shrunk.home_win + shrunk.draw + shrunk.away_win, 1.0, abs_tol=1e-6)


def test_end_to_end_strong_vs_weak_odds():
    results = [
        MatchResult("Strong", "Weak", 3, 0),
        MatchResult("Strong", "Weak", 4, 1),
        MatchResult("Weak", "Strong", 0, 2),
        MatchResult("Strong", "Mid", 2, 1),
        MatchResult("Mid", "Weak", 2, 0),
        MatchResult("Weak", "Mid", 1, 1),
    ]
    strengths = fit_strengths(results)
    hl, al = expected_goals(strengths, "Strong", "Weak")
    assert hl > al
    probs = match_probabilities(hl, al)
    home_odds = probability_to_odds(probs.home_win)
    away_odds = probability_to_odds(probs.away_win)
    assert home_odds is not None and away_odds is not None
    # Favourite must have shorter odds than the underdog.
    assert home_odds < away_odds
