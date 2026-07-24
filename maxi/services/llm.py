"""
maxi.services.llm — the reasoning engine (Groq, free tier).

Exposes a tiny provider-agnostic surface:

    reply = await llm.complete(messages)             # one-shot
    async for token in llm.stream(messages): ...     # streamed tokens

Streaming is what makes Maxi feel instant: tokens flow out of Groq, get chunked
into sentences by the TTS layer, and start playing within ~1 second.
"""
from __future__ import annotations

import logging
from typing import AsyncIterator, Dict, List, Optional

from maxi.config import settings

logger = logging.getLogger("maxi.llm")

Message = Dict[str, str]  # {"role": "system"|"user"|"assistant", "content": str}


class LLMService:
    def __init__(self) -> None:
        self._client = None  # lazy AsyncGroq
        self.model = settings.llm.model
        self.enabled = settings.llm.enabled

    def _get_client(self):
        if self._client is None:
            if not settings.llm.api_key:
                raise RuntimeError("GROQ_API_KEY is not set")
            from groq import AsyncGroq
            self._client = AsyncGroq(api_key=settings.llm.api_key)
        return self._client

    async def prewarm(self) -> bool:
        """Fire a tiny request so the first real answer isn't cold."""
        if not self.enabled:
            logger.warning("LLM disabled (no GROQ_API_KEY) — Maxi will run text-limited")
            return False
        try:
            await self.complete(
                [{"role": "user", "content": "Say 'ready'."}], max_tokens=4
            )
            logger.info("Groq LLM warm (%s)", self.model)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("LLM prewarm failed: %s", exc)
            return False

    async def complete(
        self, messages: List[Message], *, max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> str:
        client = self._get_client()
        resp = await client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=settings.llm.temperature if temperature is None else temperature,
            max_tokens=settings.llm.max_tokens if max_tokens is None else max_tokens,
            top_p=settings.llm.top_p,
        )
        return (resp.choices[0].message.content or "").strip()

    async def stream(
        self, messages: List[Message], *, max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> AsyncIterator[str]:
        """Yield token deltas as they arrive from Groq."""
        client = self._get_client()
        stream = await client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=settings.llm.temperature if temperature is None else temperature,
            max_tokens=settings.llm.max_tokens if max_tokens is None else max_tokens,
            top_p=settings.llm.top_p,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
