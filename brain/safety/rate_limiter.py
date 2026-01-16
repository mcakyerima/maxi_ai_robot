# brain/safety/rate_limiter.py
"""
Rate limiter to prevent API abuse and encourage healthy usage patterns.
"""

import time
from typing import Dict, Tuple, Optional
from datetime import datetime, timedelta
from collections import deque
from utils.logger import log_info, log_warning


class RateLimiter:
    """
    Rate limiting system to encourage healthy usage patterns.
    Limits questions per hour and tracks session duration.
    """

    # Configuration
    MAX_QUESTIONS_PER_HOUR = 60  # Approx 1 question per minute
    MAX_QUESTIONS_PER_SESSION = 100  # Hard limit per session
    WARNING_THRESHOLD = 0.8  # Warn at 80% of limit

    # Break reminders
    BREAK_REMINDERS = {
        30: "Great job learning! Maybe take a quick 5-minute break?",
        45: "You've been learning a lot! Time to rest your eyes and stretch!",
        60: "Wow, an hour of learning! Let's take a real break now. Come back soon!",
    }

    def __init__(self):
        self.sessions: Dict[str, 'SessionData'] = {}

    def check_limit(
        self,
        session_id: str,
        mode: str = "chat"
    ) -> Tuple[bool, Optional[str], dict]:
        """
        Check if request should be allowed based on rate limits.

        Args:
            session_id: Unique session identifier
            mode: Mode of operation (chat, math)

        Returns:
            Tuple of (is_allowed, warning_message, stats)
            - is_allowed: True if request can proceed
            - warning_message: Optional message about limits
            - stats: Current session statistics
        """
        # Get or create session data
        if session_id not in self.sessions:
            self.sessions[session_id] = SessionData(session_id, mode)

        session = self.sessions[session_id]
        current_time = time.time()

        # Clean old requests (older than 1 hour)
        session.clean_old_requests(current_time)

        # Check hard session limit
        if session.total_questions >= self.MAX_QUESTIONS_PER_SESSION:
            log_warning(
                f"🛑 Session {session_id} reached hard limit: {session.total_questions}")
            return (
                False,
                "You've asked so many great questions today! Let's take a break and come back tomorrow!",
                session.get_stats()
            )

        # Check hourly limit
        questions_last_hour = len(session.recent_questions)
        if questions_last_hour >= self.MAX_QUESTIONS_PER_HOUR:
            log_warning(
                f"🛑 Session {session_id} exceeded hourly limit: {questions_last_hour}")
            return (
                False,
                "Let's slow down a bit! Take a 10-minute break, then we can keep learning!",
                session.get_stats()
            )

        # Check for break reminders based on duration
        session_minutes = session.get_duration_minutes()
        warning_message = None

        for threshold, message in self.BREAK_REMINDERS.items():
            if (session_minutes >= threshold and
                    not session.break_warnings_given.get(threshold, False)):
                warning_message = message
                session.break_warnings_given[threshold] = True
                log_info(
                    f"⏰ Break reminder at {threshold} mins for session {session_id}")
                break

        # Warning at 80% of hourly limit
        if questions_last_hour >= int(self.MAX_QUESTIONS_PER_HOUR * self.WARNING_THRESHOLD):
            if not warning_message:
                remaining = self.MAX_QUESTIONS_PER_HOUR - questions_last_hour
                warning_message = f"You're doing great! Just {remaining} more questions this hour, then we'll rest!"

        # Record this request
        session.add_question(current_time)

        log_info(
            f"✅ Rate limit OK - Session {session_id}: {questions_last_hour}/{self.MAX_QUESTIONS_PER_HOUR} last hour")

        return (True, warning_message, session.get_stats())

    def get_session_stats(self, session_id: str) -> Optional[dict]:
        """Get statistics for a specific session."""
        if session_id in self.sessions:
            return self.sessions[session_id].get_stats()
        return None

    def end_session(self, session_id: str) -> dict:
        """Mark session as ended and return final statistics."""
        if session_id in self.sessions:
            session = self.sessions[session_id]
            session.end_time = time.time()
            stats = session.get_stats()
            log_info(f"📊 Session {session_id} ended - {stats}")
            return stats
        return {}

    def cleanup_old_sessions(self, max_age_hours: int = 24):
        """Remove sessions older than max_age_hours."""
        current_time = time.time()
        cutoff = current_time - (max_age_hours * 3600)

        old_sessions = [
            sid for sid, session in self.sessions.items()
            if session.start_time < cutoff
        ]

        for sid in old_sessions:
            del self.sessions[sid]
            log_info(f"🧹 Cleaned up old session: {sid}")

        return len(old_sessions)


class SessionData:
    """Data structure for tracking individual session metrics."""

    def __init__(self, session_id: str, mode: str):
        self.session_id = session_id
        self.mode = mode
        self.start_time = time.time()
        self.end_time = None
        self.recent_questions = deque()  # Timestamps of recent questions
        self.total_questions = 0
        self.break_warnings_given = {}  # Track which warnings were shown

    def add_question(self, timestamp: float):
        """Record a new question."""
        self.recent_questions.append(timestamp)
        self.total_questions += 1

    def clean_old_requests(self, current_time: float):
        """Remove requests older than 1 hour."""
        cutoff = current_time - 3600  # 1 hour ago
        while self.recent_questions and self.recent_questions[0] < cutoff:
            self.recent_questions.popleft()

    def get_duration_minutes(self) -> int:
        """Get session duration in minutes."""
        end = self.end_time or time.time()
        return int((end - self.start_time) / 60)

    def get_stats(self) -> dict:
        """Get current session statistics."""
        return {
            'session_id': self.session_id,
            'mode': self.mode,
            'duration_minutes': self.get_duration_minutes(),
            'total_questions': self.total_questions,
            'questions_last_hour': len(self.recent_questions),
            'start_time': datetime.fromtimestamp(self.start_time).isoformat(),
            'is_active': self.end_time is None
        }


# Global rate limiter instance
_rate_limiter = RateLimiter()


def check_rate_limit(
    session_id: str,
    mode: str = "chat"
) -> Tuple[bool, Optional[str], dict]:
    """
    Convenience function to check rate limits.

    Args:
        session_id: Unique session identifier
        mode: Mode of operation (chat, math)

    Returns:
        Tuple of (is_allowed, warning_message, stats)
    """
    return _rate_limiter.check_limit(session_id, mode)


def get_session_stats(session_id: str) -> Optional[dict]:
    """Get statistics for a specific session."""
    return _rate_limiter.get_session_stats(session_id)


def end_session(session_id: str) -> dict:
    """Mark session as ended and return final statistics."""
    return _rate_limiter.end_session(session_id)
