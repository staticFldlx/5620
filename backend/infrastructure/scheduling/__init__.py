"""Pure time helpers for NFR-03 conflict checks. No Django imports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


@dataclass(frozen=True)
class WeeklyWindow:
    day: str
    start: time
    end: time


def parse_hhmm(value: str) -> time:
    hours, minutes = value.strip().split(":")[:2]
    return time(int(hours), int(minutes))


def normalise_day(value: str) -> str:
    day = value.strip()[:3].title()
    if day not in WEEKDAYS:
        raise ValueError(f"unknown weekday: {value}")
    return day


def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and b_start < a_end


def fits_weekly_window(starts_at: datetime, ends_at: datetime, windows: list[WeeklyWindow], tz: str) -> bool:
    """True if [starts_at, ends_at) lies inside one weekly window, evaluated in the teacher's time zone."""
    zone = ZoneInfo(tz or "UTC")
    start, end = starts_at.astimezone(zone), ends_at.astimezone(zone)
    if start.date() != end.date():
        return False
    day = WEEKDAYS[start.weekday()]
    return any(w.day == day and w.start <= start.time() and end.time() <= w.end for w in windows)
