"""Pre-match insights: recent form, head-to-head, and totals-line hit rates.

A fixture card shows prices; this module shows the evidence behind them. For
each side it gathers the most recent matches we hold — goals, corners, shots,
shots on target — and counts how often common totals lines would have landed,
then does the same for previous meetings between the two clubs.

These are historical frequencies over small samples, not probabilities. Five
matches can only say 0/5 … 5/5, so every count carries its sample size and the
trend board ranks lines by a Wilson lower bound rather than the raw rate: a
14/15 record outranks a 5/5 one because it is better evidence.

Team names differ by source ("AC Milan" from the odds feeds, "Milan" in
Football-Data, "Inter Milan" vs "Inter"), so everything is keyed on a
normalised club key. A name we cannot resolve exactly yields no history rather
than a guess — showing Inter Miami's form for Inter would be worse than nothing.

Pure functions apart from ``load_insight_rows``; no framework dependency.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel
from sqlmodel import Session, or_, select

from oddsmith.db import MatchObservation
from oddsmith.models import Market, MarketType
from oddsmith.odds_model.value import implied_probabilities
from oddsmith.textnorm import fold_accents

# A side's latest stored match this long before kickoff means the sync is behind:
# "last 5" would silently describe a different stretch of the season.
STALE_AFTER = timedelta(days=21)

_NON_ALNUM = re.compile(r"[^a-z0-9]+")

# Legal-form and boilerplate tokens that sources add or drop freely.
_NOISE = frozenset(
    {
        "ac", "afc", "aj", "as", "bc", "ca", "cd", "cf", "club", "de", "fc", "fsv",
        "hsc", "losc", "ogc", "rc", "rcd", "sc", "sco", "sd", "ss", "ssc", "sv",
        "tsg", "ud", "us", "vfb", "vfl",
    }
)  # fmt: skip

# Spellings that still differ after noise is stripped, mapped onto Football-Data's
# naming because it holds the deepest history. Keys are already-cleaned forms.
_ALIASES = {
    # Serie A
    "inter milan": "inter",
    "internazionale": "inter",
    "hellas verona": "verona",
    # Premier League
    "brighton and hove albion": "brighton",
    "brighton hove albion": "brighton",
    "coventry city": "coventry",
    "hull city": "hull",
    "ipswich town": "ipswich",
    "leeds united": "leeds",
    "leicester city": "leicester",
    "luton town": "luton",
    "man utd": "man united",
    "manchester united": "man united",
    "manchester city": "man city",
    "newcastle united": "newcastle",
    "nottingham forest": "nott m forest",
    "sheffield utd": "sheffield united",
    "spurs": "tottenham",
    "tottenham hotspur": "tottenham",
    "west ham united": "west ham",
    "wolverhampton wanderers": "wolves",
    # La Liga
    "athletic": "ath bilbao",
    "athletic bilbao": "ath bilbao",
    "atletico madrid": "ath madrid",
    "celta vigo": "celta",
    "deportivo": "la coruna",
    "deportivo alaves": "alaves",
    "deportivo la coruna": "la coruna",
    "espanyol": "espanol",
    "espanyol barcelona": "espanol",
    "r racing": "santander",
    "racing santander": "santander",
    "real racing santander": "santander",
    "rayo vallecano": "vallecano",
    "real betis": "betis",
    "real oviedo": "oviedo",
    "real sociedad": "sociedad",
    "real valladolid": "valladolid",
    # Bundesliga
    "bayer leverkusen": "leverkusen",
    "bayern munchen": "bayern munich",
    "borussia dortmund": "dortmund",
    "borussia monchengladbach": "m gladbach",
    "eintracht frankfurt": "ein frankfurt",
    "hamburger": "hamburg",
    "sport freiburg": "freiburg",
    # Ligue 1
    "estac troyes": "troyes",
    "havre athletic": "le havre",
    "olympique lyonnais": "lyon",
    "olympique marseille": "marseille",
    "paris saint germain": "paris sg",
    "psg": "paris sg",
    "saint etienne": "st etienne",
    "stade brestois": "brest",
    "stade reims": "reims",
    "stade rennais": "rennes",
    "strasbourg alsace": "strasbourg",
    # 2. Bundesliga
    "dynamo dresden": "dresden",
    "hertha bsc": "hertha",
    # MLS
    "atlanta united": "atlanta utd",
    "d c united": "dc united",
    "la galaxy": "los angeles galaxy",
    # Brazil Serie A
    "atletico mineiro": "atletico mg",
    "atletico paranaense": "athletico pr",
    "bragantino sp": "bragantino",
    # Argentina Primera Division
    "aldosivi mar del plata": "aldosivi",
    "argentinos juniors": "argentinos jrs",
    "atletico huracan": "huracan",
    "belgrano cordoba": "belgrano",
    "deportivo riestra": "dep riestra",
    "estudiantes": "estudiantes l p",
    "gimnasia la plata": "gimnasia l p",
    "independiente rivadavia": "ind rivadavia",
    "instituto cordoba": "instituto",
    "talleres": "talleres cordoba",
    "tigre ba": "tigre",
    "velez sarsfield ba": "velez sarsfield",
}


def club_key(name: str) -> str:
    """Normalise a club name so every source's spelling lands on one key.

    'AC Milan' -> 'milan', '1. FSV Mainz 05' -> 'mainz', 'Inter Milan' -> 'inter'.
    """
    tokens = _NON_ALNUM.sub(" ", fold_accents(name).lower()).split()
    kept = [t for t in tokens if t not in _NOISE and not t.isdigit()]
    key = " ".join(kept or tokens)
    return _ALIASES.get(key, key)


# --------------------------------------------------------------------------- #
# Response shapes
# --------------------------------------------------------------------------- #


class TeamMatch(BaseModel):
    """One past match seen from a particular club's side."""

    kickoff_utc: datetime
    league: str
    opponent: str
    venue: str  # "H" or "A"
    result: str  # "W" / "D" / "L"
    goals_for: int
    goals_against: int
    total_goals: int
    corners_for: int | None = None
    corners_against: int | None = None
    total_corners: int | None = None
    shots_for: int | None = None
    shots_against: int | None = None
    shots_on_target_for: int | None = None
    shots_on_target_against: int | None = None


