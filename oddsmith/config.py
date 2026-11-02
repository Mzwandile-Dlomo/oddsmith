"""Application configuration loaded from environment / .env.

Keys are optional so the app and test-suite import cleanly without secrets.
Provider adapters raise a clear error only when actually used without a key.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- The Odds API (the-odds-api.com, v4) ---
    the_odds_api_key: str | None = Field(default=None, repr=False)
    the_odds_api_base_url: str = "https://api.the-odds-api.com/v4"
    # Regions to pull bookmaker odds for (comma-separated per the API).
    the_odds_api_regions: str = "uk,eu"
    # The rate limit counts requests, not credits, so the free /events lookups
    # are spaced too. A 429 waits (Retry-After, else a backoff) and retries.
    the_odds_api_min_interval_seconds: float = 1.0
    the_odds_api_max_retries: int = 3

    # --- API-Football (v3) ---
    api_football_key: str | None = Field(default=None, repr=False)
    # Direct api-sports host by default; override with the RapidAPI host if you use RapidAPI.
    api_football_base_url: str = "https://v3.football.api-sports.io"
    api_football_use_rapidapi: bool = False
    # The free plan allows 10 requests a minute; 6.5s apart stays under it.
    # A rate limit (a 429, or a 200 whose body says rateLimit) waits and retries.
    api_football_min_interval_seconds: float = 6.5
    api_football_max_retries: int = 3

    # --- Claude (match read write-ups) ---
    # Without a key, match pages still show every computed angle and number;
    # only the written summary is missing.
    anthropic_api_key: str | None = Field(default=None, repr=False)
    match_read_model: str = "claude-opus-5-5"

    # --- WhatsApp (scripts/send_strong_picks.py) ---
    # CallMeBot (callmebot.com) only messages the number that activated the
    # key, which is all a "send me today's picks" job needs. The phone is in
    # international format, e.g. +27821234567.
    whatsapp_phone: str | None = Field(default=None, repr=False)
    callmebot_api_key: str | None = Field(default=None, repr=False)

    # Optional additional trusted root for corporate TLS inspection. This is
    # added to the normal public CA set; verification is never disabled.
    football_data_ca_bundle: str | None = None

    # --- App ---
    # Postgres in Docker by default (see docker-compose.yml). Host port 5435.
    database_url: str = Field(
        default="postgresql+psycopg://oddsmith:oddsmith@localhost:5435/oddsmith",
        repr=False,
    )
    default_currency: str = "ZAR"
    # Whose days the daily paper ticket, Today and the calendar count in
    # (see oddsmith/localdays.py). Stored timestamps stay UTC.
    local_timezone: str = "Africa/Johannesburg"
    http_timeout_seconds: float = 15.0
    cors_origins: list[str] = ["http://localhost:3000"]
    # Simple in-memory cache TTL for provider responses (seconds).
    provider_cache_ttl_seconds: int = 60

    # --- Fixtures DB cache (protects provider quota) ---
    # Serve fixtures from Postgres; only re-fetch from providers when the cached
    # window is older than this TTL (default 6h). The cap trims what one refresh
    # stores, after the providers have already been paid for those odds, so it
    # sits above a busy weekend across every competition in DEFAULT_SOCCER_SPORTS.
    fixtures_cache_ttl_seconds: int = 21600
    max_fixtures_per_refresh: int = 400

    # --- Provider quota guard (oddsmith/quota.py) ---
    # Every metered call reserves its cost against a per-UTC-day ledger in the
    # DB before it is sent, so the app, scripts and scheduled jobs share one
    # budget. A call is also refused when the provider's own remaining count
    # would fall below the floor.
    # API-Football free plan: 100 requests/day, resets at 00:00 UTC.
    api_football_daily_budget: int = 90
    api_football_floor: int = 5
    # Odds requests per refresh; the rest of the day's budget stays free for
    # match pages and the results sync.
    api_football_odds_per_refresh: int = 8
    # The Odds API free plan: 500 credits/month. 15/day x 31 days = 465, so the
    # month cannot run dry even if every day spends its full allowance.
    the_odds_api_daily_budget: int = 15
    the_odds_api_floor: int = 10

    # --- Odds model tuning (fit cross-league on EPL/Bundesliga/LaLiga/SerieA) ---
    # rho: Dixon-Coles low-score correction; decay: recency weighting per match.
    # These reached ~54% mean 1X2 accuracy in walk-forward backtests.
    model_rho: float = -0.10
    model_decay: float = 0.008
    model_shrinkage: float = 0.06


@lru_cache
def get_settings() -> Settings:
    return Settings()
