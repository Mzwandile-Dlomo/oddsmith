from datetime import UTC, datetime, timedelta

from oddsmith.db import MatchObservation
from oddsmith.insights import build_insights
from oddsmith.models import Fixture, Market, MarketType, ModelMarket, ModelOutcome, Outcome
from oddsmith.strong_slip import StrongLeg, build_strong_slip, strong_candidates

KICKOFF = datetime(2026, 10, 31, 19, 45, tzinfo=UTC)


def _row(days_before, home, away, hg, ag):
    return MatchObservation(
        source_key=f"test:{home}:{away}:{days_before}",
        source="football_data",
        league="SerieA",
        season=2026,
        kickoff_utc=KICKOFF - timedelta(days=days_before),
        home_team=home,
        away_team=away,
        home_goals=hg,
        away_goals=ag,
        home_corners=5,
        away_corners=4,
        raw_payload={},
    )


# Parma's last five all finish 2-1, Udinese's all 1-0: Under 3.5 lands 10/10,
# and 9 corners a match makes the corner unders Strong too.
FIVE_EACH = [_row(7 * i + 1, "Parma", f"Opp{i}", 2, 1) for i in range(5)] + [
    _row(7 * i + 2, "Udinese", f"Rival{i}", 1, 0) for i in range(5)
]


def _fixture(markets, model_markets=()):
    return Fixture(
        id="fx:1",
        home_team="Parma",
        away_team="Udinese",
        kickoff_utc=KICKOFF,
        league="Serie A - Italy",
        provider="the_odds_api",
        markets=markets,
        model_markets=list(model_markets),
    )


def _candidates(fixture):
    insights = build_insights(
        fixture_id=fixture.id,
        home_team=fixture.home_team,
        away_team=fixture.away_team,
        kickoff_utc=KICKOFF,
        rows=FIVE_EACH,
        markets=fixture.markets,
    )
    return strong_candidates(fixture, insights)


UNDER_3_5 = Market(
    type=MarketType.OVER_UNDER,
    outcomes=[Outcome(name="Over", price=3.4, point=3.5), Outcome(name="Under", price=1.3, point=3.5)],
)


def test_strong_candidates_map_angles_to_real_markets_and_skip_corners():
    legs = _candidates(_fixture([UNDER_3_5]))

    under = next(leg for leg in legs if leg.label == "Under 3.5 goals")
    assert (under.market_type, under.selection, under.point) == (MarketType.OVER_UNDER, "Under", 3.5)
    assert (under.offered_odds, under.hits, under.sample) == (1.3, 10, 10)
    assert under.book_implied_prob is not None
    # Corner lines are Strong here too, but corner prices are research-only.
    assert all(leg.market_type is not MarketType.CORNER_TOTALS for leg in legs)


def test_strong_candidates_keep_unpriced_lines_and_attach_the_models_view():
    model = ModelMarket(
        type=MarketType.OVER_UNDER,
        outcomes=[
            ModelOutcome(name="Under", model_prob=0.61, model_odds=1.64, point=2.5),
            ModelOutcome(name="Over", model_prob=0.39, model_odds=2.56, point=2.5),
        ],
    )
    legs = _candidates(_fixture([], model_markets=[model]))

    assert legs, "Under 3.5 is Strong even with no price collected"
    assert all(leg.offered_odds is None for leg in legs)
    # The model prices only the 2.5 line, so it never vouches for Under 3.5.
    under_35 = next(leg for leg in legs if leg.label == "Under 3.5 goals")
    assert under_35.model_prob is None


def _leg(fixture_id, odds, *, hits=9, sample=10, support=0.6):
    return StrongLeg(
        fixture_id=fixture_id,
        home_team=f"{fixture_id} H",
        away_team=f"{fixture_id} A",
        kickoff_utc=KICKOFF,
        league="EPL",
        provider="the_odds_api",
        market_type=MarketType.OVER_UNDER,
        selection="Over",
        point=2.5,
        label="Over 2.5 goals",
        offered_odds=odds,
        hits=hits,
        sample=sample,
        h2h_hits=0,
        h2h_sample=0,
        support=support,
        book_implied_prob=None if odds is None else round(1 / odds, 4),
        model_prob=None,
    )


def _build(per_fixture, **overrides):
    params = {"target_odds": 2.0, "max_legs": 5, "fixtures_scanned": 9, "priced_fixtures": 9}
    return build_strong_slip(per_fixture, **(params | overrides))


def test_slip_stacks_strongest_fixtures_until_the_target_and_keeps_the_rest():
    slip = _build(
        [
            [_leg("a", 1.4, support=0.7)],
            [_leg("b", 1.5, support=0.65)],
            [_leg("c", 1.6, support=0.5)],
        ]
    )

    assert [leg.fixture_id for leg in slip.legs] == ["a", "b"]
    assert slip.combined_odds == 2.1
    assert slip.target_met is True
    assert [leg.fixture_id for leg in slip.alternatives] == ["c"]
    assert slip.combined_book_prob == round((1 / 1.4) * (1 / 1.5), 4)
    # One leg has no model probability, so no combined model figure is claimed.
    assert slip.combined_model_prob is None


def test_slip_takes_one_leg_per_fixture():
    slip = _build([[_leg("a", 1.3, support=0.7), _leg("a", 1.8, support=0.6)]])

    assert [leg.offered_odds for leg in slip.legs] == [1.3]
    assert slip.alternatives == []
    assert slip.target_met is False
    assert slip.note.startswith("Only 1 Strong leg available")


def test_too_short_legs_fall_back_to_the_fixtures_next_angle():
    slip = _build([[_leg("a", 1.05, support=0.8), _leg("a", 1.6, support=0.6)]])

    assert [leg.offered_odds for leg in slip.legs] == [1.6]


def test_unpriced_strong_picks_are_listed_but_never_enter_the_slip():
    slip = _build([[_leg("a", None, support=0.8)], [_leg("b", 2.2, support=0.5)]])

    assert [leg.fixture_id for leg in slip.legs] == ["b"]
    assert [leg.fixture_id for leg in slip.unpriced] == ["a"]


def test_empty_window_says_so():
    slip = _build([], fixtures_scanned=0, priced_fixtures=0)

    assert slip.legs == [] and slip.combined_odds == 0.0 and slip.target_met is False
    assert slip.note == "No priced fixtures still to kick off in this window."
