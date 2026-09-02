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

Corners are intentionally not modelled yet. They require historical team-level
corner counts, a separately calibrated model, and a walk-forward backtest. Odds
alone are not enough to produce a trustworthy corner prediction.

## Build the training dataset

Oddsmith can download Football-Data CSV archives into the enriched
`matchobservation` table. The default divisions are EPL, Bundesliga, La Liga,
Serie A, and Ligue 1. Without `--write`, the command only downloads and validates:

```bash
uv run --active python scripts/import_football_data.py \
  --season-code 2223 --season-code 2324 --season-code 2425
```

After checking the row totals, explicitly write to the database configured by
`DATABASE_URL`:

```bash
uv run --active python scripts/import_football_data.py \
  --season-code 2223 --season-code 2324 --season-code 2425 --write
```

Imports are idempotent. Enriched rows preserve source metadata and the raw CSV
record, while new matches are also copied into `historicalmatch` for the current
Poisson model. Missing statistics remain null rather than being converted to
false zeroes.

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

Add at least one odds-provider key to `.env`. The prediction endpoints also need
rows in `historicalmatch`; without them the API now reports that the model is
untrained instead of presenting a generic empty ticket.

## Persistent match API

The API-Football schedule is synchronized into PostgreSQL and served without a
provider call on each app request. Preview the current 2026/27 import (one
request per competition), then run it explicitly:

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
GET /matches/{api_football_fixture_id}
GET /teams/{api_football_team_id}/matches
GET /matches/{api_football_fixture_id}/statistics
GET /matches/{api_football_fixture_id}/odds
GET /predictions/{api_football_fixture_id}
```

Statistics, odds, and provider predictions are fetched lazily, stored in
PostgreSQL, and reused. Pass `refresh=true` only when a fresh provider read is
intended. Dates and the `today` boundary use UTC.

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
