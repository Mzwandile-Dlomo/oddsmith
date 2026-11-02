"""Send today's and tomorrow's Strong slip to the user's Telegram and/or WhatsApp.

Builds the same slip as the Picks page's Strong tab on its "2 days" window
with the tab's default target (2.00) and leg cap (5). Prints the message and
stops there unless ``--send`` is passed, so a run by hand previews first.
``--find-telegram-chat`` prints the chat id to put in ``TELEGRAM_CHAT_ID``.
"""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path

from sqlmodel import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oddsmith.api import strong_acca
from oddsmith.db import get_engine, init_db
from oddsmith.localdays import local_today
from oddsmith.notify import format_strong_slip, send_picks, telegram_chat_ids
from oddsmith.strong_slip import DEFAULT_MIN_LEG_ODDS


def _find_telegram_chat() -> int:
    chats = telegram_chat_ids()
    if not chats:
        print("No messages yet. Send /start to your bot in Telegram, then run this again.")
        return 1
    for chat_id, name in chats:
        print(f"TELEGRAM_CHAT_ID={chat_id}   # {name}")
    return 0


def _run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--send", action="store_true", help="deliver it, not just print it")
    parser.add_argument(
        "--find-telegram-chat",
        action="store_true",
        help="print the chat ids that have messaged your bot, then stop",
    )
    args = parser.parse_args(argv)
    if args.find_telegram_chat:
        return _find_telegram_chat()

    init_db()
    today = local_today()
    with Session(get_engine()) as session:
        slip = strong_acca(
            date_from=today,
            date_to=today + timedelta(days=1),
            target_odds=2.0,
            max_legs=5,
            min_leg_odds=DEFAULT_MIN_LEG_ODDS,
            session=session,
        )
    text = format_strong_slip(slip)
    print(text)
    print()
    if not args.send:
        print("Dry run: add --send to deliver it.")
        return 0
    for channel, receipt in send_picks(text).items():
        print(f"{channel}: {receipt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_run())
