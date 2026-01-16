# handlers/time_handler.py
"""
Time handler for Maxi AI.
Provides kid-friendly time/date responses with humor and LLM fallback.
"""

import re
from datetime import datetime
import random
from ui.socket_server import SocketServer
from voice.speaker import SmoothTTSEngine
from utils.logger import log_info, log_error
from brain.context_manager.context_manager import context_manager

# Time patterns
TIME_PATTERNS = [
    r"\b(time|clock|hour|what time|current time)\b",
    r"\b(tell me|what is|what's) the time\b",
    r"\bhow (late|early) is it\b"
]

# Date patterns
DATE_PATTERNS = [
    r"\b(date|day|today|tomorrow|yesterday)\b",
    r"\bwhat(?:'s| is) (?:the )?(date|day)\b",
    r"\bwhich day (is|are) we(?: in)?\b"
]

# Time responses
TIME_RESPONSES = [
    "The clock says {time}, but my robot watch says it's time for fun!",
    "Beep boop! According to my circuits, it's {time} sharp!",
    "It's {time}! Time flies when you're learning cool stuff!",
    "Ding dong! The time is {time}. Perfect time for a snack break!",
    "My super-accurate robot clock shows {time}. Well, mostly accurate!",
    "If I had a watch, it would show {time}. But I tell time with math magic!"
]

# Date responses
DATE_RESPONSES = {
    "Monday": [
        "Monday again! Let's start the week with big smiles!",
        "It's Monday! The day we discover new adventures!",
        "Happy Monday! Did you know robots don't get Monday blues?"
    ],
    "Tuesday": [
        "Tuesday! Two days of learning already this week!",
        "It's Tuesday! My second favorite T-day after Today!",
        "Happy Tuesday! Let's make it a terrific day!"
    ],
    "Wednesday": [
        "Wednesday! We're halfway through the week!",
        "It's Wednesday! Also known as 'hump day' (though camels explain that better)!",
        "Happy Wednesday! The day when even robots say 'Whoo-hoo!'"
    ],
    "Thursday": [
        "Thursday! One more day until Friday fun!",
        "It's Thursday! The day we practice our thankful thoughts!",
        "Happy Thursday! Almost there, little champion!"
    ],
    "Friday": [
        "Friday! High five... if you had five hands!",
        "It's Friday! The day even robots dance! Beep boop shake!",
        "Happy Friday! Tomorrow I'll be recharging my humor circuits!"
    ],
    "Saturday": [
        "Saturday! My favorite S-word after Science and Snacks!",
        "It's Saturday! Weekend means extra time for fun learning!"
    ],
    "Sunday": [
        "Sunday! A great day to relax and recharge!",
        "It's Sunday! My circuits are programmed to say 'happy family day'!"
    ]
}

# Generic date fallbacks
GENERIC_DATE_RESPONSES = [
    "Today is {date}. A perfect day to learn something new!",
    "My calendar says it's {date}. I'm always ready to help!",
    "It's {date}! My favorite day is today because you're here!"
]

def get_current_time():
    """Returns formatted current time (e.g., '3:45 PM')"""
    return datetime.now().strftime("%I:%M %p").lstrip("0")

def get_current_date():
    """Returns formatted date (e.g., 'Tuesday, October 17, 2023')"""
    return datetime.now().strftime("%A, %B %d, %Y")

def get_day_of_week():
    """Returns current day name (e.g., 'Wednesday')"""
    return datetime.now().strftime("%A")

def is_time_question(prompt: str) -> bool:
    """Check if prompt is asking for time using regex patterns"""
    prompt_lower = prompt.lower()
    return any(re.search(pattern, prompt_lower) for pattern in TIME_PATTERNS)

def is_date_question(prompt: str) -> bool:
    """Check if prompt is asking for date using regex patterns"""
    prompt_lower = prompt.lower()
    return any(re.search(pattern, prompt_lower) for pattern in DATE_PATTERNS)

def create_time_response():
    """Generate kid-friendly time response"""
    time = get_current_time()
    return random.choice(TIME_RESPONSES).format(time=time)

def create_date_response():
    """Generate kid-friendly date response with day-specific humor"""
    day = get_day_of_week()
    date = get_current_date()
    
    if day in DATE_RESPONSES:
        return random.choice(DATE_RESPONSES[day])
    return random.choice(GENERIC_DATE_RESPONSES).format(date=date)

async def handle_time_date(prompt: str, tts_engine: SmoothTTSEngine, socket: SocketServer):
    """
    Handle time/date requests with:
    - Regex pattern matching
    - Complete day coverage
    - Kid-friendly humor
    - LLM fallback when needed
    """
    try:
        log_info(f"⏰ Handling time/date request: {prompt}")
        
        # Determine request type
        asking_time = is_time_question(prompt)
        asking_date = is_date_question(prompt)
        
        if not (asking_time or asking_date):
            log_info("Not a clear time/date question, passing to LLM")
            return None  # Signal to fall back to LLM

        if asking_time:
            response = create_time_response()
        else:
            response = create_date_response()

        log_info(f"Time/date response: {response}")
        await socket.emit_response(response)
        await tts_engine.speak_text(response)
        return response

    except Exception as e:
        log_error(f"Time handler error: {e}")
        # On failure, pass context to LLM
        time_context = {
            "current_time": get_current_time(),
            "current_date": get_current_date(),
            "original_question": prompt
        }
        return None  # Signal to fall back to LLM with context