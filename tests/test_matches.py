import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, create_engine

from oddsmith import db as db_module
from oddsmith.api import app
from oddsmith.match_sync import upsert_fixtures
from oddsmith.matches import get_match_provider


def _fixture(*, status="NS", home_goals=None, away_goals=None):
    return {
        "fixture": {
            "id": 12345,
            "date": "2026-09-12T14:00:00+00:00",
            "venue": {"id": 10, "name": "Test Ground", "city": "London"},
            "status": {"long": "Not Started", "short": status, "elapsed": None},
        },
        "league": {
            "id": 39,
            "name": "Premier League",
            "type": "League",
            "country": "England",
            "season": 2026,
            "round": "Regular Season - 4",
        },
        "teams": {
            "home": {"id": 42, "name": "Arsenal"},
            "away": {"id": 49, "name": "Chelsea"},
        },
        "goals": {"home": home_goals, "away": away_goals},
        "score": {"halftime": {"home": None, "away": None}},
        "events": [],
        "lineups": [],
        "statistics": [],
    }


class _MatchProvider:
    def __init__(self):
        self.calls = 0

    async def fixture_resource(self, fixture_id, resource):
        self.calls += 1
        return [{"fixture": fixture_id, "resource": resource}], None


@pytest.fixture
def match_client(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'matches.db'}", connect_args={"check_same_thread": False}
    )
    monkeypatch.setattr(db_module, "_engine", engine)
    monkeypatch.setattr(db_module, "get_engine", lambda: engine)
    SQLModel.metadata.create_all(engine)
    with db_module.Session(engine) as session:
        upsert_fixtures(session, [_fixture()])
    provider = _MatchProvider()
    app.dependency_overrides[get_match_provider] = lambda: provider
    with TestClient(app) as client:
        yield client, provider
    app.dependency_overrides.clear()


def test_match_catalogue_filters_and_detail(match_client):
    client, _ = match_client

    response = client.get("/matches", params={"season": 2026, "league": "epl"})
    assert response.status_code == 200
    assert response.json()[0]["id"] == 12345

    detail = client.get("/matches/12345")
    assert detail.status_code == 200
    assert detail.json()["details"]["events"] == []

    team = client.get("/teams/42/matches")
    assert [item["id"] for item in team.json()] == [12345]


def test_expensive_match_resources_are_persistently_cached(match_client):
    client, provider = match_client

    first = client.get("/matches/12345/statistics")
    second = client.get("/matches/12345/statistics")

    assert first.status_code == 200
    assert second.json() == first.json()
    assert provider.calls == 1

    client.get("/matches/12345/statistics", params={"refresh": True})
    assert provider.calls == 2


def test_upsert_updates_mutable_match_state(match_client):
    client, _ = match_client
    engine = db_module.get_engine()
    with db_module.Session(engine) as session:
        upsert_fixtures(session, [_fixture(status="FT", home_goals=2, away_goals=1)])

    body = client.get("/matches/12345").json()
    assert body["status_short"] == "FT"
    assert body["home_goals"] == 2


def test_unknown_league_returns_validation_error(match_client):
    client, _ = match_client
    response = client.get("/matches", params={"league": "made-up-league"})
    assert response.status_code == 422
