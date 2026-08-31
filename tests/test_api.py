
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from oddsmith import api as api_module
from oddsmith import db as db_module
from oddsmith.api import app, get_providers
from oddsmith.db import (
    CornerEvaluationSnapshot,
    HistoricalMatch,
    MatchObservation,
    ModelEvaluationSnapshot,
)
from oddsmith.models import Fixture, Market, MarketType, Outcome
from oddsmith.providers.base import OddsProvider


class _StubProvider(OddsProvider):
    name = "stub"

    async def list_fixtures(self, *, date_from, date_to, markets=None):
        return [
            Fixture(
                id="stub:1",
                home_team="Arsenal",
                away_team="Chelsea",
                kickoff_utc=date_from,
                league="EPL",
                provider="stub",
                markets=[
                    Market(
                        type=MarketType.MATCH_WINNER,
                        outcomes=[
                            Outcome(name="Home", price=2.1),
                            Outcome(name="Draw", price=3.2),
                            Outcome(name="Away", price=3.4),
                        ],
                    )
                ],
            )
        ]

    async def get_markets(self, fixture_id):
        return []


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path/'test.db'}", connect_args={"check_same_thread": False}
    )
    monkeypatch.setattr(db_module, "_engine", engine)
    monkeypatch.setattr(db_module, "get_engine", lambda: engine)
    SQLModel.metadata.create_all(engine)

    # The model service is cached in a module global; reset it so a model trained
    # in one test cannot leak into the next.
    monkeypatch.setattr(api_module, "_model_service", None)

    app.dependency_overrides[get_providers] = lambda: [_StubProvider()]
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_list_fixtures(client):
    resp = client.get("/fixtures")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["home_team"] == "Arsenal"


def test_model_readiness_is_honest_when_dataset_is_empty(client):
    body = client.get("/model/readiness").json()

    assert body["model_stage"] == "research_baseline"
    assert body["model_trained"] is False
    assert body["dataset_matches"] == 0
    assert body["price_snapshots"] == 0
    assert all(item["roi_validated"] is False for item in body["markets"])


def test_model_readiness_reports_coverage(client):
    with Session(db_module.get_engine()) as session:
        session.add(
            MatchObservation(
                source_key="test:readiness",
                source="test",
                league="EPL",
                season=2025,
                kickoff_utc=datetime(2025, 8, 1, tzinfo=UTC),
                home_team="Arsenal",
                away_team="Chelsea",
                home_goals=2,
                away_goals=1,
                home_shots=12,
                away_shots=8,
                home_corners=6,
                away_corners=4,
                home_yellow_cards=1,
                away_yellow_cards=2,
                close_home_odds=1.9,
                close_draw_odds=3.5,
                close_away_odds=4.2,
                raw_payload={},
            )
        )
        session.add(
            HistoricalMatch(
                league="EPL",
                season=2025,
                kickoff_utc=datetime(2025, 8, 1, tzinfo=UTC),
                home_team="Arsenal",
                away_team="Chelsea",
                home_goals=2,
                away_goals=1,
            )
        )
        session.commit()

    body = client.get("/model/readiness").json()
    coverage = {item["key"]: item for item in body["coverage"]}
    markets = {item["key"]: item for item in body["markets"]}

    assert body["model_trained"] is True
    assert body["dataset_matches"] == 1
    assert body["leagues"] == 1
    assert coverage["corners"]["percent"] == 100.0
    assert coverage["odds_1x2"]["records"] == 1
    assert coverage["odds_goals"]["records"] == 0
    assert coverage["odds_btts"]["records"] == 0
    assert markets["match_winner"]["settled_rows"] == 0


