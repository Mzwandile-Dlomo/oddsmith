"""Provider adapter interface.

Each odds source implements ``OddsProvider`` so the rest of the app never cares
which upstream API produced a fixture. Add a new source by writing one class.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

import httpx

from oddsmith.models import Fixture, MarketType


class ProviderError(RuntimeError):
    """Raised when a provider is misconfigured or the upstream call fails."""


def retry_after(response: httpx.Response, attempt: int) -> float:
    """Seconds to wait after a rate limit: the server's Retry-After, else 2, 4, 8..."""
    try:
        seconds = float(response.headers["retry-after"])
    except (KeyError, ValueError):
        seconds = 2.0 ** (attempt + 1)
    return min(max(seconds, 0.0), 60.0)


@runtime_checkable
class OddsProvider(Protocol):
    """Read-only source of soccer fixtures and their odds."""

    name: str

    async def list_fixtures(
        self,
        *,
        date_from: datetime,
        date_to: datetime,
        markets: list[MarketType] | None = None,
    ) -> list[Fixture]:
        """Return fixtures kicking off in [date_from, date_to], with odds attached."""
        ...

    async def get_markets(self, fixture_id: str) -> list["Fixture"]:  # pragma: no cover - see impls
        """Return the fixture(s) matching ``fixture_id`` with full market odds."""
        ...
