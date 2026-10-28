from types import SimpleNamespace

from sqlmodel import create_engine

from oddsmith.models import MarketType
from oddsmith.odds_model.target_acca import MAX_PLAUSIBLE_EDGE
from scripts import generate_daily_paper


def test_run_passes_plain_canonical_values_to_daily_acca(
    tmp_path, monkeypatch, capsys
):
    engine = create_engine(f"sqlite:///{tmp_path / 'daily-paper.db'}")
    received = {}

    def fake_daily_acca(**kwargs):
        received.update(kwargs)
        return SimpleNamespace(
            auto_tracked=False,
            note="no qualifying selections",
            fixtures_scanned=0,
            candidates_scanned=0,
        )

    monkeypatch.setattr(generate_daily_paper, "init_db", lambda: None)
    monkeypatch.setattr(generate_daily_paper, "get_engine", lambda: engine)
    monkeypatch.setattr(generate_daily_paper, "daily_acca", fake_daily_acca)

    assert generate_daily_paper._run() == 0
    assert received["target_odds"] == 1.5
    assert received["max_legs"] == 4
    assert received["min_leg_prob"] == 0.55
    assert received["require_value"] is True
    assert received["max_edge"] == MAX_PLAUSIBLE_EDGE
    assert received["bankroll"] == 100.0
    assert received["horizon_bets"] == 30
    assert received["markets"] == [
        MarketType.MATCH_WINNER,
        MarketType.OVER_UNDER,
        MarketType.BTTS,
    ]
    assert received["auto_track"] is True
    assert "providers" not in received
    assert "No paper ticket" in capsys.readouterr().out
