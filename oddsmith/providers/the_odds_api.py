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

BTTS is not offered by this provider's core markets; API-Football supplies it.
"""

from __future__ import annotations

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

_MARKET_KEY_TO_TYPE = {
    "h2h": MarketType.MATCH_WINNER,
    "totals": MarketType.OVER_UNDER,
}
_TYPE_TO_MARKET_KEY = {v: k for k, v in _MARKET_KEY_TO_TYPE.items()}


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
        keys = [_TYPE_TO_MARKET_KEY[m] for m in markets if m in _TYPE_TO_MARKET_KEY]
        return ",".join(keys) if keys else "h2h,totals"

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
        # v4 has a per-event endpoint but it needs the sport key; for the MVP we
        # resolve markets via list_fixtures + client-side id filter in the API layer.
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
