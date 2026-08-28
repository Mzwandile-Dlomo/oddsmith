"""Run the league-by-league expanding-window benchmark on stored observations."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from sqlmodel import SQLModel, Session, select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oddsmith.config import get_settings
from oddsmith.db import MatchObservation, ModelEvaluationSnapshot, get_engine
from oddsmith.odds_model.evaluation import EvaluationMatch, evaluate_expanding_window


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-train-seasons", type=int, default=4)
    parser.add_argument("--min-edge", type=float, default=0.03)
    parser.add_argument("--max-edge", type=float, default=0.15)
    parser.add_argument("--bootstrap-samples", type=int, default=1000)
    parser.add_argument("--output", type=Path, help="optional JSON output path")
    parser.add_argument(
        "--publish",
        action="store_true",
        help="store this immutable evaluation snapshot in the configured database",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    with Session(get_engine()) as session:
        rows = list(
            session.exec(
                select(
                    MatchObservation.league,
                    MatchObservation.season,
                    MatchObservation.kickoff_utc,
                    MatchObservation.home_team,
                    MatchObservation.away_team,
                    MatchObservation.home_goals,
                    MatchObservation.away_goals,
                    MatchObservation.close_home_odds,
                    MatchObservation.close_draw_odds,
                    MatchObservation.close_away_odds,
                ).order_by(MatchObservation.kickoff_utc)
            )
        )
    matches = [
        EvaluationMatch(
            league=league,
            season=season,
            kickoff_utc=kickoff_utc,
            home_team=home_team,
            away_team=away_team,
            home_goals=home_goals,
            away_goals=away_goals,
            odds_home=odds_home,
            odds_draw=odds_draw,
            odds_away=odds_away,
        )
        for (
            league,
            season,
            kickoff_utc,
            home_team,
            away_team,
            home_goals,
            away_goals,
            odds_home,
            odds_draw,
            odds_away,
        ) in rows
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
    payload = json.loads(json.dumps(asdict(report), default=str))
    document = json.dumps(payload, indent=2)
    if args.publish:
        engine = get_engine()
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            session.add(
                ModelEvaluationSnapshot(
                    model_name=report.model_name,
                    generated_at=report.generated_at,
                    dataset_matches=len(matches),
                    payload=payload,
                )
            )
            session.commit()
        print("Published evaluation snapshot.")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(document + "\n", encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
