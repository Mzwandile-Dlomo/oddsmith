"""Match research: the day's fixtures with the evidence behind each one.

Everything here is computed, never generated. ``rank_angles`` turns the totals
lines from ``insights`` into ranked betting angles graded by how often each
side's recent matches landed them ("Over 1.5 goals — Strong, 9/10"). The written
read in ``match_read`` may only pick from these angles and repeat these numbers.

Counts over five matches are frequencies, not probabilities: a 9/10 says what
happened, and the page always shows the sample next to it.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel

from oddsmith.db import MatchObservation
from oddsmith.insights import MatchInsights, TrendRow, club_key

STRONG = 0.8
MODERATE = 0.6
# Below this many recorded matches across both sides, a line is not graded at
# all; 2/3 would read as "Moderate" on almost no evidence.
MIN_SAMPLE = 6
PLACEHOLDER_UTC_HOURS = frozenset({22, 23, 0})
# Sources disagree on kickoff times by a few hours (time zones, late changes);
# the same tolerance settlement uses to pair a fixture with its result.
RESULT_TOLERANCE = timedelta(hours=12)


class Angle(BaseModel):
    key: str
    label: str
    strength: str  # "Strong" / "Moderate" / "Weak"
    hits: int  # home + away recent matches that landed the line
    sample: int
    home_hits: int
    home_sample: int
    away_hits: int
    away_sample: int
    h2h_hits: int
    h2h_sample: int
    book_price: float | None = None
    book_implied_prob: float | None = None

    @property
    def headline(self) -> str:
        return f"{self.label} — {self.strength} ({self.hits}/{self.sample})"


def _strength(rate: float) -> str:
    return "Strong" if rate >= STRONG else "Moderate" if rate >= MODERATE else "Weak"


def _angle(row: TrendRow) -> Angle | None:
    hits = row.home.hits + row.away.hits
    sample = row.home.sample + row.away.sample
    if sample < MIN_SAMPLE:
        return None
    return Angle(
        key=row.key,
        label=row.label,
        strength=_strength(hits / sample),
        hits=hits,
        sample=sample,
        home_hits=row.home.hits,
        home_sample=row.home.sample,
        away_hits=row.away.hits,
        away_sample=row.away.sample,
        h2h_hits=row.head_to_head.hits,
        h2h_sample=row.head_to_head.sample,
        book_price=row.book_price,
        book_implied_prob=row.book_implied_prob,
    )


def rank_angles(insights: MatchInsights, limit: int = 4) -> list[Angle]:
    """Most consistent lines first: recent rate, then the head-to-head as a tiebreak."""
    angles = [a for a in (_angle(row) for row in insights.trends) if a is not None]
    angles.sort(
        key=lambda a: (
            a.hits / a.sample,
            a.h2h_hits / a.h2h_sample if a.h2h_sample else 0.0,
            a.sample,
        ),
        reverse=True,
    )
    return angles[:limit]


class ResearchCard(BaseModel):
    fixture_id: str
    league: str | None
    kickoff_utc: datetime
    home_team: str
    away_team: str
    home_form: list[str]  # newest first, "W"/"D"/"L"
    away_form: list[str]
    home_goals_for: float | None
    away_goals_for: float | None
    home_avg_total_goals: float | None
    away_avg_total_goals: float | None
    home_score: int | None = None  # full time, once a results sync has stored it
    away_score: int | None = None
    angles: list[Angle]  # top two
    has_history: bool  # both clubs matched to stored results
    time_confirmed: bool  # False while the schedule only knows the date
    stale: bool
    priced: bool  # bookmaker odds collected for this fixture


class ResearchDay(BaseModel):
    date_from: datetime
    date_to: datetime
    leagues: list[str]
    cards: list[ResearchCard]


def kickoff_time_known(provider: str, kickoff_utc: datetime) -> bool:
    """Fixture Download stores a fixture whose time is not yet announced at
    local midnight: 00:00 UTC for most leagues, 22:00/23:00 UTC (Paris
    midnight) for Ligue 1. No top-five European league kicks off between 22:00
    and 00:59 UTC, so from that source those on-the-hour times mean "date only"."""
    kickoff = kickoff_utc if kickoff_utc.tzinfo else kickoff_utc.replace(tzinfo=UTC)
    utc = kickoff.astimezone(UTC)
    placeholder = utc.minute == 0 and utc.hour in PLACEHOLDER_UTC_HOURS
    return not (provider == "fixture_download" and placeholder)


def final_score(
    rows: Iterable[MatchObservation], *, home_team: str, away_team: str, kickoff_utc: datetime
) -> tuple[int, int] | None:
    """The stored full-time score of this fixture, or None until a results sync has it.

    Both clubs must match in the same orientation, so a reverse fixture from
    earlier in the season is never mistaken for this one.
    """
    home, away = club_key(home_team), club_key(away_team)
    kickoff = kickoff_utc if kickoff_utc.tzinfo else kickoff_utc.replace(tzinfo=UTC)
    for row in rows:
        played = row.kickoff_utc if row.kickoff_utc.tzinfo else row.kickoff_utc.replace(tzinfo=UTC)
        if (
            club_key(row.home_team) == home
            and club_key(row.away_team) == away
            and abs(played - kickoff) <= RESULT_TOLERANCE
        ):
            return row.home_goals, row.away_goals
    return None


def research_card(
    *,
    fixture_id: str,
    league: str | None,
    kickoff_utc: datetime,
    priced: bool,
    insights: MatchInsights,
    provider: str = "",
    score: tuple[int, int] | None = None,
) -> ResearchCard:
    home, away = insights.home, insights.away
    home_score, away_score = score or (None, None)
    return ResearchCard(
        fixture_id=fixture_id,
        league=league,
        kickoff_utc=kickoff_utc,
        home_team=home.team,
        away_team=away.team,
        home_form=[m.result for m in home.matches],
        away_form=[m.result for m in away.matches],
        home_goals_for=home.averages.goals_for,
        away_goals_for=away.averages.goals_for,
        home_avg_total_goals=home.averages.total_goals,
        away_avg_total_goals=away.averages.total_goals,
        home_score=home_score,
        away_score=away_score,
        angles=rank_angles(insights, limit=2),
        has_history=bool(home.club_key and away.club_key and home.matches and away.matches),
        time_confirmed=kickoff_time_known(provider, kickoff_utc),
        stale=insights.stale,
        priced=priced,
    )
