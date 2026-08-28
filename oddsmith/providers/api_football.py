"""API-Football (v3) adapter.

Two upstream hosts share the same v3 API but differ in auth headers:
  * Direct  (v3.football.api-sports.io):  header  x-apisports-key: <key>
  * RapidAPI (…rapidapi.com):             headers x-rapidapi-key / x-rapidapi-host

Endpoints used:
  GET /fixtures?from=YYYY-MM-DD&to=YYYY-MM-DD&timezone=UTC
    -> response[].fixture{id,date}, .teams.home.name/.away.name, .league.name
  GET /odds?fixture={id}
    -> response[].bookmakers[].bets[]{id,name,values[]{value,odd}}

Bet ids we map:
  1 Match Winner (1X2)        -> MATCH_WINNER  (Home / Draw / Away)
  8 Both Teams Score          -> BTTS          (Yes / No)
  5 Goals Over/Under          -> OVER_UNDER    ("Over 2.5" -> point 2.5)
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

import httpx

from oddsmith.config import Settings, get_settings
from oddsmith.models import Fixture, Market, MarketType, Outcome
from oddsmith.providers.base import OddsProvider, ProviderError

BET_MATCH_WINNER = 1
BET_BTTS = 8
BET_OVER_UNDER = 5

_BET_ID_TO_TYPE = {
    BET_MATCH_WINNER: MarketType.MATCH_WINNER,
    BET_BTTS: MarketType.BTTS,
    BET_OVER_UNDER: MarketType.OVER_UNDER,
}

_OVER_UNDER_RE = re.compile(r"^(Over|Under)\s+([0-9]+(?:\.[0-9]+)?)$", re.IGNORECASE)


class ApiFootballProvider(OddsProvider):
    name = "api_football"

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = client

    def _headers(self) -> dict[str, str]:
        key = self._settings.api_football_key
        if not key:
            raise ProviderError("API_FOOTBALL_KEY is not configured")
        if self._settings.api_football_use_rapidapi:
            host = self._settings.api_football_base_url.replace("https://", "").rstrip("/")
            return {"x-rapidapi-key": key, "x-rapidapi-host": host}
        return {"x-apisports-key": key}

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        return httpx.AsyncClient(
            base_url=self._settings.api_football_base_url,
            timeout=self._settings.http_timeout_seconds,
        )

    async def list_fixtures(
        self,
        *,
        date_from: datetime,
        date_to: datetime,
        markets: list[MarketType] | None = None,
    ) -> list[Fixture]:
        client = await self._get_client()
        owns_client = self._client is None
        headers = self._headers()
        try:
            fixtures: list[Fixture] = []
            for day in _days_in_range(date_from, date_to):
                resp = await client.get(
                    "/fixtures",
                    headers=headers,
                    params={"date": day.isoformat(), "timezone": "UTC"},
                )
                resp.raise_for_status()
                entries = resp.json().get("response", [])
                fixtures.extend(self._parse_fixture(e) for e in entries)

            for fixture in fixtures:
                raw_id = fixture.id.split(":", 1)[1]
                fixture.markets = await self._fetch_markets(client, headers, raw_id)
        except httpx.HTTPError as exc:  # pragma: no cover - network failure path
            raise ProviderError(f"api-football request failed: {exc}") from exc
        finally:
            if owns_client:
                await client.aclose()
        return fixtures

    async def get_markets(self, fixture_id: str) -> list[Fixture]:
        raw_id = fixture_id.split(":", 1)[-1]
        client = await self._get_client()
        owns_client = self._client is None
        headers = self._headers()
        try:
            markets = await self._fetch_markets(client, headers, raw_id)
        finally:
            if owns_client:
                await client.aclose()
        return markets

    async def _fetch_markets(
        self, client: httpx.AsyncClient, headers: dict[str, str], raw_fixture_id: str
    ) -> list[Market]:
        resp = await client.get("/odds", headers=headers, params={"fixture": raw_fixture_id})
        resp.raise_for_status()
        response = resp.json().get("response", [])
        if not response:
            return []
        markets: list[Market] = []
        for bookmaker in response[0].get("bookmakers", []):
            title = bookmaker.get("name")
            for bet in bookmaker.get("bets", []):
                mtype = _BET_ID_TO_TYPE.get(bet.get("id"))
                if mtype is None:
                    continue
                outcomes = self._parse_values(mtype, bet.get("values", []))
                if outcomes:
                    markets.append(
                        Market(
                            type=mtype,
                            outcomes=outcomes,
                            bookmaker=title,
                            provider=self.name,
                        )
                    )
        return markets

    def _parse_values(self, mtype: MarketType, values: list[dict]) -> list[Outcome]:
        outcomes: list[Outcome] = []
        for v in values:
            price = _to_float(v.get("odd"))
            if price is None or price <= 1.0:
                continue
            label = str(v.get("value", "")).strip()
            name, point = self._canonical(mtype, label)
            if name is None:
                continue
            outcomes.append(Outcome(name=name, price=price, point=point))
        return outcomes

    def _canonical(
        self, mtype: MarketType, label: str
    ) -> tuple[str | None, float | None]:
        if mtype is MarketType.MATCH_WINNER:
            mapping = {"home": "Home", "draw": "Draw", "away": "Away"}
            return mapping.get(label.lower()), None
        if mtype is MarketType.BTTS:
            if label.lower() in {"yes", "no"}:
                return label.capitalize(), None
            return None, None
        if mtype is MarketType.OVER_UNDER:
            match = _OVER_UNDER_RE.match(label)
            if not match:
                return None, None
            return match.group(1).capitalize(), float(match.group(2))
        return None, None

    def _parse_fixture(self, entry: dict) -> Fixture:
        fx = entry["fixture"]
        teams = entry["teams"]
        league = entry.get("league", {})
        return Fixture(
            id=f"{self.name}:{fx['id']}",
            home_team=teams["home"]["name"],
            away_team=teams["away"]["name"],
            kickoff_utc=datetime.fromisoformat(fx["date"].replace("Z", "+00:00")),
            league=league.get("name"),
            provider=self.name,
        )


def _to_float(value: object) -> float | None:
    if isinstance(value, (int, float, str)):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return None


# The Free plan rejects from/to ranges (and the `next` param), but `date=` for a
# single day works unrestricted. We scan day-by-day, capped so a wide window
# cannot exhaust the tight daily request quota.
_MAX_DAYS = 7


def _days_in_range(date_from: datetime, date_to: datetime) -> list[date]:
    cursor = date_from.date()
    end = date_to.date()
    days: list[date] = []
    while cursor <= end and len(days) < _MAX_DAYS:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days