class LineCount(BaseModel):
    key: str
    label: str
    hits: int
    # Matches where the statistic was recorded; unrecorded corners are not misses.
    sample: int


class TeamAverages(BaseModel):
    goals_for: float | None = None
    goals_against: float | None = None
    total_goals: float | None = None
    corners_for: float | None = None
    corners_against: float | None = None
    total_corners: float | None = None
    shots_for: float | None = None
    shots_on_target_for: float | None = None
    shots_on_target_against: float | None = None


class TeamForm(BaseModel):
    team: str  # as the fixture names it
    club_key: str | None  # None when no stored history matches this name
    matches: list[TeamMatch]  # most recent first
    averages: TeamAverages
    team_lines: list[LineCount]
    total_lines: list[LineCount]


class HeadToHead(BaseModel):
    matches: list[TeamMatch]  # from the fixture home club's side, most recent first
    home_wins: int
    draws: int
    away_wins: int
    averages: TeamAverages
    total_lines: list[LineCount]


class TrendRow(BaseModel):
    key: str
    label: str
    home: LineCount
    away: LineCount
    head_to_head: LineCount
    # Distinct matches across all three samples: a recent meeting appears in both
    # sides' form and the head-to-head, and must only be counted once.
    pooled_hits: int
    pooled_sample: int
    # 95% Wilson lower bound on the pooled rate; what the board is sorted by.
    support: float
    book_price: float | None = None
    book_implied_prob: float | None = None


class MatchInsights(BaseModel):
    fixture_id: str
    home: TeamForm
    away: TeamForm
    head_to_head: HeadToHead
    trends: list[TrendRow]
    data_through: datetime | None
    stale: bool


# --------------------------------------------------------------------------- #
# Lines
# --------------------------------------------------------------------------- #

# (key, label, predicate or None when unrecorded, bookmaker market, outcome, point)
_TotalLine = tuple[str, str, Callable[[TeamMatch], bool | None], MarketType, str, float | None]


def _corners(test: Callable[[int], bool]) -> Callable[[TeamMatch], bool | None]:
    return lambda m: None if m.total_corners is None else test(m.total_corners)


