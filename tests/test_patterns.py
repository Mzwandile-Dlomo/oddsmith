from datetime import UTC, datetime, timedelta
from itertools import cycle

import pytest

from oddsmith.db import MatchObservation
from oddsmith.insights import TOTAL_LINES, build_insights
from oddsmith.patterns import (
    MarketStats,
    SplitStats,
    _average_prices,
    active_patterns,
    board_grade,
    evaluate_patterns,
    replay,
    situation_from_insights,
    verdict,
)
from oddsmith.research import rank_angles

START = datetime(2018, 8, 1, 15, 0, tzinfo=UTC)
KICKOFF = datetime(2026, 10, 31, 19, 45, tzinfo=UTC)


def _row(kickoff, home, away, hg, ag, *, season=2026, corners=(5, 4), payload=None):
    return MatchObservation(
        source_key=f"test:{home}:{away}:{kickoff.isoformat()}",
        source="football_data",
        league="Test",
        season=season,
        kickoff_utc=kickoff,
        home_team=home,
        away_team=away,
        home_goals=hg,
        away_goals=ag,
        home_corners=corners[0] if corners else None,
        away_corners=corners[1] if corners else None,
        raw_payload=payload or {},
    )


def _league(seasons=range(2018, 2024)):
    """Two closed groups: 'Hi' clubs always draw 3-3 between themselves, 'Lo' clubs 1-0.

    The board then grades Over 2.5 Strong for every Hi meeting and it always
    lands, while the league base rate sits near one half.
    """
    pairings = cycle([(("Hi1", "Hi2"), ("Hi3", "Hi4")), (("Hi1", "Hi3"), ("Hi2", "Hi4")), (("Hi1", "Hi4"), ("Hi2", "Hi3"))])
    rows = []
    week = 0
    for season in seasons:
        for _ in range(38):
            kickoff = START + timedelta(weeks=week)
            for home, away in next(pairings):
                rows.append(_row(kickoff, home, away, 3, 3, season=season))
                rows.append(_row(kickoff, home.replace("Hi", "Lo"), away.replace("Hi", "Lo"), 1, 0, season=season))
            week += 1
    return rows  # fmt: skip


def test_replay_never_lets_a_match_describe_itself():
    rows = _league(seasons=[2018])
    for match in replay(rows):
        sides = match.situation.home + match.situation.away + match.situation.h2h
        # Every match in the league is on its own week; the situation must be strictly earlier.
        kickoff = next(
            r.kickoff_utc
            for r in rows
            if r.home_team == match.situation.home[0].opponent
            or r.away_team == match.situation.home[0].opponent
        )
        assert all(m.kickoff_utc >= kickoff - timedelta(days=400) for m in sides)
    first = next(iter(replay(rows)))
    # Clubs play weekly; the first full window opens in week six, so the history is weeks 1-5.
    assert first.situation.home[0].kickoff_utc == START + timedelta(weeks=4)
    assert first.situation.home[-1].kickoff_utc == START
    # Fewer than 100 earlier league matches: no base rate yet, rather than a noisy one.
    assert first.base_rates["goals_over_2.5"] is None


def test_base_rate_is_strictly_from_earlier_matches():
    rows = _league(seasons=[2018])
    matches = list(replay(rows))
    # 4 matches a week, half of them 3-3: once 100+ are stored the over-2.5 rate is exactly 0.5
    # at the start of each week, because the current week is not counted yet.
    rated = [m for m in matches if m.base_rates["goals_over_2.5"] is not None]
    assert rated
    assert {m.base_rates["goals_over_2.5"] for m in rated} == {0.5}


def test_board_grade_matches_the_live_research_board():
    rows = [_row(KICKOFF - timedelta(days=7 * i + 1), "Parma", f"Opp{i}", 2, 1) for i in range(5)] + [
        _row(KICKOFF - timedelta(days=7 * i + 2), "Udinese", f"Rival{i}", 1, 0) for i in range(5)
    ]  # fmt: skip
    insights = build_insights(
        fixture_id="fx:1", home_team="Parma", away_team="Udinese", kickoff_utc=KICKOFF, rows=rows
    )
    live = {a.key: a.strength for a in rank_angles(insights, limit=len(TOTAL_LINES))}
    situation = situation_from_insights(insights)
    replayed = {key: board_grade(situation, test) for key, _, test, *_ in TOTAL_LINES}
    assert replayed == live


def _split(fires, z):
    return SplitStats(eligible=1000, fires=fires, hits=0, hit_rate=0.5, base_rate=0.5, lift=0.0, z=z)


