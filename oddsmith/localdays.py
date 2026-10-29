"""The user's calendar day, as opposed to the UTC instants everything stores.

Timestamps stay naive UTC in the DB and the API. Only "which day is this?"
questions (the daily paper ticket, the Today window, the calendar grid) use
the configured local zone, so a 23:30 UTC kickoff, 01:30 SAST, belongs to the
day it is played on for the user rather than to the previous UTC date.
Provider quota is the exception: the providers reset on UTC days.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from functools import lru_cache
from zoneinfo import ZoneInfo

from oddsmith.config import get_settings


@lru_cache
def local_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().local_timezone)


def local_date(moment: datetime) -> date:
    """The local calendar date of an instant; a naive value is UTC."""
    aware = moment if moment.tzinfo else moment.replace(tzinfo=UTC)
    return aware.astimezone(local_tz()).date()


def local_today() -> date:
    return datetime.now(local_tz()).date()


def local_day_bounds(day: date) -> tuple[datetime, datetime]:
    """The first and last instant of a local day, as aware UTC datetimes."""
    tz = local_tz()
    return (
        datetime.combine(day, time.min, tzinfo=tz).astimezone(UTC),
        datetime.combine(day, time.max, tzinfo=tz).astimezone(UTC),
    )
