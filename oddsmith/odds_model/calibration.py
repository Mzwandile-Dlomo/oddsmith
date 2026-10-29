"""Grade stored paper predictions: does "67% to land" land about 67% of the time?

Ticket profit is a slow, noisy way to judge a model — a 1.50 acca wins or loses
mostly on luck over a few dozen tickets. Calibration uses every graded leg and
asks the sharper question first: are the probabilities themselves honest? A
model whose probabilities are honest can still lose to the bookmaker's margin,
but one whose probabilities are dishonest cannot be trusted at any price.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# (lower bound inclusive, upper bound exclusive, label). The daily ticket only
# takes legs the model rates at 55%+, so the lowest bucket is thin by design.
BUCKETS: tuple[tuple[float, float, str], ...] = (
    (0.0, 0.6, "Under 60%"),
    (0.6, 0.7, "60–70%"),
    (0.7, 0.8, "70–80%"),
    (0.8, 1.0 + 1e-9, "80%+"),
)

# Below this many graded legs the predicted-vs-actual gap is mostly luck.
MIN_MEANINGFUL_LEGS = 30


@dataclass(frozen=True)
class CalibrationBucket:
    label: str
    legs: int
    predicted_rate: float | None
    actual_rate: float | None


@dataclass(frozen=True)
class CalibrationReport:
    legs: int
    expected_hits: float
    # Roughly 95% of runs land inside [low, high] IF the probabilities are
    # honest (normal approximation to a sum of independent Bernoullis).
    expected_hits_low: float
    expected_hits_high: float
    actual_hits: int
    buckets: list[CalibrationBucket]
    verdict: str


def grade_predictions(predictions: list[tuple[float, bool]]) -> CalibrationReport:
    """Grade ``(model_prob, landed)`` pairs for legs that won or lost (never void)."""
    n = len(predictions)
    expected = sum(prob for prob, _ in predictions)
    spread = 1.96 * math.sqrt(sum(prob * (1 - prob) for prob, _ in predictions))
    low = max(0.0, expected - spread)
    high = min(float(n), expected + spread)
    actual = sum(1 for _, landed in predictions if landed)

    buckets: list[CalibrationBucket] = []
    for lower, upper, label in BUCKETS:
        inside = [(p, landed) for p, landed in predictions if lower <= p < upper]
        buckets.append(
            CalibrationBucket(
                label=label,
                legs=len(inside),
                predicted_rate=(
                    round(sum(p for p, _ in inside) / len(inside), 4) if inside else None
                ),
                actual_rate=(
                    round(sum(1 for _, landed in inside if landed) / len(inside), 4)
                    if inside
                    else None
                ),
            )
        )

    return CalibrationReport(
        legs=n,
        expected_hits=round(expected, 2),
        expected_hits_low=round(low, 2),
        expected_hits_high=round(high, 2),
        actual_hits=actual,
        buckets=buckets,
        verdict=_verdict(n, actual, low, high),
    )


def _verdict(n: int, actual: int, low: float, high: float) -> str:
    if n == 0:
        return (
            "No graded legs yet. Each new paper ticket stores the model's probability "
            "when it is saved; older tickets have none and are left out, not guessed."
        )
    if actual < low:
        verdict = "Fewer legs landed than its own probabilities allow for: it looks overconfident."
    elif actual > high:
        verdict = "More legs landed than it predicted: underconfident, or a lucky run."
    else:
        verdict = "Hits are inside the range its own probabilities predict."
    if n < MIN_MEANINGFUL_LEGS:
        return (
            f"{verdict} But only {n} graded legs: under {MIN_MEANINGFUL_LEGS}, the gap "
            "between predicted and actual is mostly luck."
        )
    return verdict