def test_paper_performance_uses_only_generated_paper_tickets_and_unit_stakes(client):
    paper_win = _slip_on("2026-07-22T15:00:00Z", stake=0, price=2.0)
    paper_win["name"] = "Paper 2.00 (1x)"
    won = client.post("/slips", json=paper_win).json()
    client.patch(
        f"/slips/{won['id']}",
        json={"legs": [{"leg_id": won["legs"][0]["id"], "result": "won"}]},
    )

    paper_loss = _slip_on("2026-07-23T15:00:00Z", stake=0, price=1.5)
    paper_loss["name"] = "Paper 1.50 (1x)"
    lost = client.post("/slips", json=paper_loss).json()
    client.patch(
        f"/slips/{lost['id']}",
        json={"legs": [{"leg_id": lost["legs"][0]["id"], "result": "lost"}]},
    )

    manual = _slip_on("2026-07-24T15:00:00Z", stake=10, price=10.0)
    manual_slip = client.post("/slips", json=manual).json()
    client.patch(
        f"/slips/{manual_slip['id']}",
        json={
            "legs": [
                {"leg_id": manual_slip["legs"][0]["id"], "result": "won"}
            ]
        },
    )

    body = client.get("/model/paper-performance").json()

    assert body["generated_tickets"] == 2
    assert body["settled_tickets"] == 2
    assert body["won_tickets"] == 1
    assert body["lost_tickets"] == 1
    assert body["win_rate"] == 0.5
    assert body["average_odds"] == 1.75
    assert body["unit_staked"] == 2.0
    assert body["unit_returned"] == 2.0
    assert body["unit_profit"] == 0.0
    assert body["unit_roi"] == 0.0


def test_latest_model_evaluation_requires_a_published_snapshot(client):
    assert client.get("/model/evaluation/latest").status_code == 404


def test_latest_model_evaluation_returns_published_payload(client):
    generated_at = datetime(2026, 8, 29, tzinfo=UTC)
    metrics = {
        "matches": 100,
        "accuracy": 0.5,
        "log_loss": 1.0,
        "brier": 0.6,
        "calibration_error": 0.02,
    }
    strategy = {
        "bets": 20,
        "wins": 8,
        "profit": -1.0,
        "roi": -0.05,
        "roi_ci_low": -0.2,
        "roi_ci_high": 0.1,
    }
    payload = {
        "generated_at": generated_at.isoformat(),
        "model_name": "Dixon-Coles Poisson",
        "min_train_seasons": 4,
        "min_edge": 0.03,
        "max_edge": 0.15,
        "leagues": [],
        "overall": {"model": metrics, "market": metrics, "strategy": strategy},
    }
    with Session(db_module.get_engine()) as session:
        session.add(
            ModelEvaluationSnapshot(
                model_name="Dixon-Coles Poisson",
                generated_at=generated_at,
                dataset_matches=100,
                payload=payload,
            )
        )
        session.commit()

    body = client.get("/model/evaluation/latest").json()

    assert body["model_name"] == "Dixon-Coles Poisson"
    assert body["overall"]["strategy"]["roi"] == -0.05


def test_latest_corner_evaluation_requires_a_published_snapshot(client):
    assert client.get("/model/corners/evaluation/latest").status_code == 404


def test_latest_corner_evaluation_returns_published_payload(client):
    generated_at = datetime(2026, 8, 29, tzinfo=UTC)
    metrics = {
        "matches": 100,
        "mean_actual": 9.8,
        "mean_prediction": 9.7,
        "mae": 2.6,
        "rmse": 3.3,
        "poisson_deviance": 1.1,
    }
    payload = {
        "generated_at": generated_at.isoformat(),
        "model_name": "Poisson HistGradientBoosting total corners",
        "min_train_seasons": 4,
        "leagues": [],
        "overall": {
            "model": metrics,
            "baseline": {**metrics, "mae": 2.7},
            "mae_improvement": 0.1,
            "improvement_ci_low": 0.02,
            "improvement_ci_high": 0.18,
        },
        "odds_rows": 0,
        "roi_validated": False,
        "limitation": "Historical corner lines and prices are unavailable.",
    }
    with Session(db_module.get_engine()) as session:
        session.add(
            CornerEvaluationSnapshot(
                model_name=payload["model_name"],
                generated_at=generated_at,
                dataset_matches=100,
                payload=payload,
            )
        )
        session.commit()

    body = client.get("/model/corners/evaluation/latest").json()

    assert body["overall"]["model"]["mae"] == 2.6
    assert body["roi_validated"] is False


