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
    "-": ["minus", "subtract", "take away", "takeaway", "less", "difference"],
    "*": ["times", "multiply", "multiplied by", "product of"],
    "/": ["divided by", "divide", "over", "shared"],
}
# Symbols the browser speech engine may produce (e.g. "2 + 2", "3 × 4").
_OP_SYMBOLS = {"+": "+", "-": "-", "×": "*", "*": "*", "x": "*", "÷": "/", "/": "/"}
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
    # Words first (so "six" isn't mistaken for the "x" times-symbol).
    for op, words in _OP_WORDS.items():
        if any(w in low for w in words):
            return op
    padded = f" {low} "
    for sym, op in _OP_SYMBOLS.items():
        if sym == "x":
            if " x " in padded:  # standalone x only, not inside a word
                return op
        elif sym in low:
            return op
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
        """Teach the sum: show it on screen, count it on the fingers if it fits."""
        result_int = int(s.result) if float(s.result).is_integer() else None
        result_str = str(result_int) if result_int is not None else str(s.result)

        # Answers 0-10 count out on the 10 fingers; bigger answers show in the UI.
        is_finger = result_int is not None and 0 <= result_int <= 10
        can_count = is_finger and 0 <= s.a <= 10 and 0 <= s.b <= 10
        explanation = self._explain(s, result_str)
        mode = "finger_counting" if is_finger else "advanced"

        # Drive the UI: equation display + (finger mode) animated hands.
        await ctx.emit(events.math_result(
            s.a, s.b, s.op,
            result_int if result_int is not None else s.result,
            explanation, mode,
        ))

        word = _OP_SPOKEN[s.op]
        await ctx.speaker.say(f"Let's work out {s.a} {word} {s.b}.")

        hands = ctx.hands
        if can_count and hands:
            await hands.show_number(s.a, "right")
            await ctx.speaker.say(f"We start with {s.a}.")
            if s.op == "+":
                await ctx.speaker.say(f"Then we add {s.b} more.")
            elif s.op == "-":
                await ctx.speaker.say(f"Then we take {s.b} away.")
            elif s.op == "*":
                await ctx.speaker.say(f"That's {s.a}, {s.b} times.")
            await hands.show_number(result_int, "right")
        elif is_finger and hands:
            await hands.show_number(result_int, "right")

        await ctx.speaker.say(f"The answer is {result_str}!")
        if explanation:
            await ctx.speaker.say(explanation)

        await ctx.memory.add_user(ctx.text)
        await ctx.memory.add_assistant(f"{s.a} {word} {s.b} equals {result_str}")

        if hands:
            await hands.close_all()

    def _explain(self, s: Solved, result_str: str) -> str:
        a, b = s.a, s.b
        if s.op == "+":
            return f"When we put {a} and {b} together, we count all the way up to {result_str}."
        if s.op == "-":
            return f"Starting at {a} and taking {b} away leaves {result_str}."
        if s.op == "*":
            return f"{b} groups of {a} make {result_str} altogether."
        if s.op == "/":
            return f"Sharing {a} into {b} equal parts gives {result_str} in each part."
        return ""

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
