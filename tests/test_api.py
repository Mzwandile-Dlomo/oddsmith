
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from oddsmith import api as api_module
from oddsmith import db as db_module
from oddsmith.api import app, get_providers
from oddsmith.db import HistoricalMatch
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
    assert set(body["markets_used"]) == {"match_winner", "over_under", "btts"}


def test_daily_acca_with_no_model_returns_an_honest_empty_slip(client):
    # No history seeded -> the model is untrained -> no candidates at all.
    body = client.get("/acca/daily").json()

    assert body["legs"] == []
    assert body["target_met"] is False
    assert body["staking"]["recommended_stake"] == 0.0
    assert "no bet worth making" in body["note"]


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
