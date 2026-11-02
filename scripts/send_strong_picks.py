"""Send today's and tomorrow's Strong slip to the user's WhatsApp.

Builds the same slip as the Picks page's Strong tab on its "2 days" window
with the tab's default target (2.00) and leg cap (5). Prints the message and
stops there unless ``--send`` is passed, so a run by hand previews first.
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
from oddsmith.strong_slip import DEFAULT_MIN_LEG_ODDS
from oddsmith.whatsapp import format_strong_slip, send_whatsapp


def _run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--send", action="store_true", help="deliver it, not just print it")
    args = parser.parse_args(argv)

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
        print("Dry run: add --send to deliver it to WhatsApp.")
        return 0
    print(f"CallMeBot: {send_whatsapp(text)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_run())
