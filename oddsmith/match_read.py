"""Claude's written read for one match, grounded in computed evidence.

The engine decides; the model narrates. ``research.rank_angles`` has already
chosen the candidate angles and every count. Claude receives that evidence as
JSON, picks one of the given angles and writes two short paragraphs about it.
The headline is rebuilt here from the computed angle, so a model that names an
angle we did not offer, or a different count, cannot reach the page.

Reads are cached per fixture and evidence fingerprint: a match is written once
and rewritten only when a new result or new prices change the evidence.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Literal

import anthropic
from pydantic import BaseModel
from sqlmodel import Session, select

from oddsmith.db import MatchRead
from oddsmith.insights import MatchInsights, TeamForm
from oddsmith.research import Angle, rank_angles

SYSTEM_PROMPT = """You write the short research read for one football match, for a bettor who will place any bet themselves on a licensed bookmaker's site.

You receive JSON evidence: each side's recent matches, averages, head-to-head meetings, and a list of candidate angles. The app has already computed every number and graded each angle (Strong / Moderate / Weak) from how often each side's recent matches landed it.

Rules:
- Choose exactly one angle from `angles` and return its `key` as `angle_key`. Prefer the strongest; you may choose a slightly weaker angle only if the evidence makes the stronger one misleading (for example, its head-to-head record contradicts it), and say why.
- Use only numbers that appear in the evidence. Never invent statistics, probabilities, injuries, line-ups, motivation or news. If a figure is null it was not recorded; say it is unavailable rather than guessing.
- When a bookmaker price is given, compare the angle's hit rate with the price's implied probability in plain words. When none is given, say the price still needs checking.
- `summary`: two or three sentences explaining why the chosen angle stands out, citing specific counts or recent scores.
- `match_read`: one or two sentences: the angle, any alternative worth considering, and that this is a research angle, not a guaranteed result, so the bettor should check the starting line-ups and the price before betting.
- Plain, calm English. No hype, no emojis, no markdown."""


class ReadDraft(BaseModel):
    angle_key: str
    summary: str
    match_read: str


class MatchReadView(BaseModel):
    status: Literal["ok", "no_key", "no_history", "error"]
    angles: list[Angle]
    angle_key: str | None = None
    headline: str | None = None
    summary: str | None = None
    match_read: str | None = None
    model: str | None = None
    generated_at: datetime | None = None
    message: str | None = None


def _side(form: TeamForm) -> dict:
    return {
        "team": form.team,
        "averages_last_matches": form.averages.model_dump(),
        "recent_matches_newest_first": [
            {
                "date": m.kickoff_utc.date().isoformat(),
                "opponent": m.opponent,
                "venue": m.venue,
                "score_for_against": f"{m.goals_for}-{m.goals_against}",
                "result": m.result,
                "total_goals": m.total_goals,
                "total_corners": m.total_corners,
                "shots_for": m.shots_for,
                "shots_on_target_for": m.shots_on_target_for,
                "shots_on_target_against": m.shots_on_target_against,
            }
            for m in form.matches
        ],
        "team_lines": [f"{line.label}: {line.hits}/{line.sample}" for line in form.team_lines],
    }


def build_evidence(
    *, league: str | None, kickoff_utc: datetime, insights: MatchInsights, angles: list[Angle]
) -> dict:
    h2h = insights.head_to_head
    return {
        "competition": league,
        "kickoff_utc": kickoff_utc.isoformat(),
        "home": _side(insights.home),
        "away": _side(insights.away),
        "head_to_head": {
            "meetings": len(h2h.matches),
            "home_side_wins": h2h.home_wins,
            "draws": h2h.draws,
            "away_side_wins": h2h.away_wins,
            "recent_scores_home_side_first": [
                f"{m.kickoff_utc.date().isoformat()} {m.goals_for}-{m.goals_against}"
                for m in h2h.matches[:5]
            ],
        },
        "angles": [
            {
                "key": a.key,
                "label": a.label,
                "grade": a.strength,
                "both_sides_recent": f"{a.hits}/{a.sample}",
                "home_recent": f"{a.home_hits}/{a.home_sample}",
                "away_recent": f"{a.away_hits}/{a.away_sample}",
                "head_to_head": f"{a.h2h_hits}/{a.h2h_sample}" if a.h2h_sample else None,
                "bookmaker_price": a.book_price,
                "bookmaker_implied_probability": (
                    round(a.book_implied_prob, 3) if a.book_implied_prob is not None else None
                ),
            }
            for a in angles
        ],
        "data_stale": insights.stale,
    }


def evidence_key(evidence: dict, model: str) -> str:
    """Fingerprint of what the read is written from; any new result or price changes it."""
    blob = json.dumps({"model": model, "evidence": evidence}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:32]


def _view(row: MatchRead, angles: list[Angle]) -> MatchReadView:
    chosen = next((a for a in angles if a.key == row.angle_key), angles[0])
    return MatchReadView(
        status="ok",
        angles=angles,
        angle_key=chosen.key,
        headline=chosen.headline,
        summary=row.summary,
        match_read=row.match_read,
        model=row.model,
        generated_at=row.created_at,
    )


async def get_match_read(
    session: Session,
    *,
    fixture_id: str,
    league: str | None,
    kickoff_utc: datetime,
    insights: MatchInsights,
    api_key: str | None,
    model: str,
    client: anthropic.AsyncAnthropic | None = None,
) -> MatchReadView:
    # Every graded line, best first: the page grades its whole trend table from these.
    angles = rank_angles(insights, limit=len(insights.trends))
    if not angles:
        return MatchReadView(
            status="no_history",
            angles=[],
            message="Not enough stored results for both clubs to grade any angle.",
        )

    evidence = build_evidence(
        league=league, kickoff_utc=kickoff_utc, insights=insights, angles=angles
    )
    key = evidence_key(evidence, model)
    cached = session.exec(
        select(MatchRead).where(MatchRead.fixture_id == fixture_id, MatchRead.data_key == key)
    ).first()
    if cached is not None:
        return _view(cached, angles)

    fallback = MatchReadView(status="no_key", angles=angles, headline=angles[0].headline)
    if not api_key and client is None:
        fallback.message = "Add ANTHROPIC_API_KEY to .env to get a written read for each match."
        return fallback

    client = client or anthropic.AsyncAnthropic(api_key=api_key)
    try:
        response = await client.beta.messages.parse(
            model=model,
            max_tokens=4000,
            # Short, evidence-bound prose: low effort is enough.
            output_config={"effort": "low"},
            # A classifier decline is retried server-side on a suitable model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps(evidence, default=str)}],
            output_format=ReadDraft,
        )
    except anthropic.AuthenticationError:
        fallback.status = "error"
        fallback.message = "The Anthropic API key was rejected. Check ANTHROPIC_API_KEY in .env."
        return fallback
    except (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.APIStatusError) as exc:
        fallback.status = "error"
        fallback.message = f"Couldn't reach Claude right now ({type(exc).__name__}). Try again shortly."
        return fallback

    draft = response.parsed_output
    if response.stop_reason == "refusal" or draft is None:
        fallback.status = "error"
        fallback.message = "Claude declined to write this read; the computed angles are still shown."
        return fallback

    # The model may only choose among computed angles; anything else falls back
    # to the top-ranked one rather than reaching the page.
    angle_key = draft.angle_key if any(a.key == draft.angle_key for a in angles) else angles[0].key
    row = MatchRead(
        fixture_id=fixture_id,
        data_key=key,
        model=response.model,
        angle_key=angle_key,
        summary=draft.summary.strip(),
        match_read=draft.match_read.strip(),
        created_at=datetime.now(UTC),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return _view(row, angles)
