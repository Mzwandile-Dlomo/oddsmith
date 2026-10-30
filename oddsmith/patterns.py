"""Pattern recognition: which recurring pre-match situations actually predict a line.

The research board grades lines from five-match form ("Over 1.5 goals — Strong,
9/10") and the Strong slip stacks those grades. Nothing in a single fixture can
say whether "Strong" means anything, so this module replays every stored match
in date order and asks, for each pattern and each totals line:

1. When the pattern fired, how often did the line land compared with that
   league's base rate for the line on the same dates?
2. Did the lift survive on later seasons the pattern was never measured on?
3. Where prices exist (Over/Under 2.5), did it beat the market price on both
   blocks of seasons, or had the bookmakers already priced it in?

A pattern is a fixed, pre-registered rule over what was knowable before kickoff:
each side's last five matches and the last meetings between the clubs, exactly
the samples ``insights`` shows on the match page. The replay builds those samples
before the match is added to history, the same leakage barrier as
``data.features``.

Many patterns × many lines means some will look good by luck. A pattern-line
pair is only confirmed when its lift clears the threshold on the discovery
seasons *and again* on the holdout seasons; the chance of a pure-noise pair
doing both is roughly 0.02² per pair. Once a holdout has been looked at, do not
edit a pattern and re-run against it — that is tuning on the test set.

Pure functions apart from ``load_pattern_observations``; no framework dependency.
"""

from __future__ import annotations

import math
from collections import defaultdict, deque
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel
from sqlmodel import Session, select

from oddsmith.db import MatchObservation
from oddsmith.insights import TOTAL_LINES, MatchInsights, TeamMatch, club_key, dedupe, team_view
from oddsmith.research import MIN_SAMPLE, MODERATE, STRONG

MODEL_NAME = "pattern_replay_v1"
# The samples the match page shows: last five per side, last ten meetings.
FORM_WINDOW = 5
H2H_WINDOW = 10
# A line's league base rate needs this many earlier recorded matches first.
MIN_BASE_SAMPLE = 100
# One-sided z threshold (~2.3% each) applied to discovery and holdout separately.
Z_CONFIRM = 2.0
MIN_DISCOVERY_FIRES = 200
MIN_HOLDOUT_FIRES = 100
DEFAULT_HOLDOUT_SEASONS = 3

# Lines with historical closing prices: key -> which side of the 2.5 pair.
PRICED_LINES = {"goals_over_2.5": "over", "goals_under_2.5": "under"}
# Average across bookmakers, closing first; older seasons only have the
# pre-closing average. The stored ``close_*`` columns are maximums, and betting
# the best price in hindsight overstates every ROI.
_AVERAGE_PRICE_COLUMNS = {
    "over": ("AvgC>2.5", "Avg>2.5", "BbAv>2.5"),
    "under": ("AvgC<2.5", "Avg<2.5", "BbAv<2.5"),
}

LineTest = Callable[[TeamMatch], bool | None]
_LINES: dict[str, tuple[str, LineTest]] = {key: (label, test) for key, label, test, *_ in TOTAL_LINES}


# --------------------------------------------------------------------------- #
# Situations and patterns
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Situation:
    """What was knowable before kickoff, newest first, as the match page shows it."""

    home: list[TeamMatch]
    away: list[TeamMatch]
    # From the current home club's side, like ``HeadToHead.matches``.
    h2h: list[TeamMatch]


def _tally(matches: list[TeamMatch], test: LineTest) -> tuple[int, int]:
    outcomes = [o for o in (test(m) for m in matches) if o is not None]
    return sum(outcomes), len(outcomes)


def board_grade(s: Situation, test: LineTest) -> str | None:
    """The grade ``research.rank_angles`` gives this line, or None when ungraded.

    Same pooling (home sample + away sample) and thresholds as the live board.
    """
    home_hits, home_sample = _tally(s.home, test)
    away_hits, away_sample = _tally(s.away, test)
    sample = home_sample + away_sample
    if sample < MIN_SAMPLE:
        return None
    rate = (home_hits + away_hits) / sample
    return "Strong" if rate >= STRONG else "Moderate" if rate >= MODERATE else "Weak"


