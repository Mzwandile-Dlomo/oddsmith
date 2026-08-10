"""Provider adapter interface.

Each odds source implements ``OddsProvider`` so the rest of the app never cares
which upstream API produced a fixture. Add a new source by writing one class.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from oddsmith.models import Fixture, MarketType


class ProviderError(RuntimeError):
    """Raised when a provider is misconfigured or the upstream call fails."""


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
