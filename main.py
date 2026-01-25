# main.py
"""
Maxi AI - main control loop (refactored)

Features:
- Mode-based operation: IDLE, GENERAL_CHAT, MATH_GESTURE
- Wake-word detection in any mode (voice + UI buttons)
- Wake-word detection works while IDLE (defaults to last selected mode)
- Mode change logging when switching mid-loop
- Immediate cancellation and clean shutdown on Ctrl+C
- Defensive error handling and helpful log messages

Author: regenerated for Mohammed Kaka
Date: 2025-08-12 (based on user's environment)
"""

from brain.controller.finger_controller import create_finger_controller
from common.enums import AppMode
from brain.handlers.ollama_handler import prewarm_model as prewarm_ollama
from brain.handlers.groq_llm_handler import prewarm_model as prewarm_groq
from utils.logger import log_info, log_error, log_warning
from ui.socket_server import SocketServer
from brain.intent_router import IntentRouter
from voice.interrupt_aware_speaker import SmoothTTSEngine
from voice.groq_transcriber import GroqTranscriber
import os
from pathlib import Path
import concurrent.futures.thread
import threading
from dotenv import load_dotenv
from datetime import datetime
import asyncio
import sys
import signal
import platform
import random
import traceback
from typing import Optional, Set, Any, Coroutine

# Check if running on Railway (cloud) or local
IS_RAILWAY = os.getenv(
    'RAILWAY_ENVIRONMENT') is not None or os.getenv('PORT') is not None

# local imports (project-specific)
# Only import audio modules if NOT on Railway (they need pyaudio/hardware)
if not IS_RAILWAY:
    try:
        from voice.interrupt_vad_listener import (
            record_until_silence_with_quality_check,
            record_until_silence,
            set_timeout_config,
            get_timeout_status
        )
        from voice.vad_listener import record_until_silence as record_until_silence_simple
        from voice.transcriber import Transcriber
        from wake_word import listen_for_wake_word
    except ImportError as e:
        print(f"⚠️ Local audio modules not available: {e}")
        # Define dummy functions for Railway

        def record_until_silence_with_quality_check(*args, **kwargs):
            return None

        def record_until_silence(*args, **kwargs):
            return None

        def record_until_silence_simple(*args, **kwargs):
            return None

        def set_timeout_config(*args, **kwargs):
            pass

        def get_timeout_status():
            return {
                'enabled': False,
                'default_timeout': 20.0,
                'short_timeout': 8.0,
                'wake_timeout': 45.0
            }

        def listen_for_wake_word(*args, **kwargs):
            return False
else:
    # Define dummy functions for Railway (no local audio hardware)
    print("☁️ Running on Railway - Local audio modules disabled")

    def record_until_silence_with_quality_check(*args, **kwargs):
        return None

    def record_until_silence(*args, **kwargs):
        return None

    def record_until_silence_simple(*args, **kwargs):
        return None

    def set_timeout_config(*args, **kwargs):
        pass

    def get_timeout_status():
        return {
            'enabled': False,
            'default_timeout': 20.0,
            'short_timeout': 8.0,
            'wake_timeout': 45.0
        }

    def listen_for_wake_word(*args, **kwargs):
        return False

    class Transcriber:
        def transcribe(self, *args, **kwargs):
            return ""

# Cloud-compatible imports (always available)

load_dotenv()

# Global configuration
# ---------------------------------------------------------
# Whether to use wake word detection (true/false)
# If false, only UI buttons will trigger listening
# ---------------------------------------------------------

USE_WAKE_WORD = os.getenv("USE_WAKE_WORD", "true").lower() == "true"
log_info(f"🎙️ Wake word enabled: {USE_WAKE_WORD}")

# -----------------------------------------------------------------------
# SimpleContextManager - fallback context manager (kept from your original)
# -----------------------------------------------------------------------


class SimpleContextManager:
    """
    Basic fallback context manager if advanced one fails.
    Keeps a very small buffer of messages and provides the system prompt.
    """

    def __init__(self):
        self.context = []
        self.system_prompt = (
            "You are Maxi, a friendly and HUMOROUS science teacher created at Maxeeton Technology "
            "by \"Mohammed Kaka\", and you tutor Nigerian children ages 6-12. "
            "Your response must STRICTLY follow these rules and for location context, you are currently in Maiduguri (Borno State): "
            "1. ALWAYS keep answers EXTREMELY brief - ONE or TWO short sentences MAX. "
            "2. Use simple English words a 6-year-old would understand. "
            "3. Be encouraging and fun in your explanations. "
            "4. Add a touch of gentle, kid-friendly humor to EVERY response. "
            "5. NEVER add extra information beyond what was asked. "
            "6. NEVER ask follow-up questions. "
            "7. Use concrete examples from everyday Nigerian life. "
            "8. STOP immediately after your brief answer - do not continue talking. "
            "9. Never use special characters or emojis. "
            "10. Make learning fun with simple jokes or silly comparisons. "
            "11. ABSOLUTELY NO LENGTHY EXPLANATIONS - be short and sweet! "
            "12. Be humorous and funny!"
        )

    async def add_message(self, role: str, content: str) -> str:
        self.context.append({"role": role, "content": content})
        if len(self.context) > 10:
            self.context = self.context[-10:]
        return f"simple_{len(self.context)}"

    async def get_optimized_context(self, query: str = "") -> list:
        return [{"role": "system", "content": self.system_prompt}] + self.context[-5:]

    async def get_basic_context(self) -> list:
        return [{"role": "system", "content": self.system_prompt}] + self.context[-5:]

    async def is_initialized(self) -> bool:
        return True

    def get_memory_stats(self) -> dict:
        return {
            "short_term_messages": len(self.context),
            "long_term_messages": 0,
            "system_prompt_tokens": len(self.system_prompt.split()),
            "initialized": True,
            "type": "simple"
        }


