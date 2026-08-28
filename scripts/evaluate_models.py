"""Run the league-by-league expanding-window benchmark on stored observations."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oddsmith.config import get_settings
from oddsmith.db import MatchObservation, get_engine
from oddsmith.odds_model.evaluation import EvaluationMatch, evaluate_expanding_window


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-train-seasons", type=int, default=4)
    parser.add_argument("--min-edge", type=float, default=0.03)
    parser.add_argument("--max-edge", type=float, default=0.15)
    parser.add_argument("--bootstrap-samples", type=int, default=1000)
    parser.add_argument("--output", type=Path, help="optional JSON output path")
    return parser


def main() -> int:
    args = _parser().parse_args()
    with Session(get_engine()) as session:
        rows = list(session.exec(select(MatchObservation).order_by(MatchObservation.kickoff_utc)))
    matches = [
        EvaluationMatch(
            league=row.league,
            season=row.season,
            kickoff_utc=row.kickoff_utc,
            home_team=row.home_team,
            away_team=row.away_team,
            home_goals=row.home_goals,
            away_goals=row.away_goals,
            odds_home=row.close_home_odds,
            odds_draw=row.close_draw_odds,
            odds_away=row.close_away_odds,
        )
        for row in rows
    ]
    settings = get_settings()
    report = evaluate_expanding_window(
        matches,
        min_train_seasons=args.min_train_seasons,
        rho=settings.model_rho,
        decay=settings.model_decay,
        shrinkage=settings.model_shrinkage,
        min_edge=args.min_edge,
        max_edge=args.max_edge,
        bootstrap_samples=args.bootstrap_samples,
    )
    document = json.dumps(asdict(report), default=str, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(document + "\n", encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
