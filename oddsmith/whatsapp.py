"""Send a Strong slip to the user's own WhatsApp.

The text mirrors the Picks page's Share button (``web/src/lib/share.ts``), so
an automatic message reads the same as one sent by hand. Kickoffs are in the
local zone: the job runs on a UTC server, but the reader is in SAST.

CallMeBot relays to the number that activated the API key and no one else.
That is enough for a daily "here are today's picks" message and needs no Meta
business account or template approval, whose policy restricts gambling
content anyway. Sending to friends or groups would need another provider.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import httpx

from oddsmith.config import Settings, get_settings
from oddsmith.localdays import local_tz
from oddsmith.strong_slip import StrongLeg, StrongSlip

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
    if client is None:
        with httpx.Client(timeout=settings.http_timeout_seconds) as owned:
            response = owned.get(CALLMEBOT_URL, params=params)
    else:
        response = client.get(CALLMEBOT_URL, params=params)
    response.raise_for_status()
    # The reply is a small HTML page saying whether the message was queued.
    return " ".join(re.sub(r"<[^>]+>", " ", response.text).split())
