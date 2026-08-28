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
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from oddsmith.config import Settings, get_settings
from oddsmith.models import Fixture, Market, MarketType, Outcome
from oddsmith.providers.base import OddsProvider, ProviderError

# Soccer competitions to query. The Odds API exposes soccer under many keys;
# these cover the major European leagues. Extend as needed.
DEFAULT_SOCCER_SPORTS = (
    "soccer_epl",
    "soccer_spain_la_liga",
    "soccer_italy_serie_a",
    "soccer_germany_bundesliga",
    "soccer_france_ligue_one",
    "soccer_uefa_champs_league",
    "soccer_brazil_campeonato",
    "soccer_argentina_primera_division",
    "soccer_usa_mls",
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
    ) -> None:
        self._settings = settings or get_settings()
        self._client = client
        self._sports = sports

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
        region_count = len(
            [region for region in self._settings.the_odds_api_regions.split(",") if region]
        )
        maximum_per_event = len(market_keys) * max(region_count, 1)
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
                response = await client.get(
                    f"/sports/{sport}/events",
                    params={
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
                response = await client.get(
                    f"/sports/{sport}/events/{event['id']}/odds",
                    params={
                        "apiKey": key,
                        "regions": self._settings.the_odds_api_regions,
                        "markets": ",".join(market_keys),
                        "oddsFormat": "decimal",
                        "dateFormat": "iso",
                    },
                )
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

        client = await self._get_client()
        owns_client = self._client is None
        fixtures: list[Fixture] = []
        try:
            for sport in self._sports:
                resp = await client.get(f"/sports/{sport}/odds", params=params)
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
