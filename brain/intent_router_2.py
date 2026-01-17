# brain/intent_router_2.py
import asyncio
from datetime import datetime
import random
import os
import sys
from dotenv import load_dotenv
from typing import List, Dict, Any, Optional, Tuple
from brain.handlers.time_handler import handle_time_date
from ui.socket_server import SocketServer

# Check if running on Railway (cloud) or local
IS_RAILWAY = os.getenv('RAILWAY_ENVIRONMENT') is not None or os.getenv('PORT') is not None

# Only import local audio modules if NOT on Railway
if not IS_RAILWAY:
    try:
        from voice import transcriber
        from voice.vad_listener import record_until_silence
    except ImportError:
        transcriber = None
        def record_until_silence(*args, **kwargs):
            return None
else:
    transcriber = None
    def record_until_silence(*args, **kwargs):
        return None

from voice.groq_transcriber import GroqTranscriber
from voice.shutdown_confirmation_voice import SHUTDOWN_CONFIRMATIONS, shutdown_farewells
from voice.speaker import SmoothTTSEngine
from brain.intent_matcher import match_intent, IntentMatch
from brain.handlers.humor_handler import handle_humor
from brain.handlers.weather_handler import handle_weather
from brain.handlers.vision_handler import handle_vision
from brain.handlers.math_handler import handle_math
from brain.handlers.gesture_handler import handle_gesture
from brain.handlers.ollama_handler import handle_ollama, prewarm_model
from brain.handlers.groq_llm_handler import handle_llm
from utils.logger import log_info, log_error, log_debug
from brain.context_manager.context_manager import get_context_manager
from functools import lru_cache

load_dotenv()