TOTAL_LINES: list[_TotalLine] = [
    ("goals_over_1.5", "Over 1.5 goals", lambda m: m.total_goals > 1.5, MarketType.OVER_UNDER, "Over", 1.5),
    ("goals_over_2.5", "Over 2.5 goals", lambda m: m.total_goals > 2.5, MarketType.OVER_UNDER, "Over", 2.5),
    ("goals_under_2.5", "Under 2.5 goals", lambda m: m.total_goals < 2.5, MarketType.OVER_UNDER, "Under", 2.5),
    ("goals_under_3.5", "Under 3.5 goals", lambda m: m.total_goals < 3.5, MarketType.OVER_UNDER, "Under", 3.5),
    ("btts_yes", "Both teams score", lambda m: m.goals_for > 0 and m.goals_against > 0, MarketType.BTTS, "Yes", None),
    ("btts_no", "Not both to score", lambda m: m.goals_for == 0 or m.goals_against == 0, MarketType.BTTS, "No", None),
    ("corners_over_8.5", "Over 8.5 corners", _corners(lambda c: c > 8.5), MarketType.CORNER_TOTALS, "Over", 8.5),
    ("corners_over_9.5", "Over 9.5 corners", _corners(lambda c: c > 9.5), MarketType.CORNER_TOTALS, "Over", 9.5),
    ("corners_under_9.5", "Under 9.5 corners", _corners(lambda c: c < 9.5), MarketType.CORNER_TOTALS, "Under", 9.5),
    ("corners_under_10.5", "Under 10.5 corners", _corners(lambda c: c < 10.5), MarketType.CORNER_TOTALS, "Under", 10.5),
]  # fmt: skip


def _optional(value: int | None, test: Callable[[int], bool]) -> bool | None:
    return None if value is None else test(value)


TEAM_LINES: list[tuple[str, str, Callable[[TeamMatch], bool | None]]] = [
    ("won", "Won", lambda m: m.result == "W"),
    ("scored", "Scored", lambda m: m.goals_for > 0),
    ("clean_sheet", "Clean sheet", lambda m: m.goals_against == 0),
    ("sot_over_3.5", "Over 3.5 shots on target", lambda m: _optional(m.shots_on_target_for, lambda v: v > 3.5)),
    ("corners_over_4.5", "Over 4.5 corners", lambda m: _optional(m.corners_for, lambda v: v > 4.5)),
]  # fmt: skip


def _count(key: str, label: str, matches: list[TeamMatch], test) -> LineCount:
    outcomes = [test(m) for m in matches]
    recorded = [o for o in outcomes if o is not None]
    return LineCount(key=key, label=label, hits=sum(recorded), sample=len(recorded))


def _total_lines(matches: list[TeamMatch]) -> list[LineCount]:
    return [_count(key, label, matches, test) for key, label, test, *_ in TOTAL_LINES]


def wilson_lower_bound(hits: int, sample: int, z: float = 1.96) -> float:
    """Pessimistic estimate of a hit rate that accounts for how small the sample is."""
    if sample == 0:
        return 0.0
    p = hits / sample
    denom = 1 + z * z / sample
    centre = p + z * z / (2 * sample)
    margin = z * math.sqrt(p * (1 - p) / sample + z * z / (4 * sample * sample))
    return (centre - margin) / denom


def _mean(values: Iterable[int | None]) -> float | None:
    recorded = [v for v in values if v is not None]
    return round(sum(recorded) / len(recorded), 2) if recorded else None


def _averages(matches: list[TeamMatch]) -> TeamAverages:
    return TeamAverages(
        goals_for=_mean(m.goals_for for m in matches),
        goals_against=_mean(m.goals_against for m in matches),
        total_goals=_mean(m.total_goals for m in matches),
        corners_for=_mean(m.corners_for for m in matches),
        corners_against=_mean(m.corners_against for m in matches),
        total_corners=_mean(m.total_corners for m in matches),
        shots_for=_mean(m.shots_for for m in matches),
        shots_on_target_for=_mean(m.shots_on_target_for for m in matches),
        shots_on_target_against=_mean(m.shots_on_target_against for m in matches),
    )


# --------------------------------------------------------------------------- #
# Match rows
# --------------------------------------------------------------------------- #


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _recorded_stats(row: MatchObservation) -> int:
    return sum(
        value is not None
        for value in (
            row.home_corners,
            row.away_corners,
            row.home_shots,
            row.away_shots,
            row.home_shots_on_target,
            row.away_shots_on_target,
        )
    )


