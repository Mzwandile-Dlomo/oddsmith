# Oddsmith

Oddsmith is a football decision-support app that compares bookmaker prices with
an explainable statistical model, then builds the most likely ticket that clears
a target decimal price (for example, `1.50`). It can also save slips, recommend a
bankroll-aware stake, and track results.

It does **not** promise daily wins or guaranteed profit. A target price is a
payout constraint, not a probability. The generator can return “no bet today”
when the data does not support one.

## What works today

- Live fixtures and odds from The Odds API and API-Football.
- Modelled markets: straight win (1X2), Over/Under 2.5 goals, and both teams to
  score.
- A daily generator that finds the highest-model-probability slip above a chosen
  target while allowing at most one selection per fixture.
- Positive-value, minimum-confidence, and implausible-edge filters.
- Half-Kelly stake sizing with a 25% bankroll cap.
- Saved slips, settlement, profit/loss, historical results, and backtesting.
- Provider caching to protect paid API quotas.

Corners are intentionally not modelled or offered in generated tickets yet.
Oddsmith does collect a small, credit-capped sample of pre-match corner-total
prices so the market can later be evaluated honestly. They require historical
team-level corner counts, a separately calibrated model, and a walk-forward
backtest; odds alone are not enough to produce a trustworthy prediction.

## Build and synchronize the match dataset

Football-Data.co.uk is the primary source for the five major domestic leagues.
The range sync downloads all 75 league-season CSV files from 2012/13 through
2026/27 and normalizes completed games into `matchobservation` and
`historicalmatch`. Football-Data has no stable fixture or team IDs, so CSV rows
do not use the live-provider `footballmatch` catalogue and no synthetic IDs are
generated.

```bash
uv run --active python scripts/sync_football_data.py \
  --from-season 2012 --to-season 2026
```

The first command is plan-only and makes no network requests. Add `--write` to
download and persist, or use the Make target:

```bash
uv run --active python scripts/sync_football_data.py \
  --from-season 2012 --to-season 2026 --write
make sync-football-data
```

Complete current-season schedules come from Fixture Download's public JSON
feeds because Football-Data CSVs contain completed results and API-Football's
free plan does not expose 2026/27. Synchronize all five leagues with:

```bash
uv run --active python scripts/sync_fixtures.py --season 2026 --write
# or
make sync-fixtures
```

## Corner-price research collection

The six-hourly sync collects up to five corner-total events (at most ten The
Odds API credits per run) as append-only research snapshots. This does not turn
on corners in the prediction model or ticket generator. To run the same
collection locally:

```bash
make collect-corners
```

These rows use the source's competition-scoped `MatchNumber` in a composite
string key; no synthetic fixture or team IDs are generated. `GET
/matches/upcoming` returns the complete remaining schedule by default. Use
`days=14` when only a shorter window is needed.

Imports are idempotent. Re-running the command refreshes current-season scores
and odds without duplicating matches. Enriched rows retain source metadata,
normalized maximum/average 1X2 prices, over/under 2.5 prices, Asian handicap,
and the original CSV record. Missing statistics remain null rather than being
converted to false zeroes.

The leakage-safe feature pipeline and model promotion rules are documented in
[docs/MODEL_STRATEGY.md](docs/MODEL_STRATEGY.md).

## Run locally

Requirements: Python 3.14, `uv`, Node.js/npm, and optionally Tilt. The
database is hosted on Supabase — set `DATABASE_URL` in `.env` to its
connection string. Docker is only needed for the optional local Postgres
(`make db-up`, or `make up-db` to run it as part of the Tilt stack).

```bash
cp .env.example .env
make setup
make web-setup
make up
```

`make up` starts the backend and frontend under a Tilt dashboard. The web app
runs at `http://localhost:3000`; the API runs at `http://localhost:8137`.

For separate processes:

```bash
make run
make web-dev
```

The Football-Data sync needs no API key. Live odds providers are optional and
require their corresponding key. Oddsmith's model endpoints need rows in
`historicalmatch`; without them the API reports that the model is untrained.

## Persistent match API

Historical Football-Data rows are served by the `/history` and model endpoints.
API-Football remains an optional path for competitions and live fixtures that
the CSV source does not cover. Its sync can be previewed and run with:

```bash
uv run --active python scripts/sync_api_football.py
uv run --active python scripts/sync_api_football.py --write
```

Use repeated `--league` flags for a smaller job, for example
`--league epl --league champions-league`. Schedule the write command (cron,
systemd, GitHub Actions, or the deployment platform's scheduler) to keep scores
and statuses current. The sync is idempotent.

The stored catalogue is available through:

```text
GET /matches?season=2026&league=epl
GET /matches/today
GET /matches/upcoming
GET /matches/{match_id}
GET /teams/{team_id}/matches
GET /matches/{match_id}/statistics
GET /matches/{match_id}/odds
GET /predictions/{match_id}
```

CSV statistics and odds are returned directly from PostgreSQL. For
API-Football-backed rows, statistics, odds, and provider predictions are fetched
lazily and stored. Pass `refresh=true` only when a fresh provider read is
intended. Provider predictions are not available for CSV rows. Dates and the
`today` boundary use UTC.

## Quality checks

```bash
make check
make web-lint
cd web && npx tsc --noEmit
```

## Product and revenue direction

A sustainable first product is a subscription for analysis—not selling a
guarantee:

- Free: fixture browser, manual bet builder, saved slips, and delayed results.
- Pro: daily target-ticket generator, market filters, model-vs-bookmaker edge,
  alerts when a valid ticket appears, and bankroll/performance analytics.
- Later: bookmaker comparison or affiliate revenue where legally permitted,
  clearly separated from model rankings.

Before charging users, add authentication and per-user data, automated result
settlement, scheduled daily generation/notifications, a reproducible historical
data loader, model monitoring, and jurisdiction-specific responsible-gambling
and affiliate disclosures.

The metrics that matter are out-of-sample calibration, closing-line value, and
real settled ROI after a meaningful sample—not the number of winning days.
