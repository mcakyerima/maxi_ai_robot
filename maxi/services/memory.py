"""
maxi.services.memory — conversation memory behind a small, swappable interface.

Ships with a fast in-process implementation (a sliding window + the persona
system prompt) that has zero heavy dependencies, so the brain boots instantly.
The advanced embedding-based context manager (SQLite + sentence-transformers)
can be dropped in later behind the same `Memory` interface without touching the
orchestrator or skills.
"""
from __future__ import annotations

from collections import deque
from typing import Deque, Dict, List, Protocol

from maxi import persona

Message = Dict[str, str]


class Memory(Protocol):
    async def add_user(self, text: str) -> None: ...
    async def add_assistant(self, text: str) -> None: ...
    async def context(self, query: str = "") -> List[Message]: ...


class WindowMemory:
    """Keeps the last N turns and prepends the persona system prompt."""

    def __init__(self, turns: int = 12) -> None:
        self._buf: Deque[Message] = deque(maxlen=turns * 2)

    async def add_user(self, text: str) -> None:
        self._buf.append({"role": "user", "content": text})

    async def add_assistant(self, text: str) -> None:
        self._buf.append({"role": "assistant", "content": text})

    async def context(self, query: str = "") -> List[Message]:
        return [{"role": "system", "content": persona.system_prompt()}, *self._buf]

    def reset(self) -> None:
        self._buf.clear()