def _match_identity(row: MatchObservation) -> tuple:
    return (_aware(row.kickoff_utc).date(), club_key(row.home_team), club_key(row.away_team))


def dedupe(rows: Iterable[MatchObservation]) -> list[MatchObservation]:
    """One row per real match, chronological.

    Football-Data CSVs and live API-Football results can both describe the same
    game; keep whichever recorded more statistics.
    """
    best: dict[tuple, MatchObservation] = {}
    for row in rows:
        identity = _match_identity(row)
        current = best.get(identity)
        if current is None or _recorded_stats(row) > _recorded_stats(current):
            best[identity] = row
    return sorted(best.values(), key=lambda row: _aware(row.kickoff_utc))


def _total(a: int | None, b: int | None) -> int | None:
    return None if a is None or b is None else a + b


def team_view(row: MatchObservation, club: str) -> TeamMatch:
    is_home = club_key(row.home_team) == club
    gf, ga = (row.home_goals, row.away_goals) if is_home else (row.away_goals, row.home_goals)
    cf, ca = (row.home_corners, row.away_corners) if is_home else (row.away_corners, row.home_corners)
    sf, sa = (row.home_shots, row.away_shots) if is_home else (row.away_shots, row.home_shots)
    tf, ta = (
        (row.home_shots_on_target, row.away_shots_on_target)
        if is_home
        else (row.away_shots_on_target, row.home_shots_on_target)
    )
    return TeamMatch(
        kickoff_utc=_aware(row.kickoff_utc),
        league=row.league,
        opponent=row.away_team if is_home else row.home_team,
        venue="H" if is_home else "A",
        result="W" if gf > ga else "D" if gf == ga else "L",
        goals_for=gf,
        goals_against=ga,
        total_goals=gf + ga,
        corners_for=cf,
        corners_against=ca,
        total_corners=_total(cf, ca),
        shots_for=sf,
        shots_against=sa,
        shots_on_target_for=tf,
        shots_on_target_against=ta,
    )


def _involves(row: MatchObservation, club: str) -> bool:
    return club in (club_key(row.home_team), club_key(row.away_team))


def resolve_club(name: str, known_clubs: set[str]) -> str | None:
    """The stored club key for a fixture name, or None when we hold no history.

    Exact key matches only — see the module docstring for why there is no
    fuzzy fallback.
    """
    key = club_key(name)
    return key if key in known_clubs else None


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #


def _book_view(
    markets: list[Market], mtype: MarketType, outcome: str, point: float | None
) -> tuple[float | None, float | None]:
    """Best offered price for a line plus that book's de-margined probability."""
    best_price: float | None = None
    best_prob: float | None = None
    for market in markets:
        if market.type is not mtype:
            continue
        pair = [o for o in market.outcomes if point is None or o.point == point]
        ours = next((o for o in pair if o.name == outcome), None)
        if ours is None or (best_price is not None and ours.price <= best_price):
            continue
        best_price = ours.price
        if len(pair) == 2:
            probs = implied_probabilities([o.price for o in pair])
            best_prob = probs[pair.index(ours)]
        else:
            best_prob = 1 / ours.price
    return best_price, (round(best_prob, 4) if best_prob is not None else None)


def _team_form(team: str, club: str | None, history: list[MatchObservation], last: int) -> TeamForm:
    rows = [r for r in history if _involves(r, club)][-last:] if club else []
    matches = [team_view(r, club) for r in reversed(rows)] if club else []
    return TeamForm(
        team=team,
        club_key=club,
        matches=matches,
        averages=_averages(matches),
        team_lines=[_count(key, label, matches, test) for key, label, test in TEAM_LINES],
        total_lines=_total_lines(matches),
    )


