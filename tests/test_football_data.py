from sqlmodel import Session, SQLModel, create_engine, select

from oddsmith.data.football_data import import_observations, parse_csv
from oddsmith.db import HistoricalMatch, MatchObservation


CSV = """Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,HTHG,HTAG,HS,AS,HST,AST,HC,AC,HY,AY,HR,AR,MaxCH,MaxCD,MaxCA,MaxC>2.5,MaxC<2.5
E0,16/08/2025,12:30,Liverpool,Bournemouth,4,2,1,0,19,10,10,3,6,3,1,2,0,0,1.45,5.20,7.40,1.70,2.30
E0,not-a-date,,Broken,Row,1,0,,,,,,,,,,,,,,,,,
"""


def test_parse_csv_keeps_ml_features_and_closing_odds():
    rows, rejected = parse_csv(CSV, season=2025)

    assert len(rows) == 1
    assert rejected == 1
    match = rows[0]
    assert match.league == "EPL"
    assert match.home_goals == 4
    assert match.home_shots_on_target == 10
    assert match.home_corners == 6
    assert match.away_corners == 3
    assert match.close_home_odds == 1.45
    assert match.close_over_2_5_odds == 1.70
    assert match.raw_payload["HomeTeam"] == "Liverpool"


def test_import_is_idempotent_and_feeds_poisson_baseline():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    rows, rejected = parse_csv(CSV, season=2025)

    with Session(engine) as session:
        first = import_observations(session, rows, rejected=rejected)
        second = import_observations(session, rows, rejected=rejected)
        observations = list(session.exec(select(MatchObservation)))
        baseline = list(session.exec(select(HistoricalMatch)))

    assert first.inserted == 1
    assert first.baseline_inserted == 1
    assert second.inserted == 0
    assert second.existing == 1
    assert len(observations) == 1
    assert len(baseline) == 1