def _rate_at_least(matches: list[TeamMatch], test: LineTest, rate: float, min_sample: int) -> bool:
    hits, sample = _tally(matches, test)
    return sample >= min_sample and hits >= rate * sample


def _mean(values: Iterable[int | None], min_recorded: int) -> float | None:
    recorded = [v for v in values if v is not None]
    return sum(recorded) / len(recorded) if len(recorded) >= min_recorded else None


def _wasteful(matches: list[TeamMatch]) -> bool:
    shots = _mean((m.shots_on_target_for for m in matches), 4)
    goals = _mean((m.goals_for for m in matches), 4)
    return shots is not None and goals is not None and shots >= 5.0 and goals <= 1.0


def _avg_total(matches: list[TeamMatch]) -> float:
    return sum(m.total_goals for m in matches) / len(matches)


PatternTest = Callable[[Situation, LineTest], bool]


@dataclass(frozen=True)
class Pattern:
    key: str
    label: str
    description: str
    test: PatternTest
    # Line-relative patterns judge the line itself ("this line is Strong");
    # the rest describe the match and are checked against every line.
    line_relative: bool


PATTERNS: list[Pattern] = [
    Pattern("board_strong", "Board: Strong", "The research board grades the line Strong (both sides' last five landed it at least 80% of the time).", lambda s, t: board_grade(s, t) == "Strong", True),
    Pattern("board_moderate", "Board: Moderate", "The research board grades the line Moderate (60–79%).", lambda s, t: board_grade(s, t) == "Moderate", True),
    Pattern("board_weak", "Board: Weak", "The research board grades the line Weak (below 60%).", lambda s, t: board_grade(s, t) == "Weak", True),
    Pattern("both_sides_4_of_5", "Both sides 4/5+", "Each side on its own landed the line in at least four of its last five.", lambda s, t: _rate_at_least(s.home, t, 0.8, 4) and _rate_at_least(s.away, t, 0.8, 4), True),
    Pattern("h2h_4_of_5", "Head-to-head 4/5+", "The line landed in at least four of the clubs' last five meetings.", lambda s, t: _rate_at_least(s.h2h[:5], t, 0.8, 4), True),
    Pattern("strong_and_h2h", "Strong + head-to-head", "Board grade Strong and the last five meetings agree (4/5+).", lambda s, t: board_grade(s, t) == "Strong" and _rate_at_least(s.h2h[:5], t, 0.8, 4), True),
    Pattern("both_scoring_streak", "Both sides scoring", "Both sides scored in every one of their last five.", lambda s, _: all(m.goals_for > 0 for m in s.home + s.away), False),
    Pattern("both_leaking", "Both defences leaking", "Both sides conceded in every one of their last five.", lambda s, _: all(m.goals_against > 0 for m in s.home + s.away), False),
    Pattern("home_blanking", "Home side blanking", "The home side failed to score in at least three of its last five.", lambda s, _: sum(m.goals_for == 0 for m in s.home) >= 3, False),
    Pattern("wasteful_attack", "Chances, few goals", "A side averaged 5+ shots on target but at most one goal over its last five.", lambda s, _: _wasteful(s.home) or _wasteful(s.away), False),
    Pattern("tight_games", "Both in tight games", "Both sides' last five averaged two goals or fewer a match.", lambda s, _: _avg_total(s.home) <= 2.0 and _avg_total(s.away) <= 2.0, False),
    Pattern("goal_fests", "Both in open games", "Both sides' last five averaged three goals or more a match.", lambda s, _: _avg_total(s.home) >= 3.0 and _avg_total(s.away) >= 3.0, False),
]  # fmt: skip

_PATTERNS = {p.key: p for p in PATTERNS}


def situation_ready(s: Situation) -> bool:
    """Patterns are only judged on a full window, as in the replay."""
    return len(s.home) == FORM_WINDOW and len(s.away) == FORM_WINDOW


