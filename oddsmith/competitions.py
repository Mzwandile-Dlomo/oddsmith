"""The initial API-Football competition catalogue exposed by Oddsmith.

Seasons use their starting year: ``2026`` means the 2026/27 European season.
Aliases are deliberately stable API values; display names can change upstream.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Competition:
    key: str
    api_football_id: int
    name: str
    kind: str


COMPETITIONS = (
    Competition("epl", 39, "Premier League", "league"),
    Competition("la-liga", 140, "La Liga", "league"),
    Competition("bundesliga", 78, "Bundesliga", "league"),
    Competition("serie-a", 135, "Serie A", "league"),
    Competition("ligue-1", 61, "Ligue 1", "league"),
    Competition("champions-league", 2, "UEFA Champions League", "continental_cup"),
    Competition("europa-league", 3, "UEFA Europa League", "continental_cup"),
    Competition("sa-premiership", 288, "South African Premiership", "league"),
    Competition("fa-cup", 45, "FA Cup", "domestic_cup"),
    Competition("efl-cup", 48, "League Cup", "domestic_cup"),
    Competition("copa-del-rey", 143, "Copa del Rey", "domestic_cup"),
    Competition("dfb-pokal", 81, "DFB Pokal", "domestic_cup"),
    Competition("coppa-italia", 137, "Coppa Italia", "domestic_cup"),
    Competition("coupe-de-france", 66, "Coupe de France", "domestic_cup"),
)

BY_KEY = {competition.key: competition for competition in COMPETITIONS}
BY_ID = {competition.api_football_id: competition for competition in COMPETITIONS}


def resolve_competition(value: str) -> Competition:
    """Resolve a public alias or API-Football numeric league ID."""
    normalized = value.strip().lower().replace("_", "-").replace(" ", "-")
    if normalized in BY_KEY:
        return BY_KEY[normalized]
    try:
        return BY_ID[int(normalized)]
    except (KeyError, ValueError) as exc:
        supported = ", ".join(BY_KEY)
        raise ValueError(f"unknown league '{value}'; supported values: {supported}") from exc
