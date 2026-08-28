"""Model service: train from stored history, attach model odds + value to fixtures.

Team strengths are fit once from the ``HistoricalMatch`` table and cached in
process (the history is static, so there is no need to refit per request). For an
upcoming fixture we predict market probabilities, convert them to fair odds, and
compare against the bookmaker's de-margined implied probabilities to flag value.

Team names from the live odds providers and the historical table may differ
slightly, so lookups fall back to a normalised match before giving up.
"""

from __future__ import annotations

import re

from sqlmodel import Session, select

from oddsmith.config import get_settings
from oddsmith.db import HistoricalMatch
from oddsmith.models import (
    Fixture,
    Market,
    MarketType,
    ModelMarket,
    ModelOutcome,
)
from oddsmith.odds_model.poisson import (
    MatchProbabilities,
    MatchResult,
    TeamStrengths,
    expected_goals,
    fit_strengths,
    match_probabilities,
    probability_to_odds,
)
from oddsmith.odds_model.value import assess_value, implied_probabilities
from oddsmith.textnorm import fold_accents

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _norm(name: str) -> str:
    """Fold accents first — dropping them outright would delete the letter entirely
    and stop every accented club from ever matching the history."""
    return _NON_ALNUM.sub("", fold_accents(name).lower())


class PoissonModelService:
    def __init__(
        self, strengths_by_league: dict[str, TeamStrengths], rho: float, shrinkage: float = 0.0
    ) -> None:
        self._by_league = strengths_by_league
        self._rho = rho
        self._shrinkage = shrinkage
        self._team_league: dict[str, str] = {}
        self._norm_index: dict[str, tuple[str, str]] = {}
        for league, strengths in strengths_by_league.items():
            for team in strengths.attack:
                self._team_league.setdefault(team, league)
                self._norm_index.setdefault(_norm(team), (league, team))

    def is_trained(self) -> bool:
        return any(s.attack for s in self._by_league.values())

    def _resolve(self, team: str, league: str | None) -> tuple[str, str] | None:
        """Resolve (league, canonical_team) for a team, preferring the given league."""
        if league and league in self._by_league and self._by_league[league].has(team):
            return league, team
        hit = self._norm_index.get(_norm(team))
        return hit

    def predict(
        self, home_team: str, away_team: str, league: str | None = None
    ) -> MatchProbabilities | None:
        home = self._resolve(home_team, league)
        away = self._resolve(away_team, league)
        if home is None or away is None:
            return None
        # Both teams must belong to the same league's strength table to compare.
        if home[0] != away[0]:
            return None
        strengths = self._by_league[home[0]]
        hl, al = expected_goals(strengths, home[1], away[1])
        return match_probabilities(hl, al, rho=self._rho, shrinkage=self._shrinkage)


def train_from_db(session: Session) -> PoissonModelService:
    settings = get_settings()
    rows = list(session.exec(select(HistoricalMatch).order_by(HistoricalMatch.kickoff_utc)))
    by_league: dict[str, list[MatchResult]] = {}
    for r in rows:
        by_league.setdefault(r.league, []).append(
            MatchResult(r.home_team, r.away_team, r.home_goals, r.away_goals)
        )
    strengths_by_league = {
        league: fit_strengths(results, decay=settings.model_decay)
        for league, results in by_league.items()
    }
    return PoissonModelService(
        strengths_by_league, rho=settings.model_rho, shrinkage=settings.model_shrinkage
    )


_PROB_ACCESSOR = {
    ("match_winner", "Home"): lambda p: p.home_win,
    ("match_winner", "Draw"): lambda p: p.draw,
    ("match_winner", "Away"): lambda p: p.away_win,
    ("btts", "Yes"): lambda p: p.btts_yes,
    ("btts", "No"): lambda p: p.btts_no,
    ("over_under", "Over"): lambda p: p.over_2_5,
    ("over_under", "Under"): lambda p: p.under_2_5,
}


def _model_prob(mtype: MarketType, outcome_name: str, probs: MatchProbabilities) -> float | None:
    accessor = _PROB_ACCESSOR.get((mtype.value, outcome_name))
    return accessor(probs) if accessor else None


def _best_bookmaker_odds(markets: list[Market], mtype: MarketType) -> dict[str, float]:
    """Highest offered price per outcome name across bookmakers for a market type."""
    best: dict[str, float] = {}
    for m in markets:
        if m.type is not mtype:
            continue
        for o in m.outcomes:
            # The scoreline model currently prices only the 2.5-goal line. Mixing
            # in (say) an Over 4.5 price and presenting it as Over 2.5 creates a
            # selection that does not exist and badly overstates its value.
            if mtype is MarketType.OVER_UNDER and o.point != 2.5:
                continue
            if o.name not in best or o.price > best[o.name]:
                best[o.name] = o.price
    return best


def build_model_markets(fixture: Fixture, service: PoissonModelService) -> list[ModelMarket]:
    """Compute model odds + value flags for the fixture's supported markets."""
    probs = service.predict(fixture.home_team, fixture.away_team, fixture.league)
    if probs is None:
        return []

    out: list[ModelMarket] = []
    for mtype in (MarketType.MATCH_WINNER, MarketType.OVER_UNDER, MarketType.BTTS):
        names = _outcome_names(mtype)
        model_probs = {n: _model_prob(mtype, n, probs) for n in names}
        if any(v is None for v in model_probs.values()):
            continue

        book = _best_bookmaker_odds(fixture.markets, mtype)
        fair_implied = _fair_implied(book, names)

        outcomes: list[ModelOutcome] = []
        for name in names:
            mp = model_probs[name]
            assert mp is not None
            model_odds = probability_to_odds(mp) or 0.0
            bk = book.get(name)
            edge = ev = None
            is_value = False
            if bk is not None and name in fair_implied:
                pick = assess_value(name, mp, bk, fair_implied[name])
                edge, ev, is_value = pick.edge, pick.expected_value, pick.is_value
            outcomes.append(
                ModelOutcome(
                    name=name,
                    model_prob=round(mp, 4),
                    model_odds=model_odds,
                    bookmaker_odds=bk,
                    edge=edge,
                    expected_value=ev,
                    is_value=is_value,
                    point=2.5 if mtype is MarketType.OVER_UNDER else None,
                )
            )
        out.append(ModelMarket(type=mtype, outcomes=outcomes))
    return out


def _outcome_names(mtype: MarketType) -> list[str]:
    if mtype is MarketType.MATCH_WINNER:
        return ["Home", "Draw", "Away"]
    if mtype is MarketType.OVER_UNDER:
        return ["Over", "Under"]
    return ["Yes", "No"]


def _fair_implied(book: dict[str, float], names: list[str]) -> dict[str, float]:
    present = [n for n in names if n in book]
    if len(present) < len(names):
        return {}
    probs = implied_probabilities([book[n] for n in present])
    return dict(zip(present, probs, strict=True))
