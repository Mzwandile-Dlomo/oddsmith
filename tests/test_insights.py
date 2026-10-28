from datetime import UTC, datetime, timedelta

import pytest

from oddsmith.db import MatchObservation
from oddsmith.insights import (
    build_insights,
    club_key,
    dedupe,
    resolve_club,
    wilson_lower_bound,
)
from oddsmith.models import Market, MarketType, Outcome

KICKOFF = datetime(2026, 10, 28, 19, 45, tzinfo=UTC)


def _row(days_before, home, away, hg, ag, *, corners=(5, 4), sot=(5, 3), source="football_data"):
    kickoff = KICKOFF - timedelta(days=days_before)
    return MatchObservation(
        source_key=f"{source}:{home}:{away}:{days_before}",
        source=source,
        league="SerieA",
        season=2026,
        kickoff_utc=kickoff,
        home_team=home,
        away_team=away,
        home_goals=hg,
        away_goals=ag,
        home_corners=corners[0] if corners else None,
        away_corners=corners[1] if corners else None,
        home_shots_on_target=sot[0],
        away_shots_on_target=sot[1],
        raw_payload={},
    )


@pytest.mark.parametrize(
    ("provider_name", "stored_name"),
    [
        ("AC Milan", "Milan"),
        ("Inter Milan", "Inter"),
        ("Internazionale", "Inter"),
        ("1. FSV Mainz 05", "Mainz"),
        ("FC Bayern München", "Bayern Munich"),
        ("Atlético de Madrid", "Ath Madrid"),
        ("Paris Saint-Germain", "Paris SG"),
        ("Brighton and Hove Albion", "Brighton"),
        ("Man Utd", "Man United"),
        ("Borussia Mönchengladbach", "M'gladbach"),
    ],
)
def test_club_key_aligns_provider_and_history_spellings(provider_name, stored_name):
    assert club_key(provider_name) == club_key(stored_name)


def test_distinct_clubs_stay_distinct():
    assert club_key("Inter Milan") != club_key("AC Milan")
    assert club_key("Paris FC") != club_key("Paris Saint-Germain")
    assert club_key("Inter Miami") != club_key("Inter")


def test_unknown_name_resolves_to_nothing_rather_than_a_guess():
    known = {club_key("Inter"), club_key("Milan")}
    assert resolve_club("Inter Miami", known) is None


def test_dedupe_keeps_the_richer_source_row():
    csv_row = _row(3, "Milan", "Udinese", 0, 2)
    live_row = _row(3, "AC Milan", "Udinese", 0, 2, corners=None, source="api_football_result")
    rows = dedupe([live_row, csv_row])
    assert len(rows) == 1
    assert rows[0].source == "football_data"


def test_form_is_from_the_teams_side_and_most_recent_first():
    rows = [
        _row(10, "Sassuolo", "Milan", 1, 1),
        _row(3, "Milan", "Udinese", 0, 2, corners=(6, 3), sot=(4, 2)),
    ]
    insights = build_insights(
        fixture_id="f", home_team="AC Milan", away_team="Bologna", kickoff_utc=KICKOFF, rows=rows
    )
    latest = insights.home.matches[0]
    assert (latest.opponent, latest.venue, latest.result) == ("Udinese", "H", "L")
    assert (latest.corners_for, latest.total_corners, latest.shots_on_target_for) == (6, 9, 4)
    assert insights.home.matches[1].venue == "A"
    assert insights.away.club_key is None
    assert insights.away.matches == []


def test_matches_at_or_after_kickoff_are_excluded():
    rows = [_row(3, "Milan", "Udinese", 0, 2), _row(0, "Milan", "Bologna", 3, 0)]
    insights = build_insights(
        fixture_id="f", home_team="Milan", away_team="Bologna", kickoff_utc=KICKOFF, rows=rows
    )
    assert [m.opponent for m in insights.home.matches] == ["Udinese"]
    assert insights.head_to_head.matches == []


