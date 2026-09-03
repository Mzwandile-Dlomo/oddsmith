"""Fixture Download full-season schedule provider.

The public JSON feed has no authentication and uses a match number scoped to a
competition and season. Those three source fields form our stable source key;
we do not invent external fixture or team IDs.
"""

from __future__ import annotations

import ssl
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from oddsmith.db import ScheduledFixture

BASE_URL = "https://fixturedownload.com/feed/json/{slug}-{season}"


@dataclass(frozen=True)
class FixtureDownloadCompetition:
    key: str
    slug: str
    league_id: int
    name: str
    country: str


COMPETITIONS = (
    FixtureDownloadCompetition("epl", "epl", 39, "Premier League", "England"),
    FixtureDownloadCompetition("la-liga", "la-liga", 140, "La Liga", "Spain"),
    FixtureDownloadCompetition("bundesliga", "bundesliga", 78, "Bundesliga", "Germany"),
    FixtureDownloadCompetition("serie-a", "serie-a", 135, "Serie A", "Italy"),
    FixtureDownloadCompetition("ligue-1", "ligue-1", 61, "Ligue 1", "France"),
)

BY_KEY = {competition.key: competition for competition in COMPETITIONS}


class FixtureDownloadProvider:
    name = "fixture_download"

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        ca_bundle: str | None = None,
    ) -> None:
        self._client = client
        self._ca_bundle = ca_bundle

    def fetch(
        self, competition: FixtureDownloadCompetition, season: int
    ) -> list[ScheduledFixture]:
        verify: bool | ssl.SSLContext = True
        if self._ca_bundle:
            verify = ssl.create_default_context()
            verify.load_verify_locations(cafile=self._ca_bundle)
        client = self._client or httpx.Client(timeout=30, verify=verify)
        owns_client = self._client is None
        try:
            response = client.get(
                BASE_URL.format(slug=competition.slug, season=season)
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                raise ValueError("Fixture Download returned a non-list response")
            return [self._normalize(row, competition, season) for row in payload]
        finally:
            if owns_client:
                client.close()

    def _normalize(
        self,
        row: dict,
        competition: FixtureDownloadCompetition,
        season: int,
    ) -> ScheduledFixture:
        match_number = int(row["MatchNumber"])
        kickoff = (
            datetime.strptime(row["DateUtc"], "%Y-%m-%d %H:%M:%SZ")
            .replace(tzinfo=UTC)
            .astimezone(UTC)
            .replace(tzinfo=None)
        )
        return ScheduledFixture(
            source_key=f"fixture_download:{competition.key}:{season}:{match_number}",
            source=self.name,
            competition_key=competition.key,
            league_id=competition.league_id,
            league_name=competition.name,
            country=competition.country,
            season=season,
            match_number=match_number,
            round_number=_integer(row.get("RoundNumber")),
            kickoff_utc=kickoff,
            location=_string(row.get("Location")),
            home_team=str(row["HomeTeam"]),
            away_team=str(row["AwayTeam"]),
            home_goals=_integer(row.get("HomeTeamScore")),
            away_goals=_integer(row.get("AwayTeamScore")),
            raw_payload=row,
        )


def _integer(value: object) -> int | None:
    return None if value is None or value == "" else int(value)


def _string(value: object) -> str | None:
    return None if value is None or value == "" else str(value)
