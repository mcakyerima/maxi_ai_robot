# Stub for handlers/vision_handler.py
"""
Vision handler for Maxi AI.
Placeholder for future computer vision functionality.
"""

import random
from voice.speaker import SmoothTTSEngine
from utils.logger import log_info

# Placeholder responses for vision capabilities
VISION_RESPONSES = [
    "I can see you! You look fantastic today!",
    "I can see about 3 people in front of me. Hello everyone!",
    "I spotted something colorful! Is that your favorite shirt?",
    "I see someone waving at me! Hello there!",
    "My camera shows a smiling face! That's a great smile!",
    "I can see the classroom! It looks like a fun place to learn!",
    "I noticed someone holding a book! Reading is a wonderful adventure!",
    "My vision sensors detect movement! Are you dancing?",
    "I can see the sun shining through the window! What a beautiful day!",
    "Let me look... I can see we're going to have fun learning together!"
]

async def handle_vision(prompt: str, tts_engine: SmoothTTSEngine):
    """
    Handle vision-related commands with playful responses.
    
    Args:
        prompt: User's vision-related request
        tts_engine: TTS engine for speech output
    """
    log_info(f"👁 Handling vision request: {prompt}")
    
    # TODO: In the future, capture image and use image captioning model
    # For now, just give a random response
    response = random.choice(VISION_RESPONSES)
    
    log_info(f"Vision response: {response}")
    print(response)
    await tts_engine.speak_text(response)
