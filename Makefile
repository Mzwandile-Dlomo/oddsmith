# Oddsmith developer tasks.
# `VIRTUAL_ENV` is pinned to this project's .venv so uv does not warn about a
# stale env var inherited from a sibling project.
export VIRTUAL_ENV := $(CURDIR)/.venv

UV := uv run --active
WEB := web
PORT ?= 8137
WEB_PORT ?= 3000

.DEFAULT_GOAL := help

.PHONY: help setup web-setup db-up db-down db-reset db-logs \
        up up-db down run web-dev test lint fmt check \
        web-build web-lint web-check sync-football-data sync-fixtures \
        settle sync daily-paper whatsapp-picks collect-corners clean

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

# --- Setup ---------------------------------------------------------------- #

setup: ## Install/sync backend dependencies (incl. dev group)
	uv sync

web-setup: ## Install frontend dependencies
	cd $(WEB) && npm install

# --- Database ------------------------------------------------------------- #

db-up: ## Start the Postgres container and wait until healthy
	docker compose up -d
	@echo "Waiting for Postgres to be healthy..."
	@until [ "$$(docker inspect --format '{{.State.Health.Status}}' oddsmith-postgres 2>/dev/null)" = "healthy" ]; do sleep 1; done
	@echo "Postgres is healthy."

db-down: ## Stop the Postgres container (data is preserved)
	docker compose down

db-reset: ## Stop Postgres and DELETE its data volume
	docker compose down -v

db-logs: ## Tail Postgres container logs
	docker compose logs -f db

# --- Run ------------------------------------------------------------------ #

up: ## Run the app stack (backend + frontend) via Tilt with a dashboard; DB is Supabase
	tilt up

up-db: ## Same as `up`, but also starts the local Postgres container
	tilt up -- --with-db

down: ## Stop the Tilt stack
	tilt down

run: db-up ## Run ONLY the API with autoreload (starts the DB first) on $(PORT)
	$(UV) uvicorn oddsmith.api:app --reload --port $(PORT)

sync-football-data: ## Import Football-Data seasons 2012/13 through 2026/27
	$(UV) python scripts/sync_football_data.py --from-season 2012 --to-season 2026 --write

sync-football-data-current: ## Import only 2026/27 Football-Data results (fast; keeps insights fresh)
	$(UV) python scripts/sync_football_data.py --from-season 2026 --to-season 2026 --write

sync-fixtures: ## Import complete 2026/27 schedules for the five major leagues
	$(UV) python scripts/sync_fixtures.py --season 2026 --write

# --- Scheduled sync (mirrors .github/workflows) --------------------------- #

settle: ## Settle from data already in the DB (no provider calls, no quota)
	$(UV) python scripts/settle_odds_snapshots.py
	$(UV) python scripts/settle_slips.py

sync: ## Fetch results and fresh prices, then settle (spends provider quota)
	$(UV) python scripts/ingest_current_results.py --lookback-days 3 --write
	$(UV) python scripts/capture_odds.py --days 3

daily-paper: ## Archive today's qualified model ticket as a paper observation
	$(UV) python scripts/generate_daily_paper.py

whatsapp-picks: ## Preview the Strong slip WhatsApp message (SEND=1 to deliver it)
	$(UV) python scripts/send_strong_picks.py $(if $(SEND),--send)

collect-corners: ## Collect research-only corner prices (max 5 events / 10 credits)
	$(UV) python scripts/capture_odds.py --markets corner_totals --max-additional-events 5 --max-additional-credits 10

web-dev: ## Run ONLY the Next.js frontend dev server on $(WEB_PORT)
	cd $(WEB) && npm run dev

# --- Backend quality ------------------------------------------------------ #

test: ## Run the backend test suite
	$(UV) pytest -q

lint: ## Lint backend with ruff
	$(UV) ruff check .

fmt: ## Auto-fix lint issues and format backend with ruff
	$(UV) ruff check --fix .
	$(UV) ruff format .

check: lint test ## Lint then run backend tests

# --- Frontend quality ----------------------------------------------------- #

web-build: ## Production build of the frontend (type-checks)
	cd $(WEB) && npm run build

web-lint: ## Lint the frontend with eslint
	cd $(WEB) && npm run lint

web-check: web-lint web-build ## Lint then build the frontend

# --- Cleanup -------------------------------------------------------------- #

clean: ## Remove caches and build artifacts (backend + frontend)
	rm -rf .pytest_cache .ruff_cache .mypy_cache build dist *.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf $(WEB)/.next
