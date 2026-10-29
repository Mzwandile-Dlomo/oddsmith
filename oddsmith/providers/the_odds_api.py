"""The Odds API (the-odds-api.com) v4 adapter.

Docs shape (v4):
  GET /v4/sports/{sport}/odds
    ?apiKey=...&regions=uk,eu&markets=h2h,totals&oddsFormat=decimal
     &dateFormat=iso&commenceTimeFrom=...&commenceTimeTo=...

  Response: [ { id, commence_time, home_team, away_team, sport_title,
                bookmakers: [ { key, title,
                  markets: [ { key, outcomes: [ {name, price, point?} ] } ] } ] } ]

Market keys we map:
  h2h     -> MATCH_WINNER  (outcomes: home team / away team / "Draw")
  totals  -> OVER_UNDER    (outcomes: "Over"/"Under" with a `point` line)

BTTS and corner totals use a separately budgeted per-event collector because
they are not available through the lower-cost bulk featured-market endpoint.

Quota: ``/sports`` and ``/events`` are free; an ``/odds`` call costs
markets x regions credits. ``list_fixtures`` asks ``/events`` which sports have
matches in the window and only pays for those, each reserved with the shared
``QuotaGuard`` first.

Rate limit: separate from credits, the API answers 429 to requests sent too
close together. Every call goes through ``_get``, one at a time and spaced by
``the_odds_api_min_interval_seconds``.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from oddsmith.config import Settings, get_settings
from oddsmith.models import Fixture, Market, MarketType, Outcome
from oddsmith.providers.base import OddsProvider, ProviderError, retry_after
from oddsmith.quota import QuotaExceeded, QuotaGuard, the_odds_api_policy

# Soccer competitions to query, in priority order: the refresh cap keeps the
# first fixtures fetched, so the leagues the model is trained on lead. Keys are
# the in-season men's competitions from GET /v4/sports (checked 2026-10-28).
# A sport with no events in the window returns an empty list or a 404.
DEFAULT_SOCCER_SPORTS = (
    "soccer_epl",
    "soccer_spain_la_liga",
    "soccer_italy_serie_a",
    "soccer_germany_bundesliga",
    "soccer_france_ligue_one",
    "soccer_uefa_champs_league",
    "soccer_uefa_europa_league",
    "soccer_brazil_campeonato",
    "soccer_argentina_primera_division",
    "soccer_usa_mls",
    # UEFA and domestic cups
    "soccer_uefa_europa_conference_league",
    "soccer_uefa_nations_league",
    "soccer_england_efl_cup",
    "soccer_germany_dfb_pokal",
    # Second tiers of the big five
    "soccer_efl_champ",
    "soccer_england_league1",
    "soccer_england_league2",
    "soccer_spain_segunda_division",
    "soccer_italy_serie_b",
    "soccer_germany_bundesliga2",
    "soccer_germany_liga3",
    "soccer_france_ligue_two",
    # Rest of Europe
    "soccer_netherlands_eredivisie",
    "soccer_portugal_primeira_liga",
    "soccer_belgium_first_div",
    "soccer_spl",
    "soccer_turkey_super_league",
    "soccer_austria_bundesliga",
    "soccer_switzerland_superleague",
    "soccer_denmark_superliga",
    "soccer_greece_super_league",
    "soccer_poland_ekstraklasa",
    "soccer_norway_eliteserien",
    "soccer_sweden_allsvenskan",
    "soccer_sweden_superettan",
    "soccer_finland_veikkausliiga",
    "soccer_league_of_ireland",
    "soccer_russia_premier_league",
    # Americas
    "soccer_conmebol_copa_libertadores",
    "soccer_conmebol_copa_sudamericana",
    "soccer_brazil_serie_b",
    "soccer_chile_campeonato",
    "soccer_mexico_ligamx",
    # Asia-Pacific and Middle East
    "soccer_saudi_arabia_pro_league",
    "soccer_japan_j_league",
    "soccer_korea_kleague1",
    "soccer_china_superleague",
    "soccer_australia_aleague",
)

_FEATURED_MARKET_KEY_TO_TYPE = {
    "h2h": MarketType.MATCH_WINNER,
    "totals": MarketType.OVER_UNDER,
}
_ADDITIONAL_MARKET_KEY_TO_TYPE = {
    "btts": MarketType.BTTS,
    "alternate_totals_corners": MarketType.CORNER_TOTALS,
}
_MARKET_KEY_TO_TYPE = {
    **_FEATURED_MARKET_KEY_TO_TYPE,
    **_ADDITIONAL_MARKET_KEY_TO_TYPE,
}
_TYPE_TO_FEATURED_MARKET_KEY = {
    value: key for key, value in _FEATURED_MARKET_KEY_TO_TYPE.items()
}
_TYPE_TO_ADDITIONAL_MARKET_KEY = {
    value: key for key, value in _ADDITIONAL_MARKET_KEY_TO_TYPE.items()
}


@dataclass(frozen=True)
class AdditionalMarketCollection:
    fixtures: list[Fixture]
    events_discovered: int
    event_requests: int
    estimated_max_credits: int
    credits_used: int
    credits_remaining: int | None


class TheOddsApiProvider(OddsProvider):
    name = "the_odds_api"

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.AsyncClient | None = None,
        sports: tuple[str, ...] = DEFAULT_SOCCER_SPORTS,
        guard: QuotaGuard | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = client
        self._sports = sports
        self._guard = guard
        self._pace = asyncio.Lock()
        self._last_request = float("-inf")

    @property
    def guard(self) -> QuotaGuard:
        if self._guard is None:
            self._guard = QuotaGuard(
                the_odds_api_policy(self._settings), database_url=self._settings.database_url
            )
        return self._guard

    def _region_count(self) -> int:
        regions = [r for r in self._settings.the_odds_api_regions.split(",") if r]
        return max(len(regions), 1)

    def _observe(self, response: httpx.Response) -> None:
        remaining = response.headers.get("x-requests-remaining")
        if remaining is not None:
            self.guard.observe(int(float(remaining)))

    async def _get(
        self, client: httpx.AsyncClient, path: str, params: dict
    ) -> httpx.Response:
        """Send one request, spaced from the last; a 429 waits and retries."""
        interval = self._settings.the_odds_api_min_interval_seconds
        retries = self._settings.the_odds_api_max_retries
        for attempt in range(retries + 1):
            async with self._pace:
                wait = self._last_request + interval - time.monotonic()
                if wait > 0:
                    await asyncio.sleep(wait)
                response = await client.get(path, params=params)
                self._last_request = time.monotonic()
            if response.status_code != 429 or attempt == retries:
                return response
            await asyncio.sleep(retry_after(response, attempt))
        raise AssertionError("unreachable")

    async def _sports_with_events(
        self,
        client: httpx.AsyncClient,
        key: str,
        date_from: datetime,
        date_to: datetime,
    ) -> list[str]:
        """Which sports have a match in the window, via the free /events endpoint.

        One sport at a time: a concurrent sweep of every league is the burst
        that trips the rate limit, even though these calls cost no credits.
        """
        found: list[str] = []
        for sport in self._sports:
            response = await self._get(
                client,
                f"/sports/{sport}/events",
                {
                    "apiKey": key,
                    "dateFormat": "iso",
                    "commenceTimeFrom": _iso_z(date_from),
                    "commenceTimeTo": _iso_z(date_to),
                },
            )
            if response.status_code == 404:
                continue
            response.raise_for_status()
            if response.json():
                found.append(sport)
        return found

    def _require_key(self) -> str:
        key = self._settings.the_odds_api_key
        if not key:
            raise ProviderError("THE_ODDS_API_KEY is not configured")
        return key

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        return httpx.AsyncClient(
            base_url=self._settings.the_odds_api_base_url,
            timeout=self._settings.http_timeout_seconds,
        )

    def _market_keys(self, markets: list[MarketType] | None) -> str:
        if not markets:
            return "h2h,totals"
        keys = [
            _TYPE_TO_FEATURED_MARKET_KEY[m]
            for m in markets
            if m in _TYPE_TO_FEATURED_MARKET_KEY
        ]
        return ",".join(keys) if keys else "h2h,totals"

    async def collect_additional_markets(
        self,
        *,
        date_from: datetime,
        date_to: datetime,
        markets: list[MarketType],
        max_events: int,
        max_credits: int,
    ) -> AdditionalMarketCollection:
        """Fetch explicitly budgeted per-event BTTS/corner markets."""
        if max_events < 1 or max_credits < 1:
            raise ValueError("max_events and max_credits must be >= 1")
        unsupported = set(markets) - set(_TYPE_TO_ADDITIONAL_MARKET_KEY)
        if not markets or unsupported:
            raise ValueError("additional markets must contain only btts and corner_totals")

        market_keys = [
            _TYPE_TO_ADDITIONAL_MARKET_KEY[market] for market in dict.fromkeys(markets)
        ]
        maximum_per_event = len(market_keys) * self._region_count()
        event_limit = min(max_events, max_credits // maximum_per_event)
        if event_limit < 1:
            raise ValueError(
                f"max_credits must be at least {maximum_per_event} for one event"
            )

        key = self._require_key()
        client = await self._get_client()
        owns_client = self._client is None
        discovered: list[tuple[str, dict]] = []
        fixtures: list[Fixture] = []
        credits_used = 0
        credits_remaining: int | None = None
        try:
            for sport in self._sports:
                response = await self._get(
                    client,
                    f"/sports/{sport}/events",
                    {
                        "apiKey": key,
                        "dateFormat": "iso",
                        "commenceTimeFrom": _iso_z(date_from),
                        "commenceTimeTo": _iso_z(date_to),
                    },
                )
                if response.status_code == 404:
                    continue
                response.raise_for_status()
                discovered.extend((sport, event) for event in response.json())

            discovered.sort(key=lambda item: item[1]["commence_time"])
            for sport, event in discovered[:event_limit]:
                if not self.guard.reserve(maximum_per_event):
                    break
                response = await self._get(
                    client,
                    f"/sports/{sport}/events/{event['id']}/odds",
                    {
                        "apiKey": key,
                        "regions": self._settings.the_odds_api_regions,
                        "markets": ",".join(market_keys),
                        "oddsFormat": "decimal",
                        "dateFormat": "iso",
                    },
                )
                self._observe(response)
                if response.status_code == 404:
                    continue
                response.raise_for_status()
                credits_used += int(response.headers.get("x-requests-last", "0"))
                remaining = response.headers.get("x-requests-remaining")
                if remaining is not None:
                    credits_remaining = int(remaining)
                fixture = self._parse_event(response.json())
                if fixture.markets:
                    fixtures.append(fixture)
        except httpx.HTTPError as exc:  # pragma: no cover - network failure path
            raise ProviderError(f"the-odds-api additional-market request failed: {exc}") from exc
        finally:
            if owns_client:
                await client.aclose()

        return AdditionalMarketCollection(
            fixtures=fixtures,
            events_discovered=len(discovered),
            event_requests=min(len(discovered), event_limit),
            estimated_max_credits=min(len(discovered), event_limit) * maximum_per_event,
            credits_used=credits_used,
            credits_remaining=credits_remaining,
        )

    async def list_fixtures(
        self,
        *,
        date_from: datetime,
        date_to: datetime,
        markets: list[MarketType] | None = None,
    ) -> list[Fixture]:
        key = self._require_key()
        params = {
            "apiKey": key,
            "regions": self._settings.the_odds_api_regions,
            "markets": self._market_keys(markets),
            "oddsFormat": "decimal",
            "dateFormat": "iso",
            "commenceTimeFrom": _iso_z(date_from),
            "commenceTimeTo": _iso_z(date_to),
        }

        cost = len(params["markets"].split(",")) * self._region_count()

        client = await self._get_client()
        owns_client = self._client is None
        fixtures: list[Fixture] = []
        try:
            sports = await self._sports_with_events(client, key, date_from, date_to)
            for i, sport in enumerate(sports):
                if not self.guard.reserve(cost):
                    if i == 0:
                        raise QuotaExceeded(
                            "the_odds_api: daily credit budget reached; serving stored data only"
                        )
                    break  # sports are in priority order; keep what we paid for
                resp = await self._get(client, f"/sports/{sport}/odds", params)
                self._observe(resp)
                if resp.status_code == 404:
                    # Sport out of season / no events in window.
                    continue
                resp.raise_for_status()
                for event in resp.json():
                    fixtures.append(self._parse_event(event))
        except httpx.HTTPError as exc:  # pragma: no cover - network failure path
            raise ProviderError(f"the-odds-api request failed: {exc}") from exc
        finally:
            if owns_client:
                await client.aclose()
        return fixtures

    async def get_markets(self, fixture_id: str) -> list[Fixture]:
        # Generic API lookups still resolve via list_fixtures. Additional BTTS
        # and corner markets use collect_additional_markets with explicit limits.
        raise ProviderError(
            "the-odds-api: fetch markets via list_fixtures; per-event lookup not used in MVP"
        )

    def _parse_event(self, event: dict) -> Fixture:
        markets = self._parse_markets(event)
        return Fixture(
            id=f"{self.name}:{event['id']}",
            home_team=event["home_team"],
            away_team=event["away_team"],
            kickoff_utc=datetime.fromisoformat(event["commence_time"].replace("Z", "+00:00")),
            league=event.get("sport_title"),
            provider=self.name,
            markets=markets,
        )

    def _parse_markets(self, event: dict) -> list[Market]:
        home, away = event["home_team"], event["away_team"]
        out: list[Market] = []
        for bookmaker in event.get("bookmakers", []):
            title = bookmaker.get("title") or bookmaker.get("key")
            for market in bookmaker.get("markets", []):
                mtype = _MARKET_KEY_TO_TYPE.get(market.get("key"))
                if mtype is None:
                    continue
                outcomes = [
                    Outcome(
                        name=_normalize_outcome_name(o["name"], home, away),
                        price=float(o["price"]),
                        point=o.get("point"),
                    )
                    for o in market.get("outcomes", [])
                    if float(o.get("price", 0)) > 1.0
                ]
                if outcomes:
                    out.append(
                        Market(
                            type=mtype,
                            outcomes=outcomes,
                            bookmaker=title,
                            provider=self.name,
                        )
                    )
        return out


def _normalize_outcome_name(name: str, home: str, away: str) -> str:
    """Map team names / labels to canonical selection labels."""
    if name == home:
        return "Home"
    if name == away:
        return "Away"
    return name  # "Draw", "Over", "Under" pass through


def _iso_z(dt: datetime) -> str:
    """The Odds API expects ISO8601 in UTC with a trailing Z and no microseconds."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
