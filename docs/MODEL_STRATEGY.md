# Oddsmith data and model strategy

## Objective

Estimate calibrated pre-match probabilities, then act only when the available
price has positive expected value after bookmaker margin. The system optimizes
long-run decision quality, not daily win streaks.

The bookmaker market is the benchmark. A new model is useful only if it improves
out-of-sample log loss/Brier score, calibration, closing-line value, or settled
ROI after costs over a meaningful sample.

## Data layers

1. **Historical outcomes and match facts** — goals, shots, shots on target,
   corners, fouls, cards, referee, and half-time scores.
2. **Odds history** — opening, timestamped, and closing prices per bookmaker and
   market. Closing consensus prices are both a strong benchmark and the fairest
   way to evaluate whether a signal beat the market.
3. **Pre-match context** — lineups, injuries/suspensions, rest, travel, manager,
   competition stage, weather, and schedule congestion.
4. **Identity and quality** — stable provider IDs, team-name mappings, source,
   collection time, null coverage, and corrections. Missing data stays null.

`MatchObservation` is the wide source-of-truth table. The original payload is
retained so parsers can be repaired without downloading the data again.

## Leakage barrier

Every feature for match `t` must be computable before match `t` kicks off.
Current-match shots, corners, cards, goals, and closing prices collected after
kickoff cannot enter its feature vector. `build_training_examples` emits a row
before updating either team's rolling history.

Never use a random train/test split. Use expanding-window evaluation:

```text
train seasons 1..N  -> validate season N+1
train seasons 1..N+1 -> validate season N+2
```

Tune on validation seasons once; keep the newest full season untouched as the
final test. Report metrics by league, season, market, odds band, and data source.

## Model ladder

Start simple and make every new model beat the previous rung:

1. **Market probabilities** — de-margined bookmaker consensus. This is the real
   baseline, not a naive home-win guess.
2. **Dixon-Coles Poisson** — current explainable goals/1X2 baseline.
3. **Gradient-boosted trees** — one calibrated classifier each for 1X2, BTTS,
   and Over/Under 2.5 using rolling team features, rest, league, and market
   probabilities.
4. **Count models** — Poisson or negative-binomial models for home/away corners;
   derive totals and lines from the predicted count distribution.
5. **Ensemble** — blend model and market probabilities only when walk-forward
   validation proves the blend is better calibrated.

An LLM should explain selections and summarize evidence, not generate numeric
probabilities. Tabular/count models are the appropriate prediction engines.

## Promotion gates

A candidate model becomes the live champion only when it:

- beats the current champion on out-of-sample log loss and calibration;
- shows no catastrophic league or odds-band segment;
- has enough qualifying bets for the ROI interval to be meaningful;
- remains positive after realistic odds availability and limits;
- uses only fields available at the actual prediction timestamp.

Model probabilities should be calibrated separately after training. Kelly stake
sizing must use the calibrated probability and remain capped; no calibration,
no automated stake.

## Current benchmark (2026-08-29)

The five-league expanding-window benchmark uses eight unseen test seasons per
league. The boosted challenger pools the leagues, fits on older seasons,
calibrates on the immediately preceding season, and scores only the following
season. Because closing probabilities are input features, its conclusions apply
only to close-to-kickoff decisions.

| Candidate | Unseen matches | Log loss | Brier | Strategy ROI | 95% ROI interval |
| --- | ---: | ---: | ---: | ---: | ---: |
| Closing market | 14,168 | 0.9695 | 0.5762 | — | — |
| Calibrated boosted 1X2 | 14,168 | 0.9826 | 0.5843 | -2.35% | -5.64% to +1.76% |
| Dixon-Coles Poisson | 14,285 | 1.0208 | 0.6106 | -1.65% | -5.58% to +2.36% |

The boosted model is a meaningful improvement over Poisson, but the closing
market still wins on accuracy, log loss, Brier score, and calibration. Neither
model passes the promotion gates, and neither ROI interval establishes a
positive edge. Oddsmith therefore remains a research baseline, not a proven
profit engine.

The first total-corners count benchmark covers 14,167 unseen matches. Its MAE is
2.6903 corners versus 2.7110 for a prior league-mean baseline, a paired gain of
0.0207 with a 95% bootstrap interval from 0.0120 to 0.0307. The gain is positive
overall but not reliable in Bundesliga or Ligue 1. This validates a small amount
of count signal, not a betting edge: the dataset contains zero historical corner
lines/prices, so corner ROI remains untestable and corner tickets remain blocked.

New provider refreshes now append one `OddsSnapshot` row per bookmaker outcome,
including capture time and hours before kickoff. This makes opening, 24-hour,
and closing-horizon evaluation possible once enough fixtures have accumulated.
Run `scripts/capture_odds.py` on a schedule; its default deliberately uses only
The Odds API because API-Football can consume one odds request per fixture.

The standard bulk endpoint supplies 1X2 and goals totals. BTTS and total-corner
markets require separate provider support or per-event endpoints, so adding the
snapshot table does not imply those markets are already being collected.

The initial quota-free backfill recovered 8,632 outcome prices across 64 cached
fixtures: 6,672 match-winner outcomes and 1,960 goals-total outcomes, observed
between 2.3 and 74.0 hours before kickoff. It recovered no BTTS or corner prices,
so those ROI gates remain blocked.

The additional-market collector discovers events through the provider's free
events endpoint, then fetches BTTS and total-corner prices one event at a time.
It is plan-only unless `--write` is supplied and enforces both event and credit
ceilings:

```bash
# No network or quota use; prints the configured worst-case plan.
uv run --active python scripts/collect_additional_odds.py

# Explicitly permit at most five events and 20 credits.
uv run --active python scripts/collect_additional_odds.py \
  --max-events 5 --max-credits 20 --write
```

The command records the provider-reported credits used and remaining. Schedule
it only after confirming the account plan and preferred bookmaker regions.

The first capped live run requested five of 79 discovered events. It used 18 of
the allowed 20 credits, leaving 434, and stored 254 outcomes: 114 BTTS prices
across five fixtures and 140 total-corner prices across four fixtures. These
were captured 0.7–13.7 hours before kickoff. This proves collection works; it is
far too small and too close to kickoff to validate ROI or a 24-hour strategy.

## Immediate sequence

1. Keep the latest full season untouched while iterating on challenger features.
2. Add opening and timestamped odds so 24-hour and close-to-kickoff models can
   be evaluated separately.
3. Add API-Football post-match statistics for current/future coverage.
4. Evaluate a market-residual model without tuning against the final test fold.
5. Build the corners count model once corner coverage passes the chosen minimum.
6. Promote a model only after it clears every gate above on unseen matches.