# --------------------------------------------------------------------------- #
# Replay
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ReplayedMatch:
    league: str
    season: int
    situation: Situation
    # line key -> did it land; None when the statistic was not recorded.
    outcomes: dict[str, bool | None]
    # line key -> the league's rate for it from strictly earlier matches.
    base_rates: dict[str, float | None]
    # "over"/"under" -> average closing decimal price, when stored.
    prices: dict[str, float]


def _average_prices(row: MatchObservation) -> dict[str, float]:
    payload = row.raw_payload or {}
    prices: dict[str, float] = {}
    for side, columns in _AVERAGE_PRICE_COLUMNS.items():
        for column in columns:
            try:
                value = float(payload.get(column) or 0)
            except (TypeError, ValueError):
                continue
            if value > 1.0:
                prices[side] = value
                break
    return prices


def replay(rows: Iterable[MatchObservation]) -> Iterator[ReplayedMatch]:
    """Every match whose clubs both have a full window, in date order.

    The situation and base rates are read before the match joins any history,
    so nothing a match produced can describe that match.
    """
    form: dict[str, deque[MatchObservation]] = defaultdict(lambda: deque(maxlen=FORM_WINDOW))
    meetings: dict[frozenset[str], deque[MatchObservation]] = defaultdict(
        lambda: deque(maxlen=H2H_WINDOW)
    )
    league_tally: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    views: dict[tuple[str, str], TeamMatch] = {}

    def view(row: MatchObservation, club: str) -> TeamMatch:
        key = (row.source_key, club)
        if key not in views:
            views[key] = team_view(row, club)
        return views[key]

    for row in dedupe(rows):
        home, away = club_key(row.home_team), club_key(row.away_team)
        pair = frozenset((home, away))
        target = team_view(row, home)
        outcomes = {key: test(target) for key, (_, test) in _LINES.items()}

        if len(form[home]) == FORM_WINDOW and len(form[away]) == FORM_WINDOW:
            base_rates: dict[str, float | None] = {}
            for key in _LINES:
                hits, sample = league_tally[(row.league, key)]
                base_rates[key] = hits / sample if sample >= MIN_BASE_SAMPLE else None
            yield ReplayedMatch(
                league=row.league,
                season=row.season,
                situation=Situation(
                    home=[view(r, home) for r in reversed(form[home])],
                    away=[view(r, away) for r in reversed(form[away])],
                    h2h=[view(r, home) for r in reversed(meetings[pair])],
                ),
                outcomes=outcomes,
                base_rates=base_rates,
                prices=_average_prices(row),
            )

        # The leakage barrier: history grows only after the match was judged.
        form[home].append(row)
        form[away].append(row)
        meetings[pair].append(row)
        for key, landed in outcomes.items():
            if landed is not None:
                tally = league_tally[(row.league, key)]
                tally[0] += landed
                tally[1] += 1


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #


class SplitStats(BaseModel):
    """How a pattern-line pair did on one block of seasons, against base rates."""

    eligible: int  # matches where the line was recorded and a base rate existed
    fires: int  # of those, matches where the pattern fired
    hits: int
    hit_rate: float | None
    base_rate: float | None  # mean league base rate on the same matches
    lift: float | None  # hit_rate - base_rate, in probability points
    z: float | None


class MarketStats(BaseModel):
    """Fires with an average price on one block of seasons: did it beat the price?"""

    matches: int
    hits: int
    hit_rate: float | None
    market_prob: float | None  # mean de-margined average closing probability
    z: float | None
    # Flat one-unit stake at the average closing price; normal-approximation interval.
    roi: float | None
    roi_ci_low: float | None
    roi_ci_high: float | None


Verdict = Literal[
    "beats_market", "edge_candidate", "holds_up", "priced_in", "backfires", "noise", "too_rare"
]

VERDICT_LABELS: dict[str, str] = {
    "beats_market": "Beat the price",
    "edge_candidate": "Beat the price · ROI unproven",
    "holds_up": "Holds up · price untested",
    "priced_in": "Real, but priced in",
    "backfires": "Lands less than usual",
    "noise": "Not reliable",
    "too_rare": "Too rare to judge",
}
# Best evidence first, for listing a fixture's active patterns.
VERDICT_ORDER = [
    "beats_market", "edge_candidate", "holds_up", "priced_in", "backfires", "noise", "too_rare"
]  # fmt: skip