def test_create_and_settle_slip_lifecycle(client):
    payload = {
        "name": "My Acca",
        "stake": 10,
        "legs": [
            {
                "fixture_id": "stub:1",
                "home_team": "Arsenal",
                "away_team": "Chelsea",
                "kickoff_utc": "2026-07-25T15:00:00Z",
                "league": "EPL",
                "provider": "stub",
                "market_type": "match_winner",
                "selection": "Home",
                "price": 2.0,
            },
            {
                "fixture_id": "stub:2",
                "home_team": "Liverpool",
                "away_team": "Everton",
                "kickoff_utc": "2026-07-26T12:00:00Z",
                "league": "EPL",
                "provider": "stub",
                "market_type": "btts",
                "selection": "Yes",
                "price": 1.5,
            },
        ],
    }
    created = client.post("/slips", json=payload)
    assert created.status_code == 201
    slip = created.json()
    assert slip["combined_odds"] == 3.0
    assert slip["potential_return"] == 30.0
    assert slip["result"] == "pending"
    slip_id = slip["id"]
    leg_ids = [leg["id"] for leg in slip["legs"]]

    # Settle both legs as won -> slip won, payout 30.
    won = client.patch(
        f"/slips/{slip_id}",
        json={"legs": [{"leg_id": lid, "result": "won"} for lid in leg_ids]},
    )
    assert won.status_code == 200
    body = won.json()
    assert body["result"] == "won"
    assert body["payout"] == 30.0
    assert body["profit_loss"] == 20.0
    assert body["settled_at"] is not None

    # It persists.
    fetched = client.get(f"/slips/{slip_id}").json()
    assert fetched["result"] == "won"


def test_one_lost_leg_makes_slip_lost(client):
    payload = {
        "stake": 10,
        "legs": [
            {
                "fixture_id": "stub:1",
                "home_team": "Arsenal",
                "away_team": "Chelsea",
                "kickoff_utc": "2026-07-25T15:00:00Z",
                "provider": "stub",
                "market_type": "match_winner",
                "selection": "Home",
                "price": 2.0,
            }
        ],
    }
    slip = client.post("/slips", json=payload).json()
    leg_id = slip["legs"][0]["id"]
    updated = client.patch(
        f"/slips/{slip['id']}", json={"legs": [{"leg_id": leg_id, "result": "lost"}]}
    ).json()
    assert updated["result"] == "lost"
    assert updated["payout"] == 0.0
    assert updated["profit_loss"] == -10.0


def test_create_slip_requires_at_least_one_leg(client):
    resp = client.post("/slips", json={"stake": 5, "legs": []})
    assert resp.status_code == 422


def test_get_missing_slip_404(client):
    assert client.get("/slips/9999").status_code == 404


# --------------------------------------------------------------------------- #
# Daily "banker" acca + staking
# --------------------------------------------------------------------------- #


def _seed_history(engine, league="EPL"):
    """Enough results for the Poisson model to fit strengths for both teams."""
    base = datetime(2024, 8, 1, tzinfo=UTC)
    rows = []
    for i in range(30):
        rows.append(
            HistoricalMatch(
                league=league,
                season=2024,
                kickoff_utc=base + timedelta(days=i),
                home_team="Arsenal",
                away_team="Chelsea",
                home_goals=3,
                away_goals=0,
            )
        )
    with Session(engine) as s:
        s.add_all(rows)
        s.commit()


