"""Aggregate fixtures from multiple providers into one de-duplicated list.

The same real-world match can come from both providers under different ids and
slightly different team spellings. We key matches on (normalized home, normalized
away, kickoff rounded to the hour) and merge their markets so a user sees one
fixture carrying every available "take".

Provider-specific ids are preserved per market via the ``bookmaker`` label and
the fixture keeps the id of the first provider that reported it, while exposing
sibling ids so the API layer can re-fetch markets from either source.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime

from oddsmith.models import Fixture, MarketType
from oddsmith.providers.base import OddsProvider, ProviderError
from oddsmith.textnorm import fold_accents


class AllProvidersFailed(ProviderError):
    """Every provider errored, so the window's emptiness says nothing about it."""

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_TEAM_NOISE = ("fc", "afc", "cf", "sc")


def _normalize_team(name: str) -> str:
    # Fold accents before stripping punctuation, so "Grêmio" and "Gremio" from two
    # providers collapse to the same key instead of "grmio" and "gremio".
    slug = _NON_ALNUM.sub(" ", fold_accents(name).lower()).strip()
    tokens = [t for t in slug.split() if t not in _TEAM_NOISE]
    return " ".join(tokens) if tokens else slug


def _match_key(fixture: Fixture) -> tuple[str, str, str]:
    hour = fixture.kickoff_utc.replace(minute=0, second=0, microsecond=0)
    return (
        _normalize_team(fixture.home_team),
        _normalize_team(fixture.away_team),
        hour.isoformat(),
    )


async def gather_fixtures(
    providers: list[OddsProvider],
    *,
    date_from: datetime,
    date_to: datetime,
    markets: list[MarketType] | None = None,
) -> list[Fixture]:
    """Fetch from every provider concurrently and merge the results.

    A single provider failing (e.g. missing key) does not sink the request; its
    error is skipped so any working provider still returns fixtures. When EVERY
    provider fails, that is raised instead: an empty list would read as "no
    matches those days" and get logged as fetched, freezing the gap.
    """
    results = await asyncio.gather(
        *(
            p.list_fixtures(date_from=date_from, date_to=date_to, markets=markets)
            for p in providers
        ),
        return_exceptions=True,
    )

    all_fixtures: list[Fixture] = []
    failures: list[str] = []
    for provider, result in zip(providers, results):
        if isinstance(result, ProviderError):
            failures.append(f"{provider.name}: {result}")
            continue
        if isinstance(result, BaseException):
            raise result
        all_fixtures.extend(result)

    if providers and len(failures) == len(providers):
        raise AllProvidersFailed("; ".join(failures))

    return _merge(all_fixtures)


def _merge(fixtures: list[Fixture]) -> list[Fixture]:
    merged: dict[tuple[str, str, str], Fixture] = {}
    for fixture in fixtures:
        key = _match_key(fixture)
        existing = merged.get(key)
        if existing is None:
            merged[key] = fixture.model_copy(deep=True)
        else:
            existing.markets.extend(fixture.markets)
    return sorted(merged.values(), key=lambda f: f.kickoff_utc)
