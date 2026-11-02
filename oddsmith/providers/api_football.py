"""API-Football (v3) adapter.

Two upstream hosts share the same v3 API but differ in auth headers:
  * Direct  (v3.football.api-sports.io):  header  x-apisports-key: <key>
  * RapidAPI (…rapidapi.com):             headers x-rapidapi-key / x-rapidapi-host

Endpoints used:
  GET /fixtures?from=YYYY-MM-DD&to=YYYY-MM-DD&timezone=UTC
    -> response[].fixture{id,date}, .teams.home.name/.away.name, .league{id,name,country}
  GET /odds?fixture={id}
    -> response[].bookmakers[].bets[]{id,name,values[]{value,odd}}

Quota: the free plan allows 100 requests a day and 10 a minute, and every
request below costs one. ``/fixtures?date=`` returns the whole world's card
(~500 matches) in one request, but odds cost one request *per fixture* — so we
keep only our tracked competitions and price a few upcoming ones per refresh.
Every call reserves its cost with the shared ``QuotaGuard`` first, and ``_get``
spaces calls by ``api_football_min_interval_seconds`` for the per-minute limit.

Bet ids we map:
  1 Match Winner (1X2)        -> MATCH_WINNER  (Home / Draw / Away)
  8 Both Teams Score          -> BTTS          (Yes / No)
  5 Goals Over/Under          -> OVER_UNDER    ("Over 2.5" -> point 2.5)
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta

import httpx

from oddsmith.competitions import BY_ID, COMPETITIONS
from oddsmith.config import Settings, get_settings
from oddsmith.models import Fixture, Market, MarketType, Outcome
from oddsmith.providers.base import OddsProvider, ProviderError, retry_after
from oddsmith.quota import QuotaExceeded, QuotaGuard, api_football_policy

BET_MATCH_WINNER = 1
BET_BTTS = 8
BET_OVER_UNDER = 5

_BET_ID_TO_TYPE = {
    BET_MATCH_WINNER: MarketType.MATCH_WINNER,
    BET_BTTS: MarketType.BTTS,
    BET_OVER_UNDER: MarketType.OVER_UNDER,
}

_OVER_UNDER_RE = re.compile(r"^(Over|Under)\s+([0-9]+(?:\.[0-9]+)?)$", re.IGNORECASE)
_COMPLETED_STATUSES = {"FT", "AET", "PEN"}

# The Odds API does not price these, so their odds requests go first.
_ODDS_FIRST = {"sa-premiership", "copa-del-rey", "coppa-italia", "coupe-de-france", "fa-cup"}
_COMPETITION_ORDER = {competition.api_football_id: i for i, competition in enumerate(COMPETITIONS)}


@dataclass(frozen=True)
class ApiFootballResult:
    fixture_id: str
    kickoff_utc: datetime
    league: str
    season: int
    home_team_id: int
    away_team_id: int
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int
    home_shots: int | None = None
    away_shots: int | None = None
    home_shots_on_target: int | None = None
    away_shots_on_target: int | None = None
    home_corners: int | None = None
    away_corners: int | None = None
    home_fouls: int | None = None
    away_fouls: int | None = None
    home_yellow_cards: int | None = None
    away_yellow_cards: int | None = None
    home_red_cards: int | None = None
    away_red_cards: int | None = None
    league_id: int | None = None


@dataclass(frozen=True)
class ApiFootballQuota:
    requests_remaining: int | None
    minute_remaining: int | None


class PlanRestricted(ProviderError):
    """The plan does not serve this request; the free plan only answers for
    dates from yesterday to tomorrow, so an older results day is refused."""


class ApiFootballProvider(OddsProvider):
    name = "api_football"

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.AsyncClient | None = None,
        guard: QuotaGuard | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = client
        self._guard = guard
        self._pace = asyncio.Lock()
        self._last_request = float("-inf")

    @property
    def guard(self) -> QuotaGuard:
        if self._guard is None:
            self._guard = QuotaGuard(
                api_football_policy(self._settings), database_url=self._settings.database_url
            )
        return self._guard

    async def _get(
        self,
        client: httpx.AsyncClient,
        path: str,
        params: dict[str, object],
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Send one metered request, after reserving it with the quota guard.

        Requests are spaced from the last one, and a rate limit waits and
        retries. Every attempt is reserved, so the guard never undercounts.
        """
        headers = headers or self._headers()
        interval = self._settings.api_football_min_interval_seconds
        retries = self._settings.api_football_max_retries
        for attempt in range(retries + 1):
            self.guard.require(1)
            async with self._pace:
                wait = self._last_request + interval - time.monotonic()
                if wait > 0:
                    await asyncio.sleep(wait)
                response = await client.get(path, headers=headers, params=params)
                self._last_request = time.monotonic()
            self.guard.observe(_header_integer(response, "x-ratelimit-requests-remaining"))
            if _is_rate_limited(response):
                # Shown to callers as a 429 so raise_for_status catches it; a 200
                # with an empty list would read as "no matches that day".
                response = httpx.Response(
                    429, headers=response.headers, request=response.request
                )
            if response.status_code != 429 or attempt == retries:
                _raise_for_body_errors(response)
                return response
            await asyncio.sleep(retry_after(response, attempt))
        raise AssertionError("unreachable")

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
            order: dict[str, tuple[int, int]] = {}
            for day in _days_in_range(date_from, date_to):
                try:
                    resp = await self._get(
                        client,
                        "/fixtures",
                        {"date": day.isoformat(), "timezone": "UTC"},
                        headers,
                    )
                except QuotaExceeded:
                    if not fixtures:
                        raise
                    break  # keep the days we already paid for
                resp.raise_for_status()
                for entry in resp.json().get("response", []):
                    league_id = entry.get("league", {}).get("id")
                    if league_id not in BY_ID:
                        continue
                    fixture = self._parse_fixture(entry)
                    fixtures.append(fixture)
                    first = 0 if BY_ID[league_id].key in _ODDS_FIRST else 1
                    order[fixture.id] = (first, _COMPETITION_ORDER[league_id])

            now = datetime.now(UTC)
            upcoming = sorted(
                (f for f in fixtures if f.kickoff_utc > now),
                key=lambda f: (*order[f.id], f.kickoff_utc),
            )
            for fixture in upcoming[: self._settings.api_football_odds_per_refresh]:
                raw_id = fixture.id.split(":", 1)[1]
                try:
                    fixture.markets = await self._fetch_markets(client, headers, raw_id)
                except QuotaExceeded:
                    break
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

    async def completed_results(self, day: date) -> tuple[list[ApiFootballResult], ApiFootballQuota]:
        """Return final scores for one day in one quota-counted request."""
        client = await self._get_client()
        owns_client = self._client is None
        try:
            response = await self._get(
                client, "/fixtures", {"date": day.isoformat(), "timezone": "UTC"}
            )
            response.raise_for_status()
            results = [
                parsed
                for entry in response.json().get("response", [])
                if (parsed := self._parse_completed_result(entry)) is not None
            ]
            return results, _quota(response)
        finally:
            if owns_client:
                await client.aclose()

    async def league_fixtures(
        self, *, league_id: int, season: int
    ) -> tuple[list[dict], ApiFootballQuota]:
        """Fetch one competition-season schedule in a single provider request."""
        return await self._raw_response(
            "/fixtures", {"league": league_id, "season": season, "timezone": "UTC"}
        )

    async def fixture_resource(
        self, fixture_id: int, resource: str
    ) -> tuple[list[dict] | dict, ApiFootballQuota]:
        """Fetch a supported match resource for lazy, persistent caching."""
        endpoints = {
            "details": ("/fixtures", {"id": fixture_id, "timezone": "UTC"}),
            "statistics": ("/fixtures/statistics", {"fixture": fixture_id}),
            "odds": ("/odds", {"fixture": fixture_id}),
            "predictions": ("/predictions", {"fixture": fixture_id}),
        }
        if resource not in endpoints:
            raise ValueError(f"unsupported fixture resource: {resource}")
        endpoint, params = endpoints[resource]
        return await self._raw_response(endpoint, params)

    async def _raw_response(
        self, endpoint: str, params: dict[str, object]
    ) -> tuple[list[dict] | dict, ApiFootballQuota]:
        client = await self._get_client()
        owns_client = self._client is None
        try:
            response = await self._get(client, endpoint, params)
            response.raise_for_status()
            body = response.json()
            errors = body.get("errors")
            if errors:
                raise ProviderError(f"api-football returned errors: {errors}")
            return body.get("response", []), _quota(response)
        except httpx.HTTPError as exc:
            raise ProviderError(f"api-football request failed: {exc}") from exc
        finally:
            if owns_client:
                await client.aclose()

    async def add_result_statistics(
        self, result: ApiFootballResult
    ) -> tuple[ApiFootballResult, ApiFootballQuota]:
        """Add corner/card/shot facts using one targeted fixture request."""
        client = await self._get_client()
        owns_client = self._client is None
        try:
            response = await self._get(
                client, "/fixtures/statistics", {"fixture": result.fixture_id}
            )
            response.raise_for_status()
            by_team = {
                int(block["team"]["id"]): {
                    item["type"]: _stat_integer(item.get("value"))
                    for item in block.get("statistics", [])
                }
                for block in response.json().get("response", [])
            }
            home = by_team.get(result.home_team_id, {})
            away = by_team.get(result.away_team_id, {})
            return (
                replace(
                    result,
                    home_shots=home.get("Total Shots"),
                    away_shots=away.get("Total Shots"),
                    home_shots_on_target=home.get("Shots on Goal"),
                    away_shots_on_target=away.get("Shots on Goal"),
                    home_corners=home.get("Corner Kicks"),
                    away_corners=away.get("Corner Kicks"),
                    home_fouls=home.get("Fouls"),
                    away_fouls=away.get("Fouls"),
                    home_yellow_cards=home.get("Yellow Cards"),
                    away_yellow_cards=away.get("Yellow Cards"),
                    home_red_cards=home.get("Red Cards"),
                    away_red_cards=away.get("Red Cards"),
                ),
                _quota(response),
            )
        finally:
            if owns_client:
                await client.aclose()

    def _parse_completed_result(self, entry: dict) -> ApiFootballResult | None:
        fixture = entry.get("fixture", {})
        goals = entry.get("goals", {})
        teams = entry.get("teams", {})
        league = entry.get("league", {})
        if (
            fixture.get("status", {}).get("short") not in _COMPLETED_STATUSES
            or goals.get("home") is None
            or goals.get("away") is None
        ):
            return None
        return ApiFootballResult(
            fixture_id=str(fixture["id"]),
            kickoff_utc=datetime.fromisoformat(fixture["date"].replace("Z", "+00:00")),
            league=league_label(league),
            league_id=league.get("id"),
            season=int(league.get("season") or fixture["date"][:4]),
            home_team_id=int(teams["home"]["id"]),
            away_team_id=int(teams["away"]["id"]),
            home_team=str(teams["home"]["name"]),
            away_team=str(teams["away"]["name"]),
            home_goals=int(goals["home"]),
            away_goals=int(goals["away"]),
        )

    async def _fetch_markets(
        self, client: httpx.AsyncClient, headers: dict[str, str], raw_fixture_id: str
    ) -> list[Market]:
        resp = await self._get(client, "/odds", {"fixture": raw_fixture_id}, headers)
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