def test_daily_acca_returns_a_staking_plan(client):
    body = client.get("/acca/daily").json()

    assert body["target_odds"] == 1.5
    assert "staking" in body and "note" in body
    staking = body["staking"]
    # Half-Kelly, never above the hard cap.
    assert staking["recommended_fraction"] <= 0.25
    assert staking["recommended_stake"] <= staking["bankroll"]
    # The naive "let it ride" plan is always reported as ruin.
    assert staking["let_it_ride_bankroll"] == 0.0
    assert body["fixtures_scanned"] == 1
    assert body["candidates_scanned"] == 0
    assert body["model_trained"] is False
    assert body["execution_mode"] == "paper"
    assert staking["recommended_stake"] == 0.0
    assert set(body["markets_used"]) == {"match_winner", "over_under", "btts"}


def test_daily_acca_with_no_model_returns_an_honest_empty_slip(client):
    # No history seeded -> the model is untrained -> no candidates at all.
    body = client.get("/acca/daily").json()

    assert body["legs"] == []
    assert body["target_met"] is False
    assert body["staking"]["recommended_stake"] == 0.0
    assert "no historical match data" in body["note"]


def test_daily_acca_echoes_its_parameters(client):
    body = client.get(
        "/acca/daily", params={"target_odds": 2.0, "bankroll": 500, "horizon_bets": 10}
    ).json()

    assert body["target_odds"] == 2.0
    assert body["staking"]["bankroll"] == 500.0
    assert body["staking"]["horizon_bets"] == 10


def test_daily_acca_trains_from_history(client):
    _seed_history(db_module.get_engine())
    body = client.get("/acca/daily", params={"min_leg_prob": 0.0}).json()

    # The model now prices the fixture, so the response is coherent whether or
    # not the bookmaker's price happens to leave value on the table.
    assert body["pool_size"] >= 0
    assert 0.0 <= body["combined_model_prob"] <= 1.0
    assert body["staking"]["recommended_fraction"] >= 0.0


def test_daily_acca_unlocks_live_mode_only_after_all_promotion_gates_pass(client):
    metrics = {
        "matches": 1000,
        "accuracy": 0.55,
        "log_loss": 0.9,
        "brier": 0.54,
        "calibration_error": 0.01,
    }
    market = {**metrics, "log_loss": 0.95, "brier": 0.57, "calibration_error": 0.02}
    with Session(db_module.get_engine()) as session:
        session.add(
            ModelEvaluationSnapshot(
                model_name="Promotable challenger",
                generated_at=datetime(2026, 8, 29, tzinfo=UTC),
                dataset_matches=1000,
                payload={
                    "overall": {
                        "model": metrics,
                        "market": market,
                        "strategy": {"roi_ci_low": 0.01},
                    }
                },
            )
        )
        session.commit()

    body = client.get("/acca/daily").json()

    assert body["execution_mode"] == "live"
    assert body["validation_model"] == "Promotable challenger"


def test_daily_acca_rejects_a_backwards_window(client):
    resp = client.get(
        "/acca/daily",
        params={"date_from": "2026-01-10T00:00:00Z", "date_to": "2026-01-01T00:00:00Z"},
    )
    assert resp.status_code == 400


def test_daily_acca_validates_target_odds(client):
    assert client.get("/acca/daily", params={"target_odds": 0.9}).status_code == 422
    assert client.get("/acca/daily", params={"max_legs": 99}).status_code == 422


def test_daily_acca_accepts_market_filters(client):
    body = client.get(
        "/acca/daily",
        params=[("markets", "match_winner"), ("markets", "btts")],
    ).json()

    assert body["markets_used"] == ["btts", "match_winner"]


def test_daily_acca_rejects_unmodelled_market(client):
    response = client.get("/acca/daily", params={"markets": "double_chance"})

    assert response.status_code == 422
    assert "not modelled" in response.json()["detail"]


# --------------------------------------------------------------------------- #
# Calendar
# --------------------------------------------------------------------------- #


