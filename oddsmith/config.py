"""Application configuration loaded from environment / .env.

Keys are optional so the app and test-suite import cleanly without secrets.
Provider adapters raise a clear error only when actually used without a key.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- The Odds API (the-odds-api.com, v4) ---
    the_odds_api_key: str | None = None
    the_odds_api_base_url: str = "https://api.the-odds-api.com/v4"
    # Regions to pull bookmaker odds for (comma-separated per the API).
    the_odds_api_regions: str = "uk,eu"

    # --- API-Football (v3) ---
    api_football_key: str | None = None
    # Direct api-sports host by default; override with the RapidAPI host if you use RapidAPI.
    api_football_base_url: str = "https://v3.football.api-sports.io"
    api_football_use_rapidapi: bool = False

    # --- App ---
    # Postgres in Docker by default (see docker-compose.yml). Host port 5435.
    database_url: str = "postgresql+psycopg://oddsmith:oddsmith@localhost:5435/oddsmith"
    default_currency: str = "USD"
    http_timeout_seconds: float = 15.0
    cors_origins: list[str] = ["http://localhost:3000"]
    # Simple in-memory cache TTL for provider responses (seconds).
    provider_cache_ttl_seconds: int = 60

    # --- Fixtures DB cache (protects provider quota) ---
    # Serve fixtures from Postgres; only re-fetch from providers when the cached
    # window is older than this TTL (default 6h). API-Football charges 1 request
    # per fixture's odds, so cap how many fixtures we pull odds for per refresh.
    fixtures_cache_ttl_seconds: int = 21600
    max_fixtures_per_refresh: int = 40

    # --- Odds model tuning (fit cross-league on EPL/Bundesliga/LaLiga/SerieA) ---
    # rho: Dixon-Coles low-score correction; decay: recency weighting per match.
    # These reached ~54% mean 1X2 accuracy in walk-forward backtests.
    model_rho: float = -0.10
    model_decay: float = 0.008
    model_shrinkage: float = 0.06


@lru_cache
def get_settings() -> Settings:
    return Settings()
