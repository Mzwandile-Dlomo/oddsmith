"""Evaluate and optionally publish the total-corners count-model benchmark."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from sqlmodel import SQLModel, Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oddsmith.data.features import build_training_examples
from oddsmith.data.observations import load_feature_observations
from oddsmith.db import CornerEvaluationSnapshot, get_engine
from oddsmith.odds_model.corners import evaluate_corner_counts


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-train-seasons", type=int, default=4)
    parser.add_argument("--feature-window", type=int, default=8)
    parser.add_argument("--min-team-matches", type=int, default=3)
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
        observations = load_feature_observations(session)
    examples = build_training_examples(
        observations,
        window=args.feature_window,
        min_team_matches=args.min_team_matches,
    )
    report = evaluate_corner_counts(
        examples,
        min_train_seasons=args.min_train_seasons,
        bootstrap_samples=args.bootstrap_samples,
    )
    payload = json.loads(json.dumps(asdict(report), default=str))
    document = json.dumps(payload, indent=2)
    if args.publish:
        engine = get_engine()
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            session.add(
                CornerEvaluationSnapshot(
                    model_name=report.model_name,
                    generated_at=report.generated_at,
                    dataset_matches=len(observations),
                    payload=payload,
                )
            )
            session.commit()
        print("Published corner evaluation snapshot.")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(document + "\n", encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
