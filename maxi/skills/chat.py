"""
maxi.skills.chat — general tutoring conversation.

Pulls recent context from memory, streams a Groq answer straight into speech,
then records the turn. Input/output safety is applied around the LLM call.
"""
from __future__ import annotations

import logging

from maxi.core.events import Mode
from maxi.services.safety import Safety
from maxi.skills.base import Skill, SkillContext

logger = logging.getLogger("maxi.skills.chat")


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

        await ctx.memory.add_user(text)
        messages = await ctx.memory.context(text)

        if not ctx.llm.enabled:
            await ctx.speaker.say("My thinking is offline right now, but I'm still here with you!")
            return

        spoken = await ctx.speaker.say_stream(ctx.llm, messages)

        # Output safety net + remember the turn.
        ok, cleaned = self.safety.clean_output(spoken)
        if not ok and cleaned:
            await ctx.speaker.say(cleaned)
            spoken = cleaned
        if spoken:
            await ctx.memory.add_assistant(spoken)
