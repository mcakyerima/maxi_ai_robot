"""
maxi.core.events — the tablet ⇄ brain message contract.

Every message on the Socket.IO ``message`` channel is a JSON object with a
``type`` field. This module is the single, authoritative list of those types
(so we never again have magic strings scattered across the codebase) plus small
typed builders for outbound messages.

Kept wire-compatible with the existing tablet client so migration is seamless;
new types (e.g. ``speaking_script``) are additive.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Incoming(str, Enum):
    """Messages the tablet sends to the brain."""
    WAKE = "wake_word_detected"          # child said "Hey Maxi" (or tapped mic) while idle
    MATH_WAKE = "math_gesture_wake"      # wake specifically into math mode
    TRANSCRIPTION = "user_transcription"  # {text, confidence} — a captured utterance
    INTERRUPT = "interrupted"            # validated barge-in ("stop Maxi")
    AUDIO_STARTED = "audio_started"      # tablet began playing an audio chunk
    AUDIO_COMPLETE = "audio_complete"    # tablet finished the audio queue
    AUDIO_INTERRUPTED = "audio_interrupted"  # tablet stopped audio locally
    SET_MODE = "set_mode"                # {mode: general_chat|math_gesture|idle}
    BACK_TO_MENU = "back_to_menu"
    PING = "ping"


class Outgoing(str, Enum):
    """Messages the brain sends to the tablet."""
    STATE_CHANGE = "state_change"        # {state} — drives the robot face/animation
    TRANSCRIPTION = "transcription"      # echo the recognized text back to the UI
    RESPONSE = "response"                # a full (non-streaming) text response
    RESPONSE_START = "response_start"    # begin a streamed response (UI opens a bubble)
    RESPONSE_CHUNK = "response_chunk"    # a streamed token/sentence of the response
    RESPONSE_COMPLETE = "response_complete"
    AUDIO_CHUNK = "audio_chunk"          # {audio(base64), format} — a sentence of TTS
    SPEAKING_SCRIPT = "speaking_script"  # {text} — what Maxi is saying NOW (echo rejection)
    FINGER_POSE = "finger_pose"          # {pose} — mirror hand movement in the UI
    MATH_RESULT = "math_result"          # {A,B,OP,result,explanation,mode} — math display
    HIGHLIGHT_STEP = "highlight_step"    # {step_number} — highlight a solution step
    EMOTION = "emotion"                  # {emotion} — robot-face expression synced to content
    ERROR = "error"                      # {message}
    PONG = "pong"


class Phase(str, Enum):
    """The conversation state machine's states (also sent as ``state_change``)."""
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"


class Mode(str, Enum):
    """What Maxi is doing. Extensible — add a mode, register a skill."""
    IDLE = "idle"
    GENERAL_CHAT = "general_chat"
    MATH_GESTURE = "math_gesture"

    @classmethod
    def from_wire(cls, value: Optional[str]) -> "Mode":
        try:
            return cls(value)
        except (ValueError, TypeError):
            return cls.GENERAL_CHAT


# --- Outbound message builders (always include type + timestamp) -------------

def _msg(type_: Outgoing, **fields: Any) -> Dict[str, Any]:
    return {"type": type_.value, "timestamp": _now(), **fields}


def state_change(state: Phase | str, **extra: Any) -> Dict[str, Any]:
    return _msg(Outgoing.STATE_CHANGE, state=str(getattr(state, "value", state)), **extra)


def transcription(text: str) -> Dict[str, Any]:
    return _msg(Outgoing.TRANSCRIPTION, text=text)


def response_start(stream_id: str = "default") -> Dict[str, Any]:
    return _msg(Outgoing.RESPONSE_START, streamId=stream_id)


def response_chunk(text: str, stream_id: str = "default") -> Dict[str, Any]:
    return _msg(Outgoing.RESPONSE_CHUNK, text=text, streamId=stream_id)


def response_complete(stream_id: str = "default") -> Dict[str, Any]:
    return _msg(Outgoing.RESPONSE_COMPLETE, streamId=stream_id)


def response(text: str) -> Dict[str, Any]:
    return _msg(Outgoing.RESPONSE, text=text, streaming=False)


def audio_chunk(audio_base64: str, fmt: str = "mp3") -> Dict[str, Any]:
    return _msg(Outgoing.AUDIO_CHUNK, audio=audio_base64, format=fmt)


def speaking_script(text: str) -> Dict[str, Any]:
    """Tell the tablet exactly what Maxi is saying now (Layer-2 echo rejection)."""
    return _msg(Outgoing.SPEAKING_SCRIPT, text=text)


def finger_pose(pose: Dict[str, Any]) -> Dict[str, Any]:
    return _msg(Outgoing.FINGER_POSE, pose=pose)


def math_result(a: Any, b: Any, op: str, result: Any, explanation: str, mode: str) -> Dict[str, Any]:
    """Drive the math UI: equation display + (for finger_counting) UI hand animation."""
    return _msg(Outgoing.MATH_RESULT, A=a, B=b, OP=op, result=result,
                explanation=explanation, mode=mode)


def math_advanced(original_question: str, result: Any, steps: list,
                  breakdown: str = "", explanation: str = "") -> Dict[str, Any]:
    """Drive the step-by-step UI (word problems / multi-step): renders a step list."""
    return _msg(Outgoing.MATH_RESULT, mode="advanced", original_question=original_question,
                result=result, steps=steps, breakdown=breakdown, explanation=explanation)


def highlight_step(step_number: int) -> Dict[str, Any]:
    """Highlight the given step in the UI while Maxi explains it."""
    return _msg(Outgoing.HIGHLIGHT_STEP, step_number=step_number)


# Robot-face expressions the tablet knows how to render.
EMOTIONS = ("neutral", "happy", "excited", "curious", "sad")


def emotion(name: str) -> Dict[str, Any]:
    """Set the robot face's expression (happy | excited | curious | sad | neutral)."""
    name = name if name in EMOTIONS else "neutral"
    return _msg(Outgoing.EMOTION, emotion=name)


def error(message: str) -> Dict[str, Any]:
    return _msg(Outgoing.ERROR, message=message)


def pong() -> Dict[str, Any]:
    return _msg(Outgoing.PONG)
