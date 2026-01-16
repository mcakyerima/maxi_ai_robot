# brain/safety/__init__.py
"""
Safety and parental control module for Maxi AI Robot.
Provides content filtering, usage tracking, and session management.
"""

from .content_filter import ContentFilter, filter_input, filter_output
from .rate_limiter import RateLimiter, check_rate_limit
from .usage_tracker import (
    UsageTracker,
    log_question,
    log_filter_event,
    get_today_stats,
    get_weekly_topics,
    get_filter_events,
    start_session,
    end_session
)


def get_system_status() -> dict:
    """
    Get status of all safety systems for startup display.
    Returns dict with status of each component.
    """
    try:
        # Check if instances exist and are working
        status = {
            'content_filter': 'Active',
            'rate_limiter': 'Active',
            'usage_tracker': 'Active',
            'session_timer': 'Active'
        }

        # Quick validation checks
        try:
            _ = ContentFilter()
            status['content_filter'] = 'Active ✓'
        except Exception:
            status['content_filter'] = 'Error'

        try:
            _ = RateLimiter()
            status['rate_limiter'] = 'Active ✓'
        except Exception:
            status['rate_limiter'] = 'Error'

        try:
            _ = UsageTracker()
            status['usage_tracker'] = 'Active ✓'
        except Exception:
            status['usage_tracker'] = 'Error'

        return status

    except Exception as e:
        return {
            'content_filter': 'Unknown',
            'rate_limiter': 'Unknown',
            'usage_tracker': 'Unknown',
            'session_timer': 'Unknown',
            'error': str(e)
        }


__all__ = [
    'ContentFilter',
    'filter_input',
    'filter_output',
    'RateLimiter',
    'check_rate_limit',
    'UsageTracker',
    'log_question',
    'log_filter_event',
    'get_today_stats',
    'get_weekly_topics',
    'get_filter_events',
    'start_session',
    'end_session',
    'get_system_status'
]
