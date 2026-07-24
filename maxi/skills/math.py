"""
maxi.skills.math — math tutoring with finger counting.

Fast path: recognise simple "A <op> B" arithmetic locally and narrate it while
showing the numbers on Maxi's hands. Fallback: hand word-problems to Groq for a
short, kid-friendly explanation. Everything runs inside the orchestrator's
cancellable task, so a child can barge in on a long explanation.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import List, Optional

from maxi.core import events
from maxi.core.events import Mode
from maxi.persona import MATH_GREETINGS
from maxi.services.safety import Safety
from maxi.skills.base import Skill, SkillContext

logger = logging.getLogger("maxi.skills.math")

_WORD_NUMBERS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
}

_OP_WORDS = {
    "+": ["plus", "add", "added to", "and", "sum of"],
    "-": ["minus", "subtract", "take away", "less", "difference"],
    "*": ["times", "multiply", "multiplied by", "product of"],
    "/": ["divided by", "divide", "over", "shared"],
}
_OP_SPOKEN = {"+": "plus", "-": "minus", "*": "times", "/": "divided by"}


@dataclass
class Solved:
    a: int
    b: int
    op: str
    result: float
    basic: bool  # small whole-number arithmetic we can show on fingers


def _to_number(token: str) -> Optional[int]:
    token = token.strip().lower()
    if token.isdigit():
        return int(token)
    return _WORD_NUMBERS.get(token)


def _extract_numbers(text: str) -> List[int]:
    nums: List[int] = []
    for tok in re.findall(r"[a-z]+|\d+", text.lower()):
        n = _to_number(tok)
        if n is not None:
            nums.append(n)
    return nums


def _detect_op(text: str) -> Optional[str]:
    low = text.lower()
    for op, words in _OP_WORDS.items():
        if any(w in low for w in words):
            return op
    for sym in ("+", "-", "*", "x", "/"):
        if sym in low:
            return "*" if sym == "x" else sym
    return None


def _calc(a: int, op: str, b: int) -> Optional[float]:
    try:
        if op == "+":
            return a + b
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if op == "/":
            return round(a / b, 2) if b else None
    except Exception:  # noqa: BLE001
        return None
    return None


def _quick_solve(text: str) -> Optional[Solved]:
    op = _detect_op(text)
    nums = _extract_numbers(text)
    if op is None or len(nums) < 2:
        return None
    a, b = nums[0], nums[1]
    result = _calc(a, op, b)
    if result is None:
        return None
    basic = op in "+-*/" and float(result).is_integer() and 0 <= result <= 10 and 0 <= a <= 10 and 0 <= b <= 10
    return Solved(a=a, b=b, op=op, result=result, basic=basic)


class MathSkill(Skill):
    name = "math"
    mode = Mode.MATH_GESTURE

    def __init__(self, safety: Safety | None = None) -> None:
        self.safety = safety or Safety()

    async def handle(self, ctx: SkillContext) -> None:
        text = ctx.text.strip()
        if not text:
            import random
            await ctx.speaker.say(random.choice(MATH_GREETINGS))
            return

        allowed, warning = self.safety.rate_limit(ctx.session_id, "math")
        if not allowed:
            await ctx.speaker.say(warning or "Let's take a short break and do more math soon!")
            return
        safe, fallback = self.safety.check_input(text, ctx.session_id)
        if not safe:
            self.safety.log_filter_event(ctx.session_id, text, "unsafe_input")
            await ctx.speaker.say(fallback)
            return
        self.safety.log_question(ctx.session_id, text, "math", "mathematics")

        solved = _quick_solve(text)
        if solved is not None:
            await self._narrate(ctx, solved)
        else:
            await self._llm_solve(ctx, text)

    async def _narrate(self, ctx: SkillContext, s: Solved) -> None:
        """Speak the sum while counting it out on the hands."""
        hands = ctx.hands
        result_str = str(int(s.result)) if float(s.result).is_integer() else str(s.result)

        await ctx.speaker.say(f"Let's count! {s.a} {_OP_SPOKEN[s.op]} {s.b}.")

        if hands and s.basic:
            await hands.show_number(s.a, "right")
            await self._mirror(ctx, hands)
            await ctx.speaker.say(f"We start with {s.a}.")
            if s.op == "+":
                await ctx.speaker.say(f"Now we add {s.b} more.")
            elif s.op == "-":
                await ctx.speaker.say(f"Now we take away {s.b}.")
            await hands.show_number(int(s.result), "right")
            await self._mirror(ctx, hands)

        await ctx.speaker.say(f"The answer is {result_str}!")
        await ctx.memory.add_user(ctx.text)
        await ctx.memory.add_assistant(f"{s.a} {_OP_SPOKEN[s.op]} {s.b} equals {result_str}")

        if hands:
            await hands.close_all()
            await self._mirror(ctx, hands)

    async def _llm_solve(self, ctx: SkillContext, text: str) -> None:
        """Word problems / bigger numbers → short Groq explanation."""
        if not ctx.llm.enabled:
            await ctx.speaker.say("That's a tricky one and my math brain is offline. Try a smaller sum!")
            return
        messages = [
            {"role": "system", "content": (
                "You are Maxi, a fun math teacher for kids 6-12. Solve the problem and "
                "explain it in ONE or TWO very short, simple sentences. End with the final "
                "answer clearly. No emojis."
            )},
            {"role": "user", "content": text},
        ]
        spoken = await ctx.speaker.say_stream(ctx.llm, messages)
        await ctx.memory.add_user(text)
        if spoken:
            await ctx.memory.add_assistant(spoken)

    async def _mirror(self, ctx: SkillContext, hands) -> None:
        """Reflect the current hand pose in the tablet UI."""
        try:
            await ctx.emit(events.finger_pose(hands.pose()))
        except Exception:  # noqa: BLE001
            pass