def _market(matches, z, roi_low):
    return MarketStats(
        matches=matches, hits=0, hit_rate=0.5, market_prob=0.5, z=z,
        roi=0.05, roi_ci_low=roi_low, roi_ci_high=0.1,
    )  # fmt: skip


@pytest.mark.parametrize(
    ("discovery", "holdout", "md", "mh", "expected"),
    [
        # Strong on old seasons only: the holdout decides.
        (_split(500, 4.0), _split(200, 1.0), None, None, "noise"),
        (_split(500, 4.0), _split(200, 3.0), None, None, "holds_up"),
        (_split(500, 4.0), _split(200, 3.0), _market(500, 0.5, -0.1), _market(200, 0.2, -0.1), "priced_in"),
        (_split(500, -3.0), _split(200, -2.5), None, None, "backfires"),
        (_split(150, 4.0), _split(200, 3.0), None, None, "too_rare"),
        # Beating the price is tested on both blocks, and only an ROI floor above zero is an edge.
        (_split(500, 0.5), _split(200, 0.5), _market(500, 3.0, 0.01), _market(200, 2.5, -0.02), "edge_candidate"),
        (_split(500, 0.5), _split(200, 0.5), _market(500, 3.0, 0.01), _market(200, 2.5, 0.01), "beats_market"),
        (_split(500, 0.5), _split(200, 0.5), _market(500, 1.0, -0.1), _market(200, 3.5, 0.05), "noise"),
    ],
)  # fmt: skip
def test_verdict_requires_both_blocks(discovery, holdout, md, mh, expected):
    assert verdict(discovery, holdout, md, mh) == expected


def test_evaluate_confirms_a_real_pattern_and_holds_out_the_latest_seasons():
    report = evaluate_patterns(
        _league(), holdout_seasons=2, min_discovery_fires=50, min_holdout_fires=20
    )
    assert report.holdout_seasons == [2022, 2023]
    assert report.discovery_seasons == [2018, 2019, 2020, 2021]

    strong_over = next(
        r for r in report.results if (r.pattern_key, r.line_key) == ("board_strong", "goals_over_2.5")
    )
    assert strong_over.holdout.hit_rate == 1.0
    assert strong_over.holdout.base_rate == pytest.approx(0.5, abs=0.01)
    # No prices in this league, so the most it can say is that it held up.
    assert strong_over.verdict == "holds_up"
    assert strong_over.market_holdout is not None and strong_over.market_holdout.matches == 0

    # Corners are a flat 9 everywhere: no pattern can beat a base rate of 1.0 or 0.0.
    corners = [r for r in report.results if r.line_key.startswith("corners")]
    assert all(r.verdict in {"noise", "too_rare"} for r in corners)


def test_evaluate_needs_a_season_beyond_the_holdout():
    with pytest.raises(ValueError, match="holdout"):
        evaluate_patterns(_league(seasons=[2018, 2019]), holdout_seasons=2)


def test_average_prices_prefer_closing_average_and_ignore_maximums():
    row = _row(KICKOFF, "A", "B", 1, 1, payload={"AvgC>2.5": "1.9", "Avg>2.5": "2.1", "Max>2.5": "2.4", "AvgC<2.5": "", "Avg<2.5": "1.95"})  # fmt: skip
    assert _average_prices(row) == {"over": 1.9, "under": 1.95}


def test_active_patterns_list_what_fires_on_a_fixture_best_evidence_first():
    rows = _league()
    report = evaluate_patterns(rows, holdout_seasons=2, min_discovery_fires=50, min_holdout_fires=20)
    kickoff = max(r.kickoff_utc for r in rows) + timedelta(weeks=1)
    insights = build_insights(
        fixture_id="fx:hi", home_team="Hi1", away_team="Hi2", kickoff_utc=kickoff, rows=rows
    )
    view = active_patterns(insights, report)
    assert view.status == "ok"
    assert view.patterns[0].verdict == "holds_up"
    assert ("board_strong", "goals_over_2.5") in {(p.pattern_key, p.line_key) for p in view.patterns}


def test_active_patterns_without_a_report_or_history():
    insights = build_insights(
        fixture_id="fx:new", home_team="Nobody", away_team="Else", kickoff_utc=KICKOFF, rows=[]
    )
    assert active_patterns(insights, None).status == "no_report"
    report = evaluate_patterns(_league(), holdout_seasons=2, min_discovery_fires=50, min_holdout_fires=20)
    assert active_patterns(insights, report).status == "not_enough_history"
