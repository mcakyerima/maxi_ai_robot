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
import traceback
from typing import Any, Dict, Optional

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
        elif mtype in (
            Incoming.AUDIO_STARTED.value, Incoming.AUDIO_COMPLETE.value,
            Incoming.AUDIO_INTERRUPTED.value,
        ):
            logger.debug("tablet audio state: %s", mtype)
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
        logger.info("Wake → LISTENING (mode=%s)", self.session.mode.value)

    async def _on_transcription(self, msg: Dict[str, Any]) -> None:
        text = (msg.get("text") or "").strip()
        if not text:
            return
        # A transcription always starts (or restarts) an interaction. If Maxi was
        # mid-sentence, this is a follow-up after a barge-in — cancel and re-answer.
        await self.session.cancel_speaking()
        if self.session.mode == Mode.IDLE:
            self.session.set_mode(Mode.GENERAL_CHAT)
        await self.transport.emit(events.transcription(text))
        await self._start_interaction(text)

    async def _start_interaction(self, text: str) -> None:
        skill = self.router.for_mode(self.session.mode) or self.router.for_mode(Mode.GENERAL_CHAT)
        if skill is None:
            await self.transport.emit(events.error("No skill available for this mode."))
            return

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
            await skill.handle(ctx)
            await self.transport.emit(events.response_complete())
            # Conversation stays live: after speaking, keep listening for a follow-up.
            self.session.enter(Phase.LISTENING)
            await self.transport.emit(events.state_change(Phase.LISTENING))
        except asyncio.CancelledError:
            logger.info("Speaking cancelled (barge-in).")
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("skill '%s' failed: %s\n%s", skill.name, exc, traceback.format_exc())
            try:
                await ctx.speaker.say("Oops, my brain hiccuped. Let's try that again!")
            except Exception:  # noqa: BLE001
                pass
            self.session.enter(Phase.LISTENING)
            await self.transport.emit(events.state_change(Phase.LISTENING))
        finally:
            self.session.current_script = ""
            if self.session.speaking_task is me:
                self.session.speaking_task = None

    async def _on_interrupt(self) -> None:
        if self.session.is_speaking():
            logger.info("Barge-in accepted → stopping speech.")
            await self.transport.emit(events.state_change(Phase.INTERRUPTED))
            await self.session.cancel_speaking()
        self.session.enter(Phase.LISTENING)
        await self.transport.emit(events.state_change(Phase.LISTENING))

    async def _on_set_mode(self, mode_wire: Optional[str]) -> None:
        mode = Mode.from_wire(mode_wire)
        await self.session.cancel_speaking()
        self.session.set_mode(mode)
        if mode == Mode.IDLE:
            await self.transport.emit(events.state_change(Phase.IDLE))
        else:
            self.session.enter(Phase.LISTENING)
            await self.transport.emit(events.state_change(Phase.LISTENING))
        logger.info("Mode → %s", mode.value)

    async def _to_idle(self) -> None:
        await self.session.cancel_speaking()
        self.session.set_mode(Mode.IDLE)
        await self.transport.emit(events.state_change(Phase.IDLE))
