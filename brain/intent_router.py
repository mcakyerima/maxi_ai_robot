import asyncio
from datetime import datetime
import random
import os
import sys
from dotenv import load_dotenv
from typing import List, Dict, Any, Optional
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
from brain.intent_matcher import match_intent
from brain.handlers.humor_handler import handle_humor
from brain.handlers.weather_handler import handle_weather
from brain.handlers.vision_handler import handle_vision
from brain.handlers.math_handler import handle_math
from brain.handlers.gesture_handler import handle_gesture
from brain.handlers.ollama_handler import handle_ollama, prewarm_model
from brain.handlers.groq_llm_handler import handle_llm
from utils.logger import log_info, log_error
from brain.context_manager.context_manager import get_context_manager
            


load_dotenv()

class IntentRouter:
    """Routes user commands to appropriate intent handlers with full state management."""
    
    def __init__(self, maxi_ai, tts_engine: SmoothTTSEngine, socket_server: SocketServer, context_manager=None, servo_controller=None):
        self.maxi_ai = maxi_ai
        self.tts_engine = tts_engine
        self.socket_server = socket_server
        self.context_manager = context_manager
        self.awaiting_shutdown_confirmation = False
        self.transcriber = GroqTranscriber()
        self.servo_controller = servo_controller

        if self.servo_controller is None:
            log_error("⚠️ Servo controller not initialized")
        else:
            log_info(f"✅🛠️ Servo connection received {self.servo_controller}")

        
        self.greeting_messages = [
            "Hi there! What's your question?",
            "Hello! I'm Maxi. What can I help with?",
            "I'm here! What would you like to know?",
            "Hey friend! Ask me anything!",
            "Hi! Maxi's listening!"
        ]
        
        self.thinking_phrases = [
            "Hmm, let me think...",
            "Searching my robo-brain...",
            "Thinking cap on...",
            "Let me figure this out...",
            "Just a second, thinking..."
        ]

    async def _ensure_socket(self) -> SocketServer:
        """Validate socket server is available."""
        if not self.socket_server:
            raise RuntimeError("Socket server not initialized")
        return self.socket_server
    
    async def get_context(self):
        """Get or create the global context manager instance."""
        if not self.context_manager:
            self.context_manager = await get_context_manager()

    async def _add_user_message(self, content: str) -> str:
        """Add user message to context manager"""
        if self.context_manager:
            return await self.context_manager.add_message("user", content)
        return ""

    async def _add_assistant_message(self, content: str) -> str:
        """Add assistant message to context manager"""
        if self.context_manager:
            return await self.context_manager.add_message("assistant", content)
        return ""

    async def _get_optimized_context(self, query: str = "") -> List[Dict[str, str]]:
        """Get optimized context for LLM processing"""
        if self.context_manager:
            return await self.context_manager.get_optimized_context(query)
        return []

    async def handle_wake_word(self) -> asyncio.Event:
        """
        Handle wake word with proper state transitions.
        Returns an Event that is set when the greeting is complete.
        """
        socket = await self._ensure_socket()
        greeting_complete = asyncio.Event()

        try:
            await socket.emit_state_change("wake")
            greeting = random.choice(self.greeting_messages)
            await socket.emit_response(greeting)
            await self.tts_engine.speak_text(greeting)
            
            # Add greeting to context
            await self._add_assistant_message(greeting)
            
            greeting_complete.set()
        except Exception as e:
            log_error(f"Wake word handling failed: {e}")
            await socket.emit_error("Failed to greet")
            greeting_complete.set()
            raise

        return greeting_complete

    async def play_thinking_sound(self):
        """Play thinking sound with state management."""
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

    async def playful_shutdown(self):
        """Play shutdown sequence with synchronized TTS and UI emission"""
        socket = await self._ensure_socket()
        farewell = random.choice(shutdown_farewells)
        log_info(f"🎤 Shutdown message: {farewell}")
        
        # Emit to UI first for instant display
        await socket.emit_response(farewell) 
        
        # Add to context
        await self._add_assistant_message(farewell)
        await self.tts_engine.speak_text(farewell)


    async def speak_with_effect(self, text):
        """Make Maxi's speech more dynamic with pauses"""
        await asyncio.sleep(0.2)  # Dramatic pause
        await self.tts_engine.speak_text(text)
        

    async def _initiate_system_shutdown(self):
        """Initiate full system shutdown"""
        log_info("🔄 Initiating complete system shutdown...")
        if not self.maxi_ai:
            return

        self.maxi_ai.request_shutdown()        # ✅ stops the main loop
        await self.maxi_ai.cleanup()           # ✅ cleans up gracefully



    async def process_command(self, command: str):
        """Process user command with full context management"""
        socket = await self._ensure_socket()

        try:
            # Add user message to context first
            await self._add_user_message(command)
            
            intent = match_intent(command)
            log_info(f"🔍 Detected intent: {intent}")
            
            if intent != "shutdown": 
                await self.play_thinking_sound()
                
            await socket.emit_state_change("processing")
            print(f"\n🤖 Maxi's response: ", end="", flush=True)

            # === Handle shutdown intent ===
            if intent == "shutdown":
                self.awaiting_shutdown_confirmation = True

                # Ask for confirmation
                confirmation_message = random.choice(SHUTDOWN_CONFIRMATIONS)
                await socket.emit_shutdown(confirmation_message)
                await self.speak_with_effect(confirmation_message)
                
                # Add confirmation request to context
                await self._add_assistant_message(confirmation_message)

                # Setup listeners for both button (UI) and voice response
                ui_reply_task = asyncio.create_task(socket.wait_for_message("user_input"))

                # Start voice input collection
                await socket.emit_state_change("listening")
                audio_data = await record_until_silence()
                await socket.emit_state_change("processing")
                voice_reply = await self.transcriber.transcribe(audio_data, socket)
                voice_reply = voice_reply.strip().lower() if voice_reply else ""

                log_info(f"🗣️ Voice reply: {voice_reply}")

                try:
                    # Race both UI and voice replies
                    done, pending = await asyncio.wait(
                        [ui_reply_task],
                        timeout=0.1,
                        return_when=asyncio.FIRST_COMPLETED
                    )

                    if done:
                        ui_data = await ui_reply_task
                        user_reply = ui_data.get("data", "").strip().lower()
                        log_info(f"🖱️ UI reply: {user_reply}")
                    else:
                        user_reply = voice_reply
                except Exception as e:
                    log_error(f"Shutdown confirmation error: {e}")
                    user_reply = voice_reply or ""

                # Add user's shutdown response to context
                await self._add_user_message(user_reply)

                # Decide based on response
                if any(p in user_reply for p in ["yes", "yeah", "confirm", "do it", "sure", "okay"]):
                    log_info("👋 Shutdown confirmed by user.")
                    await self.playful_shutdown()
                    await socket.emit_state_change("shutdown")
                    await asyncio.sleep(1.5)
                    await socket.stop()
                    
                    # Initiate full system shutdown
                    await self._initiate_system_shutdown()

                elif any(p in user_reply for p in ["no", "cancel", "never mind", "not now"]):
                    self.awaiting_shutdown_confirmation = False
                    cancel_message = "Alright, still running! Let me know if you change your mind."
                    await self.tts_engine.speak_text(cancel_message)
                    await self._add_assistant_message(cancel_message)
                    return cancel_message
                else:
                    unclear_message = "Hmm, I didn't catch that. You can say yes or no."
                    await self.tts_engine.speak_text(unclear_message)
                    await self._add_assistant_message(unclear_message)
                    self.awaiting_shutdown_confirmation = False
                    return unclear_message

            # === Other Intents ===
            handler_result = None
            
            if intent == "joke_request":
                handler_result = await handle_humor(self.tts_engine, socket)
            elif intent == "weather":
                handler_result = await handle_weather(command, self.tts_engine, socket)
            elif intent == "vision_request":
                handler_result = await handle_vision(command, self.tts_engine, socket)
            elif intent == "math_calculation":
                math_response = await handle_math(command, self.tts_engine, socket)
                if math_response is None:  # Fall back to LLM
                    handler_result = await self._handle_llm_with_context(command)
                else:
                    handler_result = math_response
            elif intent == "gesture_request":
                handler_result = await handle_gesture(command, self.tts_engine, self.servo_controller, socket)
            elif intent == "time_date":
                time_response = await handle_time_date(command, self.tts_engine, socket)
                if time_response is None:
                    # Get current time context for LLM
                    current_time = datetime.now().strftime("%I:%M %p").lstrip("0")
                    current_date = datetime.now().strftime("%A, %B %d")
                    llm_prompt = f"Current time: {current_time}, Date: {current_date}. {command}"
                    handler_result = await self._handle_llm_with_context(llm_prompt)
                else:
                    handler_result = time_response
            else:
                # Default to LLM with full context
                handler_result = await self._handle_llm_with_context(command)

            # Add successful response to context
            if handler_result:
                await self._add_assistant_message(handler_result)

            print()  # Line break after response
            await socket.emit_state_change("speaking")
            
            return handler_result

        except Exception as e:
            log_error(f"Command processing failed: {str(e)}")
            error_message = "Sorry, something went wrong. Let's try that again."
            await socket.emit_error("Oops! Something went wrong.")
            await self.tts_engine.speak_text(error_message)
            await self._add_assistant_message(error_message)
            return error_message
        finally:
            await socket.emit_state_change("idle")

    async def _handle_llm_with_context(self, command: str) -> Optional[str]:
        """Handle LLM requests with proper context, context are fetched for prompt internally by handle_llm"""
        try:
            llm_provider = os.getenv("LLM_PROVIDER", "ollama").lower()
            
            if llm_provider == "groq":
                # For Groq, we might need to pass context differently
                return await handle_llm(command, self.tts_engine, self.socket_server)
            else:
                # For Ollama, we might need to pass context differently  
                return await handle_ollama(command, self.tts_engine, self.socket_server)
                
        except Exception as e:
            log_error(f"LLM handler failed: {e}")
            return None

    def set_main_app(self, main_app):
        """Set reference to main application for shutdown coordination"""
        if self.socket_server:
            self.socket_server.main_app = main_app