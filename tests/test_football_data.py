import httpx
import respx
from sqlmodel import Session, SQLModel, create_engine, select

from datetime import UTC, date, datetime

from oddsmith.data.football_data import (
    FootballDataCsvProvider,
    import_observations,
    parse_csv,
    parse_extra_csv,
    season_code,
    season_start,
)
from oddsmith.db import HistoricalMatch, MatchObservation
from oddsmith.insights import dedupe


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


EXTRA_CSV = """Country,League,Season,Date,Time,Home,Away,HG,AG,Res,PSCH,PSCD,PSCA,MaxCH,MaxCD,MaxCA
USA,MLS,2025,19/07/2026,00:30,Old Season,Row,1,1,D,,,,,,
USA,MLS,2026,26/10/2026,01:00,Los Angeles FC,Los Angeles Galaxy,2,2,D,2.0,3.6,3.4,2.1,3.8,3.6
USA,MLS,2026,01/11/2026,20:00,Upcoming,Fixture,,,,,,,,,
"""


def test_extra_league_file_maps_short_columns_and_row_seasons():
    observations, rejected = parse_extra_csv(EXTRA_CSV, code="USA")

    assert rejected == 1  # the unplayed fixture
    latest = observations[-1]
    assert (latest.home_team, latest.away_team) == ("Los Angeles FC", "Los Angeles Galaxy")
    assert (latest.home_goals, latest.away_goals) == (2, 2)
    assert latest.league == "MLS"
    assert latest.season == 2026
    assert latest.source_league_code == "USA"
    assert latest.close_home_odds == 2.1


@respx.mock
def test_extra_league_fetch_keeps_only_the_kickoff_window():
    respx.get("https://www.football-data.co.uk/new/USA.csv").mock(
        return_value=httpx.Response(200, text=EXTRA_CSV)
    )
    with httpx.Client() as client:
        document = FootballDataCsvProvider(client).fetch_extra(
            "usa", kickoff_from=date(2026, 8, 1), kickoff_to=date(2027, 7, 31)
        )

    assert [row.home_team for row in document.observations] == ["Los Angeles FC"]


def test_second_tier_divisions_are_supported():
    observations, _ = parse_csv(CSV.replace("E0,", "D2,"), season=2025)

    assert observations[0].league == "Bundesliga2"


def test_kickoff_times_are_uk_local_and_stored_as_utc():
    summer, _ = parse_csv(CSV, season=2025)  # 12:30 BST
    winter, _ = parse_csv(CSV.replace("16/08/2025", "06/12/2025"), season=2025)
    untimed, _ = parse_csv(CSV.replace(",12:30,", ",,"), season=2025)

    assert summer[0].kickoff_utc == datetime(2025, 8, 16, 11, 30, tzinfo=UTC)
    assert winter[0].kickoff_utc == datetime(2025, 12, 6, 12, 30, tzinfo=UTC)
    assert untimed[0].kickoff_utc == datetime(2025, 8, 16, 12, 0, tzinfo=UTC)


def test_late_summer_kickoff_deduplicates_against_api_football():
    document = (
        "Country,League,Season,Date,Time,Home,Away,HG,AG,Res\n"
        "USA,MLS,2026,30/08/2026,00:30,Inter Miami,CF Montreal,2,0,H\n"
    )
    (csv_row,), _ = parse_extra_csv(document, code="USA")
    live_row = MatchObservation(
        source_key="api_football_result:1",
        source="api_football_result",
        league="Major League Soccer",
        season=2026,
        kickoff_utc=datetime(2026, 8, 29, 23, 30, tzinfo=UTC),
        home_team="Inter Miami",
        away_team="CF Montreal",
        home_goals=2,
        away_goals=0,
        raw_payload={},
    )

    assert csv_row.kickoff_utc == live_row.kickoff_utc
    assert len(dedupe([csv_row, live_row])) == 1
