from oddsmith.slips import (
    LegInput,
    LegResult,
    SlipResult,
    combined_odds,
    potential_profit,
    potential_return,
    profit_loss,
    settle,
    settled_return,
)


def test_combined_odds_is_product():
    assert combined_odds([1.5, 2.0, 1.33]) == 3.99
    assert combined_odds([2.0]) == 2.0


def test_combined_odds_empty_is_zero_not_one():
    assert combined_odds([]) == 0.0


def test_potential_return_and_profit():
    assert potential_return(10, [1.5, 2.0]) == 30.0
    assert potential_profit(10, [1.5, 2.0]) == 20.0


def test_potential_return_rejects_negative_stake():
    import pytest

    with pytest.raises(ValueError):
        potential_return(-1, [2.0])


def test_settle_any_lost_is_lost():
    legs = [
        LegInput(price=2.0, result=LegResult.WON),
        LegInput(price=1.5, result=LegResult.LOST),
    ]
    assert settle(legs) is SlipResult.LOST
    assert settled_return(10, legs) == 0.0
    assert profit_loss(10, legs) == -10.0


def test_settle_pending_when_any_pending():
    legs = [
        LegInput(price=2.0, result=LegResult.WON),
        LegInput(price=1.5, result=LegResult.PENDING),
    ]
    assert settle(legs) is SlipResult.PENDING
    assert profit_loss(10, legs) == 0.0


def test_settle_all_won_pays_product():
    legs = [
        LegInput(price=2.0, result=LegResult.WON),
        LegInput(price=1.5, result=LegResult.WON),
    ]
    assert settle(legs) is SlipResult.WON
    assert settled_return(10, legs) == 30.0
    assert profit_loss(10, legs) == 20.0


def test_void_leg_drops_from_accumulator():
    legs = [
        LegInput(price=2.0, result=LegResult.WON),
        LegInput(price=5.0, result=LegResult.VOID),
    ]
    assert settle(legs) is SlipResult.WON
    assert settled_return(10, legs) == 20.0


def test_all_void_returns_stake():
    legs = [LegInput(price=2.0, result=LegResult.VOID)]
    assert settle(legs) is SlipResult.WON
    assert settled_return(10, legs) == 10.0
    assert profit_loss(10, legs) == 0.0
