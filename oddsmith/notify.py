"""Send a Strong slip to the user's own Telegram and/or WhatsApp.

The text mirrors the Picks page's Share button (``web/src/lib/share.ts``), so
an automatic message reads the same as one sent by hand. Kickoffs are in the
local zone: the job runs on a UTC server, but the reader is in SAST.

Each channel sends only when its settings are filled in:

- Telegram: a bot from @BotFather messaging the user's chat with it. Official,
  free, and its legacy Markdown reads WhatsApp's ``*bold*``/``_italic_`` as is.
- WhatsApp via CallMeBot: relays to the number that activated the API key and
  no one else. No Meta business account or template approval, whose policy
  restricts gambling content anyway, but its free signups are sometimes full.

Errors quote what the service said, never the request URL, which carries the
bot token or API key.
"""

from __future__ import annotations

import re
from contextlib import nullcontext
from datetime import UTC, datetime

import httpx

from oddsmith.config import Settings, get_settings
from oddsmith.localdays import local_tz
from oddsmith.strong_slip import StrongLeg, StrongSlip

TELEGRAM_API = "https://api.telegram.org"
CALLMEBOT_URL = "https://api.callmebot.com/whatsapp.php"
# The slip is capped at its leg count; this caps the unpriced fallback list.
MAX_UNPRICED_LEGS = 5


def _local(moment: datetime) -> datetime:
    aware = moment if moment.tzinfo else moment.replace(tzinfo=UTC)
    return aware.astimezone(local_tz())


def _kickoff(moment: datetime) -> str:
    local = _local(moment)
    return f"{local:%a} {local.day} {local:%b}, {local:%H:%M}"


def _legs_text(title: str, legs: list[StrongLeg], now: datetime) -> str:
    lines = [f"*{title}* · {len(legs)} leg{'' if len(legs) == 1 else 's'}", ""]
    for i, leg in enumerate(legs, start=1):
        lines.append(f"{i}. {leg.home_team} vs {leg.away_team}")
        when = " · ".join(part for part in (_kickoff(leg.kickoff_utc), leg.league) if part)
        lines.append(f"   {when}")
        price = f"@ {leg.offered_odds:.2f}" if leg.offered_odds is not None else "(check price)"
        lines.append(f"   ➜ *{leg.label}* {price}")
        lines.append("")

    prices = [leg.offered_odds for leg in legs]
    if all(p is not None for p in prices):
        combined = 1.0
        for p in prices:
            combined *= p
        lines.append(f"*Combined odds: {combined:.2f}*")
    elif all(p is None for p in prices):
        lines.append("No prices collected yet. Check each one at your bookmaker.")
    else:
        lines.append("Some legs have no price yet. Check them at your bookmaker.")

    local_now = _local(now)
    read_at = f"{local_now.day} {local_now:%b}, {local_now:%H:%M}"
    as_of = f"Prices as of {read_at}; they move. " if any(p is not None for p in prices) else ""
    lines.append(f"_{as_of}Every leg has to land._")
    return "\n".join(lines)


def format_strong_slip(slip: StrongSlip, *, now: datetime | None = None) -> str:
    """The slip if there is one, else the unpriced Strong picks, else why there's neither.

    A quiet day still sends a message, so a missing one means the job didn't run.
    """
    now = now or datetime.now(UTC)
    if slip.legs:
        return _legs_text("Oddsmith · Strong slip", slip.legs, now)
    if slip.unpriced:
        return _legs_text("Oddsmith · Strong picks", slip.unpriced[:MAX_UNPRICED_LEGS], now)
    return f"*Oddsmith · Strong picks*\n\n{slip.note}"


def _http(settings: Settings, client: httpx.Client | None):
    return nullcontext(client) if client else httpx.Client(timeout=settings.http_timeout_seconds)


def _telegram_error(response: httpx.Response) -> str:
    try:
        return response.json().get("description", response.reason_phrase)
    except ValueError:
        return f"HTTP {response.status_code}"