def build_insights(
    *,
    fixture_id: str,
    home_team: str,
    away_team: str,
    kickoff_utc: datetime,
    rows: Iterable[MatchObservation],
    markets: list[Market] | None = None,
    last: int = 5,
    h2h_limit: int = 10,
) -> MatchInsights:
    kickoff = _aware(kickoff_utc)
    # Only what was knowable before kickoff; a past fixture reviewed from the
    # calendar must not see its own result in "recent form".
    history = [r for r in dedupe(rows) if _aware(r.kickoff_utc) < kickoff]
    known = {club_key(r.home_team) for r in history} | {club_key(r.away_team) for r in history}
    home_club = resolve_club(home_team, known)
    away_club = resolve_club(away_team, known)

    home = _team_form(home_team, home_club, history, last)
    away = _team_form(away_team, away_club, history, last)

    meetings: list[MatchObservation] = []
    if home_club and away_club:
        meetings = [r for r in history if _involves(r, home_club) and _involves(r, away_club)]
        meetings = meetings[-h2h_limit:]
    h2h_matches = [team_view(r, home_club) for r in reversed(meetings)] if meetings else []
    head_to_head = HeadToHead(
        matches=h2h_matches,
        home_wins=sum(m.result == "W" for m in h2h_matches),
        draws=sum(m.result == "D" for m in h2h_matches),
        away_wins=sum(m.result == "L" for m in h2h_matches),
        averages=_averages(h2h_matches),
        total_lines=_total_lines(h2h_matches),
    )

    pooled: dict[tuple, TeamMatch] = {}
    for club, sample in ((home_club, home.matches), (away_club, away.matches), (home_club, h2h_matches)):
        for match in sample:
            pooled[(match.kickoff_utc.date(), *sorted((club or "", club_key(match.opponent))))] = match
    pooled_matches = list(pooled.values())

    trends: list[TrendRow] = []
    for index, (key, label, test, mtype, outcome, point) in enumerate(TOTAL_LINES):
        combined = _count(key, label, pooled_matches, test)
        price, implied = _book_view(markets or [], mtype, outcome, point)
        trends.append(
            TrendRow(
                key=key,
                label=label,
                home=home.total_lines[index],
                away=away.total_lines[index],
                head_to_head=head_to_head.total_lines[index],
                pooled_hits=combined.hits,
                pooled_sample=combined.sample,
                support=round(wilson_lower_bound(combined.hits, combined.sample), 4),
                book_price=price,
                book_implied_prob=implied,
            )
        )
    trends.sort(key=lambda row: row.support, reverse=True)

    latest = [m.kickoff_utc for m in (home.matches[:1] + away.matches[:1])]
    data_through = max(latest) if latest else None
    stale_sides = [
        form for form in (home, away)
        if form.club_key and (not form.matches or kickoff - form.matches[0].kickoff_utc > STALE_AFTER)
    ]  # fmt: skip
    return MatchInsights(
        fixture_id=fixture_id,
        home=home,
        away=away,
        head_to_head=head_to_head,
        trends=trends,
        data_through=data_through,
        stale=bool(stale_sides),
    )


# --------------------------------------------------------------------------- #
# Database read
# --------------------------------------------------------------------------- #


def load_insight_rows(session: Session, team_names: Iterable[str]) -> list[MatchObservation]:
    """Every stored match involving any spelling of the given clubs.

    Two narrow queries instead of hydrating all observations: first the distinct
    stored team names, then only rows whose names resolve to a wanted club.
    """
    wanted = {club_key(name) for name in team_names}
    stored = set(session.exec(select(MatchObservation.home_team).distinct())) | set(
        session.exec(select(MatchObservation.away_team).distinct())
    )
    spellings = [name for name in stored if club_key(name) in wanted]
    if not spellings:
        return []
    columns = (
        MatchObservation.source_key,
        MatchObservation.source,
        MatchObservation.league,
        MatchObservation.season,
        MatchObservation.kickoff_utc,
        MatchObservation.home_team,
        MatchObservation.away_team,
        MatchObservation.home_goals,
        MatchObservation.away_goals,
        MatchObservation.home_corners,
        MatchObservation.away_corners,
        MatchObservation.home_shots,
        MatchObservation.away_shots,
        MatchObservation.home_shots_on_target,
        MatchObservation.away_shots_on_target,
    )
    rows = session.exec(
        select(*columns).where(
            or_(
                MatchObservation.home_team.in_(spellings),
                MatchObservation.away_team.in_(spellings),
            )
        )
    )
    return [
        MatchObservation(**dict(zip((c.key for c in columns), row)), raw_payload={})
        for row in rows
    ]
