"""
maxi.skills.datetime_intent — answer "what time / what day is it?" LOCALLY.

The LLM cannot know the real wall clock (and Railway runs in UTC), so time/date
questions are answered here with the actual local time — kid-friendly, in words a
young child understands. Wired into ChatSkill *before* the LLM call.

Pure + deterministic: ``maybe_answer_datetime(text, now=...)`` takes an optional
``now`` so it's unit-testable without depending on the real clock.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from maxi.config import settings

# "what" possibly followed by "'s" / "s" / " is".
_WHAT = r"what(?:'s|s| is)?"
# "what time is it", "what's the time", "tell me the time", "current time"…
_TIME_RE = re.compile(
    rf"\b({_WHAT}\s+the\s+time|what\s+time\s+is\s+it|what\s+time\b|tell\s+me\s+the\s+time"
    r"|current\s+time|the\s+time\s+now|time\s+is\s+it)\b",
    re.I,
)
# "what day is it", "what's the date", "today's date", "what month/year"…
_DATE_RE = re.compile(
    rf"\b({_WHAT}\s+(?:the\s+|today'?s\s+)?date|today'?s\s+date|what\s+day\s+is\s+(?:it|today)"
    rf"|{_WHAT}\s+today|which\s+day\s+is\s+it|what\s+month\s+is\s+it|what\s+year\s+is\s+it"
    rf"|{_WHAT}\s+the\s+day)\b",
    re.I,
)


def local_now() -> datetime:
    """Current time at the child's location (UTC + configured offset)."""
    return datetime.now(timezone(timedelta(hours=settings.tz_offset_hours)))


def _part_of_day(hour: int) -> str:
    if 5 <= hour < 12:
        return "in the morning"
    if 12 <= hour < 17:
        return "in the afternoon"
    if 17 <= hour < 21:
        return "in the evening"
    return "at night"


def _ordinal(day: int) -> str:
    if 11 <= day % 100 <= 13:
        return f"{day}th"
    return f"{day}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th') }"


def time_phrase(now: datetime) -> str:
    hour12 = now.hour % 12 or 12
    part = _part_of_day(now.hour)
    if now.minute == 0:
        return f"It's {hour12} o'clock {part}!"
    return f"Right now it's {hour12}:{now.minute:02d} {part}!"


def date_phrase(now: datetime) -> str:
    return now.strftime(f"Today is %A, the {_ordinal(now.day)} of %B, %Y.")


def maybe_answer_datetime(text: str, now: Optional[datetime] = None) -> Optional[str]:
    """Return a kid-friendly spoken answer for a time/date question, else None."""
    if not text:
        return None
    if now is None:
        now = local_now()
    if _TIME_RE.search(text):
        return time_phrase(now)
    if _DATE_RE.search(text):
        return date_phrase(now)
    return None