def send_telegram(
    text: str,
    *,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
) -> str:
    """Send ``text`` to ``TELEGRAM_CHAT_ID`` and return a one-line receipt."""
    settings = settings or get_settings()
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        raise RuntimeError(
            "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to send Telegram messages "
            "(see .env.example)."
        )
    url = f"{TELEGRAM_API}/bot{settings.telegram_bot_token}/sendMessage"
    body = {"chat_id": settings.telegram_chat_id, "text": text}
    with _http(settings, client) as http:
        response = http.post(url, json={**body, "parse_mode": "Markdown"})
        # Legacy Markdown rejects an unpaired * or _, say in a team name. Plain
        # asterisks beat no message at all.
        if response.status_code == 400 and "parse entities" in _telegram_error(response):
            response = http.post(url, json=body)
    if not response.is_success:
        raise RuntimeError(f"Telegram refused the message: {_telegram_error(response)}")
    return f"sent (message {response.json()['result']['message_id']})"


def telegram_chat_ids(
    *,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
) -> list[tuple[int, str]]:
    """``(chat id, name)`` for each chat that has messaged the bot lately.

    A bot can't message anyone first, so the user sends it /start and reads
    their chat id from here.
    """
    settings = settings or get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN first (see .env.example).")
    with _http(settings, client) as http:
        response = http.get(f"{TELEGRAM_API}/bot{settings.telegram_bot_token}/getUpdates")
    if not response.is_success:
        raise RuntimeError(f"Telegram refused the lookup: {_telegram_error(response)}")
    chats: dict[int, str] = {}
    for update in response.json()["result"]:
        chat = (update.get("message") or {}).get("chat")
        if chat:
            name = chat.get("username") or chat.get("first_name") or chat.get("title") or ""
            chats[chat["id"]] = name
    return list(chats.items())


def send_whatsapp(
    text: str,
    *,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
) -> str:
    """Send ``text`` to ``WHATSAPP_PHONE`` and return CallMeBot's reply, tags stripped."""
    settings = settings or get_settings()
    if not settings.whatsapp_phone or not settings.callmebot_api_key:
        raise RuntimeError(
            "Set WHATSAPP_PHONE and CALLMEBOT_API_KEY to send WhatsApp messages (see .env.example)."
        )
    params = {
        "phone": settings.whatsapp_phone,
        "text": text,
        "apikey": settings.callmebot_api_key,
    }
    with _http(settings, client) as http:
        response = http.get(CALLMEBOT_URL, params=params)
    # The reply is a small HTML page saying whether the message was queued.
    reply = " ".join(re.sub(r"<[^>]+>", " ", response.text).split())
    if not response.is_success:
        raise RuntimeError(f"CallMeBot answered HTTP {response.status_code}: {reply[:200]}")
    return reply


def send_picks(
    text: str,
    *,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
) -> dict[str, str]:
    """Send ``text`` on every configured channel; ``{channel: receipt}``.

    Every channel is tried before any failure is raised, so a broken WhatsApp
    key doesn't stop the Telegram message.
    """
    settings = settings or get_settings()
    channels = []
    if settings.telegram_bot_token or settings.telegram_chat_id:
        channels.append(("Telegram", send_telegram))
    if settings.whatsapp_phone or settings.callmebot_api_key:
        channels.append(("WhatsApp", send_whatsapp))
    if not channels:
        raise RuntimeError(
            "No channel configured: set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID, "
            "or WHATSAPP_PHONE and CALLMEBOT_API_KEY (see .env.example)."
        )

    receipts: dict[str, str] = {}
    failures: list[str] = []
    for name, send in channels:
        try:
            receipts[name] = send(text, settings=settings, client=client)
        except RuntimeError as exc:
            failures.append(f"{name}: {exc}")
    if failures:
        raise RuntimeError(
            "; ".join(failures) + (f" (sent: {', '.join(receipts)})" if receipts else "")
        )
    return receipts
