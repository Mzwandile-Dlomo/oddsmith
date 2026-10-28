"""Evaluate and optionally publish the calibrated boosted-tree 1X2 challenger."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from sqlmodel import SQLModel, Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oddsmith.data.features import FEATURE_GROUPS, build_training_examples
from oddsmith.data.observations import load_feature_observations
from oddsmith.db import ModelEvaluationSnapshot, get_engine
from oddsmith.odds_model.boosted import evaluate_calibrated_boosted


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-train-seasons", type=int, default=4)
    parser.add_argument("--feature-window", type=int, default=8)
    parser.add_argument("--min-team-matches", type=int, default=3)
    parser.add_argument(
        "--extra-features",
        nargs="+",
        default=[],
        choices=sorted(FEATURE_GROUPS),
        help="opt-in feature groups to evaluate as a candidate (cannot be published)",
    )
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
    parser = _parser()
    args = parser.parse_args()
    if args.publish and args.extra_features:
        # A snapshot is published under the live model's name; a candidate must
        # beat the baseline and become the default before it is published.
        parser.error("--extra-features is evaluation-only; it cannot be combined with --publish")
    with Session(get_engine()) as session:
        observations = load_feature_observations(session)
    examples = build_training_examples(
        observations,
        window=args.feature_window,
        min_team_matches=args.min_team_matches,
        extra_features=args.extra_features,
    )
    report = evaluate_calibrated_boosted(
        examples,
        min_train_seasons=args.min_train_seasons,
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
                    dataset_matches=len(observations),
                    payload=payload,
                )
            )
            session.commit()
        print("Published challenger evaluation snapshot.")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(document + "\n", encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
