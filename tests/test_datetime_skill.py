"""
Self-audit: the time/date intent answers locally, kid-friendly, deterministic.

Run:  venv/Scripts/python.exe tests/test_datetime_skill.py
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from maxi.skills.datetime_intent import maybe_answer_datetime  # noqa: E402

PASS = 0
FAIL = 0


def check(label, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label}")


WAT = timezone(timedelta(hours=1))
afternoon = datetime(2026, 7, 27, 15, 5, tzinfo=WAT)   # Monday
morning = datetime(2026, 7, 27, 9, 0, tzinfo=WAT)
night = datetime(2026, 7, 27, 22, 30, tzinfo=WAT)

print("time questions:")
check("'what time is it' → time", "3:05 in the afternoon" in maybe_answer_datetime("Maxi, what time is it?", afternoon))
check("o'clock phrasing at :00", "9 o'clock in the morning" in maybe_answer_datetime("what's the time", morning))
check("night part-of-day", "at night" in maybe_answer_datetime("tell me the time", night))

print("\ndate questions:")
ans = maybe_answer_datetime("what day is it today?", afternoon)
check("'what day is it' → date", ans is not None and "Monday" in ans)
check("date includes ordinal day", "27th of July" in ans)
check("date includes year", "2026" in ans)
check("'what's the date' works", "Monday" in (maybe_answer_datetime("what is the date?", afternoon) or ""))

print("\nnon-matches (fall through to normal chat):")
check("'once upon a time' is NOT time intent", maybe_answer_datetime("tell me a story about a time long ago", afternoon) is None)
check("'what is 2 plus 2' → None", maybe_answer_datetime("what is 2 plus 2", afternoon) is None)
check("empty → None", maybe_answer_datetime("", afternoon) is None)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
