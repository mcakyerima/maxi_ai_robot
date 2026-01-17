"""
WebSocket server for Maxi AI
Provides real-time updates and control through WebSockets
"""
import asyncio
import json
import logging
from typing import Dict, Set, Any, Optional, Callable, Coroutine
from datetime import datetime
from common.enums import AppMode


logger = logging.getLogger("ui.socket")


class SocketServer:
    """WebSocket server for real-time communication with the UI using Flask-SocketIO."""

    MODE_TRANSITION_GRACE_PERIOD = 1.5  # seconds (now a class constant)

    def __init__(self, socketio_instance=None):
        """
        Initialize WebSocket server for Flask-SocketIO.

        Args:
            socketio_instance: Flask-SocketIO instance for emitting events
        """
        self.socketio = socketio_instance
        self.clients: Set[str] = set()  # Track client session IDs
        self._listeners: Dict[str, asyncio.Queue] = {}
        self.intent_router: Optional[Any] = None
        self.mode_change_callback = None
        self._last_mode_change_time = 0
        self._mode_transition_grace_period = self.MODE_TRANSITION_GRACE_PERIOD
        self._mode_lock = asyncio.Lock()
        self.active_interaction = None

    def set_intent_router(self, router):
        print(f"Router: {router}\n")
        self.intent_router = router

    async def start(self):
        """Start the WebSocket server (no-op for Flask-SocketIO)."""
        logger.info("Socket server initialized with Flask-SocketIO")

    async def stop(self):
        """Stop the WebSocket server (no-op for Flask-SocketIO)."""
        logger.info("Socket server stopped")

    async def clear_pending_messages(self, message_types: list[str]):
        """
        Clear any queued messages for the given types so they won't trigger stale events.
        """
        for m_type in message_types:
            if m_type in self._listeners:
                queue = self._listeners[m_type]
                while not queue.empty():
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                # Remove the listener entirely to prevent stale wake events
                del self._listeners[m_type]
        logger.info(f"Cleared pending messages for: {message_types}")

    def set_mode_change_callback(self, callback: Callable):
        """Set the callback for mode changes"""
        self.mode_change_callback = callback

    def _is_in_mode_transition_grace_period(self) -> bool:
        """Check if we're in grace period after mode change to prevent spurious triggers"""
        return (datetime.now().timestamp() - self._last_mode_change_time) < self._mode_transition_grace_period

    async def wait_for_message(self, message_type: str, timeout: float = None):
        """Wait for a specific message type with improved cleanup."""
        if message_type in self._listeners:
            old_listener = self._listeners.pop(message_type)
            while not old_listener.empty():
                try:
                    old_listener.get_nowait()
                except asyncio.QueueEmpty:
                    break
            logger.info(f"🧹 Cleaned up existing listener for {message_type}")

        queue = asyncio.Queue()
        self._listeners[message_type] = queue

        try:
            if timeout:
                result = await asyncio.wait_for(queue.get(), timeout=timeout)
            else:
                result = await queue.get()

            logger.info(f"📨 Successfully received {message_type}")
            return result

        except asyncio.TimeoutError:
            logger.warning(f"⏰ Timeout waiting for {message_type}")
            raise
        except asyncio.CancelledError:
            logger.info(f"❌ Cancelled waiting for {message_type}")
            raise
        finally:
            if message_type in self._listeners:
                del self._listeners[message_type]
                logger.info(f"🧹 Cleaned up listener for {message_type}")

    async def _process_message(self, websocket, data: Dict):
        """Process incoming message from frontend with improved transcription handling."""
        message_type = data.get("type")

        # FIXED: Priority routing for transcriptions
        if message_type == "user_transcription":
            transcription = data.get("text", "").strip()
            confidence = data.get("confidence", 0.0)
            logger.info(
                f"🎤 Received transcription: '{transcription}' (confidence: {confidence:.2f})")

            # FIXED: Always check for waiting listeners first
            if "user_transcription" in self._listeners:
                # Remove immediately to prevent duplicates
                listener = self._listeners.pop("user_transcription")
                try:
                    await listener.put(data)
                    logger.info(f"✅ Transcription routed to waiting listener")
                    return  # Important: return early to prevent further processing
                except Exception as e:
                    logger.error(
                        f"Failed to route transcription to listener: {e}")
            else:
                logger.warning("⚠️ No listener waiting for user_transcription")

            return

        # Handle other message types...
        if message_type in self._listeners:
            listener = self._listeners.pop(message_type)
            await listener.put(data)
            return
        
        # Audio state tracking from frontend
        if message_type == "audio_started":
            logger.info("🔊 Frontend: Audio playback started")
            # Could be used for state tracking or metrics
            return
        
        if message_type == "audio_complete":
            logger.info("✅ Frontend: Audio playback complete")
            # Could trigger idle timeout or other logic
            return
        
        if message_type == "audio_interrupted":
            logger.info("⏸️ Frontend: Audio playback interrupted")
            # Already handled by interrupt flow
            return

        if message_type == "ping":
            await self._send(websocket, {"type": "pong"})
            return

        # FIXED: Proper wake message routing
        if message_type == "wake_word_detected":
            if self._is_in_mode_transition_grace_period():
                logger.info("Ignoring wake_word_detected during grace period")
                return
            logger.info("General chat wake triggered")
            # Forward to listener if one is waiting
            if "wake_word_detected" in self._listeners:
                listener = self._listeners.pop("wake_word_detected")
                await listener.put(data)
                logger.info("✅ wake_word_detected routed to listener")
            return

        if message_type == "math_gesture_wake":
            if self._is_in_mode_transition_grace_period():
                logger.info("Ignoring math_gesture_wake during grace period")
                return
            logger.info("Math/Gesture wake triggered")
            # Forward to listener if one is waiting
            if "math_gesture_wake" in self._listeners:
                listener = self._listeners.pop("math_gesture_wake")
                await listener.put(data)
                logger.info("✅ math_gesture_wake routed to listener")
            return

        # Mode changes
        if message_type == "set_mode":
            mode = data.get("mode")
            if not self.mode_change_callback:
                logger.error("Mode change callback not set")
                return

            self._last_mode_change_time = datetime.now().timestamp()

            await self.clear_pending_messages([
                "wake_word_detected",
                "math_gesture_wake",
                "interrupted",
                "user_transcription"
            ])

            if mode == "general_chat":
                await self.emit_state_change("switching_to_general_chat")
                asyncio.create_task(
                    self.mode_change_callback(AppMode.GENERAL_CHAT))
            elif mode == "math_gesture":
                await self.emit_state_change("switching_to_math_gesture")
                asyncio.create_task(
                    self.mode_change_callback(AppMode.MATH_GESTURE))
            elif mode == "idle":
                await self.emit_state_change("switching_to_idle")
                asyncio.create_task(self.mode_change_callback(AppMode.IDLE))

            logger.info(f"Mode change requested: {mode}")
            return

        if message_type == "finger_pose_update":
            # Handle finger pose updates from backend to frontend
            pose = data.get("pose", {})
            await self.broadcast({
                "type": "finger_pose",
                "pose": pose,
                "timestamp": datetime.now().isoformat()
            })
            return

        if message_type == "math_sequence_update":
            # Handle math sequence updates
            await self.broadcast({
                "type": "math_sequence",
                "stage": data.get("stage"),
                "payload": data.get("payload", {}),
                "timestamp": datetime.now().isoformat()
            })
            return

        if message_type == "highlight_step":
            # Handle step highlighting for advanced math
            await self.broadcast({
                "type": "highlight_step",
                "step_number": data.get("step_number"),
                "operation": data.get("operation", ""),
                "result": data.get("result", ""),
                "timestamp": datetime.now().isoformat()
            })
            return

         # Handle immediate back button / navigation requests
        if message_type == "back_to_menu":
            logger.info(
                "Back to menu requested - immediate mode switch to idle")
            await self.emit_state_change("switching_to_idle")
            if self.mode_change_callback:
                # Set grace period
                self._last_mode_change_time = datetime.now().timestamp()
                # Clear pending messages
                await self.clear_pending_messages([
                    "wake_word_detected",
                    "math_gesture_wake",
                    "interrupted"
                ])
                asyncio.create_task(self.mode_change_callback(AppMode.IDLE))
            return

        if not message_type:
            await self._send(websocket, {
                "type": "error",
                "message": "Missing message type"
            })
            return

        logger.debug(f"Processing message type: {message_type}")

        if not message_type:
            await self._send(websocket, {
                "type": "error",
                "message": "Missing message type"
            })
            return

        logger.debug(f"Processing message type: {message_type}")

    # Add this method to the SocketServer class to handle enhanced state changes
    async def emit_mode_switch_complete(self, mode: str):
        """Emit when mode switch is fully complete."""
        await self.broadcast({
            "type": "mode_switch_complete",
            "mode": mode,
            "timestamp": datetime.now().isoformat()
        })

    def _send_sync(self, data: Dict):
        """Synchronous emit using Flask-SocketIO."""
        if self.socketio:
            # Emit on the specific event type AND on 'message' for backward compatibility
            event_type = data.get('type', 'message')
            # Emit on the type-specific channel
            self.socketio.emit(event_type, data)
            # Also emit on 'message' channel for clients listening there
            if event_type != 'message':
                self.socketio.emit('message', data)

    async def _send(self, websocket, data: Dict):
        """Send message via Flask-SocketIO (websocket param unused but kept for compatibility)."""
        self._send_sync(data)

    async def broadcast(self, data: Dict):
        """Broadcast data to all connected clients using Flask-SocketIO."""
        if self.socketio:
            # Emit on the specific event type AND on 'message' for backward compatibility
            event_type = data.get('type', 'message')
            # Emit on the type-specific channel
            self.socketio.emit(event_type, data)
            # Also emit on 'message' channel for clients listening there
            if event_type != 'message':
                self.socketio.emit('message', data)

    # State Management API
    async def emit_state_change(self, state: str, data: Dict = None):
        """Emit a state change event."""
        payload = {
            "type": "state_change",
            "state": state,
            "timestamp": datetime.now().isoformat()
        }
        if data:
            payload.update(data)
        await self.broadcast(payload)

    async def emit_transcription(self, text: str):
        """Emit transcription text."""
        await self.broadcast({
            "type": "transcription",
            "text": text,
            "timestamp": datetime.now().isoformat()
        })

    async def emit_shutdown(self, text: str):
        """Emit Shutdown text."""
        await self.broadcast({
            "type": "shutdown_confirm",
            "text": text,
            "timestamp": datetime.now().isoformat()
        })

    async def emit_response_start(self, stream_id: str = "default", initial_text: str = ""):
        """Start a streaming response."""
        await self.broadcast({
            "type": "response",
            "streaming": True,
            "streamId": stream_id,
            "text": initial_text,
            "timestamp": datetime.now().isoformat()
        })

    async def emit_response_chunk(self, text: str, stream_id: str = "default"):
        """Emit a response chunk."""
        await self.broadcast({
            "type": "response_chunk",
            "streamId": stream_id,
            "text": text,
            "timestamp": datetime.now().isoformat()
        })

    async def emit_response_complete(self, stream_id: str = "default"):
        """Complete a streaming response."""
        await self.broadcast({
            "type": "response_complete",
            "streamId": stream_id,
            "timestamp": datetime.now().isoformat()
        })

    async def emit_response(self, text: str):
        """Emit a complete response (non-streaming)."""
        await self.broadcast({
            "type": "response",
            "text": text,
            "streaming": False,
            "timestamp": datetime.now().isoformat()
        })

    async def emit_error(self, message: str):
        """Emit error message."""
        await self.broadcast({
            "type": "error",
            "message": message,
            "timestamp": datetime.now().isoformat()
        })

    async def emit_event(self, event_type: str, data: Dict = None):
        """Compatibility wrapper for emit_state_change."""
        await self.emit_state_change(event_type, data)

    async def emit_wake_word(self):
        """Emit wake word detected event."""
        await self.emit_state_change("wake", {
            "greeting": {
                "text": "Hello! How can I help you today?",
                "timestamp": datetime.now().isoformat()
            }
        })

    async def emit_audio_chunk(self, audio_base64: str, audio_format: str = "mp3"):
        """
        Stream audio data to the client for playback.
        Used for cloud-based TTS where server can't play audio.

        Args:
            audio_base64: Base64-encoded audio data
            audio_format: Audio format (mp3, wav, etc.)
        """
        await self.broadcast({
            "type": "audio_chunk",
            "audio": audio_base64,
            "format": audio_format,
            "timestamp": datetime.now().isoformat()
        })
