from oddsmith.history import team_stats
from oddsmith.odds_model.poisson import MatchResult


RESULTS = [
    MatchResult("Alpha", "Beta", 2, 0),   # Alpha W (home)
    MatchResult("Beta", "Alpha", 1, 1),    # Alpha D (away)
    MatchResult("Alpha", "Gamma", 0, 3),   # Alpha L (home)
    MatchResult("Gamma", "Alpha", 2, 2),   # Alpha D (away)
    MatchResult("Alpha", "Delta", 4, 1),   # Alpha W (home)
]


def test_record_totals():
    s = team_stats("Alpha", RESULTS)
    assert s.played == 5
    assert s.won == 2
    assert s.drawn == 2
    assert s.lost == 1
    assert s.points == 2 * 3 + 2


def test_goals_and_difference():
    s = team_stats("Alpha", RESULTS)
    # scored: 2+1+0+2+4 = 9 ; conceded: 0+1+3+2+1 = 7
    assert s.goals_for == 9
    assert s.goals_against == 7
    assert s.goal_difference == 2


def test_home_away_splits():
    s = team_stats("Alpha", RESULTS)
    # home games: W(2-0), L(0-3), W(4-1) -> 2W 0D 1L
    assert (s.home_won, s.home_drawn, s.home_lost) == (2, 0, 1)
    # away games: D(1-1), D(2-2) -> 0W 2D 0L
    assert (s.away_won, s.away_drawn, s.away_lost) == (0, 2, 0)


def test_form_is_recent_last():
    s = team_stats("Alpha", RESULTS, form_n=5)
    assert s.form == ["W", "D", "L", "D", "W"]


def test_form_limited_to_n():
    s = team_stats("Alpha", RESULTS, form_n=3)
    assert s.form == ["L", "D", "W"]


def test_team_with_no_matches():
    s = team_stats("Nobody", RESULTS)
    assert s.played == 0
    assert s.points == 0
    assert s.form == []
