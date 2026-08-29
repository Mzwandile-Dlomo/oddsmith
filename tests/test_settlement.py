from datetime import UTC, datetime, timedelta

from sqlmodel import Session, SQLModel, create_engine, select

from oddsmith.data.settlement import settle_from_match_observations, snapshot_result
from oddsmith.db import MatchObservation, OddsFixtureResult, OddsSnapshot


def _session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _snapshot(
    *, market: str = "btts", selection: str = "Yes", point: float | None = None
) -> OddsSnapshot:
    kickoff = datetime(2026, 8, 1, 15, tzinfo=UTC)
    return OddsSnapshot(
        snapshot_key=f"{market}:{selection}:{point}",
        fixture_id="provider:event-1",
        provider="provider",
        bookmaker="Book",
        league="League",
        kickoff_utc=kickoff,
        captured_at=kickoff - timedelta(hours=24),
        hours_to_kickoff=24.0,
        home_team="Atlético FC",
        away_team="Chelsea",
        market_type=market,
        selection=selection,
        point=point,
        price=1.9,
    )


def test_settlement_matches_normalized_teams_and_kickoff():
    with _session() as session:
        session.add(_snapshot())
        session.add(
            MatchObservation(
                source_key="result:1",
                source="test",
                league="League",
                season=2026,
                kickoff_utc=datetime(2026, 8, 1, 19, tzinfo=UTC),
                home_team="Atletico",
                away_team="Chelsea FC",
                home_goals=2,
                away_goals=1,
                home_corners=6,
                away_corners=4,
                raw_payload={},
            )
        )
        session.commit()

        run = settle_from_match_observations(
            session, now=datetime(2026, 8, 2, tzinfo=UTC)
        )
        result = session.exec(select(OddsFixtureResult)).one()

    assert run.matched == 1
    assert run.unmatched == 0
    assert result.home_goals == 2
    assert result.home_corners == 6


def test_snapshot_result_supports_btts_goals_corners_and_match_winner():
    result = OddsFixtureResult(
        fixture_id="provider:event-1",
        source="test",
        source_key="result:1",
        kickoff_utc=datetime(2026, 8, 1, 15, tzinfo=UTC),
        home_team="Home",
        away_team="Away",
        home_goals=2,
        away_goals=1,
        home_corners=6,
        away_corners=4,
    )

    assert snapshot_result(_snapshot(), result) == "won"
    assert snapshot_result(_snapshot(market="match_winner", selection="Away"), result) == "lost"
    assert snapshot_result(
        _snapshot(market="over_under", selection="Over", point=2.5), result
    ) == "won"
    assert snapshot_result(
        _snapshot(market="corner_totals", selection="Under", point=10.0), result
    ) == "void"


def test_settlement_leaves_unmatched_fixture_unsettled():
    with _session() as session:
        session.add(_snapshot())
        session.commit()

        run = settle_from_match_observations(
            session, now=datetime(2026, 8, 2, tzinfo=UTC)
        )

    assert run.matched == 0
    assert run.unmatched == 1
