"""Parse and import Football-Data CSV archives.

Football-Data files evolve across seasons, so the parser uses ordered aliases
for every field and keeps the original row in ``raw_payload``. Missing statistics
remain ``None``; treating an unrecorded corner count as zero would poison a model.
"""

from __future__ import annotations

import csv
import hashlib
import io
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime, time

import httpx

from sqlmodel import Session, select

from oddsmith.db import HistoricalMatch, MatchObservation

DIVISION_NAMES = {
    "E0": "EPL",
    "D1": "Bundesliga",
    "SP1": "LaLiga",
    "I1": "SerieA",
    "F1": "Ligue1",
    "N1": "Eredivisie",
    "P1": "PrimeiraLiga",
    "SC0": "ScottishPremiership",
}

MAJOR_DIVISIONS = {
    "E0": (39, "Premier League", "England"),
    "D1": (78, "Bundesliga", "Germany"),
    "SP1": (140, "La Liga", "Spain"),
    "I1": (135, "Serie A", "Italy"),
    "F1": (61, "Ligue 1", "France"),
}

BASE_URL = "https://www.football-data.co.uk/mmz4281/{season_code}/{division}.csv"


@dataclass(frozen=True)
class ImportResult:
    parsed: int
    inserted: int
    existing: int
    baseline_inserted: int
    rejected: int


@dataclass(frozen=True)
class FootballDataDocument:
    season_code: str
    division: str
    observations: list[MatchObservation]
    rejected: int


class FootballDataCsvProvider:
    """Download and normalize Football-Data league CSV documents."""

    name = "football_data"

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        ca_bundle: str | None = None,
    ) -> None:
        self._client = client
        self._ca_bundle = ca_bundle

    def fetch(self, *, season_code: str, division: str) -> FootballDataDocument:
        season = season_start(season_code)
        division = division.upper()
        if division not in MAJOR_DIVISIONS:
            raise ValueError(f"unsupported Football-Data division: {division}")
        verify: bool | ssl.SSLContext = True
        if self._ca_bundle:
            verify = ssl.create_default_context()
            verify.load_verify_locations(cafile=self._ca_bundle)
        client = self._client or httpx.Client(
            timeout=30,
            follow_redirects=True,
            verify=verify,
        )
        owns_client = self._client is None
        try:
            response = client.get(
                BASE_URL.format(season_code=season_code, division=division)
            )
            response.raise_for_status()
            observations, rejected = parse_csv(response.text, season=season)
            return FootballDataDocument(
                season_code=season_code,
                division=division,
                observations=observations,
                rejected=rejected,
            )
        finally:
            if owns_client:
                client.close()


def season_code(start_year: int) -> str:
    if start_year < 1900 or start_year >= 2099:
        raise ValueError("season start year must be between 1900 and 2098")
    return f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"


def season_start(code: str) -> int:
    if len(code) != 4 or not code.isdigit():
        raise ValueError("season code must look like 2425")
    year = int(code[:2])
    return 1900 + year if year >= 90 else 2000 + year


def _first(row: dict[str, str], *names: str) -> str | None:
    for name in names:
        value = row.get(name)
        if value is not None and value.strip() != "":
            return value.strip()
    return None


def _integer(row: dict[str, str], *names: str) -> int | None:
    value = _first(row, *names)
    if value is None:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _decimal(row: dict[str, str], *names: str) -> float | None:
    value = _first(row, *names)
    if value is None:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if parsed > 1.0 else None


def _kickoff(row: dict[str, str]) -> datetime | None:
    raw_date = _first(row, "Date")
    if raw_date is None:
        return None
    parsed_date = None
    for pattern in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            parsed_date = datetime.strptime(raw_date, pattern).date()
            break
        except ValueError:
            continue
    if parsed_date is None:
        return None

    parsed_time = time(12, 0)
    raw_time = _first(row, "Time")
    if raw_time:
        for pattern in ("%H:%M", "%H:%M:%S"):
            try:
                parsed_time = datetime.strptime(raw_time, pattern).time()
                break
            except ValueError:
                continue
    # The archive does not carry a timezone. Noon UTC is used when time is absent;
    # chronological daily features remain valid and the raw value is preserved.
    return datetime.combine(parsed_date, parsed_time, tzinfo=UTC)


def _source_key(division: str, season: int, kickoff: datetime, home: str, away: str) -> str:
    identity = f"{division}|{season}|{kickoff.date().isoformat()}|{home}|{away}".casefold()
    digest = hashlib.sha256(identity.encode()).hexdigest()[:24]
    return f"football_data:{digest}"


