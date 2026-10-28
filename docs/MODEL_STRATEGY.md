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

The daily-ticket endpoint enforces this gate in the product. It may generate a
paper ticket for tracking, but returns a zero recommended stake until the latest
published model beats market log loss, Brier score and calibration, and the
strategy's 95% ROI lower bound is above zero. The UI labels this state explicitly
instead of presenting research probabilities as live betting advice.

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
events endpoint, then fetches total-corner prices one event at a time. Its
default is deliberately corners-only; BTTS must be requested explicitly. It is
plan-only unless `--write` is supplied and enforces both event and credit
ceilings:

```bash
# No network or quota use; prints the configured worst-case plan.
uv run --active python scripts/collect_additional_odds.py

# Explicitly permit at most five events and 20 credits.
uv run --active python scripts/collect_additional_odds.py \
  --max-events 5 --max-credits 20 --write

# Opt in to BTTS as well.
uv run --active python scripts/collect_additional_odds.py \
  --markets corner_totals btts --max-events 5 --max-credits 20 --write
```

The command records the provider-reported credits used and remaining. Schedule
it only after confirming the account plan and preferred bookmaker regions. The
six-hourly GitHub sync runs the same corner-only collection with a hard ceiling
of five events and ten credits; it stores/settles research snapshots only and
does not enable corner predictions or tickets.

The first capped live run requested five of 79 discovered events. It used 18 of
the allowed 20 credits, leaving 434, and stored 254 outcomes: 114 BTTS prices
across five fixtures and 140 total-corner prices across four fixtures. These
were captured 0.7–13.7 hours before kickoff. This proves collection works; it is
far too small and too close to kickoff to validate ROI or a 24-hour strategy.

Collection now defaults to the 18–36 hour horizon. `OddsFixtureResult` is a
separate settlement ledger: it matches completed priced fixtures to enriched
observations by normalized teams and kickoff time, then derives 1X2, BTTS,
goals-total, and corner-total outcomes. The first settlement pass found 23
completed priced fixtures but no matching current result rows, confirming that
continuous result ingestion—not outcome logic—is the next data blocker.

`scripts/ingest_current_results.py` closes that loop without downloading every
competition. It first finds priced fixtures that have kicked off but are not in
the settlement ledger. For only the affected dates it fetches final scores,
matches by normalized teams and kickoff time, requests post-match statistics
only for matched fixtures, inserts idempotent `MatchObservation` rows, and runs
settlement. The command is plan-only by default and has a hard request ceiling:

```bash
# Inspect unresolved coverage without calling API-Football or writing data.
uv run --active python scripts/ingest_current_results.py

# Explicitly permit at most 15 result/statistics requests.
uv run --active python scripts/ingest_current_results.py \
  --lookback-days 3 --max-requests 15 --write
```

This importer is intended for a daily post-match job. It reports the quota
header returned by API-Football, and stores the upstream fixture id in
`raw_payload` so repeat runs do not duplicate match observations. After linking
results, it also settles matching legs on saved paper tickets; the History and
Calendar views can therefore report realised paper P&L without manual updates.

The first capped production result run linked and settled 25 priced fixtures.
Five received post-match statistics under the request ceiling. It also settled
a previously saved, untagged two-leg slip as a loss after its 1.56 Liverpool
home-win leg lost. Because that record is not tagged `Paper`, it is correctly
excluded from generated-strategy performance. Sixteen recently priced fixtures
were still unresolved and remain queued for the next daily result pass.

Model Lab now reports generated paper performance separately. Only daily slips
whose generated name starts with `Paper ` enter this track record; manual slips
cannot contaminate it. Each settled ticket is normalized to a one-unit stake so
zero-stake safety does not prevent hit-rate, unit P&L, and ROI monitoring. The
100-ticket counter is a monitoring milestone, not a promotion rule: real-money
mode still requires the independent unseen-season gates above.

### Rejected challenger features (2026-10-28)

`build_training_examples` supports two opt-in groups, `venue` (home-only and
away-only form) and `h2h` (previous same-league meetings, scored from the
current home side). Both stay off by default. They were benchmarked with
`scripts/evaluate_challenger.py --extra-features ...` on identical rows
(17,897 unseen matches):

| Run | Log loss | Brier | Calibration error | ROI | 95% ROI interval |
| --- | ---: | ---: | ---: | ---: | ---: |
| Closing market | 0.9629 | 0.5717 | 0.0101 | — | — |
| Baseline | 0.9742 | 0.5788 | 0.0119 | -2.51% | -5.98% to +1.06% |
| + venue | 0.9744 | 0.5787 | 0.0124 | -2.72% | -6.26% to +0.80% |
| + h2h | 0.9750 | 0.5792 | 0.0124 | -4.41% | -7.80% to -0.82% |
| + venue + h2h | 0.9751 | 0.5793 | 0.0157 | -1.68% | -5.05% to +1.91% |

None beats the baseline on log loss or calibration, so none is promoted. The
higher ROI of the combined run comes with worse calibration and an interval
that still spans zero; it is noise, not an edge. These test seasons have now
been looked at, so do not tweak these groups and re-run against the same
folds: that would be tuning on the test set.

## Immediate sequence

1. Keep the latest full season untouched while iterating on challenger features.
2. Add opening and timestamped odds so 24-hour and close-to-kickoff models can
   be evaluated separately.
3. Run the capped result importer daily and report paper ROI, hit rate, CLV, and
   calibration only after the settlement sample is meaningful.
4. Evaluate a market-residual model without tuning against the final test fold.
5. Retrain the corners count model after priced corner coverage passes the
   chosen minimum.
6. Promote a model only after it clears every gate above on unseen matches.
