"""
Regression check for the math hand choreography.

The simple-addition path should narrate the operands with separate hands and
use the right hand for the final answer while the left hand clears out.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from maxi.core.events import Mode
from maxi.skills.math import MathSkill, Solved


class FakeSpeaker:
    def __init__(self):
        self.calls = []

    async def say(self, text):
        self.calls.append(("say", text))

    async def say_as(self, spoken, display):
        self.calls.append(("say_as", spoken, display))
        return display


class FakeHands:
    def __init__(self):
        self.calls = []

    async def show_number(self, number, hand, duration_ms=250):
        self.calls.append(("show_number", hand, number, duration_ms))
        return True

    async def clear_hand(self, hand):
        self.calls.append(("clear_hand", hand))
        return True

    async def close_all(self):
        self.calls.append(("close_all",))
        return True


class FakeMemory:
    async def add_user(self, text):
        return None

    async def add_assistant(self, text):
        return None


class FakeCtx:
    def __init__(self):
        self.speaker = FakeSpeaker()
        self.hands = FakeHands()
        self.memory = FakeMemory()
        self.text = "2 plus 2"
        self.mode = Mode.MATH_GESTURE
        self.session_id = "test"
        self.emits = []

    async def emit(self, message):
        self.emits.append(message)


async def main() -> int:
    skill = MathSkill()
    ctx = FakeCtx()
    solved = Solved(a=2, b=2, op="+", result=4, basic=True)

    await skill._narrate(ctx, solved)

    # Right hand first, left hand second, then final answer on the right.
    hand_calls = [call for call in ctx.hands.calls if call[0] in {"show_number", "clear_hand", "close_all"}]
    assert hand_calls[0][:3] == ("show_number", "right", 2), hand_calls
    assert hand_calls[1][:3] == ("show_number", "left", 2), hand_calls
    assert hand_calls[2][:3] == ("show_number", "right", 4), hand_calls
    assert ("clear_hand", "left") in hand_calls, hand_calls
    assert hand_calls[-1] == ("close_all",), hand_calls

    speaker_calls = [call for call in ctx.speaker.calls if call[0] in {"say", "say_as"}]
    assert speaker_calls[0] == ("say", "Let's work it out."), speaker_calls
    assert speaker_calls[1] == ("say_as", "two", "2"), speaker_calls
    assert speaker_calls[2] == ("say", "plus"), speaker_calls
    assert speaker_calls[3] == ("say_as", "two", "2"), speaker_calls

    print("PASS: simple-addition hand choreography is right-hand, left-hand, final-answer sync")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))