def _odds_payload(row: dict[str, str]) -> dict:
    """Normalize the commonly available maximum, average, and handicap prices."""
    return {
        "match_winner": {
            "closing_max": {
                "home": _decimal(row, "MaxCH"),
                "draw": _decimal(row, "MaxCD"),
                "away": _decimal(row, "MaxCA"),
            },
            "closing_average": {
                "home": _decimal(row, "AvgCH"),
                "draw": _decimal(row, "AvgCD"),
                "away": _decimal(row, "AvgCA"),
            },
            "max": {
                "home": _decimal(row, "MaxH", "BbMxH"),
                "draw": _decimal(row, "MaxD", "BbMxD"),
                "away": _decimal(row, "MaxA", "BbMxA"),
            },
            "average": {
                "home": _decimal(row, "AvgH", "BbAvH"),
                "draw": _decimal(row, "AvgD", "BbAvD"),
                "away": _decimal(row, "AvgA", "BbAvA"),
            },
        },
        "over_under_2_5": {
            "closing_max": {
                "over": _decimal(row, "MaxC>2.5"),
                "under": _decimal(row, "MaxC<2.5"),
            },
            "closing_average": {
                "over": _decimal(row, "AvgC>2.5"),
                "under": _decimal(row, "AvgC<2.5"),
            },
            "max": {
                "over": _decimal(row, "Max>2.5", "BbMx>2.5"),
                "under": _decimal(row, "Max<2.5", "BbMx<2.5"),
            },
            "average": {
                "over": _decimal(row, "Avg>2.5", "BbAv>2.5"),
                "under": _decimal(row, "Avg<2.5", "BbAv<2.5"),
            },
        },
        "asian_handicap": {
            "line": _number(row, "AHh", "BbAHh", "B365AH"),
            "max": {
                "home": _decimal(row, "MaxAHH", "BbMxAHH"),
                "away": _decimal(row, "MaxAHA", "BbMxAHA"),
            },
            "average": {
                "home": _decimal(row, "AvgAHH", "BbAvAHH"),
                "away": _decimal(row, "AvgAHA", "BbAvAHA"),
            },
        },
    }


def _number(row: dict[str, str], *names: str) -> float | None:
    value = _first(row, *names)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_csv(
    document: str,
    *,
    season: int,
    league: str | None = None,
) -> tuple[list[MatchObservation], int]:
    """Return valid match rows and the number rejected as incomplete."""
    reader = csv.DictReader(io.StringIO(document.lstrip("\ufeff")))
    observations: list[MatchObservation] = []
    rejected = 0
    for raw in reader:
        row = {str(k).strip(): str(v).strip() for k, v in raw.items() if k is not None and v}
        division = _first(row, "Div") or "unknown"
        kickoff = _kickoff(row)
        home = _first(row, "HomeTeam")
        away = _first(row, "AwayTeam")
        home_goals = _integer(row, "FTHG")
        away_goals = _integer(row, "FTAG")
        if kickoff is None or not home or not away or home_goals is None or away_goals is None:
            rejected += 1
            continue

        observations.append(
            MatchObservation(
                source_key=_source_key(division, season, kickoff, home, away),
                source="football_data",
                source_league_code=division,
                league=league or DIVISION_NAMES.get(division, division),
                season=season,
                kickoff_utc=kickoff,
                home_team=home,
                away_team=away,
                referee=_first(row, "Referee"),
                home_goals=home_goals,
                away_goals=away_goals,
                half_time_home_goals=_integer(row, "HTHG"),
                half_time_away_goals=_integer(row, "HTAG"),
                home_shots=_integer(row, "HS"),
                away_shots=_integer(row, "AS"),
                home_shots_on_target=_integer(row, "HST"),
                away_shots_on_target=_integer(row, "AST"),
                home_corners=_integer(row, "HC"),
                away_corners=_integer(row, "AC"),
                home_fouls=_integer(row, "HF"),
                away_fouls=_integer(row, "AF"),
                home_yellow_cards=_integer(row, "HY"),
                away_yellow_cards=_integer(row, "AY"),
                home_red_cards=_integer(row, "HR"),
                away_red_cards=_integer(row, "AR"),
                # Prefer market closing maximums, then pre-closing maximums,
                # then a single bookmaker. Aliases cover old and new files.
                close_home_odds=_decimal(row, "MaxCH", "MaxH", "B365CH", "B365H"),
                close_draw_odds=_decimal(row, "MaxCD", "MaxD", "B365CD", "B365D"),
                close_away_odds=_decimal(row, "MaxCA", "MaxA", "B365CA", "B365A"),
                close_over_2_5_odds=_decimal(
                    row, "MaxC>2.5", "Max>2.5", "B365C>2.5", "B365>2.5"
                ),
                close_under_2_5_odds=_decimal(
                    row, "MaxC<2.5", "Max<2.5", "B365C<2.5", "B365<2.5"
                ),
                raw_payload={**row, "_normalized_odds": _odds_payload(row)},
            )
        )
    return observations, rejected


def import_observations(
    session: Session,
    observations: list[MatchObservation],
    *,
    rejected: int = 0,
    sync_poisson_baseline: bool = True,
) -> ImportResult:
    """Insert new source rows idempotently and optionally feed the baseline model."""
    keys = [row.source_key for row in observations]
    existing_keys = set(
        session.exec(select(MatchObservation.source_key).where(MatchObservation.source_key.in_(keys)))
    )
    new_rows = [row for row in observations if row.source_key not in existing_keys]
    session.add_all(new_rows)

    baseline_inserted = 0
    if sync_poisson_baseline and new_rows:
        baseline_keys = {
            (r.league, r.season, r.kickoff_utc.date(), r.home_team, r.away_team)
            for r in session.exec(select(HistoricalMatch))
        }
        for row in new_rows:
            key = (row.league, row.season, row.kickoff_utc.date(), row.home_team, row.away_team)
            if key in baseline_keys:
                continue
            session.add(
                HistoricalMatch(
                    league=row.league,
                    season=row.season,
                    kickoff_utc=row.kickoff_utc,
                    home_team=row.home_team,
                    away_team=row.away_team,
                    home_goals=row.home_goals,
                    away_goals=row.away_goals,
                )
            )
            baseline_keys.add(key)
            baseline_inserted += 1

    session.commit()
    return ImportResult(
        parsed=len(observations),
        inserted=len(new_rows),
        existing=len(observations) - len(new_rows),
        baseline_inserted=baseline_inserted,
        rejected=rejected,
    )