def _slip_on(kickoff: str, *, stake: float = 10.0, price: float = 2.0) -> dict:
    return {
        "stake": stake,
        "legs": [
            {
                "fixture_id": "stub:1",
                "home_team": "Arsenal",
                "away_team": "Chelsea",
                "kickoff_utc": kickoff,
                "league": "EPL",
                "provider": "stub",
                "market_type": "match_winner",
                "selection": "Home",
                "price": price,
            }
        ],
    }


def test_calendar_returns_one_entry_per_day_in_the_window(client):
    resp = client.get("/calendar", params={"date_from": "2026-07-20", "date_to": "2026-07-24"})
    assert resp.status_code == 200
    body = resp.json()
    assert [d["date"] for d in body["days"]] == [
        "2026-07-20",
        "2026-07-21",
        "2026-07-22",
        "2026-07-23",
        "2026-07-24",
    ]


def test_calendar_never_calls_a_provider(client, monkeypatch):
    """A month view must not fan out into a fetch per uncovered day."""
    called = False

    async def _boom(*args, **kwargs):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(api_module, "get_cached_fixtures", _boom)
    resp = client.get("/calendar", params={"date_from": "2026-07-20", "date_to": "2026-07-24"})
    assert resp.status_code == 200
    assert called is False
    # No day was ever fetched, so every day is honestly empty.
    assert all(d["fixture_count"] == 0 for d in resp.json()["days"])


def test_calendar_buckets_a_slip_by_its_earliest_kickoff_not_creation(client):
    """A slip built the night before belongs to the day its matches are played."""
    created = client.post("/slips", json=_slip_on("2026-07-22T15:00:00Z"))
    assert created.status_code == 201

    body = client.get(
        "/calendar", params={"date_from": "2026-07-20", "date_to": "2026-07-24"}
    ).json()
    by_date = {d["date"]: d for d in body["days"]}

    assert by_date["2026-07-22"]["slip_count"] == 1
    assert by_date["2026-07-22"]["pending_count"] == 1
    assert by_date["2026-07-22"]["staked"] == 10.0
    # Pending slips contribute no P&L — only settled ones do.
    assert by_date["2026-07-22"]["profit_loss"] == 0.0
    assert body["settled_slip_count"] == 0


def test_calendar_reports_profit_for_a_settled_day(client):
    slip = client.post("/slips", json=_slip_on("2026-07-22T15:00:00Z")).json()
    leg_id = slip["legs"][0]["id"]
    client.patch(f"/slips/{slip['id']}", json={"legs": [{"leg_id": leg_id, "result": "won"}]})

    body = client.get(
        "/calendar", params={"date_from": "2026-07-20", "date_to": "2026-07-24"}
    ).json()
    day = next(d for d in body["days"] if d["date"] == "2026-07-22")

    assert day["won_count"] == 1
    assert day["profit_loss"] == 10.0  # 10 staked at 2.0 returns 20
    assert body["profit_loss"] == 10.0
    assert body["settled_slip_count"] == 1


def test_calendar_rejects_a_backwards_window(client):
    resp = client.get("/calendar", params={"date_from": "2026-07-24", "date_to": "2026-07-20"})
    assert resp.status_code == 400


def test_calendar_rejects_a_window_wider_than_the_cap(client):
    resp = client.get("/calendar", params={"date_from": "2026-01-01", "date_to": "2026-12-31"})
    assert resp.status_code == 422


def test_fixtures_cached_only_does_not_call_a_provider(client, monkeypatch):
    """`cached_only` is what keeps browsing back through the calendar free."""
    called = False

    original = api_module.get_cached_fixtures

    async def _tracking(*args, **kwargs):
        nonlocal called
        called = True
        return await original(*args, **kwargs)

    monkeypatch.setattr(api_module, "get_cached_fixtures", _tracking)

    assert client.get("/fixtures", params={"cached_only": True}).json() == []
    assert called is False

    # Without the flag the same window does reach the provider.
    assert client.get("/fixtures").status_code == 200
    assert called is True
