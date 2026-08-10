"""Derived team statistics from historical match results.

We store only scorelines, so all stats here are computed from goals: a team's
win/draw/loss record, goals for/against, recent form, and home/away splits.
Pure functions over a list of results — no I/O — so they are trivially testable
and reusable by the API layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from oddsmith.odds_model.poisson import MatchResult


@dataclass(frozen=True)
class TeamStats:
    team: str
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    home_won: int
    home_drawn: int
    home_lost: int
    away_won: int
    away_drawn: int
    away_lost: int
    form: list[str]  # most-recent-last, each "W"/"D"/"L"

    @property
    def goal_difference(self) -> int:
        return self.goals_for - self.goals_against

    @property
    def points(self) -> int:
        return self.won * 3 + self.drawn


def _outcome_for(team: str, m: MatchResult) -> str:
    is_home = m.home_team == team
    gf = m.home_goals if is_home else m.away_goals
    ga = m.away_goals if is_home else m.home_goals
    if gf > ga:
        return "W"
    if gf == ga:
        return "D"
    return "L"


def team_stats(team: str, results: list[MatchResult], form_n: int = 5) -> TeamStats:
    """Aggregate a team's record from its matches (assumed chronological)."""
    played = [m for m in results if team in (m.home_team, m.away_team)]

    won = drawn = lost = gf = ga = 0
    hw = hd = hl = aw = ad = al = 0

    for m in played:
        is_home = m.home_team == team
        scored = m.home_goals if is_home else m.away_goals
        conceded = m.away_goals if is_home else m.home_goals
        gf += scored
        ga += conceded
        outcome = _outcome_for(team, m)
        if outcome == "W":
            won += 1
            if is_home:
                hw += 1
            else:
                aw += 1
        elif outcome == "D":
            drawn += 1
            if is_home:
                hd += 1
            else:
                ad += 1
        else:
            lost += 1
            if is_home:
                hl += 1
            else:
                al += 1

    form = [_outcome_for(team, m) for m in played[-form_n:]]

    return TeamStats(
        team=team,
        played=len(played),
        won=won,
        drawn=drawn,
        lost=lost,
        goals_for=gf,
        goals_against=ga,
        home_won=hw,
        home_drawn=hd,
        home_lost=hl,
        away_won=aw,
        away_drawn=ad,
        away_lost=al,
        form=form,
    )
