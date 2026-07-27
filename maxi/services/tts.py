"""
maxi.services.tts — Microsoft Edge-TTS (free), streamed to the tablet a
**sentence at a time**.

Why per-sentence matters:
  * First words play within ~1 s instead of after the whole paragraph.
  * Barge-in stops within one sentence — the granularity of cancellation.
  * The tablet is told each sentence (``SpokenSentence.text``) so it can reject
    its own echo (docs/BARGE_IN.md, Layer 2).

Usage (the orchestrator owns the loop so it can cancel between sentences):

    async for sentence in tts.stream(llm.stream(messages)):
        await transport.emit(events.speaking_script(sentence.text))
        await transport.emit(events.audio_chunk(sentence.audio_b64))
"""
from __future__ import annotations

import asyncio
import base64
import logging
import re
from dataclasses import dataclass
from io import BytesIO
from typing import AsyncIterator, List, Optional

import edge_tts

from maxi.config import settings

logger = logging.getLogger("maxi.tts")

# Split after ., !, ? (optionally followed by quotes/brackets) + whitespace, or newlines.
_SENTENCE_END = re.compile(r'(?<=[.!?])["\')\]]?\s+|\n+')
# Strip characters Edge-TTS mangles, keep basic punctuation.
_CLEAN = re.compile(r"[^\w\s.,?!:;()'\"-]")
_WS = re.compile(r"\s+")

# Speak fragments once they reach this length, so we don't synth "3." alone.
_MIN_CHUNK = 24


@dataclass
class SpokenSentence:
    text: str          # the exact words in this chunk (for echo rejection + UI)
    audio_b64: str     # base64-encoded mp3
    fmt: str = "mp3"


def _clean(text: str) -> str:
    return _WS.sub(" ", _CLEAN.sub("", text)).strip()


class SpeechService:
    def __init__(self) -> None:
        self.voice = settings.tts.voice
        self.rate = settings.tts.rate
        self.pitch = settings.tts.pitch
        self._fallback_voices = [
            "en-US-AriaNeural", "en-US-JennyNeural",
            "en-GB-SoniaNeural", "en-US-GuyNeural",
        ]
        self._fallback_idx = 0

    async def synthesize(self, text: str, *, voice: Optional[str] = None, _retry: int = 0) -> bytes:
        """Return mp3 bytes for one chunk, with 403/rate-limit retry + voice fallback.
        ``voice`` overrides the default for this call (e.g. a specific language voice
        that pronounces a particular ack correctly)."""
        clean = _clean(text)
        if not clean:
            return b""
        use_voice = voice or self.voice
        try:
            communicate = edge_tts.Communicate(
                text=clean, voice=use_voice, rate=self.rate, pitch=self.pitch
            )
            buf = BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    buf.write(chunk["data"])
            return buf.getvalue()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if ("403" in msg or "Invalid response status" in msg) and _retry < 3:
                # Only rotate the DEFAULT voice; an explicit override keeps its voice.
                if voice is None and self._fallback_idx < len(self._fallback_voices):
                    self.voice = self._fallback_voices[self._fallback_idx]
                    self._fallback_idx += 1
                    logger.warning("Edge-TTS 403; switching voice to %s", self.voice)
                await asyncio.sleep([1, 2, 5][min(_retry, 2)])
                return await self.synthesize(text, voice=voice, _retry=_retry + 1)
            logger.error("TTS synth failed for %r: %s", clean[:40], exc)
            return b""

    async def _make(self, text: str) -> SpokenSentence:
        audio = await self.synthesize(text)
        b64 = base64.b64encode(audio).decode("utf-8") if audio else ""
        return SpokenSentence(text=_clean(text), audio_b64=b64)

    async def speak(self, text: str) -> AsyncIterator[SpokenSentence]:
        """Synthesize a fixed string, one sentence at a time (greetings, prompts)."""
        for sentence in _split_sentences(text):
            if sentence.strip():
                yield await self._make(sentence)

    async def stream(self, tokens: AsyncIterator[str]) -> AsyncIterator[SpokenSentence]:
        """Consume an LLM token stream and emit synthesized sentences as they form."""
        buffer = ""
        async for token in tokens:
            buffer += token
            if len(buffer) < _MIN_CHUNK:
                continue
            complete, buffer = _drain_sentences(buffer)
            for sentence in complete:
                yield await self._make(sentence)
        # flush the tail
        if buffer.strip():
            yield await self._make(buffer)


def _split_sentences(text: str) -> List[str]:
    return [s for s in _SENTENCE_END.split(text) if s and s.strip()]


def _drain_sentences(buffer: str) -> tuple[List[str], str]:
    """Pull all *complete* sentences out of buffer; return (sentences, remainder)."""
    parts = _SENTENCE_END.split(buffer)
    if len(parts) <= 1:
        return [], buffer
    # The last part is an incomplete sentence still being written.
    complete, remainder = parts[:-1], parts[-1]
    return [p for p in complete if p and p.strip()], remainder
