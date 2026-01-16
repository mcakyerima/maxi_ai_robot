"""
Init file for the handlers package.
Makes the handlers into a proper package.
"""

# Import handlers for easier access
from brain.handlers.humor_handler import handle_humor
from brain.handlers.weather_handler import handle_weather
from brain.handlers.vision_handler import handle_vision
from brain.handlers.math_handler import handle_math
from brain.handlers.gesture_handler import handle_gesture
from brain.handlers.ollama_handler import handle_ollama, prewarm_model

__all__ = [
    'handle_humor',
    'handle_weather',
    'handle_vision',
    'handle_math',
    'handle_gesture',
    'handle_ollama',
    'prewarm_model'
]
