"""
maxi.config — one typed source of truth for all runtime settings.

Replaces the scattered ``os.getenv(...)`` calls that were spread across ~15
modules in v1. Import ``settings`` anywhere:

    from maxi.config import settings
    client = Groq(api_key=settings.llm.api_key)

Every value is read from the environment once, at import time, with sensible
defaults so the app boots even with a bare ``.env``.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _get(name: str, default: str) -> str:
    return os.getenv(name, default)


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _get_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class LLMSettings:
    """Groq LLM (free tier) — the reasoning engine."""
    api_key: str = field(default_factory=lambda: _get("GROQ_API_KEY", ""))
    # llama-3.1-8b-instant: fast + the largest free-tier daily token budget, and
    # plenty for short kid-friendly answers. (compound-* / 70b models share the
    # small 100k tokens/day free limit and run out fast.)
    model: str = field(default_factory=lambda: _get("GROQ_MODEL", "llama-3.1-8b-instant"))
    temperature: float = field(default_factory=lambda: _get_float("LLM_TEMPERATURE", 0.7))
    max_tokens: int = field(default_factory=lambda: _get_int("LLM_MAX_TOKENS", 120))
    top_p: float = field(default_factory=lambda: _get_float("LLM_TOP_P", 0.9))

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)


@dataclass(frozen=True)
class TTSSettings:
    """Microsoft Edge-TTS (free) — streamed to the tablet as audio chunks."""
    voice: str = field(default_factory=lambda: _get("TTS_VOICE", "en-US-EmmaNeural"))
    rate: str = field(default_factory=lambda: _get("TTS_RATE", "+0%"))
    pitch: str = field(default_factory=lambda: _get("TTS_PITCH", "-2Hz"))


@dataclass(frozen=True)
class HandsSettings:
    """Raspberry Pi finger/wrist controller (HTTP)."""
    # A full URL (e.g. an ngrok tunnel "https://xxxx.ngrok.io") wins if set;
    # otherwise we build one from ip:port.
    pi_url_override: str = field(default_factory=lambda: _get("RASPBERRY_PI_URL", ""))
    pi_ip: str = field(default_factory=lambda: _get("RASPBERRY_PI_IP", "192.168.1.100"))
    pi_port: int = field(default_factory=lambda: _get_int("RASPBERRY_PI_PORT", 5001))
    api_key: str = field(default_factory=lambda: _get("MAXI_HAND_API_KEY", ""))
    simulation: bool = field(default_factory=lambda: _get_bool("FINGER_SIMULATION_MODE", False))
    request_timeout: float = field(default_factory=lambda: _get_float("HANDS_TIMEOUT", 8.0))

    @property
    def base_url(self) -> str:
        if self.pi_url_override:
            return self.pi_url_override.rstrip("/")
        return f"http://{self.pi_ip}:{self.pi_port}"


@dataclass(frozen=True)
class ServerSettings:
    """Flask + Socket.IO gateway."""
    host: str = field(default_factory=lambda: _get("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: _get_int("PORT", 5002))
    debug: bool = field(default_factory=lambda: _get_bool("DEBUG", False))
    parent_pin: str = field(default_factory=lambda: _get("PARENT_DASHBOARD_PIN", "1234"))


@dataclass(frozen=True)
class SafetySettings:
    """Guard rails for a kids' product."""
    session_minutes: int = field(default_factory=lambda: _get_int("SESSION_LIMIT_MINUTES", 60))
    hourly_question_limit: int = field(default_factory=lambda: _get_int("HOURLY_QUESTION_LIMIT", 60))
    session_question_limit: int = field(default_factory=lambda: _get_int("SESSION_QUESTION_LIMIT", 100))


@dataclass(frozen=True)
class IntegrationsSettings:
    weather_api_key: str = field(default_factory=lambda: _get("OPENWEATHER_API_KEY", ""))


@dataclass(frozen=True)
class MemorySettings:
    """Lightweight long-term memory: a SQLite store of the child's facts + a
    rolling conversation summary. Zero heavy deps (stdlib ``sqlite3`` only) — the
    embedding-based ``brain/context_manager`` is deliberately NOT used so the
    Railway image stays lean."""
    enabled: bool = field(default_factory=lambda: _get_bool("MAXI_MEMORY_ENABLED", True))
    # Empty → defaults to <repo>/data/maxi_memory.db (see memory.py). Point this at
    # a Railway volume for durability across redeploys; the default FS is ephemeral.
    db_path: str = field(default_factory=lambda: _get("MAXI_MEMORY_DB", ""))
    # One robot ≈ one child household by default. Bump to support multiple profiles.
    child_id: str = field(default_factory=lambda: _get("MAXI_CHILD_ID", "default"))
    window_turns: int = field(default_factory=lambda: _get_int("MAXI_MEMORY_WINDOW_TURNS", 12))
    # Regenerate the rolling summary every N assistant turns (needs the LLM).
    summarize_every: int = field(default_factory=lambda: _get_int("MAXI_MEMORY_SUMMARIZE_EVERY", 6))
    max_facts_recall: int = field(default_factory=lambda: _get_int("MAXI_MEMORY_MAX_FACTS", 8))
    max_topics_recall: int = field(default_factory=lambda: _get_int("MAXI_MEMORY_MAX_TOPICS", 5))


@dataclass(frozen=True)
class Settings:
    """Top-level settings aggregate. Access via the module-level ``settings``."""
    llm: LLMSettings = field(default_factory=LLMSettings)
    tts: TTSSettings = field(default_factory=TTSSettings)
    hands: HandsSettings = field(default_factory=HandsSettings)
    server: ServerSettings = field(default_factory=ServerSettings)
    safety: SafetySettings = field(default_factory=SafetySettings)
    integrations: IntegrationsSettings = field(default_factory=IntegrationsSettings)
    memory: MemorySettings = field(default_factory=MemorySettings)

    # Persona / location context used by the tutoring system prompt.
    persona_name: str = field(default_factory=lambda: _get("MAXI_NAME", "Maxi"))
    location: str = field(default_factory=lambda: _get("MAXI_LOCATION", "Maiduguri, Borno State, Nigeria"))
    creator: str = field(default_factory=lambda: _get("MAXI_CREATOR", "Mohammed Kaka"))
    company: str = field(default_factory=lambda: _get("MAXI_COMPANY", "Maxeeton Technology"))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()


settings = get_settings()
