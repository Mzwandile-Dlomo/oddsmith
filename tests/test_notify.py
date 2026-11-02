import json
from datetime import UTC, datetime

import httpx
import pytest
import respx

from oddsmith.config import Settings
from oddsmith.models import MarketType
from oddsmith.strong_slip import StrongLeg, StrongSlip
from oddsmith.notify import (
    CALLMEBOT_URL,
    TELEGRAM_API,
    format_strong_slip,
    send_picks,
    send_telegram,
    send_whatsapp,
    telegram_chat_ids,
)

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
def test_whatsapp_passes_phone_key_and_text():
    route = respx.get(CALLMEBOT_URL).mock(
        return_value=httpx.Response(200, text="<p>Message queued.</p>")
    )
    settings = _settings(whatsapp_phone="+27820000000", callmebot_api_key="123456")

    reply = send_whatsapp("*hi*\nthere", settings=settings)

    params = route.calls.last.request.url.params
    assert params["phone"] == "+27820000000"
    assert params["apikey"] == "123456"
    assert params["text"] == "*hi*\nthere"
    assert reply == "Message queued."


@respx.mock
def test_whatsapp_error_quotes_the_reply_not_the_key():
    respx.get(CALLMEBOT_URL).mock(return_value=httpx.Response(500, text="<p>APIKey is invalid</p>"))
    settings = _settings(whatsapp_phone="+27820000000", callmebot_api_key="123456")

    with pytest.raises(RuntimeError, match="HTTP 500: APIKey is invalid") as raised:
        send_whatsapp("hi", settings=settings)
    assert "123456" not in str(raised.value)


def test_whatsapp_without_config_names_the_missing_settings():
    with pytest.raises(RuntimeError, match="WHATSAPP_PHONE and CALLMEBOT_API_KEY"):
        send_whatsapp("hi", settings=_settings(whatsapp_phone=None, callmebot_api_key=None))


TOKEN = "42:secret"
SEND_URL = f"{TELEGRAM_API}/bot{TOKEN}/sendMessage"


def _settings(**values):
    blank = {
        "telegram_bot_token": None,
        "telegram_chat_id": None,
        "whatsapp_phone": None,
        "callmebot_api_key": None,
    }
    return Settings(**{**blank, **values})


TELEGRAM = {"telegram_bot_token": TOKEN, "telegram_chat_id": "777"}
SENT = httpx.Response(200, json={"ok": True, "result": {"message_id": 9}})


@respx.mock
def test_telegram_sends_markdown_to_the_chat():
    route = respx.post(SEND_URL).mock(return_value=SENT)

    receipt = send_telegram("*hi*", settings=_settings(**TELEGRAM))

    assert json.loads(route.calls.last.request.content) == {
        "chat_id": "777",
        "text": "*hi*",
        "parse_mode": "Markdown",
    }
    assert receipt == "sent (message 9)"


@respx.mock
def test_telegram_resends_plain_when_markdown_does_not_parse():
    unparsable = httpx.Response(
        400,
        json={"ok": False, "description": "Bad Request: can't parse entities: odd *"},
    )
    route = respx.post(SEND_URL).mock(side_effect=[unparsable, SENT])

    send_telegram("Inter_Miami *", settings=_settings(**TELEGRAM))

    assert "parse_mode" not in json.loads(route.calls.last.request.content)
    assert route.call_count == 2


@respx.mock
def test_telegram_error_quotes_telegram_not_the_token():
    respx.post(SEND_URL).mock(
        return_value=httpx.Response(
            403, json={"ok": False, "description": "Forbidden: bot was blocked"}
        )
    )

    with pytest.raises(RuntimeError, match="bot was blocked") as raised:
        send_telegram("hi", settings=_settings(**TELEGRAM))
    assert TOKEN not in str(raised.value)


@respx.mock
def test_chat_ids_come_from_recent_messages():
    respx.get(f"{TELEGRAM_API}/bot{TOKEN}/getUpdates").mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": True,
                "result": [
                    {"message": {"chat": {"id": 777, "username": "mzwandile"}}},
                    {"message": {"chat": {"id": 777, "username": "mzwandile"}}},
                    {"my_chat_member": {}},
                ],
            },
        )
    )

    assert telegram_chat_ids(settings=_settings(**TELEGRAM)) == [(777, "mzwandile")]


@respx.mock
def test_send_picks_uses_only_configured_channels():
    respx.post(SEND_URL).mock(return_value=SENT)
    whatsapp = respx.get(CALLMEBOT_URL)

    assert send_picks("hi", settings=_settings(**TELEGRAM)) == {"Telegram": "sent (message 9)"}
    assert not whatsapp.called


@respx.mock
def test_send_picks_tries_every_channel_before_failing():
    respx.get(CALLMEBOT_URL).mock(return_value=httpx.Response(500, text="down"))
    telegram = respx.post(SEND_URL).mock(return_value=SENT)
    settings = _settings(**TELEGRAM, whatsapp_phone="+27820000000", callmebot_api_key="123456")

    with pytest.raises(RuntimeError, match=r"WhatsApp: .*HTTP 500.*\(sent: Telegram\)"):
        send_picks("hi", settings=settings)
    assert telegram.called


def test_send_picks_with_nothing_configured_says_what_to_set():
    with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID"):
        send_picks("hi", settings=_settings())
