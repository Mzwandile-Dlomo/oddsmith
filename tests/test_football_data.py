import httpx
import respx
from sqlmodel import Session, SQLModel, create_engine, select

from oddsmith.data.football_data import (
    FootballDataCsvProvider,
    import_observations,
    parse_csv,
    season_code,
    season_start,
)
from oddsmith.db import HistoricalMatch, MatchObservation


CSV = """Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,HTHG,HTAG,HS,AS,HST,AST,HC,AC,HY,AY,HR,AR,MaxCH,MaxCD,MaxCA,MaxC>2.5,MaxC<2.5
E0,16/08/2025,12:30,Liverpool,Bournemouth,4,2,1,0,19,10,10,3,6,3,1,2,0,0,1.45,5.20,7.40,1.70,2.30
E0,not-a-date,,Broken,Row,1,0,,,,,,,,,,,,,,,,,
"""

CATALOGUE_CSV = """Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,HTHG,HTAG,HS,AS,HST,AST,HC,AC,HY,AY,HR,AR,MaxCH,MaxCD,MaxCA,AvgCH,AvgCD,AvgCA,MaxC>2.5,MaxC<2.5,AvgC>2.5,AvgC<2.5,AHh,MaxAHH,MaxAHA,AvgAHH,AvgAHA
E0,16/08/2026,12:30,Liverpool,Bournemouth,2,1,1,0,19,10,10,3,6,3,1,2,0,0,1.45,5.20,7.40,1.40,5.00,7.10,1.70,2.30,1.65,2.20,-1.0,1.95,2.02,1.90,1.98
E0,23/08/2026,15:00,Arsenal,Chelsea,,,,,,,,,,,,,,,1.80,4.00,4.50,1.75,3.90,4.30,1.90,2.00,1.85,1.95,-0.5,1.93,2.01,1.88,1.96
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


def test_parser_normalizes_market_odds_without_generating_fixture_ids():
    observations, rejected = parse_csv(CATALOGUE_CSV, season=2026)

    assert rejected == 1  # Upcoming rows are not training observations.
    assert len(observations) == 1
    odds = observations[0].raw_payload["_normalized_odds"]
    assert odds["match_winner"]["closing_average"]["home"] == 1.4
    assert odds["asian_handicap"]["line"] == -1.0


def test_season_code_round_trip():
    assert season_code(2012) == "1213"
    assert season_code(2026) == "2627"
    assert season_start("1213") == 2012


@respx.mock
def test_csv_provider_uses_archive_url_and_normalizes_both_outputs():
    route = respx.get("https://www.football-data.co.uk/mmz4281/2627/E0.csv").mock(
        return_value=httpx.Response(200, text=CATALOGUE_CSV)
    )
    with httpx.Client() as client:
        document = FootballDataCsvProvider(client).fetch(
            season_code="2627", division="E0"
        )

    assert route.called
    assert len(document.observations) == 1
    assert document.rejected == 1