class PatternResult(BaseModel):
    pattern_key: str
    pattern_label: str
    description: str
    line_key: str
    line_label: str
    verdict: Verdict
    verdict_label: str
    discovery: SplitStats
    holdout: SplitStats
    # Only for lines with historical prices.
    market_discovery: MarketStats | None
    market_holdout: MarketStats | None


class PatternReport(BaseModel):
    model_name: str
    generated_at: datetime
    matches_replayed: int
    discovery_seasons: list[int]
    holdout_seasons: list[int]
    z_confirm: float
    min_discovery_fires: int
    min_holdout_fires: int
    results: list[PatternResult]


def _z(hits: int, expected: float, variance: float) -> float | None:
    """Hits against the sum of per-match benchmark probabilities.

    Base rates differ by league and season, so the benchmark is each fired
    match's own probability rather than one pooled rate.
    """
    return round((hits - expected) / math.sqrt(variance), 3) if variance > 0 else None


@dataclass
class _Accumulator:
    eligible: int = 0
    fires: int = 0
    hits: int = 0
    expected: float = 0.0
    variance: float = 0.0

    def add(self, landed: bool, p: float) -> None:
        self.fires += 1
        self.hits += landed
        self.expected += p
        self.variance += p * (1 - p)

    def stats(self) -> SplitStats:
        if not self.fires:
            return SplitStats(
                eligible=self.eligible, fires=0, hits=0, hit_rate=None, base_rate=None, lift=None, z=None
            )
        hit_rate = self.hits / self.fires
        base_rate = self.expected / self.fires
        return SplitStats(
            eligible=self.eligible,
            fires=self.fires,
            hits=self.hits,
            hit_rate=round(hit_rate, 4),
            base_rate=round(base_rate, 4),
            lift=round(hit_rate - base_rate, 4),
            z=_z(self.hits, self.expected, self.variance),
        )


@dataclass
class _MarketAccumulator:
    hits: int = 0
    expected: float = 0.0
    variance: float = 0.0
    profits: list[float] = field(default_factory=list)

    def add(self, landed: bool, p: float, price: float) -> None:
        self.hits += landed
        self.expected += p
        self.variance += p * (1 - p)
        self.profits.append(price - 1 if landed else -1.0)

    def stats(self) -> MarketStats:
        n = len(self.profits)
        if not n:
            return MarketStats(
                matches=0, hits=0, hit_rate=None, market_prob=None, z=None,
                roi=None, roi_ci_low=None, roi_ci_high=None,
            )  # fmt: skip
        roi = sum(self.profits) / n
        spread = (
            1.96 * math.sqrt(sum((x - roi) ** 2 for x in self.profits) / (n - 1) / n)
            if n > 1
            else None
        )
        return MarketStats(
            matches=n,
            hits=self.hits,
            hit_rate=round(self.hits / n, 4),
            market_prob=round(self.expected / n, 4),
            z=_z(self.hits, self.expected, self.variance),
            roi=round(roi, 4),
            roi_ci_low=round(roi - spread, 4) if spread is not None else None,
            roi_ci_high=round(roi + spread, 4) if spread is not None else None,
        )


def _market_prob(prices: dict[str, float], side: str) -> float | None:
    if "over" not in prices or "under" not in prices:
        return None
    raw_over, raw_under = 1 / prices["over"], 1 / prices["under"]
    over = raw_over / (raw_over + raw_under)
    return over if side == "over" else 1 - over


