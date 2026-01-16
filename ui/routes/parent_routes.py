# ui/routes/parent_routes.py
"""
Parent Dashboard routes with PIN authentication and statistics API.
"""

import os
from flask import Blueprint, render_template, jsonify, request

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not required in production

# Import safety functions with error handling
try:
    from brain.safety.usage_tracker import get_today_stats, get_weekly_topics, get_filter_events
except ImportError as e:
    print(f"Warning: Could not import usage tracker functions: {e}")
    # Provide fallback functions

    def get_today_stats():
        return {"time": 0, "questions": 0, "math": 0, "chat": 0}

    def get_weekly_topics():
        return []

    def get_filter_events():
        return []

# Create blueprint
parent_dashboard_bp = Blueprint(
    'parent_dashboard', __name__, url_prefix='/api/parent-dashboard')

# Get PIN from environment (default: 1234 for testing)
PARENT_PIN = os.getenv("PARENT_DASHBOARD_PIN", "1234")


@parent_dashboard_bp.route('/verify-pin', methods=['POST'])
def verify_pin():
    """
    Verify parent dashboard PIN.

    POST /api/parent-dashboard/verify-pin
    Body: {"pin": "1234"}
    Returns: {"success": true/false}
    """
    try:
        data = request.get_json()
        pin = data.get('pin', '')

        if pin == PARENT_PIN:
            return jsonify({'success': True}), 200
        else:
            return jsonify({'success': False, 'error': 'Invalid PIN'}), 401
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@parent_dashboard_bp.route('/today-stats', methods=['GET'])
def today_stats():
    """
    Get today's usage statistics.

    GET /api/parent-dashboard/today-stats
    Returns: {
        "date": "2026-01-16",
        "total_sessions": 3,
        "total_questions": 47,
        "total_time_minutes": 83,
        "chat_questions": 35,
        "math_questions": 12
    }
    """
    try:
        stats = get_today_stats()
        return jsonify(stats), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@parent_dashboard_bp.route('/weekly-topics', methods=['GET'])
def weekly_topics():
    """
    Get most common learning topics from past 7 days.

    GET /api/parent-dashboard/weekly-topics
    Returns: {
        "topics": [
            {"topic": "Solar System", "count": 5},
            {"topic": "Mathematics", "count": 12}
        ]
    }
    """
    try:
        topics = get_weekly_topics()
        return jsonify({'topics': topics}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@parent_dashboard_bp.route('/safety-events', methods=['GET'])
def safety_events():
    """
    Get recent content filtering events.

    GET /api/parent-dashboard/safety-events?days=7
    Returns: {
        "events": [
            {
                "timestamp": "2026-01-16T10:30:00",
                "filter_type": "input",
                "reason": "inappropriate_keyword:weapon"
            }
        ]
    }
    """
    try:
        days = int(request.args.get('days', 7))
        events = get_filter_events(days=days)
        return jsonify({'events': events}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Dashboard page route (not under /api prefix)
# Note: Using separate blueprint without URL prefix for the page route

dashboard_page_bp = Blueprint('dashboard_page', __name__)


@dashboard_page_bp.route('/parent-dashboard')
def parent_dashboard_page():
    """Render the parent dashboard HTML page."""
    return render_template('parent_dashboard.html')
