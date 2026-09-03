import httpx
import respx
from sqlmodel import Session, SQLModel, create_engine, select

from oddsmith.data.schedules import upsert_scheduled_fixtures
from oddsmith.db import ScheduledFixture
from oddsmith.providers.fixture_download import BY_KEY, FixtureDownloadProvider


PAYLOAD = [
    {
        "MatchNumber": 27,
        "RoundNumber": 3,
        "DateUtc": "2026-09-04 19:00:00Z",
        "Location": "Portman Road",
        "HomeTeam": "Ipswich",
        "AwayTeam": "Liverpool",
        "Group": None,
        "HomeTeamScore": None,
        "AwayTeamScore": None,
        "Winner": "",
    }
]


@respx.mock
def test_fixture_download_provider_preserves_source_match_number():
    route = respx.get("https://fixturedownload.com/feed/json/epl-2026").mock(
        return_value=httpx.Response(200, json=PAYLOAD)
    )
    with httpx.Client() as client:
        fixtures = FixtureDownloadProvider(client).fetch(BY_KEY["epl"], 2026)

    assert route.called
    assert len(fixtures) == 1
    assert fixtures[0].source_key == "fixture_download:epl:2026:27"
    assert fixtures[0].match_number == 27
    assert fixtures[0].home_goals is None


def test_schedule_upsert_is_idempotent():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=PAYLOAD))) as client:
        fixtures = FixtureDownloadProvider(client).fetch(BY_KEY["epl"], 2026)

    with Session(engine) as session:
        first = upsert_scheduled_fixtures(session, fixtures)
        second = upsert_scheduled_fixtures(session, fixtures)
        stored = list(session.exec(select(ScheduledFixture)))

    assert first == (1, 0)
    assert second == (0, 1)
    assert len(stored) == 1