class IntentRouter:
    """Enhanced Intent Router for Maxi educational robot with improved reliability."""
    
    def __init__(self, maxi_ai, tts_engine: SmoothTTSEngine, socket_server: SocketServer, context_manager=None, servo_controller=None):
        self.maxi_ai = maxi_ai
        self.tts_engine = tts_engine
        self.socket_server = socket_server
        self.context_manager = context_manager
        self.awaiting_shutdown_confirmation = False
        self.transcriber = GroqTranscriber()
        self.servo_controller = servo_controller
        self.current_topic = None  # Track conversation topic
        self.user_preferences = {}  # Store user preferences
        self.handler_retries = {}  # Track retry counts per handler

        if self.servo_controller is None:
            log_error("⚠️ Servo controller not initialized")
        else:
            log_info(f"✅🛠️ Servo connection received {self.servo_controller}")

        # Pre-warm frequently used handlers
        asyncio.create_task(self._prewarm_handlers())
        
        self.greeting_messages = [
            "Hi there! What STEM topic can I help with today?",
            "Hello young scientist! What would you like to learn?",
            "Ready for some STEM fun! What's your question?",
            "Hey future engineer! What can I explain today?",
            "Science buddy here! Ask me anything!"
        ]
        
        self.thinking_phrases = [
            "Let me consult my knowledge base...",
            "Analyzing the scientific data...",
            "Processing your STEM question...",
            "Calculating the best response...",
            "Searching my educational resources..."
        ]

    async def _prewarm_handlers(self):
        """Pre-warm frequently used handlers for better performance."""
        try:
            # Pre-warm the LLM model
            if os.getenv("LLM_PROVIDER", "ollama").lower() == "ollama":
                await prewarm_model()
            
            # Pre-warm other handlers that need initialization
            await handle_weather("prewarm", self.tts_engine, self.socket_server)
            
            log_info("✅ Handlers pre-warmed successfully")
        except Exception as e:
            log_error(f"Handler pre-warming failed: {e}")

    async def _ensure_socket(self) -> SocketServer:
        """Validate socket server is available with retry logic."""
        if not self.socket_server:
            raise RuntimeError("Socket server not initialized")
        return self.socket_server
    
    async def get_context(self):
        """Get or create the global context manager instance."""
        if not self.context_manager:
            self.context_manager = await get_context_manager()

    async def _add_user_message(self, content: str) -> str:
        """Add user message to context manager with topic detection."""
        if self.context_manager:
            # Simple topic detection - could be enhanced with NLP
            stem_keywords = ["science", "math", "engineering", "technology", "physics", "chemistry"]
            if any(kw in content.lower() for kw in stem_keywords):
                self.current_topic = "STEM"
            return await self.context_manager.add_message("user", content)
        return ""

    async def _add_assistant_message(self, content: str) -> str:
        """Add assistant message to context manager."""
        if self.context_manager:
            return await self.context_manager.add_message("assistant", content)
        return ""

    async def _get_optimized_context(self, query: str = "") -> List[Dict[str, str]]:
        """Get optimized context for LLM processing with topic focus."""
        if self.context_manager:
            context = await self.context_manager.get_optimized_context(query)
            
            # If we have a current topic, prioritize relevant context
            if self.current_topic:
                return [msg for msg in context if self.current_topic.lower() in msg.get("content", "").lower()] or context
            return context
        return []

    async def handle_wake_word(self) -> asyncio.Event:
        """Enhanced wake word handling with educational focus."""
        socket = await self._ensure_socket()
        greeting_complete = asyncio.Event()

        try:
            await socket.emit_state_change("wake")
            greeting = random.choice(self.greeting_messages)
            await socket.emit_response(greeting)
            await self.tts_engine.speak_text(greeting)
            
            await self._add_assistant_message(greeting)
            
            greeting_complete.set()
        except Exception as e:
            log_error(f"Wake word handling failed: {e}")
            await socket.emit_error("Failed to greet")
            greeting_complete.set()
            raise

        return greeting_complete

    async def play_thinking_sound(self):
        """Play thinking sound with educational phrasing."""
        socket = await self._ensure_socket()
        try:
            await socket.emit_state_change("thinking")
            thinking_text = random.choice(self.thinking_phrases)
            await socket.emit_response(thinking_text)
            await self.tts_engine.speak_text(thinking_text)
        except Exception as e:
            log_error(f"Thinking sound failed: {e}")
            await socket.emit_error("Thinking interrupted")
            raise

    async def _handle_with_retry(self, handler, *args, max_retries=3, **kwargs):
        """Wrapper for handlers with retry logic."""
        handler_name = handler.__name__
        retry_count = self.handler_retries.get(handler_name, 0)
        
        try:
            result = await handler(*args, **kwargs)
            self.handler_retries[handler_name] = 0  # Reset on success
            return result
        except Exception as e:
            if retry_count < max_retries:
                retry_count += 1
                self.handler_retries[handler_name] = retry_count
                log_info(f"Retrying {handler_name} (attempt {retry_count})")
                await asyncio.sleep(0.5 * retry_count)  # Exponential backoff
                return await self._handle_with_retry(handler, *args, max_retries=max_retries, **kwargs)
            log_error(f"Handler {handler_name} failed after {max_retries} attempts: {e}")
            raise
        
    async def speak_with_effect(self, text):
        """Make Maxi's speech more dynamic with pauses"""
        await asyncio.sleep(0.2)  # Dramatic pause
        await self.tts_engine.speak_text(text)

    async def process_command(self, command: str):
        """Enhanced command processing with educational focus."""
        socket = await self._ensure_socket()

        try:
            # Add user message to context first
            await self._add_user_message(command)
            
            # Get intent with confidence score
            intent_match = match_intent(command)
            log_info(f"🔍 Detected intent: {intent_match.intent} (confidence: {intent_match.confidence:.2f})")
            
            # Only show thinking state for non-immediate responses
            if intent_match.intent != "shutdown" and intent_match.confidence > 0.3:
                await self.play_thinking_sound()
                
            await socket.emit_state_change("processing")
            print(f"\n🤖 Maxi's response: ", end="", flush=True)

            # === Handle shutdown intent ===
            if intent_match.intent == "shutdown":
                return await self._handle_shutdown_flow(socket)

            # === Route to appropriate handler ===
            handler_result = None
            try:
                if intent_match.intent == "joke_request":
                    handler_result = await self._handle_with_retry(
                        handle_humor, self.tts_engine, socket
                    )
                elif intent_match.intent == "weather":
                    handler_result = await self._handle_with_retry(
                        handle_weather, command, self.tts_engine, socket
                    )
                elif intent_match.intent == "vision_request":
                    handler_result = await self._handle_with_retry(
                        handle_vision, command, self.tts_engine, socket
                    )
                elif intent_match.intent == "math_calculation":
                    handler_result = await self._handle_math(command)
                elif intent_match.intent == "gesture_request":
                    handler_result = await self._handle_with_retry(
                        handle_gesture, command, self.tts_engine, self.servo_controller, socket
                    )
                elif intent_match.intent == "time_date":
                    handler_result = await self._handle_time(command)
                else:
                    # For low-confidence matches or general questions, use LLM with context
                    handler_result = await self._handle_llm_with_context(command, intent_match.confidence)
            except Exception as e:
                log_error(f"Handler failed: {e}")
                handler_result = await self._fallback_response(command, e)

            # Add successful response to context
            if handler_result:
                await self._add_assistant_message(handler_result)

            print()  # Line break after response
            await socket.emit_state_change("speaking")
            
            return handler_result

        except Exception as e:
            log_error(f"Command processing failed: {str(e)}")
            error_message = "Sorry, my circuits got a bit tangled. Could you ask again?"
            await socket.emit_error("Oops! Something went wrong.")
            await self.tts_engine.speak_text(error_message)
            await self._add_assistant_message(error_message)
            return error_message
        finally:
            await socket.emit_state_change("idle")

    async def _handle_shutdown_flow(self, socket: SocketServer) -> str:
        """Handle the shutdown confirmation flow."""
        self.awaiting_shutdown_confirmation = True

        # Ask for confirmation
        confirmation_message = random.choice(SHUTDOWN_CONFIRMATIONS)
        await socket.emit_shutdown(confirmation_message)
        await self.speak_with_effect(confirmation_message)
        
        await self._add_assistant_message(confirmation_message)

        # Get user response (voice or UI)
        user_reply = await self._get_shutdown_confirmation(socket)

        # Add user's shutdown response to context
        await self._add_user_message(user_reply)

        # Process response
        if any(p in user_reply for p in ["yes", "yeah", "confirm", "do it", "sure", "okay"]):
            log_info("👋 Shutdown confirmed by user.")
            await self.playful_shutdown()
            await socket.emit_state_change("shutdown")
            await asyncio.sleep(1.5)
            await socket.stop()
            await self._initiate_system_shutdown()
            return "Shutting down..."

        elif any(p in user_reply for p in ["no", "cancel", "never mind", "not now"]):
            self.awaiting_shutdown_confirmation = False
            cancel_message = "Alright, I'll stay awake! What STEM topic should we explore?"
            await self.tts_engine.speak_text(cancel_message)
            await self._add_assistant_message(cancel_message)
            return cancel_message
        
        else:
            unclear_message = "I didn't understand. Should I shut down? Say yes or no."
            await self.tts_engine.speak_text(unclear_message)
            await self._add_assistant_message(unclear_message)
            self.awaiting_shutdown_confirmation = False
            return unclear_message

    async def _get_shutdown_confirmation(self, socket: SocketServer) -> str:
        """Get shutdown confirmation from user (voice or UI)."""
        ui_reply_task = asyncio.create_task(socket.wait_for_message("user_input"))

        # Start voice input collection
        await socket.emit_state_change("listening")
        audio_data = await record_until_silence()
        await socket.emit_state_change("processing")
        voice_reply = await self.transcriber.transcribe(audio_data, socket)
        voice_reply = voice_reply.strip().lower() if voice_reply else ""

        log_info(f"🗣️ Voice reply: {voice_reply}")

        try:
            done, pending = await asyncio.wait(
                [ui_reply_task],
                timeout=0.1,
                return_when=asyncio.FIRST_COMPLETED
            )

            if done:
                ui_data = await ui_reply_task
                return ui_data.get("data", "").strip().lower()
            return voice_reply
        except Exception as e:
            log_error(f"Shutdown confirmation error: {e}")
            return voice_reply or ""

    async def _handle_math(self, command: str) -> str:
        """Handle math calculations with fallback to LLM."""
        math_response = await self._handle_with_retry(
            handle_math, command, self.tts_engine, socket
        )
        if math_response is None:  # Fall back to LLM
            return await self._handle_llm_with_context(command)
        return math_response

    async def _handle_time(self, command: str) -> str:
        """Handle time/date requests with fallback to LLM."""
        time_response = await self._handle_with_retry(
            handle_time_date, command, self.tts_engine, socket
        )
        if time_response is None:
            current_time = datetime.now().strftime("%I:%M %p").lstrip("0")
            current_date = datetime.now().strftime("%A, %B %d")
            llm_prompt = f"Current time: {current_time}, Date: {current_date}. {command}"
            return await self._handle_llm_with_context(llm_prompt)
        return time_response

    async def _handle_llm_with_context(self, command: str, confidence: float = 1.0) -> Optional[str]:
        """Enhanced LLM handler with confidence-based prompting."""
        try:
            llm_provider = os.getenv("LLM_PROVIDER", "ollama").lower()
            
            # Add educational context for STEM questions
            if self.current_topic == "STEM":
                command = f"This is a STEM education question from a secondary school student. {command}"
            
            # For low confidence matches, ask LLM to clarify
            if confidence < 0.4:
                command = f"The user may have asked: '{command}'. Could you clarify what they might be asking about, particularly in STEM education?"

            if llm_provider == "groq":
                return await self._handle_with_retry(
                    handle_llm, command, self.tts_engine, self.socket_server
                )
            else:
                return await self._handle_with_retry(
                    handle_ollama, command, self.tts_engine, self.socket_server
                )
        except Exception as e:
            log_error(f"LLM handler failed: {e}")
            return None

    async def _fallback_response(self, command: str, error: Exception) -> str:
        """Generate appropriate fallback response when handlers fail."""
        socket = await self._ensure_socket()
        
        # Check if this is a STEM-related question
        stem_keywords = ["science", "math", "engineering", "technology", "physics", "chemistry"]
        is_stem = any(kw in command.lower() for kw in stem_keywords)
        
        if is_stem:
            fallback = "I'm having trouble accessing my science resources. Could you try asking again?"
        else:
            fallback = "I'm having some technical difficulties. Let's try that again!"
        
        await socket.emit_error("Temporary issue")
        await self.tts_engine.speak_text(fallback)
        return fallback

    async def _initiate_system_shutdown(self):
        """Initiate full system shutdown with additional checks."""
        log_info("🔄 Initiating complete system shutdown...")
        if not self.maxi_ai:
            return

        # Ensure all pending operations are complete
        await asyncio.sleep(1)  # Brief pause to finish any ongoing operations
        
        self.maxi_ai.request_shutdown()
        await self.maxi_ai.cleanup()