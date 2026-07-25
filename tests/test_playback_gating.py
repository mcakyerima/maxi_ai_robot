"""
Self-audit: Maxi stays in SPEAKING until the tablet reports playback finished.

The backend sends audio faster than it plays, so it must NOT go idle when it
finishes *sending* — only when the tablet reports audio_complete. This proves it.

Run:  venv/Scripts/python.exe tests/test_playback_gating.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from maxi.core import events
from maxi.core.events import Incoming, Phase
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


class FakeLLM:
    enabled = True

    async def prewarm(self):
        return True

    async def complete(self, messages, **kw):
        return "hi"

    async def stream(self, messages, **kw):
        # A short answer that finishes SENDING quickly.
        for s in ("The sky is blue. ", "It scatters light. "):
            yield s


class FakeTTS:
    async def speak(self, text):
        yield SpokenSentence(text=text, audio_b64="QUJD")  # non-empty → marks playback

    async def stream(self, tokens):
        async for tok in tokens:
            yield SpokenSentence(text=tok.strip(), audio_b64="QUJD")


class EchoSkill(Skill):
    name = "echo"

    async def handle(self, ctx: SkillContext) -> None:
        await ctx.speaker.say_stream(ctx.llm, await ctx.memory.context(ctx.text))


async def main() -> int:
    transport = FakeTransport()
    orch = Orchestrator(transport, FakeLLM(), FakeTTS(), SkillRouter().register(EchoSkill()))
    runner = asyncio.create_task(orch.run())
    await asyncio.sleep(0.05)

    await transport.inbound.put({"type": Incoming.WAKE.value})
    await asyncio.sleep(0.05)
    await transport.inbound.put({"type": Incoming.TRANSCRIPTION.value, "text": "why is the sky blue"})

    # Give it time to THINK + SEND all audio and reach the playback wait.
    await asyncio.sleep(0.6)

    # It has finished SENDING but the tablet hasn't said audio_complete yet.
    assert orch.session.phase == Phase.SPEAKING, f"should still be SPEAKING, got {orch.session.phase}"
    assert transport.states()[-1] == "speaking", f"current state must be speaking, got {transport.states()[-1]}"
    assert not orch.session.playback_done.is_set(), "playback should be pending"

    # Now the tablet reports it finished playing.
    await transport.inbound.put({"type": Incoming.AUDIO_COMPLETE.value})
    await asyncio.sleep(0.2)

    assert orch.session.phase == Phase.IDLE, f"should be IDLE after audio_complete, got {orch.session.phase}"
    assert transport.states()[-1] == "idle", "last state should be idle"

    orch.stop()
    runner.cancel()
    try:
        await runner
    except asyncio.CancelledError:
        pass

    print("PASS: stayed SPEAKING while audio played, went idle only after audio_complete")
    print(f"      states: {transport.states()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
