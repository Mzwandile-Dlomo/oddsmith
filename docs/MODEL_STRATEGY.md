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

## Immediate sequence

1. Import 8–12 seasons for the five major European leagues.
2. Produce a coverage report for every field and season.
3. Train and walk-forward test the market baseline, Poisson model, and first
   boosted-tree challenger.
4. Add API-Football post-match statistics for current/future coverage.
5. Add historical odds snapshots only after pricing their quota cost.
6. Build the corners count model once corner coverage passes the chosen minimum.
