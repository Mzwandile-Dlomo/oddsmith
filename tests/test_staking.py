from math import isclose

from oddsmith.odds_model.staking import (
    build_staking_plan,
    kelly_fraction,
    log_growth_rate,
)


def test_kelly_is_zero_without_an_edge():
    # Model agrees with the price (50% at evens) -> no edge, no stake.
    assert kelly_fraction(0.50, 2.0) == 0.0
    # Model rates it BELOW the price -> still no stake, never negative.
    assert kelly_fraction(0.40, 2.0) == 0.0


def test_kelly_grows_with_the_edge():
    small = kelly_fraction(0.55, 2.0)
    large = kelly_fraction(0.70, 2.0)
    assert 0 < small < large < 1


def test_kelly_matches_the_closed_form():
    # p=0.6, b=1.0 -> f* = (0.6*1 - 0.4)/1 = 0.2
    assert isclose(kelly_fraction(0.60, 2.0), 0.20, abs_tol=1e-9)


def test_staking_everything_is_ruin():
    # This is the "let it ride" plan: one loss ends the sequence permanently.
    assert log_growth_rate(0.90, 1.5, fraction=1.0) == float("-inf")


def test_growth_is_maximised_at_full_kelly():
    p, odds = 0.75, 1.60
    f_star = kelly_fraction(p, odds)
    best = log_growth_rate(p, odds, f_star)
    assert best > log_growth_rate(p, odds, f_star * 0.5)
    assert best > log_growth_rate(p, odds, min(f_star * 1.5, 0.999))


def test_plan_recommends_half_kelly():
    plan = build_staking_plan(0.72, 1.50, bankroll=100.0)
    assert isclose(plan.recommended_fraction, plan.full_kelly_fraction * 0.5, abs_tol=1e-4)
    assert isclose(plan.recommended_stake, 100.0 * plan.recommended_fraction, abs_tol=0.01)


def test_plan_caps_the_stake_fraction():
    # A huge edge on a short price produces an enormous f*; the cap must hold.
    plan = build_staking_plan(0.98, 1.90, bankroll=100.0)
    assert plan.recommended_fraction <= 0.25


def test_plan_compounds_a_positive_edge():
    plan = build_staking_plan(0.72, 1.50, bankroll=100.0, horizon_bets=30)
    assert plan.growth_per_bet > 0
    assert plan.projected_bankroll > 100.0
    assert plan.bets_to_double is not None and plan.bets_to_double > 0


def test_plan_without_an_edge_stakes_nothing():
    plan = build_staking_plan(0.60, 1.50, bankroll=100.0)  # 0.6*1.5 = 0.9 -> EV negative
    assert plan.full_kelly_fraction == 0.0
    assert plan.recommended_stake == 0.0
    assert plan.growth_per_bet == 0.0
    assert plan.projected_bankroll == 100.0
    assert "zero" in plan.note


def test_plan_reports_the_reality_of_a_daily_streak():
    plan = build_staking_plan(0.72, 1.50, bankroll=100.0, horizon_bets=30)
    # Winning all 30 daily slips is vanishingly unlikely...
    assert plan.prob_all_win_over_horizon < 0.01
    # ...and roughly 8 of them are expected to lose.
    assert isclose(plan.expected_losses_over_horizon, 0.28 * 30, abs_tol=0.01)
    # The naive "stake everything each day" plan ends at zero.
    assert plan.let_it_ride_bankroll == 0.0
