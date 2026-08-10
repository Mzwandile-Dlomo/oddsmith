"""Build the accumulator MOST LIKELY to land that still clears a target price.

``acca.py`` answers "what are the best value bets available?" and lets the
combined price fall where it may — five value legs often come out at 20/1 or
longer and land single-digit percent of the time. This module answers the
opposite question, the one behind a daily "banker" slip:

    "Give me the acca most likely to win, that still pays at least 1.5."

Taking logs turns that into a knapsack:

    maximise   sum(log model_prob)          [most likely to land]
    subject to sum(log offered_odds) >= log(target_odds)
    and        at most one leg per fixture

The useful quantity per candidate is its EFFICIENCY — how much price it adds per
unit of probability it costs:

    efficiency = log(offered_odds) / -log(model_prob)

A leg the model rates at 90% priced at 1.25 is far more efficient than a coin
flip priced at 2.0: it buys nearly the same price for a fraction of the risk.
Efficiency is highest exactly where the bookmaker is most wrong in our favour,
so this naturally prefers value without being told to.

Greedy on efficiency overshoots on the last leg (needing 1.5 and jumping to 2.8
throws away probability for price nobody asked for), so we run a small beam
search with an optimistic bound. It is exact enough at these sizes and keeps the
one-leg-per-fixture rule trivially satisfiable.

Pure and dependency-free, like the rest of ``odds_model``.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from math import log

from oddsmith.odds_model.acca import Acca, AccaLeg, Candidate

# A model probability of exactly 1.0 would make efficiency infinite. Nothing in
# football is certain, and our own model applies shrinkage for that reason, so
# cap the probability we are willing to act on.
MAX_LEG_PROB = 0.995

# Candidates considered, after sorting by efficiency. Beyond this the tail is
# never competitive and only costs time.
MAX_POOL = 200

# Edges above this are treated as a modelling error, not an opportunity.
#
# Bookmakers price mainstream soccer markets efficiently. When our Poisson fit
# claims a 92% chance on a line the market prices near 45%, the overwhelmingly
# likelier explanation is a bad fit for that fixture — a promoted side, a team
# whose name matched the wrong history, a thin sample — rather than a 100%+ edge
# nobody else noticed. Acting on those is how a "value" model loses money fast,
# and because stake sizing scales WITH the edge, they are exactly the picks that
# would be staked hardest. Discard them.
MAX_PLAUSIBLE_EDGE = 0.15


@dataclass(frozen=True)
class TargetAcca(Acca):
    """An ``Acca`` built to clear a price target, plus whether it managed to."""

    target_odds: float = 0.0
    target_met: bool = False
    # Candidates that survived filtering — how much choice the builder actually had.
    pool_size: int = 0


@dataclass(frozen=True)
class _State:
    """A partial selection during the search."""

    indices: tuple[int, ...] = ()
    used: frozenset[str] = frozenset()
    log_odds: float = 0.0
    log_prob: float = 0.0
    # Optimistic upper bound on the log_prob this state could still reach.
    bound: float = 0.0
    legs: tuple[AccaLeg, ...] = field(default=())

    @property
    def last(self) -> int:
        return self.indices[-1] if self.indices else -1


def _leg_prob(candidate: Candidate) -> float:
    return min(candidate.pick.model_prob, MAX_LEG_PROB)


def _efficiency(candidate: Candidate) -> float:
    """Price added per unit of probability sacrificed. Higher is better."""
    prob = _leg_prob(candidate)
    cost = -log(prob)
    if cost <= 0:
        return float("inf")
    return log(candidate.pick.offered_odds) / cost


def build_target_acca(
    candidates: list[Candidate],
    *,
    target_odds: float = 1.5,
    max_legs: int = 4,
    min_leg_prob: float = 0.5,
    require_value: bool = True,
    max_edge: float = MAX_PLAUSIBLE_EDGE,
    beam_width: int = 64,
) -> TargetAcca:
    """Pick the legs most likely to all land while clearing ``target_odds``.

    ``min_leg_prob`` filters out coin flips — a banker slip wants legs the model
    is confident in. ``require_value`` keeps only positive-EV selections, which
    is what stops the accumulator from being a slow, reliable way to pay the
    bookmaker's margin; relax it only if you understand that trade.

    ``max_edge`` discards picks that look *too* good (see ``MAX_PLAUSIBLE_EDGE``);
    those are model errors, and they are the ones stake sizing would bet hardest.

    If the target cannot be reached (a thin card, or too few value picks), the
    highest-priced selection we *could* build is returned with
    ``target_met=False`` rather than an empty slip or a silently short one.
    """
    pool = [
        c
        for c in candidates
        if c.pick.offered_odds > 1.0
        and c.pick.model_prob >= min_leg_prob
        and c.pick.edge <= max_edge
        and (c.pick.is_value if require_value else True)
    ]
    pool.sort(key=_efficiency, reverse=True)
    pool = pool[:MAX_POOL]

    if not pool:
        return TargetAcca(legs=[], target_odds=target_odds, target_met=False, pool_size=0)

    # Best efficiency still available from index i onward. Because the pool is
    # sorted by efficiency descending, that is simply the efficiency at i.
    efficiencies = [_efficiency(c) for c in pool]

    log_target = log(target_odds)
    best: _State | None = None  # best complete solution (target met)
    best_partial: _State | None = None  # highest price reached, target missed

    beam = [_State()]
    for _ in range(max_legs):
        nxt: list[_State] = []
        for state in beam:
            for i in range(state.last + 1, len(pool)):
                candidate = pool[i]
                if candidate.fixture_id in state.used:
                    continue

                prob = _leg_prob(candidate)
                extended = _State(
                    indices=state.indices + (i,),
                    used=state.used | {candidate.fixture_id},
                    log_odds=state.log_odds + log(candidate.pick.offered_odds),
                    log_prob=state.log_prob + log(prob),
                    legs=state.legs + (_to_leg(candidate),),
                )

                if extended.log_odds >= log_target:
                    best = _better_complete(best, extended)
                    continue

                best_partial = _better_partial(best_partial, extended)
                nxt.append(_with_bound(extended, log_target, efficiencies, i + 1))

        if not nxt:
            break
        # Prune on the optimistic bound, not the current probability — ranking by
        # log_prob alone would always favour the shortest slips, which are
        # exactly the ones furthest from the target.
        nxt.sort(key=lambda s: s.bound, reverse=True)
        beam = nxt[:beam_width]

    chosen = best or best_partial
    if chosen is None:
        return TargetAcca(
            legs=[], target_odds=target_odds, target_met=False, pool_size=len(pool)
        )
    return TargetAcca(
        legs=list(chosen.legs),
        target_odds=target_odds,
        target_met=best is not None,
        pool_size=len(pool),
    )


def _with_bound(
    state: _State, log_target: float, efficiencies: list[float], next_index: int
) -> _State:
    """Attach an optimistic bound on the log-probability this state can reach.

    The state still needs ``log_target - log_odds`` of price. Buying it at the
    best efficiency left in the pool is the cheapest it could possibly be, so
    that gives an upper bound on the final log-probability.
    """
    if next_index >= len(efficiencies):
        return replace(state, bound=float("-inf"))
    best_eff = efficiencies[next_index]
    need = log_target - state.log_odds
    bound = state.log_prob if best_eff <= 0 else state.log_prob - (need / best_eff)
    return replace(state, bound=bound)


def _better_complete(current: _State | None, other: _State) -> _State:
    """Prefer the likelier slip; break ties toward fewer legs."""
    if current is None:
        return other
    if other.log_prob > current.log_prob:
        return other
    if other.log_prob == current.log_prob and len(other.indices) < len(current.indices):
        return other
    return current


def _better_partial(current: _State | None, other: _State) -> _State:
    """Target unreachable: keep whichever got closest to it."""
    if current is None or other.log_odds > current.log_odds:
        return other
    return current


def _to_leg(candidate: Candidate) -> AccaLeg:
    return AccaLeg(
        fixture_id=candidate.fixture_id,
        home_team=candidate.home_team,
        away_team=candidate.away_team,
        market_type=candidate.market_type,
        pick=candidate.pick,
        point=candidate.point,
    )
