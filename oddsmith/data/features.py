"""Leakage-safe pre-match features and labels for supervised models.

Match statistics are valuable only as history. The current match's shots,
corners, cards, and goals are appended *after* its feature vector is emitted, so
no training example can see information that was unavailable before kickoff.

Optional feature groups (``extra_features``) are off by default. The boosted and
corner models train on every feature key present, so turning a group on changes
the model; evaluate it as a challenger before making it a default.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from statistics import fmean

from oddsmith.db import MatchObservation

# venue: home team's home-only form and away team's away-only form.
# h2h: previous meetings in the same league, from the current home team's side.
FEATURE_GROUPS = frozenset({"venue", "h2h"})


@dataclass(frozen=True)
class TrainingExample:
    source_key: str
    league: str
    season: int
    kickoff_utc: datetime
    home_team: str
    away_team: str
    features: dict[str, float | None]
    result_label: int  # 0=home, 1=draw, 2=away
    over_2_5_label: int
    btts_label: int
    total_corners_label: int | None
    close_home_odds: float | None
    close_draw_odds: float | None
    close_away_odds: float | None


@dataclass(frozen=True)
class _TeamPerformance:
    kickoff_utc: datetime
    goals_for: int
    goals_against: int
    shots_for: int | None
    shots_against: int | None
    shots_on_target_for: int | None
    shots_on_target_against: int | None
    corners_for: int | None
    corners_against: int | None
    yellow_cards: int | None
    red_cards: int | None
    points: int


def _mean(rows: list[_TeamPerformance], field: str) -> float | None:
    values = [getattr(row, field) for row in rows if getattr(row, field) is not None]
    return round(fmean(values), 4) if values else None


def _team_features(
    prefix: str,
    history: list[_TeamPerformance],
    kickoff: datetime,
    window: int,
) -> dict[str, float | None]:
    recent = history[-window:]
    features: dict[str, float | None] = {f"{prefix}_matches": float(len(recent))}
    for field in (
        "goals_for",
        "goals_against",
        "shots_for",
        "shots_against",
        "shots_on_target_for",
        "shots_on_target_against",
        "corners_for",
        "corners_against",
        "yellow_cards",
        "red_cards",
        "points",
    ):
        features[f"{prefix}_{field}_avg"] = _mean(recent, field)
    features[f"{prefix}_rest_days"] = (
        min((kickoff - history[-1].kickoff_utc).total_seconds() / 86400, 30.0)
        if history
        else None
    )
    return features


def _venue_features(
    prefix: str, venue_history: list[_TeamPerformance], window: int
) -> dict[str, float | None]:
    recent = venue_history[-window:]
    features: dict[str, float | None] = {f"{prefix}_venue_matches": float(len(recent))}
    for field in ("goals_for", "goals_against", "points"):
        features[f"{prefix}_venue_{field}_avg"] = _mean(recent, field)
    return features


@dataclass(frozen=True)
class _Meeting:
    home_team: str
    home_goals: int
    away_goals: int


def _h2h_features(
    home_team: str, meetings: list[_Meeting], window: int
) -> dict[str, float | None]:
    recent = meetings[-window:]
    if not recent:
        return {"h2h_matches": 0.0, "h2h_home_points_avg": None, "h2h_home_goal_diff_avg": None}
    points: list[int] = []
    goal_diffs: list[int] = []
    for meeting in recent:
        # Past venues differ; always score from today's home team's side.
        diff = meeting.home_goals - meeting.away_goals
        if meeting.home_team != home_team:
            diff = -diff
        goal_diffs.append(diff)
        points.append(3 if diff > 0 else 1 if diff == 0 else 0)
    return {
        "h2h_matches": float(len(recent)),
        "h2h_home_points_avg": round(fmean(points), 4),
        "h2h_home_goal_diff_avg": round(fmean(goal_diffs), 4),
    }


def _market_features(match: MatchObservation) -> dict[str, float | None]:
    odds = (match.close_home_odds, match.close_draw_odds, match.close_away_odds)
    if any(value is None for value in odds):
        return {
            "market_home_prob": None,
            "market_draw_prob": None,
            "market_away_prob": None,
        }
    raw = [1.0 / value for value in odds if value is not None]
    total = sum(raw)
    return {
        "market_home_prob": round(raw[0] / total, 6),
        "market_draw_prob": round(raw[1] / total, 6),
        "market_away_prob": round(raw[2] / total, 6),
    }


def _performance(match: MatchObservation, *, home: bool) -> _TeamPerformance:
    goals_for = match.home_goals if home else match.away_goals
    goals_against = match.away_goals if home else match.home_goals
    return _TeamPerformance(
        kickoff_utc=match.kickoff_utc,
        goals_for=goals_for,
        goals_against=goals_against,
        shots_for=match.home_shots if home else match.away_shots,
        shots_against=match.away_shots if home else match.home_shots,
        shots_on_target_for=(
            match.home_shots_on_target if home else match.away_shots_on_target
        ),
        shots_on_target_against=(
            match.away_shots_on_target if home else match.home_shots_on_target
        ),
        corners_for=match.home_corners if home else match.away_corners,
        corners_against=match.away_corners if home else match.home_corners,
        yellow_cards=match.home_yellow_cards if home else match.away_yellow_cards,
        red_cards=match.home_red_cards if home else match.away_red_cards,
        points=3 if goals_for > goals_against else 1 if goals_for == goals_against else 0,
    )


def build_training_examples(
    matches: list[MatchObservation],
    *,
    window: int = 8,
    min_team_matches: int = 3,
    extra_features: Collection[str] = (),
    h2h_window: int = 6,
) -> list[TrainingExample]:
    """Build chronological rolling features, never using the current match's result.

    ``extra_features`` adds columns only; it never changes which matches become
    examples, so a baseline and a candidate are scored on identical rows.
    """
    if window < 1 or min_team_matches < 0 or h2h_window < 1:
        raise ValueError(
            "window and h2h_window must be >= 1 and min_team_matches must be >= 0"
        )
    unknown = set(extra_features) - FEATURE_GROUPS
    if unknown:
        raise ValueError(
            f"unknown feature groups {sorted(unknown)}; choose from {sorted(FEATURE_GROUPS)}"
        )

    history: dict[tuple[str, str], list[_TeamPerformance]] = defaultdict(list)
    home_venue: dict[tuple[str, str], list[_TeamPerformance]] = defaultdict(list)
    away_venue: dict[tuple[str, str], list[_TeamPerformance]] = defaultdict(list)
    meetings: dict[tuple[str, frozenset[str]], list[_Meeting]] = defaultdict(list)
    examples: list[TrainingExample] = []
    for match in sorted(matches, key=lambda row: row.kickoff_utc):
        home_key = (match.league, match.home_team)
        away_key = (match.league, match.away_team)
        pair_key = (match.league, frozenset((match.home_team, match.away_team)))
        home_history = history[home_key]
        away_history = history[away_key]
        if len(home_history) >= min_team_matches and len(away_history) >= min_team_matches:
            features = {
                **_team_features("home", home_history, match.kickoff_utc, window),
                **_team_features("away", away_history, match.kickoff_utc, window),
                **_market_features(match),
            }
            if "venue" in extra_features:
                features |= _venue_features("home", home_venue[home_key], window)
                features |= _venue_features("away", away_venue[away_key], window)
            if "h2h" in extra_features:
                features |= _h2h_features(match.home_team, meetings[pair_key], h2h_window)
            total_corners = (
                match.home_corners + match.away_corners
                if match.home_corners is not None and match.away_corners is not None
                else None
            )
            examples.append(
                TrainingExample(
                    source_key=match.source_key,
                    league=match.league,
                    season=match.season,
                    kickoff_utc=match.kickoff_utc,
                    home_team=match.home_team,
                    away_team=match.away_team,
                    features=features,
                    result_label=(
                        0
                        if match.home_goals > match.away_goals
                        else 1
                        if match.home_goals == match.away_goals
                        else 2
                    ),
                    over_2_5_label=int(match.home_goals + match.away_goals > 2.5),
                    btts_label=int(match.home_goals > 0 and match.away_goals > 0),
                    total_corners_label=total_corners,
                    close_home_odds=match.close_home_odds,
                    close_draw_odds=match.close_draw_odds,
                    close_away_odds=match.close_away_odds,
                )
            )

        # Update only after emitting the current example: this is the leakage barrier.
        home_performance = _performance(match, home=True)
        away_performance = _performance(match, home=False)
        home_history.append(home_performance)
        away_history.append(away_performance)
        home_venue[home_key].append(home_performance)
        away_venue[away_key].append(away_performance)
        meetings[pair_key].append(
            _Meeting(match.home_team, match.home_goals, match.away_goals)
        )
    return examples
