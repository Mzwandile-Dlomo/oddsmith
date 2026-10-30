import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from oddsmith.db import MatchObservation, MatchRead
from oddsmith.insights import build_insights
from oddsmith.match_read import ReadDraft, get_match_read
from oddsmith.research import MIN_SAMPLE, final_score, rank_angles, research_card

KICKOFF = datetime(2026, 10, 31, 19, 45, tzinfo=UTC)


def _row(days_before, home, away, hg, ag):
    return MatchObservation(
        source_key=f"test:{home}:{away}:{days_before}",
        source="football_data",
        league="SerieA",
        season=2026,
        kickoff_utc=KICKOFF - timedelta(days=days_before),
        home_team=home,
        away_team=away,
        home_goals=hg,
        away_goals=ag,
        home_corners=5,
        away_corners=4,
        raw_payload={},
    )


def _insights(rows, home="Parma", away="Udinese"):
    return build_insights(
        fixture_id="fx:1", home_team=home, away_team=away, kickoff_utc=KICKOFF, rows=rows
    )


# Parma's last five all finish 2-1 (3 goals); Udinese's all 1-0 (1 goal).
FIVE_EACH = [_row(7 * i + 1, "Parma", f"Opp{i}", 2, 1) for i in range(5)] + [
    _row(7 * i + 2, "Udinese", f"Rival{i}", 1, 0) for i in range(5)
]


def test_angles_are_graded_from_both_sides_recent_matches():
    angles = rank_angles(_insights(FIVE_EACH))
    by_key = {a.key: a for a in angles}

    # Under 3.5: all ten matches landed it.
    assert angles[0].key == "goals_under_3.5"
    assert (angles[0].hits, angles[0].sample, angles[0].strength) == (10, 10, "Strong")
    assert angles[0].headline == "Under 3.5 goals — Strong (10/10)"
    # Over 1.5 only landed in Parma's five; a 5/10 split is graded Weak.
    over = by_key.get("goals_over_1.5")
    assert over is None or (over.home_hits, over.away_hits, over.strength) == (5, 0, "Weak")


def test_lines_with_too_few_recorded_matches_are_not_graded():
    rows = [_row(1, "Parma", "Opp", 2, 1), _row(2, "Udinese", "Rival", 1, 0)]
    assert MIN_SAMPLE > 2
    assert rank_angles(_insights(rows)) == []


def test_research_card_summarises_form_and_top_angles():
    card = research_card(
        fixture_id="fx:1", league="Serie A", kickoff_utc=KICKOFF, priced=False,
        insights=_insights(FIVE_EACH),
    )
    assert card.home_form == ["W"] * 5
    assert card.away_form == ["W"] * 5
    assert card.home_avg_total_goals == 3.0
    assert len(card.angles) == 2
    assert card.has_history is True


def test_unknown_club_has_no_history_rather_than_a_guess():
    card = research_card(
        fixture_id="fx:1", league="Serie A", kickoff_utc=KICKOFF, priced=False,
        insights=_insights(FIVE_EACH, home="Inter Miami"),
    )
    assert card.has_history is False
    assert card.home_form == []


def test_played_fixture_carries_its_score_without_it_entering_form():
    rows = [*FIVE_EACH, _row(0, "Parma", "Udinese", 3, 1)]
    score = final_score(rows, home_team="Parma", away_team="Udinese", kickoff_utc=KICKOFF)
    card = research_card(
        fixture_id="fx:1", league="Serie A", kickoff_utc=KICKOFF, priced=False,
        insights=_insights(rows), score=score,
    )
    assert (card.home_score, card.away_score) == (3, 1)
    assert card.home_form == ["W"] * 5  # the result itself is not pre-match form


def test_score_needs_the_same_orientation_and_a_nearby_kickoff():
    reverse = _row(0, "Udinese", "Parma", 0, 2)
    earlier = _row(60, "Parma", "Udinese", 1, 1)
    shifted = _row(0, "Parma", "Udinese", 2, 2)
    shifted.kickoff_utc = KICKOFF + timedelta(hours=3)
    args = dict(home_team="Parma", away_team="Udinese", kickoff_utc=KICKOFF)
    assert final_score([reverse, earlier], **args) is None
    assert final_score([shifted], **args) == (2, 2)
    assert research_card(
        fixture_id="fx:1", league="Serie A", kickoff_utc=KICKOFF, priced=False,
        insights=_insights(FIVE_EACH),
    ).home_score is None


# --------------------------------------------------------------------------- #
# Written read: Claude may only choose among computed angles.
# --------------------------------------------------------------------------- #


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


class _FakeClaude:
    def __init__(self, draft, stop_reason="end_turn"):
        self.calls = []
        self._response = SimpleNamespace(
            parsed_output=draft, stop_reason=stop_reason, model="claude-opus-5-5"
        )
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._parse))

    async def _parse(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


def _read(session, client, api_key="test-key"):
    return asyncio.run(
        get_match_read(
            session,
            fixture_id="fx:1",
            league="Serie A",
            kickoff_utc=KICKOFF,
            insights=_insights(FIVE_EACH),
            api_key=api_key,
            model="claude-opus-5-5",
            client=client,
        )
    )


def test_without_a_key_the_computed_angles_still_come_back(session):
    view = _read(session, client=None, api_key=None)
    assert view.status == "no_key"
    assert view.headline == "Under 3.5 goals — Strong (10/10)"
    assert view.angles and "ANTHROPIC_API_KEY" in view.message


def test_read_is_written_once_and_served_from_cache(session):
    claude = _FakeClaude(ReadDraft(angle_key="goals_under_3.5", summary="S.", match_read="R."))
    first = _read(session, claude)
    second = _read(session, claude)

    assert first.status == second.status == "ok"
    assert first.headline == "Under 3.5 goals — Strong (10/10)"
    assert len(claude.calls) == 1
    call = claude.calls[0]
    assert call["fallbacks"] == "default"
    assert call["betas"] == ["server-side-fallback-2026-07-01"]
    assert call["output_format"] is ReadDraft


def test_an_angle_the_app_did_not_offer_never_reaches_the_page(session):
    claude = _FakeClaude(ReadDraft(angle_key="home_win_easy", summary="S.", match_read="R."))
    view = _read(session, claude)
    assert view.angle_key == "goals_under_3.5"
    assert view.headline == "Under 3.5 goals — Strong (10/10)"


def test_a_refusal_is_reported_and_not_cached(session):
    claude = _FakeClaude(None, stop_reason="refusal")
    view = _read(session, claude)
    assert view.status == "error"
    assert view.angles
    assert session.exec(select(MatchRead)).first() is None


def test_midnight_utc_from_the_schedule_feed_means_time_not_announced():
    from oddsmith.research import kickoff_time_known

    midnight = datetime(2026, 10, 30, 0, 0, tzinfo=UTC)
    assert kickoff_time_known("fixture_download", midnight) is False
    assert kickoff_time_known("fixture_download", midnight.replace(hour=18, minute=30)) is True
    # Ligue 1 placeholders sit at Paris midnight: 23:00 UTC in winter, 22:00 in summer.
    assert kickoff_time_known("fixture_download", midnight.replace(hour=23)) is False
    assert kickoff_time_known("fixture_download", midnight.replace(hour=22)) is False
    assert kickoff_time_known("fixture_download", midnight.replace(hour=20)) is True
    # Another source's midnight kickoff (e.g. an MLS night game) is taken at face value.
    assert kickoff_time_known("the_odds_api", midnight) is True
