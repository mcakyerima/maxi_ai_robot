"""
maxi.factory — assemble the brain.

One place that wires services + skills + actuators into an Orchestrator. Add a
skill here and it's live; nothing else changes.
"""
from __future__ import annotations

from maxi.actuators.hands import HandsActuator
from maxi.core.orchestrator import Orchestrator
from maxi.core.transport import Transport
from maxi.services.llm import LLMService
from maxi.services.safety import Safety
from maxi.services.tts import SpeechService
from maxi.skills.base import SkillRouter
from maxi.skills.chat import ChatSkill
from maxi.skills.math import MathSkill


def build_orchestrator(transport: Transport) -> Orchestrator:
    safety = Safety()
    router = (
        SkillRouter()
        .register(ChatSkill(safety))
        .register(MathSkill(safety))
    )
    return Orchestrator(
        transport=transport,
        llm=LLMService(),
        tts=SpeechService(),
        router=router,
        hands=HandsActuator(),
    )