def verdict(
    discovery: SplitStats,
    holdout: SplitStats,
    market_discovery: MarketStats | None = None,
    market_holdout: MarketStats | None = None,
    *,
    z_confirm: float = Z_CONFIRM,
    min_discovery_fires: int = MIN_DISCOVERY_FIRES,
    min_holdout_fires: int = MIN_HOLDOUT_FIRES,
) -> Verdict:
    """Every claim must clear the threshold on discovery *and* holdout seasons.

    Beating the market is its own two-block test: a pattern can land at the
    usual rate yet be underpriced, and one lucky holdout run is not an edge.
    Like the daily-ticket gate, "beats_market" also needs the holdout ROI
    interval above zero; short of that it is only a candidate.
    """
    if discovery.fires < min_discovery_fires or holdout.fires < min_holdout_fires:
        return "too_rare"
    priced = (
        market_discovery is not None
        and market_holdout is not None
        and market_discovery.matches >= min_discovery_fires
        and market_holdout.matches >= min_holdout_fires
    )
    if (
        priced
        and (market_discovery.z or 0.0) >= z_confirm
        and (market_holdout.z or 0.0) >= z_confirm
    ):
        roi_low = market_holdout.roi_ci_low
        return "beats_market" if roi_low is not None and roi_low > 0 else "edge_candidate"
    dz, hz = discovery.z or 0.0, holdout.z or 0.0
    if dz <= -z_confirm and hz <= -z_confirm:
        return "backfires"
    if dz < z_confirm or hz < z_confirm:
        return "noise"
    return "priced_in" if priced else "holds_up"


def evaluate_patterns(
    rows: Iterable[MatchObservation],
    *,
    holdout_seasons: int = DEFAULT_HOLDOUT_SEASONS,
    z_confirm: float = Z_CONFIRM,
    min_discovery_fires: int = MIN_DISCOVERY_FIRES,
    min_holdout_fires: int = MIN_HOLDOUT_FIRES,
    generated_at: datetime | None = None,
) -> PatternReport:
    """Score every pattern against every line: discovery seasons, then holdout."""
    if holdout_seasons < 1:
        raise ValueError("holdout_seasons must be >= 1")
    matches = list(replay(rows))
    seasons = sorted({m.season for m in matches})
    if len(seasons) <= holdout_seasons:
        raise ValueError(
            f"need more than {holdout_seasons} seasons to keep a holdout; have {seasons}"
        )
    holdout = set(seasons[-holdout_seasons:])

    splits: dict[tuple[str, str, bool], _Accumulator] = defaultdict(_Accumulator)
    markets: dict[tuple[str, str, bool], _MarketAccumulator] = defaultdict(_MarketAccumulator)
    for match in matches:
        is_holdout = match.season in holdout
        for line_key, (_, line_test) in _LINES.items():
            landed, base = match.outcomes[line_key], match.base_rates[line_key]
            if landed is None or base is None:
                continue
            side = PRICED_LINES.get(line_key)
            market_p = _market_prob(match.prices, side) if side else None
            for pattern in PATTERNS:
                acc = splits[(pattern.key, line_key, is_holdout)]
                acc.eligible += 1
                if not pattern.test(match.situation, line_test):
                    continue
                acc.add(landed, base)
                if side and market_p is not None:
                    markets[(pattern.key, line_key, is_holdout)].add(
                        landed, market_p, match.prices[side]
                    )

    results: list[PatternResult] = []
    for pattern in PATTERNS:
        for line_key, (line_label, _) in _LINES.items():
            discovery = splits[(pattern.key, line_key, False)].stats()
            held = splits[(pattern.key, line_key, True)].stats()
            priced = line_key in PRICED_LINES
            market_discovery = markets[(pattern.key, line_key, False)].stats() if priced else None
            market_holdout = markets[(pattern.key, line_key, True)].stats() if priced else None
            call = verdict(
                discovery,
                held,
                market_discovery,
                market_holdout,
                z_confirm=z_confirm,
                min_discovery_fires=min_discovery_fires,
                min_holdout_fires=min_holdout_fires,
            )
            results.append(
                PatternResult(
                    pattern_key=pattern.key,
                    pattern_label=pattern.label,
                    description=pattern.description,
                    line_key=line_key,
                    line_label=line_label,
                    verdict=call,
                    verdict_label=VERDICT_LABELS[call],
                    discovery=discovery,
                    holdout=held,
                    market_discovery=market_discovery,
                    market_holdout=market_holdout,
                )
            )
    return PatternReport(
        model_name=MODEL_NAME,
        generated_at=generated_at or datetime.now(UTC),
        matches_replayed=len(matches),
        discovery_seasons=[s for s in seasons if s not in holdout],
        holdout_seasons=sorted(holdout),
        z_confirm=z_confirm,
        min_discovery_fires=min_discovery_fires,
        min_holdout_fires=min_holdout_fires,
        results=results,
    )


