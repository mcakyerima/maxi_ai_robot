"""
maxi.core.session — the live state of one conversation.

Small and deliberate: the orchestrator is the only writer. The single most
important field is ``speaking_task`` — the cancellable handle that makes
instant barge-in possible (see docs/BARGE_IN.md).
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Optional

from maxi.core.events import Mode, Phase


@dataclass
class Session:
    """Per-conversation state for the state machine."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    mode: Mode = Mode.IDLE
    phase: Phase = Phase.IDLE

    # The in-flight "think → speak" task. Cancel it to barge in.
    speaking_task: Optional[asyncio.Task] = None
    # What Maxi is saying right now (published to the tablet for echo rejection).
    current_script: str = ""
    # Guards against overlapping interactions (double wake, echo re-trigger).
    interaction_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def is_speaking(self) -> bool:
        return self.speaking_task is not None and not self.speaking_task.done()

    def enter(self, phase: Phase) -> None:
        self.phase = phase

    def set_mode(self, mode: Mode) -> None:
        self.mode = mode
        if mode == Mode.IDLE:
            self.phase = Phase.IDLE

    async def cancel_speaking(self) -> None:
        """Cancel the in-flight speaking task and wait for it to unwind."""
        task = self.speaking_task
        self.speaking_task = None
        self.current_script = ""
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
