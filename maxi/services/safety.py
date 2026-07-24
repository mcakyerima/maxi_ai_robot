"""
maxi.services.safety — child-safety guard rails behind one clean interface.

Wraps the existing, working ``brain.safety`` implementation (content filter,
rate limiter, usage tracker) so the new brain gets battle-tested keyword/pattern
filtering without re-deriving word lists. Imports are lazy so pulling in this
module has no import-time side effects (the legacy package opens a SQLite DB on
import).
"""
from __future__ import annotations

import logging
from typing import Tuple

logger = logging.getLogger("maxi.safety")


class Safety:
    def check_input(self, text: str, session_id: str = "") -> Tuple[bool, str]:
        """Return (is_safe, kid_friendly_fallback_if_unsafe)."""
        try:
            from brain.safety import filter_input
            is_safe, _reason, fallback = filter_input(text, session_id)
            return is_safe, (fallback or "Let's talk about something fun and safe instead!")
        except Exception as exc:  # noqa: BLE001
            logger.warning("input filter unavailable: %s", exc)
            return True, ""

    def clean_output(self, text: str) -> Tuple[bool, str]:
        """Return (is_safe, sanitized_text)."""
        try:
            from brain.safety import filter_output
            return filter_output(text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("output filter unavailable: %s", exc)
            return True, text

    def rate_limit(self, session_id: str, mode: str = "chat") -> Tuple[bool, str]:
        """Return (is_allowed, warning_message_if_any)."""
        try:
            from brain.safety import check_rate_limit
            allowed, warning, _stats = check_rate_limit(session_id, mode)
            return allowed, (warning or "")
        except Exception as exc:  # noqa: BLE001
            logger.warning("rate limiter unavailable: %s", exc)
            return True, ""

    def log_question(self, session_id: str, question: str, mode: str, topic: str = "") -> None:
        try:
            from brain.safety import log_question
            log_question(session_id, question, mode, topic or None)
        except Exception:  # noqa: BLE001
            pass

    def log_filter_event(self, session_id: str, filtered: str, reason: str) -> None:
        try:
            from brain.safety import log_filter_event
            log_filter_event(session_id, "input", filtered, reason)
        except Exception:  # noqa: BLE001
            pass
