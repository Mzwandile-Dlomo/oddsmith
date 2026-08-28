"""Leakage-safe pre-match features and labels for supervised models.

Match statistics are valuable only as history. The current match's shots,
corners, cards, and goals are appended *after* its feature vector is emitted, so
no training example can see information that was unavailable before kickoff.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from statistics import fmean

from oddsmith.db import MatchObservation


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
) -> list[TrainingExample]:
    """Build chronological rolling features, never using the current match's result."""
    if window < 1 or min_team_matches < 0:
        raise ValueError("window must be >= 1 and min_team_matches must be >= 0")

    history: dict[tuple[str, str], list[_TeamPerformance]] = defaultdict(list)
    examples: list[TrainingExample] = []
    for match in sorted(matches, key=lambda row: row.kickoff_utc):
        home_history = history[(match.league, match.home_team)]
        away_history = history[(match.league, match.away_team)]
        if len(home_history) >= min_team_matches and len(away_history) >= min_team_matches:
            features = {
                **_team_features("home", home_history, match.kickoff_utc, window),
                **_team_features("away", away_history, match.kickoff_utc, window),
                **_market_features(match),
            }
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
        home_history.append(_performance(match, home=True))
        away_history.append(_performance(match, home=False))
    return examples
