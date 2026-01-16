"""
Humor Handler for Maxi AI
Provides kid-friendly jokes and fun facts with smooth streaming
"""
import asyncio
import random
from typing import AsyncGenerator
from integrations.humor_db import FUN_FACT_DB, JOKE_DB
from voice.speaker import SmoothTTSEngine
from ui.socket_server import SocketServer
from utils.logger import log_info, log_error, log_warning


# Configuration
CHUNK_DELAY = 0.08  # Optimal for natural speech rhythm
MAX_RETRIES = 2     # For TTS failures

async def _stream_response(text: str) -> AsyncGenerator[str, None]:
    """
    Smart streaming with:
    - Natural word grouping
    - Punctuation pauses
    - Adaptive delays
    """
    words = text.split(' ')
    for i, word in enumerate(words):
        # Add longer pause for punctuation
        delay = CHUNK_DELAY * (3 if any(p in word for p in '.,!?') else 1)
        
        # Group short words together
        chunk = word
        while (i < len(words)-1 and 
               len(chunk) + len(words[i+1]) < 15 and
               not any(p in word for p in '.,!?')):
            i += 1
            chunk += ' ' + words[i]
        
        yield chunk + (' ' if i < len(words)-1 else '')
        await asyncio.sleep(delay)


async def handle_humor(
    tts_engine: SmoothTTSEngine,
    socket_server: SocketServer,
    category: str = None
) -> str:
    """
    Enhanced humor handler with:
    - Category-based joke selection
    - Resilient streaming
    - Smart recovery
    """
    # Select appropriate content
    if category and category in JOKE_DB:
        response = random.choice(JOKE_DB[category])
    else:
        # Fixed: Properly select between joke or fun fact
        if random.choice([True, False]):  # 50% chance for joke or fact
            response = random.choice(random.choice(list(JOKE_DB.values())))
        else:
            response = random.choice(FUN_FACT_DB)
    
    log_info(f"🎭 Selected humor: {response[:60]}...")
    
    attempt = 0
    while attempt <= MAX_RETRIES:
        try:
            # Begin humor delivery
            await socket_server.emit_state_change("speaking")
            
            # Stream with progress tracking
            full_response = ""
            async for chunk in _stream_response(response):
                full_response += chunk
                # await socket_server.emit_response_chunk(chunk)

            
            await socket_server.emit_response(full_response)

            # Vocal delivery with retry
            try:
                await tts_engine.speak_text(response)
                log_info("✅ Humor delivered successfully")
                return full_response
            except Exception as tts_error:
                attempt += 1
                if attempt <= MAX_RETRIES:
                    log_warning(f"TTS failed (attempt {attempt}), retrying...")
                    continue
                raise tts_error
                
        except Exception as e:
            log_error(f"Humor delivery failed: {str(e)}")
            if attempt >= MAX_RETRIES:
                await socket_server.emit_error("My funny bone is broken!")
                raise
            attempt += 1