# -----------------------------------------------------------------------
# MaxiAI - main application container
# -----------------------------------------------------------------------
class MaxiAI:
    """
    Main application class handling:
    - initialization (TTS, STT, socket server, context, LLM warmup)
    - mode switching and continuous mode loops
    - wake-word detection for voice and UI triggers
    - graceful shutdown
    """

    def __init__(self):
        # lifetime flags
        self.shutdown_requested: bool = False
        # internal guard for immediate exit
        self._instant_shutdown_triggered: bool = False

        # core components (initialized later)
        self.tts_engine: Optional[SmoothTTSEngine] = None
        self.socket_server: Optional[SocketServer] = None
        self.intent_router: Optional[IntentRouter] = None
        self.transcriber: Optional[Any] = None
        self.context_manager: Optional[Any] = None
        self.finger_controller = None
        self.finger_hardware_available = False

        # runtime state
        self.current_tasks: Set[asyncio.Task] = set()
        self.current_mode: AppMode = AppMode.IDLE
        # default fallback when wake happens in idle
        self.last_selected_mode: AppMode = AppMode.GENERAL_CHAT
        self.mode_change_event: asyncio.Event = asyncio.Event()
        self.mode_active: bool = False
        self.context_ready: bool = False
        self.ollama_available: bool = True

        # timeout config
        self._configure_timeouts()

        # Wake-listener control handles
        self.wake_task: Optional[asyncio.Task] = None
        self.wake_stop_event: threading.Event = threading.Event()

        # debugging / instrumentation
        self._debug_log("MaxiAI instance created")

    # ---------------------------
    # Helper / debug utilities
    # ---------------------------
    def _debug_log(self, *args):
        try:
            log_info(" ".join(str(a) for a in args))
        except Exception:
            print("[DEBUG]", *args)

    # ---------------------------
    # Timeout configuration
    # ---------------------------
    def _configure_timeouts(self):
        """Configure timeout settings from environment variables or defaults."""
        try:
            timeout_enabled = os.getenv(
                "LISTENING_TIMEOUT_ENABLED", "true").lower() == "true"
            default_timeout = float(
                os.getenv("DEFAULT_LISTENING_TIMEOUT", "20.0"))
            short_timeout = float(os.getenv("SHORT_LISTENING_TIMEOUT", "8.0"))
            wake_timeout = float(os.getenv("WAKE_LISTENING_TIMEOUT", "45.0"))

            set_timeout_config(
                enabled=timeout_enabled,
                default_timeout=default_timeout,
                short_timeout=short_timeout,
                wake_timeout=wake_timeout
            )
            self._debug_log("ðŸ”§ Timeout config set",
                            f"enabled={timeout_enabled}",
                            f"default={default_timeout}",
                            f"short={short_timeout}",
                            f"wake={wake_timeout}")
        except Exception as e:
            log_warning(
                f"Invalid timeout configuration ({e}), using built-in defaults")
            set_timeout_config(enabled=True, default_timeout=20.0,
                               short_timeout=8.0, wake_timeout=45.0)

    # ---------------------------
    # Context system initialization
    # ---------------------------
    async def _initialize_context_system(self) -> bool:
        """
        Try to initialize the advanced context manager. If it fails, fall back to SimpleContextManager.
        Returns True if advanced context initialized, False otherwise.
        """
        try:
            log_info("ðŸ§  Initializing Advanced Context System...")
            # local optional module
            from brain.context_manager.context_manager import get_context_manager
            self.context_manager = await get_context_manager()
            initialized = await self.context_manager.is_initialized()
            if initialized:
                self.context_ready = True
                stats = self.context_manager.get_memory_stats()
                log_info(
                    f"âœ… Advanced Context Ready: {stats.get('short_term_messages', 0)} recent, {stats.get('long_term_messages', 0)} stored")
                return True
            else:
                raise RuntimeError(
                    "Advanced context manager returned uninitialized")
        except Exception as e:
            log_warning(f"âš ï¸ Advanced Context System failed: {e}")
            log_info("ðŸ”„ Falling back to basic context management...")
            self.context_manager = SimpleContextManager()
            self.context_ready = False
            stats = self.context_manager.get_memory_stats()
            log_info(
                f"âœ… Basic Context Ready: {stats.get('short_term_messages', 0)} messages")
            return False

    # ---------------------------
    # Finger controller initialization
    # ---------------------------
    async def _initialize_finger_controller(self):
        """Initialize finger controller with Raspberry Pi connection."""
        try:
            log_info("🤖 Initializing finger controller...")

            # Get Pi connection details from environment
            pi_ip = os.getenv("RASPBERRY_PI_IP", "192.168.31.156")
            pi_port = int(os.getenv("RASPBERRY_PI_PORT", "5001"))
            force_simulation = os.getenv(
                "FINGER_SIMULATION_MODE", "false").lower() == "true"

            log_info(f"🔌 Connecting to Raspberry Pi at {pi_ip}:{pi_port}")

            # Create and initialize finger controller
            self.finger_controller = create_finger_controller(
                pi_ip=pi_ip,
                pi_port=pi_port,
                simulation_mode=force_simulation
            )

            # Initialize connection (returns True if hardware available)
            self.finger_hardware_available = await self.finger_controller.initialize()

            if self.finger_hardware_available:
                log_info("✅ Finger controller hardware connected!")

                # Test basic movement
                log_info("🧪 Testing finger controller...")
                await self.finger_controller.close_all_fingers()
                await asyncio.sleep(0.5)
                await self.finger_controller.show_number(2, "right")
                await asyncio.sleep(1.0)
                await self.finger_controller.close_all_fingers()

                log_info("✅ Finger controller test completed")
            else:
                log_info("🎭 Finger controller running in simulation mode")

            return True

        except Exception as e:
            log_error(f"Finger controller initialization error: {e}")
            self.finger_hardware_available = False

            # Create fallback controller in simulation mode
            try:
                self.finger_controller = create_finger_controller(
                    simulation_mode=True)
                await self.finger_controller.initialize()
                log_info("🎭 Fallback finger controller (simulation) ready")
                return True
            except Exception as e2:
                log_error(f"Fallback finger controller failed: {e2}")
                return False

    # ---------------------------
    # Prewarm LLMs with fallback
    # ---------------------------
    async def _prewarm_ollama_with_fallback(self):
        try:
            await prewarm_ollama()
            log_info("âœ… Ollama model ready!")
        except Exception as e:
            log_error(f"Ollama warmup failed: {e}")
            if self.socket_server:
                await self.socket_server.emit_error("AI features limited")
            if self.tts_engine:
                await self.tts_engine.speak_text("Warning: Running in limited mode", interruptible=False)
            self.ollama_available = False

    # --------------------------
    # Cancel Current Wake Task
    # --------------------------

    async def _cancel_current_wake_task(self):
        """
        Cancel the currently running voice wake listening task if it exists.

        Important:
        - The voice listener runs inside a background thread via asyncio.to_thread(listen_for_wake_word, stop_event).
        - We stop it by setting self.wake_stop_event and awaiting the asyncio.Task.
        - This ensures the thread exits cleanly and resources are freed.
        """
        try:
            # Signal the underlying wake-thread to stop
            try:
                if hasattr(self, "wake_stop_event") and self.wake_stop_event:
                    self.wake_stop_event.set()
            except Exception:
                pass

            # Cancel the asyncio Task wrapper and await it so we don't leak threads
            if hasattr(self, "wake_task") and self.wake_task:
                if not self.wake_task.done():
                    try:
                        # Cancel the wrapper task (this doesn't kill the thread by itself, but it's fine)
                        self.wake_task.cancel()
                    except Exception:
                        pass
                try:
                    await self.wake_task
                except asyncio.CancelledError:
                    # Task cancelled as expected
                    pass
                except Exception:
                    # swallow any thread/exception propagated via the task
                    pass
                finally:
                    self.wake_task = None

            # Create a fresh stop event for next run (consumer must re-create/clear it before next listen)
            try:
                self.wake_stop_event = threading.Event()
            except Exception:
                pass

            log_info("â¹ï¸ Voice wake listening task cancelled/stopped")
        except Exception as e:
            log_warning(f"Error cancelling wake task: {e}")

    # FIXED: Wake trigger detection with proper mode routing
    async def _wait_for_wake_trigger(self, timeout: Optional[float] = None) -> Optional[str]:
        """
        Wait for wake triggers and return the specific trigger type.
        FIXED: Properly distinguish between math and general chat triggers.
        """
        if timeout is None:
            timeout = get_timeout_status().get("wake_timeout", 45.0)

        if self.shutdown_requested:
            return None

        # Cancel any existing wake task
        if hasattr(self, "wake_task") and self.wake_task and not self.wake_task.done():
            await self._cancel_current_wake_task()

        try:
            self.wake_stop_event = threading.Event()
        except Exception:
            self.wake_stop_event = threading.Event()

        # FIXED: Separate tasks for each wake type
        async def _voice_listen_runner():
            try:
                if USE_WAKE_WORD:
                    result = await asyncio.to_thread(listen_for_wake_word, self.wake_stop_event)
                    return "voice" if result else None
                else:
                    await asyncio.sleep(3600)  # Dummy task
                    return None
            except Exception as e:
                log_warning(f"Voice listen error: {e}")
                return None

        async def _wait_general_wake():
            try:
                data = await self.socket_server.wait_for_message("wake_word_detected")
                return "ui_general" if data else None
            except Exception as e:
                log_warning(f"General wake waiter error: {e}")
                return None

        async def _wait_math_wake():
            try:
                data = await self.socket_server.wait_for_message("math_gesture_wake")
                return "ui_math" if data else None
            except Exception as e:
                log_warning(f"Math wake waiter error: {e}")
                return None

        # Create tasks
        voice_task = asyncio.create_task(_voice_listen_runner())
        general_task = asyncio.create_task(_wait_general_wake())
        math_task = asyncio.create_task(_wait_math_wake())

        self.current_tasks.update({voice_task, general_task, math_task})
        self.wake_task = voice_task

        try:
            done, pending = await asyncio.wait(
                {voice_task, general_task, math_task},
                return_when=asyncio.FIRST_COMPLETED,
                timeout=timeout
            )

            if not done:
                # Timeout - cancel all
                for t in pending:
                    try:
                        t.cancel()
                    except Exception:
                        pass
                return None

            # FIXED: Check which specific task completed and return proper trigger
            trigger = None

            # Priority: UI triggers first (they're more specific)
            if math_task in done:
                try:
                    result = math_task.result()
                    if result == "ui_math":
                        trigger = "ui_math"
                        log_info("🧮 Math gesture wake detected")
                except Exception:
                    pass

            if not trigger and general_task in done:
                try:
                    result = general_task.result()
                    if result == "ui_general":
                        trigger = "ui_general"
                        log_info("💬 General chat wake detected")
                except Exception:
                    pass

            if not trigger and voice_task in done:
                try:
                    result = voice_task.result()
                    if result == "voice":
                        trigger = "voice"
                        log_info("🎙️ Voice wake detected")
                except Exception:
                    pass

            # Cancel remaining tasks
            for t in pending:
                try:
                    t.cancel()
                except Exception:
                    pass

            # Stop voice listener for UI triggers
            if trigger and trigger.startswith("ui_"):
                try:
                    self.wake_stop_event.set()
                except Exception:
                    pass

            return trigger

        except Exception as e:
            log_error(f"_wait_for_wake_trigger error: {e}")
            # Cancel all tasks on error
            for t in (voice_task, general_task, math_task):
                try:
                    t.cancel()
                except Exception:
                    pass
            return None
        finally:
            # Clean up task tracking
            for t in (voice_task, general_task, math_task):
                if t in self.current_tasks:
                    try:
                        self.current_tasks.remove(t)
                    except Exception:
                        pass
            if hasattr(self, "wake_task") and self.wake_task and self.wake_task.done():
                self.wake_task = None

    # ---------------------------
    # Initialization of components
    # ---------------------------
    async def initialize(self):
        """
        Initialize socket server, TTS, STT/transcriber, context, intent router, finger controller, and prewarm LLMs.
        """
        log_info("🚀 Initializing Maxi AI components...")

        # Socket server and TTS must be created before other components for dependency injection
        self.socket_server = SocketServer()
        self.tts_engine = SmoothTTSEngine(
            maxi_ai=self, socket_server=self.socket_server)

        # initialize context manager (advanced or fallback)
        await self._initialize_context_system()

        # Transcriber
        transcriber_mode = os.getenv("TRANSCRIBER_MODE", "local").lower()
        if transcriber_mode == "groq":
            log_info("🎙️ Using Groq Whisper STT")
            self.transcriber = GroqTranscriber()
        else:
            whisper_model = os.getenv("WHISPER_MODEL_NAME", "base")
            log_info(f"🎙️ Using local Whisper STT ({whisper_model})")
            self.transcriber = Transcriber(model_name=whisper_model)

        # Initialize finger controller
        finger_init_success = await self._initialize_finger_controller()

        # Decide which LLM to prewarm
        llm_provider = os.getenv("LLM_PROVIDER", "ollama").lower()
        if llm_provider == "groq":
            log_info("🧠 Using Groq LLM")
            prewarm_llm_task = prewarm_groq()
        else:
            log_info("🧠 Using Ollama LLM")
            prewarm_llm_task = self._prewarm_ollama_with_fallback()

        # Start prewarming and socket server in parallel
        prewarm_tasks = [
            self.transcriber.prewarm(),
            self.socket_server.start(),
            asyncio.create_task(prewarm_llm_task)
        ]

        # Add finger controller task if it was created
        if finger_init_success and not hasattr(self, '_finger_init_completed'):
            self._finger_init_completed = True

        # Use gather so we can continue even if one fails (return_exceptions=True)
        results = await asyncio.gather(*prewarm_tasks, return_exceptions=True)
        # Log any exceptions to help debugging
        for r in results:
            if isinstance(r, Exception):
                log_warning(f"Prewarm task returned exception: {r}")

        # Initialize IntentRouter
        self.intent_router = IntentRouter(
            maxi_ai=self,
            tts_engine=self.tts_engine,
            socket_server=self.socket_server,
            context_manager=self.context_manager
        )

        # Initialize Math Handler with finger controller
        try:
            from brain.handlers.math_gesture_handler import create_math_handler
            self.math_handler = await create_math_handler(
                self.tts_engine,
                self.socket_server,
                self.context_manager,
                self.finger_controller  # Pass finger controller to math handler
            )
            log_info("🧮 Math/Gesture handler initialized with finger controller")
        except Exception as e:
            log_warning(f"Math handler initialization failed: {e}")
            self.math_handler = None

        # Provide router callbacks to socket server
        self.socket_server.set_intent_router(self.intent_router)
        self.socket_server.set_mode_change_callback(self.set_mode)

        # Startup status summary
        timeout_status = get_timeout_status()
        log_info("=" * 60)
        log_info("📋 MAXI AI STARTUP STATUS")
        log_info("=" * 60)

        # Core systems
        log_info(
            f"   🧠 Context System: {'Advanced' if self.context_ready else 'Basic'}")
        log_info(f"   🤖 LLM Provider: {llm_provider.upper()}")
        log_info(f"   🎙️ Speech-to-Text: {transcriber_mode.upper()}")
        log_info(
            f"   🤚 Finger Control: {'Hardware Connected' if self.finger_hardware_available else 'Simulation Mode'}")

        # Timeout configuration
        log_info(
            f"   ⏰ Listening Timeouts: {'Enabled' if timeout_status['enabled'] else 'Disabled'}")
        if timeout_status['enabled']:
            log_info(f"      • Default: {timeout_status['default_timeout']}s")
            log_info(f"      • Short: {timeout_status['short_timeout']}s")
            log_info(f"      • Wake: {timeout_status['wake_timeout']}s")

        # Memory statistics (database content)
        if self.context_manager:
            stats = self.context_manager.get_memory_stats()
            log_info(f"   💾 Memory Database:")
            log_info(
                f"      • Short-term: {stats.get('short_term_messages', 0)} messages")
            log_info(
                f"      • Long-term: {stats.get('long_term_messages', 0)} stored")
            log_info(
                f"      • Summaries: {stats.get('conversation_summaries', 0)}")
            log_info(f"      • User Facts: {stats.get('user_facts', 0)}")

            # Only show working memory if there are messages
            if stats.get('working_memory_messages', 0) > 0:
                log_info(
                    f"      • Working: {stats['working_memory_messages']} active")

        # Safety systems status
        try:
            from brain.safety import get_system_status
            safety_status = get_system_status()
            log_info(f"   🛡️ Safety Systems:")
            log_info(
                f"      • Content Filter: {safety_status.get('content_filter', 'Active')}")
            log_info(
                f"      • Rate Limiter: {safety_status.get('rate_limiter', 'Active')} (60/hour, 100/session)")
            log_info(
                f"      • Usage Tracker: {safety_status.get('usage_tracker', 'Active')}")
            log_info(
                f"      • Session Timer: {safety_status.get('session_timer', 'Active')} (60 min)")
        except Exception as e:
            log_info(
                f"   🛡️ Safety Systems: Active (Content Filter, Rate Limiter, Usage Tracker)")

        # Finger controller details
        if self.finger_controller:
            finger_info = self.finger_controller.get_connection_info()
            if finger_info.get("hardware_available"):
                pi_url = finger_info.get('pi_url', 'Unknown')
                log_info(f"   🤚 Hardware Details: {pi_url}")
            else:
                error_msg = finger_info.get(
                    'last_error', 'Manual simulation mode')
                log_info(f"   🎭 Simulation Reason: {error_msg}")

        log_info("=" * 60)
        print("\n🎊 Maxi is ready! Waiting for mode selection...\n")
        log_info("System initialization complete - ready for user interaction")

    # ---------------------------
    # Mode management
    # ---------------------------
    async def set_mode(self, mode: AppMode):
        old_mode = self.current_mode

        # 🛑 PATCH 4: Kill any active wake listeners immediately to prevent stale triggers
        try:
            await self._cancel_current_wake_task()
        except Exception as e:
            log_warning(f"Failed to cancel wake task on mode change: {e}")

        if mode != old_mode:
            # Log mode change if leaving a non-idle mode
            if old_mode != AppMode.IDLE and old_mode is not None:
                log_info(
                    f"🔁 Mode switch detected in loop: {old_mode.name} → {mode.name}")

        self.current_mode = mode
        self.last_selected_mode = mode if mode != AppMode.IDLE else self.last_selected_mode

        # Wake up any waiting loop (IDLE waiting for mode_change_event)
        self.mode_change_event.set()

        # Cancel any other pending tasks
        for t in list(self.current_tasks):
            if not t.done():
                try:
                    t.cancel()
                except Exception:
                    pass
        self.current_tasks.clear()

        log_info(f"🔄 Mode changed from {old_mode.name} to {mode.name}")

        # ✅ PATCH 1: Flush stale UI triggers immediately if switching to IDLE
        if mode == AppMode.IDLE and self.socket_server:
            try:
                await self.socket_server.clear_pending_messages([
                    "wake_word_detected",
                    "math_gesture_wake",
                    "interrupted"
                ])
            except Exception as e:
                log_warning(
                    f"Failed to clear pending messages on idle switch: {e}")

        # ⏳ PATCH 3: Add short grace period after idle switch
        if mode == AppMode.IDLE and hasattr(self, "socket_server"):
            from datetime import datetime
            self.socket_server._last_mode_change_time = datetime.now().timestamp()
            self.socket_server._mode_transition_grace_period = 0.5  # half a second

    # ---------------------------
    # Main run loop & graceful shutdown
    # ---------------------------
    async def run(self):
        """
        Primary entry point that runs the Maxi AI main loops.
        It supports:
            - waiting for mode selection in IDLE
            - continuous mode loop for selected mode
            - responding to wake-word while in IDLE
            - immediate shutdown on Ctrl+C
        """
        log_info("🚀 Starting MaxiAI main run() loop")
        # initialize components
        await self.initialize()
        log_info("✅ MaxiAI initialization complete, entering main loop")

        # Register Ctrl+C handler - try to be cross-platform
        try:
            loop = asyncio.get_running_loop()
            if platform.system() == "Windows":
                # On Windows, signal.signal is OK for SIGINT
                signal.signal(signal.SIGINT, lambda s,
                              f: self.handle_ctrl_c_signal())
            else:
                # On UNIX-like, use add_signal_handler to call our method
                loop.add_signal_handler(
                    signal.SIGINT, self.handle_ctrl_c_signal)
        except Exception as e:
            log_warning(f"Could not register signal handler: {e}")

        # Main event loop
        try:
            while not self.shutdown_requested:
                # If idle, allow listening for a wake-word (and default to last selected mode)
                if self.current_mode == AppMode.IDLE:
                    log_info(
                        "â³ Waiting for mode selection (IDLE). Wake words permitted and will default to last mode.")
                    await self.socket_server.emit_state_change("idle")

                    # Wait for either a mode change from UI OR a wake word event from UI/voice
                    # We will wait for mode_change_event but also attempt a wake-word detection with timeout
                    self.mode_change_event.clear()
                    try:
                        # Wait concurrently for either event. We'll run wait_for_wake_word with a short timeout so
                        # the UI can still set mode; we re-loop to check mode_change_event.
                        wake_future = asyncio.create_task(self._wait_for_wake_word(
                            timeout=get_timeout_status().get("wake_timeout", 45.0)))
                        self.current_tasks.add(wake_future)

                        # If mode_change_event is set by UI, we should cancel the wake future and switch modes.
                        waiter = asyncio.create_task(
                            self.mode_change_event.wait())
                        self.current_tasks.add(waiter)

                        done, pending = await asyncio.wait({wake_future, waiter}, return_when=asyncio.FIRST_COMPLETED, timeout=get_timeout_status().get("wake_timeout", 45.0))

                        # If shutdown requested during waiting, break early
                        if self.shutdown_requested:
                            break

                        if waiter in done:
                            # UI requested mode change; wake future should be canceled
                            if wake_future in pending:
                                wake_future.cancel()
                            # Clear the event to be ready for next wait
                            self.mode_change_event.clear()
                            # tasks will be cleaned below; loop will process current_mode next
                        elif wake_future in done:
                            # A wake-word was detected while IDLE:
                            try:
                                wake_result = await wake_future
                            except asyncio.CancelledError:
                                wake_result = False
                            # Clean up waiter
                            if waiter in pending:
                                waiter.cancel()
                            if wake_result:
                                # default to last selected mode (fallback to GENERAL_CHAT)
                                chosen_mode = self.last_selected_mode or AppMode.GENERAL_CHAT
                                log_info(
                                    f"ðŸ”” Wake-word received while IDLE â†’ defaulting to: {chosen_mode.name}")
                                # set mode, but do not require UI - this allows hands-free activation in IDLE
                                await self.set_mode(chosen_mode)
                                # move to mode loop next iteration
                            else:
                                # No wake, simply re-loop (UI might set mode)
                                pass
                        else:
                            # Timeout expired (neither event fired)
                            pass

                    finally:
                        # Always cancel leftover tasks
                        for t in list(self.current_tasks):
                            if not t.done():
                                try:
                                    t.cancel()
                                except Exception:
                                    pass
                        self.current_tasks.clear()
                        # small backoff to avoid busy-looping
                        await asyncio.sleep(0.05)
                    # Continue, next iteration will enter mode loop if mode changed

                # Enter selected mode's continuous loop
                if self.shutdown_requested:
                    break

                log_info(
                    f"📍 Checking mode for loop execution: {self.current_mode.name}")
                if self.current_mode == AppMode.GENERAL_CHAT:
                    log_info("➡️ Calling _run_mode_loop for GENERAL_CHAT")
                    await self._run_mode_loop(self._handle_general_chat_interaction, "general_chat_active")
                    log_info("⬅️ Returned from GENERAL_CHAT mode loop")
                elif self.current_mode == AppMode.MATH_GESTURE:
                    log_info("➡️ Calling _run_mode_loop for MATH_GESTURE")
                    await self._run_mode_loop(self._handle_math_gesture_interaction, "math_gesture_active")
                    log_info("⬅️ Returned from MATH_GESTURE mode loop")
                else:
                    # Unknown mode: sleep briefly and continue
                    log_info(
                        f"⚠️ Unknown or IDLE mode: {self.current_mode.name}, sleeping...")
                    await asyncio.sleep(0.1)

            # End of main loop
            log_info(f"🛑 Main loop exited (shutdown_requested={self.shutdown_requested})")
        except asyncio.CancelledError:
            log_info("Main run loop cancelled")
        except Exception as e:
            log_error(
                f"Unexpected error in main loop: {e}\n{traceback.format_exc()}")
        finally:
            # final cleanup before exit
            log_info("🧹 Starting cleanup...")
            await self.cleanup()
            log_info("✅ Cleanup complete")

    # ---------------------------
    # Mode loop: continuous listening within a mode
    # ---------------------------
    # FIXED: Remove button interruption listeners during math interaction
    # FIXED: Mode routing in main.py _run_mode_loop
    async def _run_mode_loop(self, interaction_handler: Coroutine, state_name: str):
        """
        Continuous loop for a selected mode with proper trigger routing.
        """
        log_info(f"🔄 Starting {state_name} mode loop")

        try:
            await self.socket_server.emit_state_change(state_name)
        except Exception:
            pass

        self.mode_active = True

        try:
            while self.current_mode != AppMode.IDLE and not self.shutdown_requested:
                try:
                    log_info(f"⏳ [{state_name}] Waiting for wake trigger...")
                    trigger = await self._wait_for_wake_trigger()
                    log_info(f"🎯 [{state_name}] Received trigger: {trigger}")
                except asyncio.CancelledError:
                    log_info(f"Mode loop cancelled externally: {state_name}")
                    break
                except Exception as e:
                    log_error(
                        f"Error while waiting for wake trigger in {state_name}: {e}")
                    trigger = None

                if self.shutdown_requested:
                    break

                if not trigger:
                    await asyncio.sleep(0.05)
                    continue

                # FIXED: Route math gestures to math mode ONLY
                if trigger == "ui_math":
                    if self.current_mode != AppMode.MATH_GESTURE:
                        log_info(
                            "🔄 Math gesture triggered in wrong mode, switching to MATH_GESTURE")
                        await self.set_mode(AppMode.MATH_GESTURE)
                        break  # Exit current loop to restart in correct mode
                    else:
                        log_info(
                            "⚡ UI button wake detected (math/gesture) - correct mode")
                elif trigger == "ui_general":
                    if self.current_mode != AppMode.GENERAL_CHAT:
                        log_info(
                            "🔄 General chat triggered in wrong mode, switching to GENERAL_CHAT")
                        await self.set_mode(AppMode.GENERAL_CHAT)
                        break  # Exit current loop to restart in correct mode
                    else:
                        log_info(
                            "⚡ UI button wake detected (general chat) - correct mode")
                elif trigger == "voice":
                    log_info("🎙️ Voice wake word detected")

                # Cancel voice listener for UI triggers
                if trigger.startswith("ui_"):
                    try:
                        await self._cancel_current_wake_task()
                    except Exception:
                        pass

                    # Clear stale messages
                    if self.socket_server:
                        try:
                            await self.socket_server.clear_pending_messages([
                                "wake_word_detected",
                                "math_gesture_wake",
                                "interrupted",
                                "user_transcription"
                            ])
                        except Exception as e:
                            log_warning(
                                f"Failed to clear messages before interaction: {e}")

                # FIXED: Only run interaction if we're in the correct mode
                mode_handlers = {
                    ("general_chat_active", "ui_general"): True,
                    ("general_chat_active", "voice"): True,
                    ("math_gesture_active", "ui_math"): True,
                    ("math_gesture_active", "voice"): True
                }

                should_handle = mode_handlers.get((state_name, trigger), False)

                if should_handle:
                    try:
                        await interaction_handler()
                    except Exception as e:
                        log_error(
                            f"Error in interaction handler for {state_name}: {e}\n{traceback.format_exc()}")
                else:
                    log_warning(
                        f"Skipping interaction: {state_name} doesn't handle {trigger}")

                await asyncio.sleep(0.1)

        finally:
            self.mode_active = False
            try:
                await self._cancel_current_wake_task()
            except Exception as e:
                log_warning(f"Wake task cancel during mode exit failed: {e}")

            try:
                await self.socket_server.clear_pending_messages([
                    "wake_word_detected",
                    "math_gesture_wake",
                    "interrupted",
                    "user_transcription"
                ])
            except Exception as e:
                log_warning(f"Failed to clear stale messages: {e}")

            try:
                if not self.shutdown_requested:
                    await self.socket_server.emit_state_change("idle")
            except Exception:
                pass

            log_info(f"🏁 Exited {state_name} mode loop")
    # ---------------------------
    # Wake-word waiting helper
    # ---------------------------

    async def _wait_for_wake_word(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for either:
            - voice wake word (listen_for_wake_word executed in thread)
            - UI 'wake_word_detected' message
            - UI 'math_gesture_wake' message (useful when in math/gesture mode)
        Returns True when any of the triggers occurs; False otherwise.
        - This function is cancellable; when cancelled, it cleans up created tasks.
        """
        if timeout is None:
            timeout = get_timeout_status().get("wake_timeout", 45.0)

        # Short-circuit if shutdown already requested
        if self.shutdown_requested:
            return False

        # Prepare tasks
        # changing wake_task to use gloal config USE_WAKE_WORD
        # self.wake_task = asyncio.create_task(asyncio.to_thread(listen_for_wake_word))
        # voice_task = self.wake_task

        # Start voice listening task only if wake word is enabled
        if USE_WAKE_WORD:
            self.wake_task = asyncio.create_task(
                asyncio.to_thread(listen_for_wake_word))
            voice_task = self.wake_task
        else:
            # Dummy task
            voice_task = asyncio.create_task(asyncio.sleep(3600))

        ui_task_general = asyncio.create_task(
            self.socket_server.wait_for_message("wake_word_detected"))
        ui_task_math = asyncio.create_task(
            self.socket_server.wait_for_message("math_gesture_wake"))

        self.current_tasks.update({voice_task, ui_task_general, ui_task_math})

        try:
            done, pending = await asyncio.wait(
                {voice_task, ui_task_general, ui_task_math},
                return_when=asyncio.FIRST_COMPLETED,
                timeout=timeout
            )

            # If shutdown flag raised while waiting, cancel all and return False
            if self.shutdown_requested:
                for t in pending:
                    try:
                        t.cancel()
                    except Exception:
                        pass
                return False

            if not done:
                # timeout expired
                for t in pending:
                    try:
                        t.cancel()
                    except Exception:
                        pass
                return False

            # At least one completed - determine which
            # Prefer UI triggers because they carry context; voice_task may return True/False
            completed_names = []
            wake_happened = False
            for t in done:
                if t is ui_task_general:
                    # UI requested a generic wake word
                    try:
                        data = t.result()
                        completed_names.append("wake_word_detected")
                        await self._cancel_current_wake_task()  # cancel ongoing voice wake
                        wake_happened = True
                    except Exception:
                        pass
                elif t is ui_task_math:
                    try:
                        data = t.result()
                        completed_names.append("ui_wake_math")
                        await self._cancel_current_wake_task()  # cancel ongoing voice wake
                        wake_happened = True
                    except Exception:
                        pass
                elif t is voice_task:
                    try:
                        result = t.result()
                        # listen_for_wake_word should return True on detection
                        if result:
                            completed_names.append("voice_wake")
                            # await self._cancel_current_wake_task()
                            wake_happened = True
                    except Exception as e:
                        log_warning(f"Voice wake task raised: {e}")

            # Cancel pending tasks
            for t in pending:
                try:
                    t.cancel()
                except Exception:
                    pass

            # Clear current tasks storage
            self.current_tasks.difference_update(
                {voice_task, ui_task_general, ui_task_math})
            # Emit UI wake state to let frontend show greeting and animations
            if wake_happened:
                try:
                    await self.socket_server.emit_wake_word()
                except Exception:
                    pass
            self._debug_log("Wake detection result",
                            completed_names, "wake_happened=", wake_happened)
            return wake_happened

        except asyncio.CancelledError:
            # If cancellation happens (mode change, shutdown), make sure tasks are cancelled and return False
            for t in [voice_task, ui_task_general, ui_task_math]:
                try:
                    t.cancel()
                except Exception:
                    pass
            self.current_tasks.difference_update(
                {voice_task, ui_task_general, ui_task_math})
            raise
        except Exception as e:
            log_error(
                f"Wake word waiting error: {e}\n{traceback.format_exc()}")
            # Cleanup
            for t in [voice_task, ui_task_general, ui_task_math]:
                try:
                    t.cancel()
                except Exception:
                    pass
            self.current_tasks.difference_update(
                {voice_task, ui_task_general, ui_task_math})
            return False

    # ---------------------------
    # Interaction handlers (per-mode)
    # ---------------------------
    async def _handle_general_chat_interaction(self):
        """
        General Chat interaction - cleaned up without interfering button listeners.
        """
        log_info("💬 Processing General Chat interaction")

        try:
            # Standard general chat flow
            greeting_future = await self.intent_router.handle_wake_word()

            # Simple approach: just wait for transcription
            await self.socket_server.emit_state_change("listening")

            try:
                user_input = await self.socket_server.wait_for_message("user_transcription", timeout=30.0)
                if user_input and user_input.get("text"):
                    transcription = user_input["text"].strip()

                    # Clean repeated words for general chat too
                    words = transcription.split()
                    cleaned_words = []
                    prev_word = ""
                    for word in words:
                        if word != prev_word:
                            cleaned_words.append(word)
                        prev_word = word
                    transcription = " ".join(cleaned_words)
                    await self.socket_server.emit_transcription(transcription)
                    log_info(f"🎤 Received UI transcription: {transcription}")
                    await self.socket_server.emit_state_change("thinking")
                    await self.intent_router.process_command(transcription)
                else:
                    log_info("📤 No transcription received from UI")

            except asyncio.TimeoutError:
                log_info("⏰ Transcription timeout from UI")

        except Exception as e:
            log_error(f"General chat interaction error: {e}")
        finally:
            try:
                await self.socket_server.emit_state_change("general_chat_active")
            except Exception:
                pass

    # ---------------------------
    # Input capture & transcription
    # ---------------------------
    async def _get_user_input(self) -> Optional[str]:
        """
        Capture speech until silence, run quality check, then transcribe.
        Returns transcribed text or None.
        """
        try:
            # timeout = get_timeout_status().get('default_timeout', 20.0)
            # audio_data = await asyncio.wait_for(
            #     record_until_silence_with_quality_check(self.tts_engine),
            #     timeout=timeout
            # )

            timeout = get_timeout_status().get('default_timeout', 20.0)
            audio_data = await asyncio.wait_for(
                record_until_silence(self.tts_engine),
                timeout=timeout
            )

            if isinstance(audio_data, tuple):
                audio_data = audio_data[0] if audio_data else b''

            if audio_data and isinstance(audio_data, bytes):
                await self.socket_server.emit_state_change("processing")
                try:
                    user_text = await self.transcriber.transcribe(audio_data, self.socket_server)
                    if user_text:
                        log_info(f"ðŸ‘¶ User said: {user_text}")
                        return user_text
                except Exception as e:
                    log_error(f"Transcription error: {e}")
            return None
        except asyncio.TimeoutError:
            log_info("â° User input timeout")
            return None
        except Exception as e:
            log_error(
                f"Input processing failed: {e}\n{traceback.format_exc()}")
            return None

    # ---------------------------
    # Math/Gesture LLM handler
    # ---------------------------
    # FIXED: Enhanced math gesture interaction handler
    # FIXED: Remove button interruption listeners entirely for math mode
    async def _handle_math_gesture_interaction(self):
        """
        Math/Gesture interaction without interruption listeners that cause spam.
        """
        log_info("🧮 Processing Math/Gesture interaction")

        try:
            math_greetings = [
                "Hello math explorer! What numbers shall we play with today?",
                "Hi there number ninja! Ready for some math magic?",
                "Math time! Let's have fun with numbers - what's your question?"
            ]

            import random
            greeting = random.choice(math_greetings)

            # Set speaking state and play greeting
            await self.socket_server.emit_state_change("speaking")
            log_info("🗣️ Playing math greeting...")

            try:
                await self.tts_engine.speak_text(greeting, interruptible=False)
                await asyncio.sleep(0.5)  # Ensure TTS completion
            except Exception as e:
                log_warning(f"TTS greeting failed: {e}")

            # Set listening state
            await self.socket_server.emit_state_change("listening")
            log_info("🎤 Now listening for math question...")

            try:
                # Wait for transcription - NO interruption listeners
                user_input = await self.socket_server.wait_for_message("user_transcription", timeout=45.0)

                if user_input and user_input.get("text"):
                    user_text = user_input["text"].strip()

                    # FIXED: Clean up repeated words from transcription
                    words = user_text.split()
                    cleaned_words = []
                    prev_word = ""
                    for word in words:
                        if word != prev_word:  # Remove consecutive duplicates
                            cleaned_words.append(word)
                        prev_word = word
                    user_text = " ".join(cleaned_words)

                    if len(user_text) < 3:
                        log_warning(
                            f"Received very short input: '{user_text}'")
                        await self.socket_server.emit_state_change("speaking")
                        await self.tts_engine.speak_text("I didn't catch that. Could you ask your math question again?")
                        return

                    log_info(f"🧮 Math/Gesture input received: '{user_text}'")

                    # Process math question
                    await self.socket_server.emit_state_change("processing")

                    try:
                        if not hasattr(self, 'math_handler') or self.math_handler is None:
                            from brain.handlers.math_gesture_handler import create_math_handler
                            self.math_handler = await create_math_handler(
                                self.tts_engine,
                                self.socket_server,
                                self.context_manager,
                                self.finger_controller
                            )

                        result = await self.math_handler.process_math_question(user_text)

                        if not result.get("success", False):
                            error_msg = result.get(
                                'error', 'I had trouble understanding that. Can you ask your math question again?')
                            log_warning(
                                f"Math handler returned error: {error_msg}")

                            await self.socket_server.emit_state_change("speaking")
                            await self.tts_engine.speak_text(error_msg)
                            await self.socket_server.emit_error(error_msg)
                        else:
                            log_info(f"✅ Math problem solved successfully")

                    except Exception as e:
                        log_error(f"Math handler error: {e}")
                        fallback_response = "I had trouble with that math problem. Can you try asking in a different way?"
                        await self.socket_server.emit_state_change("speaking")
                        await self.tts_engine.speak_text(fallback_response)
                else:
                    log_info("📤 No valid transcription received")
                    await self.socket_server.emit_state_change("speaking")
                    await self.tts_engine.speak_text("I didn't hear anything. Please try again!")

            except asyncio.TimeoutError:
                log_info("⏰ Math/Gesture transcription timeout")
                await self.socket_server.emit_state_change("speaking")
                await self.tts_engine.speak_text("I didn't hear anything. Press the button when you're ready!")

            except Exception as e:
                log_error(f"Math/Gesture transcription error: {e}")
                await self.socket_server.emit_state_change("speaking")
                await self.tts_engine.speak_text("Sorry, I had a problem listening. Please try again.")

        except Exception as e:
            log_error(f"Math/Gesture interaction error: {e}")
            try:
                await self.socket_server.emit_state_change("speaking")
                await self.tts_engine.speak_text("Sorry, something went wrong. Let me get ready again.")
            except Exception:
                pass
        finally:
            await asyncio.sleep(1.0)
            try:
                await self.socket_server.emit_state_change("math_gesture_active")
                log_info("🔄 Returned to math_gesture_active state")
            except Exception as e:
                log_warning(f"Failed to return to active state: {e}")

    # ---------------------------
    # Interruption processing (UI mic button)
    # ---------------------------
    async def process_interruption(self):
        """
        Called when UI sends 'interrupted' (user pressed mic button).
        This function records a short utterance and routes to the appropriate handler.
        """
        log_info("ðŸ”˜ Processing button interruption...")
        # try:
        #     await self.socket_server.emit_state_change("listening")
        #     audio_data = await record_until_silence()
        #     if audio_data:
        #         await self.socket_server.emit_state_change("processing")
        #         user_text = await self.transcriber.transcribe(audio_data, self.socket_server)
        #         if user_text:
        #             log_info(f"ðŸ‘¶ Interrupted with: {user_text}")
        try:
            await self.socket_server.emit_state_change("listening")
            user_input = await self.socket_server.wait_for_message("user_transcription", timeout=15.0)
            if user_input and user_input.get("text"):
                user_text = user_input["text"].strip()
                log_info(f"🎤 Interrupted with: {user_text}")
                await self.socket_server.emit_state_change("processing")
                if self.current_mode == AppMode.GENERAL_CHAT:
                    await self.intent_router.process_command(user_text)
                elif self.current_mode == AppMode.MATH_GESTURE:
                    response = await self._handle_math_gesture_llm(user_text)
                    await self.tts_engine.speak_text(response)
                    await self.socket_server.emit_response(response)
                return
            # No audio captured; go back to active state
            if self.current_mode == AppMode.GENERAL_CHAT:
                await self.socket_server.emit_state_change("general_chat_active")
            elif self.current_mode == AppMode.MATH_GESTURE:
                await self.socket_server.emit_state_change("math_gesture_active")
            else:
                await self.socket_server.emit_state_change("idle")
        except Exception as e:
            log_error(
                f"Interruption processing error: {e}\n{traceback.format_exc()}")
            try:
                await self.socket_server.emit_state_change("idle")
            except Exception:
                pass

    # ---------------------------
    # Ctrl+C handler -> immediate shutdown
    # ---------------------------
    def handle_ctrl_c_signal(self):
        """Signal handler for SIGINT (Ctrl+C) â€” cancel everything and exit immediately."""
        print("\nðŸ”„ Ctrl+C detected. Exiting now...")
        log_info("Ctrl+C shutdown signal received")
        self.shutdown_requested = True
        self._instant_shutdown_triggered = True

        try:
            self.mode_change_event.set()
        except Exception:
            pass

        for t in list(self.current_tasks):
            try:
                t.cancel()
            except Exception:
                pass

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.stop()
        except Exception:
            pass

        # Immediate process exit
        os._exit(0)

    # ---------------------------
    # Clean shutdown
    # ---------------------------
    async def cleanup(self):
        """Clean shutdown with finger controller emergency stop."""
        try:
            log_info("🧹 Starting system cleanup...")

            # Emergency stop finger controller first
            if self.finger_controller:
                try:
                    log_info("🛑 Emergency stopping finger controller...")
                    await self.finger_controller.emergency_stop()
                    log_info("✅ Finger controller stopped")
                except Exception as e:
                    log_warning(f"Finger controller cleanup warning: {e}")

            # Stop TTS engine (non-async cleanup available)
            if self.tts_engine:
                try:
                    log_info("🔇 Stopping TTS engine...")
                    self.tts_engine.cleanup()
                except Exception as e:
                    log_warning(f"TTS cleanup warning: {e}")

            # Notify UI and stop socket server
            if self.socket_server:
                try:
                    log_info("🌐 Stopping WebSocket server...")
                    await self.socket_server.emit_state_change("shutdown")
                except Exception:
                    pass
                try:
                    await self.socket_server.stop()
                except Exception as e:
                    log_warning(f"Socket server stop warning: {e}")

            # Context cleanup (best effort)
            if self.context_manager and hasattr(self.context_manager, 'cleanup_old_memories'):
                try:
                    log_info("🗑️ Cleaning context memory...")
                    await self.context_manager.cleanup_old_memories(days_old=7)
                    log_info("🧹 Context cleanup completed")
                except Exception as e:
                    log_warning(f"⚠️ Context cleanup warning: {e}")

            # Audio cleanup
            try:
                from voice.interrupt_vad_listener_backup import cleanup_audio
                cleanup_audio()
                log_info("🔊 Audio resources cleaned up")
            except Exception:
                pass

            # Create shutdown log marker for next run diagnostics
            try:
                shutdown_dir = Path("shutdown_logs")
                shutdown_dir.mkdir(exist_ok=True)
                with open(shutdown_dir / "shutdown_complete.txt", "w") as f:
                    f.write("Shutdown completed at " +
                            datetime.now().isoformat())
            except Exception:
                pass

            log_info("✅ System cleanup complete")
        except Exception as e:
            log_error(f"❌ Shutdown error: {e}\n{traceback.format_exc()}")
        finally:
            # Final safeguard to avoid lingering threads created by concurrent.futures
            try:
                concurrent.futures.thread._threads_queues.clear()
            except Exception:
                pass
            print("🧹 System shutdown complete. Goodbye! 👋")
    # ---------------------------
    # Request shutdown helper (used by intent router)
    # ---------------------------

    def request_shutdown(self):
        self.shutdown_requested = True
        for t in list(self.current_tasks):
            try:
                t.cancel()
            except Exception:
                pass


# -----------------------------------------------------------------------
# CLI entry point
# -----------------------------------------------------------------------
if __name__ == "__main__":
    maxi = MaxiAI()
    try:
        asyncio.run(maxi.run())
    except KeyboardInterrupt:
        # Fallback if KeyboardInterrupt bubbles up
        try:
            maxi.handle_ctrl_c_signal()
        except Exception:
            pass
        # make a final attempt at cleanup synchronously
        try:
            asyncio.run(maxi.cleanup())
        except Exception:
            pass
    except Exception as e:
        print(f"Fatal error in main: {e}\n{traceback.format_exc()}")
        try:
            asyncio.run(maxi.cleanup())
        except Exception:
            pass