def test_last_limits_the_sample():
    rows = [_row(d, "Milan", f"Opp{d}", 1, 0) for d in range(3, 30, 3)]
    insights = build_insights(
        fixture_id="f", home_team="Milan", away_team="X", kickoff_utc=KICKOFF, rows=rows, last=5
    )
    assert len(insights.home.matches) == 5


def test_unrecorded_corners_shrink_the_sample_instead_of_counting_as_misses():
    rows = [
        _row(3, "Milan", "A", 2, 1, corners=(6, 6)),
        _row(6, "Milan", "B", 2, 1, corners=None),
    ]
    insights = build_insights(
        fixture_id="f", home_team="Milan", away_team="X", kickoff_utc=KICKOFF, rows=rows
    )
    lines = {line.key: line for line in insights.home.total_lines}
    assert (lines["corners_over_9.5"].hits, lines["corners_over_9.5"].sample) == (1, 1)
    assert (lines["goals_over_2.5"].hits, lines["goals_over_2.5"].sample) == (2, 2)


def test_head_to_head_counts_wins_by_club_not_venue():
    rows = [
        _row(100, "Milan", "Bologna", 2, 0),
        _row(200, "Bologna", "Milan", 0, 1),  # Milan win away
        _row(300, "Bologna", "Milan", 2, 2),
    ]
    insights = build_insights(
        fixture_id="f", home_team="AC Milan", away_team="Bologna", kickoff_utc=KICKOFF, rows=rows
    )
    h2h = insights.head_to_head
    assert (h2h.home_wins, h2h.draws, h2h.away_wins) == (2, 1, 0)
    assert h2h.averages.total_goals == pytest.approx((2 + 1 + 4) / 3, abs=0.01)


def test_trend_board_pools_each_meeting_once():
    # The one meeting is in Milan's form, Bologna's form and the head-to-head.
    rows = [_row(5, "Milan", "Bologna", 2, 1)]
    insights = build_insights(
        fixture_id="f", home_team="Milan", away_team="Bologna", kickoff_utc=KICKOFF, rows=rows
    )
    row = next(r for r in insights.trends if r.key == "goals_over_2.5")
    assert (row.home.sample, row.away.sample, row.head_to_head.sample) == (1, 1, 1)
    assert row.pooled_sample == 1


def test_wilson_prefers_a_larger_sample_over_a_perfect_small_one():
    assert wilson_lower_bound(14, 15) > wilson_lower_bound(5, 5)
    assert wilson_lower_bound(0, 0) == 0.0


def test_book_price_uses_the_matching_line_and_removes_margin():
    markets = [
        Market(
            type=MarketType.OVER_UNDER,
            outcomes=[
                Outcome(name="Over", price=1.25, point=1.5),
                Outcome(name="Under", price=3.75, point=1.5),
                Outcome(name="Over", price=1.9, point=2.5),
                Outcome(name="Under", price=1.9, point=2.5),
            ],
        )
    ]
    rows = [_row(3, "Milan", "A", 2, 1)]
    insights = build_insights(
        fixture_id="f",
        home_team="Milan",
        away_team="X",
        kickoff_utc=KICKOFF,
        rows=rows,
        markets=markets,
    )
    by_key = {r.key: r for r in insights.trends}
    assert by_key["goals_over_2.5"].book_price == 1.9
    assert by_key["goals_over_2.5"].book_implied_prob == pytest.approx(0.5)
    assert by_key["goals_over_1.5"].book_implied_prob == pytest.approx(0.75)
    assert by_key["corners_over_9.5"].book_price is None


def test_stale_when_latest_match_is_weeks_before_kickoff():
    fresh = build_insights(
        fixture_id="f", home_team="Milan", away_team="X", kickoff_utc=KICKOFF,
        rows=[_row(4, "Milan", "A", 1, 0)],
    )
    stale = build_insights(
        fixture_id="f", home_team="Milan", away_team="X", kickoff_utc=KICKOFF,
        rows=[_row(58, "Milan", "A", 1, 0)],
    )
    assert fresh.stale is False
    assert stale.stale is True
