"""
maxi.skills.math — math tutoring with finger counting.

Fast path: recognise simple "A <op> B" arithmetic locally and narrate it while
showing the numbers on Maxi's hands. Fallback: hand word-problems to Groq for a
short, kid-friendly explanation. Everything runs inside the orchestrator's
cancellable task, so a child can barge in on a long explanation.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

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
_OP_DISPLAY = {"+": "+", "-": "−", "*": "×", "/": "÷"}  # + − × ÷


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


def _num_str(v: Any) -> str:
    """Render a number without a trailing .0 (e.g. 15.0 -> '15'); pass strings through."""
    try:
        f = float(v)
        return str(int(f)) if f.is_integer() else str(v)
    except (TypeError, ValueError):
        return str(v)


def _quick_solve(text: str) -> Optional[Solved]:
    op = _detect_op(text)
    nums = _extract_numbers(text)
    if op is None or len(nums) != 2:
        return None
    a, b = nums[0], nums[1]
    result = _calc(a, op, b)
    if result is None:
        return None
    basic = op in "+-*/" and float(result).is_integer() and 0 <= result <= 10 and 0 <= a <= 10 and 0 <= b <= 10
    return Solved(a=a, b=b, op=op, result=result, basic=basic)


def _multi_solve(text: str) -> Optional[Dict[str, Any]]:
    """3+ numbers with one operator → left-to-right steps, computed locally."""
    op = _detect_op(text)
    nums = _extract_numbers(text)
    if op is None or len(nums) < 3:
        return None
    word = _OP_SPOKEN[op]
    sym = _OP_DISPLAY[op]
    running = nums[0]
    steps: List[Dict[str, Any]] = []
    for i in range(1, len(nums)):
        b = nums[i]
        prev = running
        running = _calc(prev, op, b)
        if running is None:
            return None
        r = int(running) if float(running).is_integer() else running
        p = int(prev) if float(prev).is_integer() else prev
        steps.append({
            "step": i,
            "operation": f"{p} {sym} {b}",
            "result": r,
            "description": f"{p} {word} {b} makes {r}.",
        })
    result = int(running) if float(running).is_integer() else running
    return {
        "original": " ".join(f"{n}" for n in nums),
        "result": result,
        "steps": steps,
        "breakdown": f"Putting it all together, we get {result}.",
    }


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
            return
        multi = _multi_solve(text)
        if multi is not None:
            await self._walk_steps(
                ctx, multi["original"], multi["result"], multi["steps"], multi["breakdown"],
                intro="Let's add these up one step at a time!",
            )
            return
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

    _JSON_SYSTEM = (
        "You are Maxi, a warm, patient math teacher for children aged 6-12. Solve the "
        "math problem or WORD PROBLEM below. Explain it like you are gently talking a "
        "child through a story: use the SAME real things and actions from the problem "
        "(for example mangoes, a friend, eating, giving) — never say the abstract word "
        "'numbers'. Reply with ONLY a JSON object (no extra text) in EXACTLY this shape:\n"
        '{"original_question": string, '
        '"answer": number or string, '
        '"intro": one short friendly sentence that sets up the story, '
        '"steps": [{"step": integer from 1, "operation": short math like "10 - 2", '
        '"result": number, "description": ONE short sentence in the story\'s own words, '
        'e.g. "You start with 10 mangoes, then you eat 2, so now you have 8 left."}], '
        '"final_answer": one warm sentence that restates the answer with the real things, '
        'e.g. "So you have 7 mangoes left!", '
        '"breakdown": one short encouraging sentence}\n'
        "Use 2 to 4 steps. Simple words a young child understands. No emojis."
    )

    async def _llm_solve(self, ctx: SkillContext, text: str) -> None:
        """Word problems / multi-step → structured step-by-step solution with UI."""
        if not ctx.llm.enabled:
            await ctx.speaker.say("That's a tricky one and my math brain is offline. Try a smaller sum!")
            return

        messages = [
            {"role": "system", "content": self._JSON_SYSTEM},
            {"role": "user", "content": text},
        ]
        data: Optional[Dict[str, Any]] = None
        try:
            raw = await ctx.llm.complete(messages, json_mode=True, max_tokens=700, temperature=0.2)
            data = json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("math JSON solve failed (%s); falling back to spoken answer", exc)

        if not isinstance(data, dict):
            # Graceful fallback: just explain it aloud.
            spoken = await ctx.speaker.say_stream(ctx.llm, [
                {"role": "system", "content": (
                    "You are Maxi, a fun math teacher for kids 6-12. Solve and explain "
                    "in ONE or TWO very short, simple sentences. No emojis.")},
                {"role": "user", "content": text},
            ])
            await ctx.memory.add_user(text)
            if spoken:
                await ctx.memory.add_assistant(spoken)
            return

        original = str(data.get("original_question") or text)
        answer = data.get("answer")
        steps = data.get("steps") or []
        breakdown = str(data.get("breakdown") or "")
        intro = str(data.get("intro") or "Let's solve this step by step!")
        final_answer = str(data.get("final_answer") or "")

        if steps:
            await self._walk_steps(ctx, original, answer, steps, breakdown,
                                   intro=intro, final_answer=final_answer)
        else:
            await ctx.speaker.say(intro)
            await ctx.speaker.say(final_answer or f"The answer is {answer}!")
            if breakdown:
                await ctx.speaker.say(breakdown)
            await ctx.memory.add_user(text)
            await ctx.memory.add_assistant(f"{original} equals {answer}")

    async def _walk_steps(
        self, ctx: SkillContext, original: str, result: Any,
        steps: List[Dict[str, Any]], breakdown: str, intro: str = "",
        final_answer: str = "",
    ) -> None:
        """Render the steps in the UI, then speak each one while highlighting it."""
        result_str = _num_str(result)
        # 1) Render the whole step list in the UI.
        await ctx.emit(events.math_advanced(original, result_str, steps, breakdown, intro))
        # 2) Speak the intro.
        if intro:
            await ctx.speaker.say(intro)
        # 3) Walk each step: highlight it in the UI, then explain it. Pace to the
        #    spoken length so the highlight stays in sync with the voice and the
        #    child can follow each step.
        for idx, step in enumerate(steps, start=1):
            num = step.get("step", idx)
            await ctx.emit(events.highlight_step(num))
            desc = str(step.get("description") or f"{step.get('operation', '')} equals {step.get('result', '')}.")
            await ctx.speaker.say(desc)
            await asyncio.sleep(max(0.6, len(desc.split()) / 2.7 + 0.3))
        # 4) Final answer + wrap-up — restate it in the story's own words when we have it.
        await ctx.speaker.say(final_answer or f"So the answer is {result_str}!")
        if breakdown:
            await ctx.speaker.say(breakdown)
        await ctx.memory.add_user(ctx.text)
        await ctx.memory.add_assistant(f"{original} equals {result_str}")
