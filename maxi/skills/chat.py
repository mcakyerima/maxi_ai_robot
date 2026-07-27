"""
maxi.skills.chat — general tutoring conversation.

Pulls recent context from memory, streams a Groq answer straight into speech,
then records the turn. Input/output safety is applied around the LLM call.
"""
from __future__ import annotations

import logging
import random
from typing import Optional

from maxi.core import events
from maxi.core.events import Mode
from maxi.services.safety import Safety
from maxi.skills.base import Skill, SkillContext
from maxi.skills.datetime_intent import maybe_answer_datetime
from maxi.skills.play_intents import (
    SPELL_WORDS,
    detect_play_intent,
    play_system_prompt,
    spell_game_reply,
    spell_word_reply,
)

logger = logging.getLogger("maxi.skills.chat")


def _child_name(memory) -> Optional[str]:
    """Best-effort read of the remembered child name (PersistentMemory has a store)."""
    store = getattr(memory, "store", None)
    if store is None:
        return None
    try:
        return store.get_name()
    except Exception:  # noqa: BLE001
        return None


class ChatSkill(Skill):
    name = "chat"
    mode = Mode.GENERAL_CHAT

    def __init__(self, safety: Safety | None = None) -> None:
        self.safety = safety or Safety()

    async def handle(self, ctx: SkillContext) -> None:
        text = ctx.text.strip()
        if not text:
            await ctx.speaker.say("I didn't catch that. Can you say it again?")
            return

        # Rate limit (gentle break reminders for a kids' product).
        allowed, warning = self.safety.rate_limit(ctx.session_id, "chat")
        if not allowed:
            await ctx.speaker.say(warning or "Let's take a little break and come back soon!")
            return

        # Input safety.
        safe, fallback = self.safety.check_input(text, ctx.session_id)
        if not safe:
            self.safety.log_filter_event(ctx.session_id, text, "unsafe_input")
            await ctx.speaker.say(fallback)
            return

        self.safety.log_question(ctx.session_id, text, "chat")

        # Time/date is answered locally with the REAL local clock (the LLM can't
        # know it). Kid-friendly, instant, always correct.
        dt_reply = maybe_answer_datetime(text)
        if dt_reply:
            await ctx.speaker.say(dt_reply)
            await ctx.memory.add_user(text)
            await ctx.memory.add_assistant(dt_reply)
            return

        # Spelling is answered LOCALLY (instant, always correct).
        intent, arg = detect_play_intent(text)
        if intent == "spell_word":
            reply = spell_word_reply(arg)
            await ctx.emit(events.emotion("happy"))
            await ctx.speaker.say(reply)
            await ctx.memory.add_user(text)
            await ctx.memory.add_assistant(reply)
            return
        if intent == "spell_game":
            reply = spell_game_reply(random.randrange(len(SPELL_WORDS)))
            await ctx.emit(events.emotion("happy"))
            await ctx.speaker.say(reply)
            await ctx.memory.add_user(text)
            await ctx.memory.add_assistant(reply)
            return

        await ctx.memory.add_user(text)
        messages = await ctx.memory.context(text)

        # Storytelling / quiz: a specialised system prompt + a matching expression.
        max_tokens = None
        if intent in ("story", "quiz"):
            await ctx.emit(events.emotion("excited" if intent == "story" else "curious"))
            extra = play_system_prompt(intent, _child_name(ctx.memory))
            if extra:
                messages.insert(1, {"role": "system", "content": extra})
            if intent == "story":
                max_tokens = 220  # stories need more room than the default

        if not ctx.llm.enabled:
            await ctx.speaker.say("My thinking is offline right now, but I'm still here with you!")
            return

        spoken = await ctx.speaker.say_stream(ctx.llm, messages, max_tokens=max_tokens)

        # Output safety net + remember the turn.
        ok, cleaned = self.safety.clean_output(spoken)
        if not ok and cleaned:
            await ctx.speaker.say(cleaned)
            spoken = cleaned
        if spoken:
            await ctx.memory.add_assistant(spoken)