# --------------------------------------------------------------------------- #
# Live fixtures
# --------------------------------------------------------------------------- #


class ActivePattern(BaseModel):
    """A pattern firing on an upcoming fixture, with its historical record."""

    pattern_key: str
    pattern_label: str
    description: str
    line_key: str
    line_label: str
    verdict: Verdict
    verdict_label: str
    holdout: SplitStats
    market_holdout: MarketStats | None
    # Today's best collected price for the line, from the fixture's insights.
    book_price: float | None
    book_implied_prob: float | None


class FixturePatterns(BaseModel):
    fixture_id: str
    status: Literal["ok", "no_report", "not_enough_history"]
    report_generated_at: datetime | None = None
    holdout_seasons: list[int] = []
    patterns: list[ActivePattern] = []
    message: str | None = None


def situation_from_insights(insights: MatchInsights) -> Situation:
    return Situation(
        home=insights.home.matches[:FORM_WINDOW],
        away=insights.away.matches[:FORM_WINDOW],
        h2h=insights.head_to_head.matches[:H2H_WINDOW],
    )


def active_patterns(insights: MatchInsights, report: PatternReport | None) -> FixturePatterns:
    """Every tested pattern firing on this fixture, best evidence first.

    Noise and too-rare pairs are kept: knowing that a 10/10 form line has never
    predicted anything is as useful as knowing one has.
    """
    if report is None:
        return FixturePatterns(
            fixture_id=insights.fixture_id,
            status="no_report",
            message="No pattern evaluation has been published yet. Run scripts/evaluate_patterns.py --publish.",
        )
    situation = situation_from_insights(insights)
    meta = {"report_generated_at": report.generated_at, "holdout_seasons": report.holdout_seasons}
    if not situation_ready(situation):
        return FixturePatterns(
            fixture_id=insights.fixture_id,
            status="not_enough_history",
            message=f"Patterns need {FORM_WINDOW} stored matches for each side.",
            **meta,
        )
    trends = {row.key: row for row in insights.trends}
    active: list[ActivePattern] = []
    for result in report.results:
        pattern = _PATTERNS.get(result.pattern_key)
        line = _LINES.get(result.line_key)
        if pattern is None or line is None or not pattern.test(situation, line[1]):
            continue
        trend = trends.get(result.line_key)
        active.append(
            ActivePattern(
                pattern_key=result.pattern_key,
                pattern_label=result.pattern_label,
                description=result.description,
                line_key=result.line_key,
                line_label=result.line_label,
                verdict=result.verdict,
                verdict_label=result.verdict_label,
                holdout=result.holdout,
                market_holdout=result.market_holdout,
                book_price=trend.book_price if trend else None,
                book_implied_prob=trend.book_implied_prob if trend else None,
            )
        )
    active.sort(key=lambda a: (VERDICT_ORDER.index(a.verdict), -(a.holdout.lift or 0.0)))
    return FixturePatterns(fixture_id=insights.fixture_id, status="ok", patterns=active, **meta)


# --------------------------------------------------------------------------- #
# Database read
# --------------------------------------------------------------------------- #


def load_pattern_observations(session: Session) -> list[MatchObservation]:
    """Only the columns the replay reads, plus the six average-price CSV fields."""
    columns = (
        MatchObservation.source_key,
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
    price_columns = [c for names in _AVERAGE_PRICE_COLUMNS.values() for c in names]
    extracts = tuple(MatchObservation.raw_payload[c].as_string() for c in price_columns)
    rows = session.exec(select(*columns, *extracts).order_by(MatchObservation.kickoff_utc))
    observations: list[MatchObservation] = []
    for row in rows:
        fields = dict(zip((c.key for c in columns), row[: len(columns)], strict=True))
        prices = {
            name: value
            for name, value in zip(price_columns, row[len(columns) :], strict=True)
            if value
        }
        observations.append(MatchObservation(**fields, source="database", raw_payload=prices))
    return observations
