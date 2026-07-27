"""
maxi.core.speaker — turns text (or an LLM token stream) into paced, interruptible
speech on the tablet.

For each sentence it:
  1. sets ``session.current_script`` (so the tablet can reject Maxi's own echo),
  2. emits ``speaking_script`` + ``response_chunk`` + ``audio_chunk``,
  3. paces itself by the sentence's estimated spoken duration.

The whole thing runs inside the orchestrator's ``speaking_task``; cancelling that
task stops speech within the current sentence — that is the backend half of
barge-in (docs/BARGE_IN.md).
"""
from __future__ import annotations

import asyncio
from typing import List, Optional

from maxi.core import events
from maxi.core.session import Session
from maxi.core.transport import Transport
from maxi.services.llm import LLMService, Message
from maxi.services.tts import SpeechService, SpokenSentence

# Emma Neural speaks ~2.7 words/sec; pad a little for natural pauses.
_WORDS_PER_SEC = 2.7
_MIN_SENTENCE_SECONDS = 0.35


def _estimate_seconds(text: str) -> float:
    words = max(1, len(text.split()))
    return max(_MIN_SENTENCE_SECONDS, words / _WORDS_PER_SEC + 0.25)


class Speaker:
    def __init__(self, tts: SpeechService, transport: Transport, session: Session) -> None:
        self.tts = tts
        self.transport = transport
        self.session = session

    async def _emit(self, sentence: SpokenSentence) -> None:
        self.session.current_script = sentence.text
        await self.transport.emit(events.speaking_script(sentence.text))
        await self.transport.emit(events.response_chunk(sentence.text))
        if sentence.audio_b64:
            # Mark playback as pending BEFORE the tablet even reports audio_started,
            # so there's no race where the backend thinks it's already done.
            self.session.mark_audio_sent()
            await self.transport.emit(events.audio_chunk(sentence.audio_b64))
        # No artificial pause: send sentences as fast as they synthesize. The
        # tablet's audio player queues them and plays back-to-back, so speech is
        # smooth and continuous instead of choppy. Barge-in still works because
        # the tablet flushes its audio queue the instant it's interrupted.

    async def say(self, text: str) -> str:
        """Speak a fixed string. Returns what was said."""
        spoken: List[str] = []
        async for sentence in self.tts.speak(text):
            await self._emit(sentence)
            spoken.append(sentence.text)
        return " ".join(spoken)

    async def say_stream(
        self, llm: LLMService, messages: List[Message], *, max_tokens: Optional[int] = None
    ) -> str:
        """Stream an LLM reply straight into speech. Returns the full text.
        ``max_tokens`` overrides the default (e.g. a longer budget for stories)."""
        spoken: List[str] = []
        async for sentence in self.tts.stream(llm.stream(messages, max_tokens=max_tokens)):
            await self._emit(sentence)
            spoken.append(sentence.text)
        return " ".join(spoken)
