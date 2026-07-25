"""
maxi.core.orchestrator — the conversation engine.

A single async event loop consumes tablet messages and drives the state machine:

    IDLE ──wake/tap──► LISTENING ──transcription──► THINKING ──► SPEAKING
      ▲                    ▲                                        │
      └──── back_to_menu ──┴───────────── barge-in ("stop") ────────┘

SPEAKING runs the chosen skill inside a single cancellable ``asyncio.Task``. A
validated ``interrupted`` event cancels that task immediately — speech stops
within the current sentence, and Maxi drops back to LISTENING to hear the child.
That is the whole point (docs/BARGE_IN.md).
"""
from __future__ import annotations

import asyncio
import logging
import random
import traceback
from typing import Any, Dict, Optional

from maxi import persona
from maxi.core import events
from maxi.core.events import Incoming, Mode, Phase
from maxi.core.session import Session
from maxi.core.speaker import Speaker
from maxi.core.transport import Transport
from maxi.services.llm import LLMService
from maxi.services.memory import Memory, WindowMemory
from maxi.services.tts import SpeechService
from maxi.skills.base import SkillContext, SkillRouter

logger = logging.getLogger("maxi.orchestrator")


class Orchestrator:
    def __init__(
        self,
        transport: Transport,
        llm: LLMService,
        tts: SpeechService,
        router: SkillRouter,
        hands: Optional[object] = None,
        memory: Optional[Memory] = None,
    ) -> None:
        self.transport = transport
        self.llm = llm
        self.tts = tts
        self.router = router
        self.hands = hands
        self.session = Session()
        self.memory: Memory = memory or WindowMemory()
        self._running = False
        # Reverts to IDLE if a wake happens but no question is heard in time.
        self._listen_timeout_task: Optional[asyncio.Task] = None
        self.listen_timeout_seconds = 15.0

    # -- lifecycle -----------------------------------------------------------
    async def run(self) -> None:
        self._running = True
        logger.info("Orchestrator starting; bringing hands online + prewarming LLM…")
        if self.hands is not None:
            try:
                await self.hands.initialize()
            except Exception as exc:  # noqa: BLE001
                logger.warning("hands init failed: %s", exc)
        await self.llm.prewarm()
        await self.transport.emit(events.state_change(Phase.IDLE))
        logger.info("Maxi is ready and idle.")
        while self._running:
            try:
                msg = await self.transport.next_message()
                await self._dispatch(msg)
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001
                logger.error("dispatch error: %s\n%s", exc, traceback.format_exc())

    def stop(self) -> None:
        self._running = False

    # -- dispatch ------------------------------------------------------------
    async def _dispatch(self, msg: Dict[str, Any]) -> None:
        mtype = msg.get("type")
        if mtype == Incoming.PING.value:
            await self.transport.emit(events.pong())
        elif mtype == Incoming.INTERRUPT.value:
            await self._on_interrupt()
        elif mtype == Incoming.TRANSCRIPTION.value:
            await self._on_transcription(msg)
        elif mtype in (Incoming.WAKE.value, Incoming.MATH_WAKE.value):
            await self._on_wake(math=mtype == Incoming.MATH_WAKE.value)
        elif mtype == Incoming.SET_MODE.value:
            await self._on_set_mode(msg.get("mode"))
        elif mtype == Incoming.BACK_TO_MENU.value:
            await self._to_idle()
        elif mtype == Incoming.AUDIO_STARTED.value:
            self.session.mark_audio_sent()
        elif mtype in (Incoming.AUDIO_COMPLETE.value, Incoming.AUDIO_INTERRUPTED.value):
            # The tablet finished (or flushed) its audio queue — playback is done.
            self.session.mark_audio_done()
        else:
            logger.debug("unhandled message type: %s", mtype)

    # -- handlers ------------------------------------------------------------
    async def _on_wake(self, *, math: bool) -> None:
        if math:
            self.session.set_mode(Mode.MATH_GESTURE)
        elif self.session.mode == Mode.IDLE:
            self.session.set_mode(Mode.GENERAL_CHAT)
        await self.session.cancel_speaking()
        self.session.enter(Phase.LISTENING)
        await self.transport.emit(events.state_change(Phase.LISTENING))
        self._start_listen_timeout()
        logger.info("Wake → LISTENING (mode=%s)", self.session.mode.value)

    async def _on_transcription(self, msg: Dict[str, Any]) -> None:
        text = (msg.get("text") or "").strip()
        if not text:
            return
        # Only accept a question when we are actually LISTENING (i.e. right after a
        # wake word or mic tap). Ignore stray/echo transcriptions during
        # THINKING / SPEAKING / IDLE — THIS is what stops Maxi from hearing its own
        # voice and answering itself in a loop.
        if self.session.phase != Phase.LISTENING:
            logger.info("Ignoring transcription in phase=%s: %r",
                        self.session.phase.value, text[:50])
            return
        self._cancel_listen_timeout()
        if self.session.mode == Mode.IDLE:
            self.session.set_mode(Mode.GENERAL_CHAT)
        await self.transport.emit(events.transcription(text))
        await self._start_interaction(text)

    async def _start_interaction(self, text: str) -> None:
        skill = self.router.for_mode(self.session.mode) or self.router.for_mode(Mode.GENERAL_CHAT)
        if skill is None:
            await self.transport.emit(events.error("No skill available for this mode."))
            return

        # Fresh playback state for this turn (ignore any stale audio_complete).
        self.session.mark_audio_done()

        self.session.enter(Phase.THINKING)
        await self.transport.emit(events.state_change(Phase.THINKING))

        ctx = SkillContext(
            text=text,
            mode=self.session.mode,
            speaker=Speaker(self.tts, self.transport, self.session),
            llm=self.llm,
            memory=self.memory,
            hands=self.hands,
            session_id=self.session.id,
            emit=self.transport.emit,
        )
        self.session.enter(Phase.SPEAKING)
        await self.transport.emit(events.state_change(Phase.SPEAKING))
        self.session.speaking_task = asyncio.create_task(self._run_skill(skill, ctx))

    async def _run_skill(self, skill, ctx: SkillContext) -> None:
        me = asyncio.current_task()
        try:
            # Open a streaming message bubble on the tablet before any chunks.
            await self.transport.emit(events.response_start())
            await skill.handle(ctx)
            await self.transport.emit(events.response_complete())
            # Stay in SPEAKING until the tablet has actually FINISHED playing the
            # audio (not just until we finished sending it). Only then go idle —
            # so the state is truthful and barge-in works right up to the last word.
            await self._await_playback_done()
            # Answer done → go back to WAITING (wake-gated). The child says
            # "Hey Maxi" or taps the mic to ask the next question. This is what
            # prevents the always-on listen→speak→listen runaway loop.
            self.session.enter(Phase.IDLE)
            await self.transport.emit(events.state_change(Phase.IDLE))
        except asyncio.CancelledError:
            logger.info("Speaking cancelled (barge-in).")
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("skill '%s' failed: %s\n%s", skill.name, exc, traceback.format_exc())
            try:
                await ctx.speaker.say("Oops, my brain hiccuped. Let's try that again!")
            except Exception:  # noqa: BLE001
                pass
            self.session.enter(Phase.IDLE)
            await self.transport.emit(events.state_change(Phase.IDLE))
        finally:
            self.session.current_script = ""
            if self.session.speaking_task is me:
                self.session.speaking_task = None

    async def _on_interrupt(self) -> None:
        # A real barge-in: the child interrupted to say something new. Stop
        # talking, give a quick natural acknowledgement (not a cold cut-off),
        # then listen for their next words (with a timeout back to idle).
        if self.session.is_speaking():
            logger.info("Barge-in accepted → stopping speech.")
            await self.transport.emit(events.state_change(Phase.INTERRUPTED))
            await self.session.cancel_speaking()
            try:
                ack = random.choice(persona.INTERRUPT_ACKS)
                await Speaker(self.tts, self.transport, self.session).say(ack)
            except Exception as exc:  # noqa: BLE001
                logger.warning("interrupt ack failed: %s", exc)
        self.session.enter(Phase.LISTENING)
        await self.transport.emit(events.state_change(Phase.LISTENING))
        self._start_listen_timeout()

    async def _on_set_mode(self, mode_wire: Optional[str]) -> None:
        # Selecting a mode does NOT start listening — Maxi waits for a wake word
        # (or mic tap). This is why it no longer listens the moment you connect.
        mode = Mode.from_wire(mode_wire)
        await self.session.cancel_speaking()
        self._cancel_listen_timeout()
        self.session.set_mode(mode)
        self.session.enter(Phase.IDLE)
        await self.transport.emit(events.state_change(Phase.IDLE))
        logger.info("Mode → %s (idle, awaiting wake)", mode.value)

    async def _to_idle(self) -> None:
        await self.session.cancel_speaking()
        self._cancel_listen_timeout()
        self.session.set_mode(Mode.IDLE)
        await self.transport.emit(events.state_change(Phase.IDLE))

    async def _await_playback_done(self, timeout: float = 45.0) -> None:
        """Block until the tablet reports the audio finished playing (or a safety timeout)."""
        if self.session.playback_done.is_set():
            return
        try:
            await asyncio.wait_for(self.session.playback_done.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("playback_done timed out after %ss; leaving SPEAKING anyway", timeout)

    # -- listen timeout ------------------------------------------------------
    def _start_listen_timeout(self) -> None:
        self._cancel_listen_timeout()
        self._listen_timeout_task = asyncio.create_task(self._listen_timeout())

    def _cancel_listen_timeout(self) -> None:
        task = self._listen_timeout_task
        self._listen_timeout_task = None
        if task and not task.done():
            task.cancel()

    async def _listen_timeout(self) -> None:
        try:
            await asyncio.sleep(self.listen_timeout_seconds)
        except asyncio.CancelledError:
            return
        if self.session.phase == Phase.LISTENING:
            self.session.enter(Phase.IDLE)
            await self.transport.emit(events.state_change(Phase.IDLE))
            logger.info("Listen timeout → IDLE (no question heard)")
