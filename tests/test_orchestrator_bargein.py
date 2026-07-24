"""
Self-audit: prove the barge-in engine cancels speech mid-answer.

No network: fake Groq (slow token stream) + fake TTS. We start a long answer,
fire an ``interrupted`` event partway, and assert the speaking task was cancelled
before finishing, and the state machine returned to LISTENING.

Run:  venv/Scripts/python.exe tests/test_orchestrator_bargein.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from maxi.core import events
from maxi.core.events import Incoming, Mode, Phase
from maxi.core.orchestrator import Orchestrator
from maxi.core.transport import Transport
from maxi.services.tts import SpokenSentence
from maxi.skills.base import Skill, SkillContext, SkillRouter


class FakeTransport(Transport):
    def __init__(self):
        super().__init__()
        self.sent = []

    async def emit(self, message):
        self.sent.append(message)

    def states(self):
        return [m["state"] for m in self.sent if m["type"] == events.Outgoing.STATE_CHANGE.value]

    def scripts(self):
        return [m["text"] for m in self.sent if m["type"] == events.Outgoing.SPEAKING_SCRIPT.value]


class FakeLLM:
    enabled = True

    async def prewarm(self):
        return True

    async def stream(self, messages, **kw):
        # A ten-sentence answer, each arriving slowly.
        for i in range(1, 11):
            await asyncio.sleep(0.05)
            yield f"This is sentence number {i}. "


class FakeTTS:
    async def speak(self, text):
        yield SpokenSentence(text=text, audio_b64="")

    async def stream(self, tokens):
        async for tok in tokens:
            yield SpokenSentence(text=tok.strip(), audio_b64="")


class EchoSkill(Skill):
    name = "echo"
    mode = Mode.GENERAL_CHAT

    async def handle(self, ctx: SkillContext) -> None:
        await ctx.speaker.say_stream(ctx.llm, await ctx.memory.context(ctx.text))


async def main() -> int:
    transport = FakeTransport()
    router = SkillRouter().register(EchoSkill())
    orch = Orchestrator(transport, FakeLLM(), FakeTTS(), router)

    runner = asyncio.create_task(orch.run())
    await asyncio.sleep(0.05)

    # Wake first (wake-gated), THEN ask — Maxi starts a long answer.
    await transport.inbound.put({"type": Incoming.WAKE.value})
    await asyncio.sleep(0.05)
    await transport.inbound.put({"type": Incoming.TRANSCRIPTION.value, "text": "tell me a long story"})
    await asyncio.sleep(1.2)  # let a few sentences play

    sentences_before = len(transport.scripts())
    assert orch.session.is_speaking(), "expected Maxi to be mid-answer"

    # Child barges in.
    await transport.inbound.put({"type": Incoming.INTERRUPT.value})
    await asyncio.sleep(0.4)

    sentences_after = len(transport.scripts())

    # --- assertions ---
    assert not orch.session.is_speaking(), "speaking task should be cancelled"
    assert orch.session.phase == Phase.LISTENING, f"expected LISTENING, got {orch.session.phase}"
    assert Phase.INTERRUPTED.value in transport.states(), "should have emitted 'interrupted'"
    assert 0 < sentences_before < 10, f"should be partway, got {sentences_before}"
    assert sentences_after <= sentences_before + 1, "no new sentences should play after barge-in"
    assert orch.session.current_script == "", "current script should be cleared"

    # Follow-up after barge-in works.
    await transport.inbound.put({"type": Incoming.TRANSCRIPTION.value, "text": "what is 2 plus 2"})
    await asyncio.sleep(0.3)
    assert orch.session.is_speaking(), "follow-up interaction should start"

    orch.stop()
    runner.cancel()
    try:
        await runner
    except asyncio.CancelledError:
        pass

    print(f"PASS: spoke {sentences_before} sentences, barge-in stopped it, returned to LISTENING")
    print(f"      states seen: {transport.states()[-6:]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
