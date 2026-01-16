"""
Updated Ollama integration handler for Maxi AI with advanced context management.
"""
import uuid
from datetime import datetime
from typing import List, Dict
from integrations.ollama_api import OllamaAPI
from voice.speaker import SmoothTTSEngine
from utils.logger import log_info, log_error
from ui.socket_server import SocketServer
from brain.context_manager.context_manager import add_user_message, add_assistant_message, get_context_for_query, get_basic_context

# Initialize the API client
ollama = OllamaAPI()

async def prewarm_model():
    """Initialize the model with a warmup prompt."""
    try:
        await ollama.connect()
        return await ollama.prewarm_model('maxi-phi3')
    except Exception as e:
        log_error(f"❌ Ollama warmup failed: {e}")
        return False

async def handle_ollama(prompt: str, tts_engine: SmoothTTSEngine, socket: SocketServer, use_semantic_search: bool = True):
    """
    Handle general questions via Ollama LLM with advanced context management.
   
    Args:
        prompt: User's question/command
        tts_engine: TTS engine for speech output
        socket: Socket server for UI communication
        use_semantic_search: Whether to use semantic search for context (default: True)
    """
    try:
        log_info(f"🤖 Processing Ollama request: {prompt[:50]}...")
        
        
        # Get optimized context from context manager
        if use_semantic_search:
            context = await get_context_for_query(prompt)
            log_info(f"📋 Using optimized context with {len(context)} messages")
        else:
            context = await get_basic_context()
            log_info(f"📋 Using basic context with {len(context)} messages")
        
        # Generate unique stream ID
        stream_id = f"ollama_{uuid.uuid4().hex[:8]}"
        
        # Start streaming to UI
        await socket.emit_response_start(stream_id)
        
        # Collect full response for TTS
        full_response = ""
        chunk_count = 0
        
        # Stream the response from Ollama
        async for chunk in ollama.generate_response(
            model='maxi-phi3',
            prompt=prompt,
            context=context
        ):
            if chunk.strip():  # Only process non-empty chunks
                # Send chunk to UI immediately
                await socket.emit_response_chunk(chunk, stream_id)
                
                # Accumulate for TTS
                full_response += chunk
                chunk_count += 1
        
        # Complete streaming to UI
        await socket.emit_response_complete(stream_id)
        
        # Process TTS with the complete response
        if full_response.strip():
            # Add assistant response to context manager
            await add_assistant_message(full_response.strip())
            
            log_info(f"✅ Ollama response completed: {len(full_response)} chars, {chunk_count} chunks")
            await tts_engine.speak_text(full_response.strip())
        else:
            log_error("⚠️ Empty response from Ollama")
            fallback_msg = "I'm not sure how to answer that. Can you ask differently?"
            
            # Add fallback to context as well
            await add_assistant_message(fallback_msg)
            
            await socket.broadcast({
                "type": "response",
                "text": fallback_msg,
                "streaming": False,
                "timestamp": datetime.now().isoformat()
            })
            await tts_engine.speak_text(fallback_msg)
       
    except Exception as e:
        log_error(f"❌ Ollama handler error: {e}")
        
        # Send error to UI
        error_msg = "I'm having trouble thinking right now. Can we try again?"
        
        # Add error to context
        await add_assistant_message(error_msg)
        
        try:
            await socket.broadcast({
                "type": "error",
                "message": error_msg,
                "timestamp": datetime.now().isoformat()
            })
        except:
            pass
            
        # Fallback TTS
        await tts_engine.speak_text(error_msg)

# Cleanup function to be called on shutdown
async def cleanup_ollama():
    """Clean up Ollama API connection."""
    try:
        await ollama.close()
        log_info("🧹 Ollama API cleaned up")
    except Exception as e:
        log_error(f"Error cleaning up Ollama: {e}")

# Additional utility functions for different context strategies
async def handle_ollama_with_basic_context(prompt: str, tts_engine: SmoothTTSEngine, socket: SocketServer):
    """Handle Ollama request with basic context (faster, no semantic search)."""
    return await handle_ollama(prompt, tts_engine, socket, use_semantic_search=False)

async def handle_ollama_with_full_context(prompt: str, tts_engine: SmoothTTSEngine, socket: SocketServer):
    """Handle Ollama request with full semantic search context (slower, more accurate)."""
    return await handle_ollama(prompt, tts_engine, socket, use_semantic_search=True)