def league_label(league: dict) -> str:
    """A league name unique across countries.

    API-Football reuses names: Italy and Brazil both run a "Serie A", and
    several countries a "Premier League". Catalogue leagues keep their own
    name; any other gets its country in front unless the name already says it.
    """
    competition = BY_ID.get(league.get("id"))
    if competition is not None:
        return competition.name
    name = str(league.get("name") or "unknown")
    country = str(league.get("country") or "")
    if not country or country == "World" or country.casefold() in name.casefold():
        return name
    return f"{country} {name}"


def _to_float(value: object) -> float | None:
    if isinstance(value, (int, float, str)):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return None


def _stat_integer(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(float(str(value).rstrip("%")))
    except ValueError:
        return None


def _is_rate_limited(response: httpx.Response) -> bool:
    """API-Sports often answers a per-minute limit with 200 and errors.rateLimit."""
    if response.status_code == 429:
        return True
    if response.status_code != 200:
        return False
    try:
        errors = response.json().get("errors")
    except ValueError:
        return False
    return isinstance(errors, dict) and "rateLimit" in errors


def _raise_for_body_errors(response: httpx.Response) -> None:
    """API-Sports refuses with 200 and errors (suspended account, bad key, plan
    limits) and an empty response; read as data, that is "no matches that day"."""
    if response.status_code != 200:
        return
    try:
        body = response.json()
    except ValueError:
        return
    errors = body.get("errors") if isinstance(body, dict) else None
    if isinstance(errors, dict) and set(errors) == {"plan"}:
        raise PlanRestricted(f"api-football returned errors: {errors}")
    if errors:
        raise ProviderError(f"api-football returned errors: {errors}")


def _header_integer(response: httpx.Response, name: str) -> int | None:
    value = response.headers.get(name)
    return int(value) if value is not None else None


def _quota(response: httpx.Response) -> ApiFootballQuota:
    return ApiFootballQuota(
        requests_remaining=_header_integer(response, "x-ratelimit-requests-remaining"),
        minute_remaining=_header_integer(response, "x-ratelimit-remaining"),
    )


# The Free plan rejects from/to ranges (and the `next` param), but `date=` for a
# single day works for the current season (odds by league/season do not; only
# per-fixture odds do). We scan day-by-day, capped so a wide window cannot
# exhaust the tight daily request quota.
_MAX_DAYS = 7


def _days_in_range(date_from: datetime, date_to: datetime) -> list[date]:
    cursor = date_from.date()
    end = date_to.date()
    days: list[date] = []
    while cursor <= end and len(days) < _MAX_DAYS:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days
