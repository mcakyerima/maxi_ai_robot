"""
maxi.skills.base — the Skill contract and a tiny router.

A Skill owns one kind of interaction. It is handed a ``SkillContext`` giving it
everything it needs — the child's words, the Speaker (interruptible speech),
the LLM, memory, and the hands — and it drives the whole response, including
interleaved gestures. Running inside the orchestrator's cancellable task means a
skill is interrupted cleanly the moment the child barges in.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional

from maxi.core.events import Mode
from maxi.core.speaker import Speaker
from maxi.services.llm import LLMService
from maxi.services.memory import Memory


async def _noop_emit(_message: Dict[str, Any]) -> None:
    return None


@dataclass
class SkillContext:
    text: str                       # what the child said
    mode: Mode
    speaker: Speaker                # interruptible speech out
    llm: LLMService
    memory: Memory
    hands: Optional[object] = None  # HandsActuator | None
    session_id: str = ""
    # Send a raw message to the tablet (e.g. mirror a finger pose in the UI).
    emit: Callable[[Dict[str, Any]], Awaitable[None]] = _noop_emit


class Skill:
    """Base class. Subclasses set ``mode`` and implement ``handle``."""
    name: str = "skill"
    mode: Mode = Mode.GENERAL_CHAT

    async def handle(self, ctx: SkillContext) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class SkillRouter:
    """Maps a Mode to the Skill that serves it."""

    def __init__(self) -> None:
        self._by_mode: Dict[Mode, Skill] = {}

    def register(self, skill: Skill) -> "SkillRouter":
        self._by_mode[skill.mode] = skill
        return self

    def for_mode(self, mode: Mode) -> Optional[Skill]:
        return self._by_mode.get(mode)
