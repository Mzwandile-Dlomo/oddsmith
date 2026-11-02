from datetime import UTC, datetime

import httpx
import pytest
import respx

from oddsmith.config import Settings
from oddsmith.models import MarketType
from oddsmith.strong_slip import StrongLeg, StrongSlip
from oddsmith.whatsapp import CALLMEBOT_URL, format_strong_slip, send_whatsapp

# 19:45 UTC is 21:45 SAST.
KICKOFF = datetime(2026, 10, 31, 19, 45, tzinfo=UTC)
NOW = datetime(2026, 10, 31, 7, 30, tzinfo=UTC)


def _leg(home, away, odds, label="Over 1.5 goals"):
    return StrongLeg(
        fixture_id=f"fx:{home}",
        home_team=home,
        away_team=away,
        kickoff_utc=KICKOFF,
        league="Serie A - Italy",
        provider="the_odds_api",
        market_type=MarketType.OVER_UNDER,
        selection="Over",
        point=1.5,
        label=label,
        offered_odds=odds,
        hits=9,
        sample=10,
        h2h_hits=0,
        h2h_sample=0,
        support=0.6,
        book_implied_prob=None,
        model_prob=None,
    )


def _slip(legs=(), unpriced=(), note="No priced fixtures still to kick off in this window."):
    return StrongSlip(
        legs=list(legs),
        alternatives=[],
        unpriced=list(unpriced),
        combined_odds=0.0,
        target_odds=2.0,
        target_met=False,
        combined_book_prob=None,
        combined_model_prob=None,
        fixtures_scanned=0,
        priced_fixtures=0,
        note=note,
    )


def test_slip_lists_legs_in_local_time_with_combined_odds():
    text = format_strong_slip(
        _slip(legs=[_leg("Parma", "Udinese", 1.32), _leg("Lecce", "Como", 1.5)]), now=NOW
    )

    assert text.startswith("*Oddsmith · Strong slip* · 2 legs")
    assert "1. Parma vs Udinese" in text
    assert "   Sat 31 Oct, 21:45 · Serie A - Italy" in text
    assert "   ➜ *Over 1.5 goals* @ 1.32" in text
    assert "*Combined odds: 1.98*" in text
    assert text.endswith("_Prices as of 31 Oct, 09:30; they move. Every leg has to land._")


def test_no_slip_falls_back_to_unpriced_picks():
    text = format_strong_slip(_slip(unpriced=[_leg("Parma", "Udinese", None)]), now=NOW)

    assert text.startswith("*Oddsmith · Strong picks* · 1 leg\n")
    assert "➜ *Over 1.5 goals* (check price)" in text
    assert "No prices collected yet." in text
    assert "Prices as of" not in text


def test_empty_day_still_says_why():
    text = format_strong_slip(_slip(note="Nothing today."), now=NOW)

    assert text == "*Oddsmith · Strong picks*\n\nNothing today."


@respx.mock
def test_send_passes_phone_key_and_text():
    route = respx.get(CALLMEBOT_URL).mock(
        return_value=httpx.Response(200, text="<p>Message queued.</p>")
    )
    settings = Settings(whatsapp_phone="+27820000000", callmebot_api_key="123456")

    reply = send_whatsapp("*hi*\nthere", settings=settings)

    params = route.calls.last.request.url.params
    assert params["phone"] == "+27820000000"
    assert params["apikey"] == "123456"
    assert params["text"] == "*hi*\nthere"
    assert reply == "Message queued."


@respx.mock
def test_send_raises_on_http_error():
    respx.get(CALLMEBOT_URL).mock(return_value=httpx.Response(500))
    settings = Settings(whatsapp_phone="+27820000000", callmebot_api_key="123456")

    with pytest.raises(httpx.HTTPStatusError):
        send_whatsapp("hi", settings=settings)


def test_send_without_config_names_the_missing_settings():
    with pytest.raises(RuntimeError, match="WHATSAPP_PHONE and CALLMEBOT_API_KEY"):
        send_whatsapp("hi", settings=Settings(whatsapp_phone=None, callmebot_api_key=None))
