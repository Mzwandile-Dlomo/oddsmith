"""Swappable odds-model interface.

The Poisson engine is today's implementation; an ML model can replace it later
by satisfying this protocol. Callers depend on the protocol, never the concrete
engine, so the upgrade is a drop-in.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from oddsmith.odds_model.poisson import MatchProbabilities


@runtime_checkable
class OddsModel(Protocol):
    def is_trained(self) -> bool: ...

    def predict(self, home_team: str, away_team: str) -> MatchProbabilities | None:
        """Return market probabilities for the fixture, or None if either team is unknown."""
        ...
