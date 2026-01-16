# brain/safety/usage_tracker.py
"""
Usage tracking system for parental monitoring and statistics.
Logs questions, session data, and learning metrics to SQLite database.
"""

import sqlite3
import uuid
from datetime import datetime, date
from typing import Optional, Dict, List
from pathlib import Path
from utils.logger import log_info, log_error


class UsageTracker:
    """
    Tracks usage patterns, questions, and learning metrics.
    Stores data in the same SQLite database as context manager.
    """

    DB_PATH = Path(__file__).parent.parent.parent / "context_memory.db"

    def __init__(self):
        self.current_session_id = None
        self.ensure_tables()

    def ensure_tables(self):
        """Create usage tracking tables if they don't exist."""
        try:
            conn = sqlite3.connect(str(self.DB_PATH))
            cursor = conn.cursor()

            # Usage sessions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS usage_sessions (
                    session_id TEXT PRIMARY KEY,
                    start_time TIMESTAMP NOT NULL,
                    end_time TIMESTAMP,
                    mode TEXT NOT NULL,
                    questions_count INTEGER DEFAULT 0,
                    duration_minutes INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Daily statistics table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_statistics (
                    date DATE PRIMARY KEY,
                    total_sessions INTEGER DEFAULT 0,
                    total_questions INTEGER DEFAULT 0,
                    total_time_minutes INTEGER DEFAULT 0,
                    chat_questions INTEGER DEFAULT 0,
                    math_questions INTEGER DEFAULT 0,
                    topics_covered TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Content filters table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS content_filters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    filter_type TEXT NOT NULL,
                    filtered_content TEXT,
                    reason TEXT,
                    FOREIGN KEY (session_id) REFERENCES usage_sessions(session_id)
                )
            """)

            # Question logs table (for topic tracking)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS question_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    question TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    topic TEXT,
                    FOREIGN KEY (session_id) REFERENCES usage_sessions(session_id)
                )
            """)

            # Create indexes for performance
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_date 
                ON usage_sessions(start_time)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_filters_session 
                ON content_filters(session_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_questions_session 
                ON question_logs(session_id)
            """)

            conn.commit()
            conn.close()
            log_info("✅ Usage tracking tables initialized")
        except Exception as e:
            log_error(f"❌ Failed to create usage tracking tables: {e}")

    def start_session(self, mode: str = "chat") -> str:
        """
        Start a new usage session.

        Args:
            mode: Session mode (chat, math)

        Returns:
            session_id: Unique session identifier
        """
        session_id = f"{mode}_{uuid.uuid4().hex[:12]}"
        self.current_session_id = session_id

        try:
            conn = sqlite3.connect(str(self.DB_PATH))
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO usage_sessions (session_id, start_time, mode)
                VALUES (?, ?, ?)
            """, (session_id, datetime.now(), mode))

            conn.commit()
            conn.close()

            log_info(f"📝 Started session: {session_id} (mode: {mode})")
            return session_id
        except Exception as e:
            log_error(f"❌ Failed to start session: {e}")
            return session_id

    def end_session(self, session_id: str):
        """Mark session as ended and calculate duration."""
        try:
            conn = sqlite3.connect(str(self.DB_PATH))
            cursor = conn.cursor()

            # Get start time
            cursor.execute("""
                SELECT start_time FROM usage_sessions WHERE session_id = ?
            """, (session_id,))
            result = cursor.fetchone()

            if result:
                start_time = datetime.fromisoformat(result[0])
                end_time = datetime.now()
                duration_minutes = int(
                    (end_time - start_time).total_seconds() / 60)

                cursor.execute("""
                    UPDATE usage_sessions 
                    SET end_time = ?, duration_minutes = ?
                    WHERE session_id = ?
                """, (end_time, duration_minutes, session_id))

                conn.commit()
                log_info(
                    f"📊 Ended session: {session_id} (duration: {duration_minutes} mins)")

            conn.close()
        except Exception as e:
            log_error(f"❌ Failed to end session: {e}")

    def log_question(
        self,
        session_id: str,
        question: str,
        mode: str,
        topic: Optional[str] = None
    ):
        """
        Log a question for tracking and analytics.

        Args:
            session_id: Session identifier
            question: User question text
            mode: Mode (chat, math)
            topic: Optional topic category
        """
        try:
            conn = sqlite3.connect(str(self.DB_PATH))
            cursor = conn.cursor()

            # Insert question log
            cursor.execute("""
                INSERT INTO question_logs (session_id, question, mode, topic)
                VALUES (?, ?, ?, ?)
            """, (session_id, question, mode, topic))

            # Update session question count
            cursor.execute("""
                UPDATE usage_sessions 
                SET questions_count = questions_count + 1
                WHERE session_id = ?
            """, (session_id,))

            # Update daily statistics
            today = date.today()
            cursor.execute("""
                INSERT INTO daily_statistics (date, total_questions)
                VALUES (?, 1)
                ON CONFLICT(date) DO UPDATE SET
                    total_questions = total_questions + 1,
                    updated_at = CURRENT_TIMESTAMP
            """, (today,))

            # Update mode-specific counts
            if mode == "chat":
                cursor.execute("""
                    UPDATE daily_statistics 
                    SET chat_questions = chat_questions + 1
                    WHERE date = ?
                """, (today,))
            elif mode == "math":
                cursor.execute("""
                    UPDATE daily_statistics 
                    SET math_questions = math_questions + 1
                    WHERE date = ?
                """, (today,))

            conn.commit()
            conn.close()
            log_info(f"✅ Logged question for session {session_id}")
        except Exception as e:
            log_error(f"❌ Failed to log question: {e}")

    def log_filter_event(
        self,
        session_id: str,
        filter_type: str,
        filtered_content: str,
        reason: str
    ):
        """
        Log a content filtering event for parental review.

        Args:
            session_id: Session identifier
            filter_type: Type of filter (input/output)
            filtered_content: Content that was filtered
            reason: Reason for filtering
        """
        try:
            conn = sqlite3.connect(str(self.DB_PATH))
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO content_filters (session_id, filter_type, filtered_content, reason)
                VALUES (?, ?, ?, ?)
            """, (session_id, filter_type, filtered_content, reason))

            conn.commit()
            conn.close()
            log_info(
                f"🛡️ Logged filter event for session {session_id}: {reason}")
        except Exception as e:
            log_error(f"❌ Failed to log filter event: {e}")

    def get_today_stats(self) -> Dict:
        """Get today's usage statistics."""
        try:
            conn = sqlite3.connect(str(self.DB_PATH))
            cursor = conn.cursor()

            today = date.today()
            cursor.execute("""
                SELECT 
                    total_sessions,
                    total_questions,
                    total_time_minutes,
                    chat_questions,
                    math_questions
                FROM daily_statistics
                WHERE date = ?
            """, (today,))

            result = cursor.fetchone()
            conn.close()

            if result:
                return {
                    'date': today.isoformat(),
                    'total_sessions': result[0] or 0,
                    'total_questions': result[1] or 0,
                    'total_time_minutes': result[2] or 0,
                    'chat_questions': result[3] or 0,
                    'math_questions': result[4] or 0
                }
            else:
                return {
                    'date': today.isoformat(),
                    'total_sessions': 0,
                    'total_questions': 0,
                    'total_time_minutes': 0,
                    'chat_questions': 0,
                    'math_questions': 0
                }
        except Exception as e:
            log_error(f"❌ Failed to get today's stats: {e}")
            return {}

    def get_weekly_topics(self) -> List[Dict]:
        """Get most common topics from past 7 days."""
        try:
            conn = sqlite3.connect(str(self.DB_PATH))
            cursor = conn.cursor()

            cursor.execute("""
                SELECT topic, COUNT(*) as count
                FROM question_logs
                WHERE timestamp >= date('now', '-7 days')
                    AND topic IS NOT NULL
                GROUP BY topic
                ORDER BY count DESC
                LIMIT 10
            """)

            results = cursor.fetchall()
            conn.close()

            return [
                {'topic': row[0], 'count': row[1]}
                for row in results
            ]
        except Exception as e:
            log_error(f"❌ Failed to get weekly topics: {e}")
            return []

    def get_filter_events(self, days: int = 7) -> List[Dict]:
        """Get recent content filter events."""
        try:
            conn = sqlite3.connect(str(self.DB_PATH))
            cursor = conn.cursor()

            cursor.execute("""
                SELECT timestamp, filter_type, reason
                FROM content_filters
                WHERE timestamp >= date('now', '-' || ? || ' days')
                ORDER BY timestamp DESC
                LIMIT 20
            """, (days,))

            results = cursor.fetchall()
            conn.close()

            return [
                {
                    'timestamp': row[0],
                    'filter_type': row[1],
                    'reason': row[2]
                }
                for row in results
            ]
        except Exception as e:
            log_error(f"❌ Failed to get filter events: {e}")
            return []


# Global tracker instance
_tracker = UsageTracker()


def start_session(mode: str = "chat") -> str:
    """Start a new usage tracking session."""
    return _tracker.start_session(mode)


def end_session(session_id: str):
    """End a usage tracking session."""
    _tracker.end_session(session_id)


def log_question(
    session_id: str,
    question: str,
    mode: str,
    topic: Optional[str] = None
):
    """Log a question for tracking."""
    _tracker.log_question(session_id, question, mode, topic)


def log_filter_event(
    session_id: str,
    filter_type: str,
    filtered_content: str,
    reason: str
):
    """Log a content filtering event."""
    _tracker.log_filter_event(session_id, filter_type,
                              filtered_content, reason)


def get_today_stats() -> Dict:
    """Get today's usage statistics."""
    return _tracker.get_today_stats()


def get_weekly_topics() -> List[Dict]:
    """Get most common topics from past 7 days."""
    return _tracker.get_weekly_topics()


def get_filter_events(days: int = 7) -> List[Dict]:
    """Get recent content filter events."""
    return _tracker.get_filter_events(days)
