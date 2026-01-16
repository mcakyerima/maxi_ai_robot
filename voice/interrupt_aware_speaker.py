"""
Button-based Interrupt-aware Text-to-Speech module for Maxi AI.
Uses UI button clicks instead of voice detection for interruptions.
Now streams audio to tablet browser instead of playing locally.
"""
import asyncio
import random
import edge_tts
import pygame
import re
import time
import base64
import os
from io import BytesIO
from typing import AsyncIterable, Tuple, Optional
from utils.logger import log_info, log_error, log_warning


class InterruptAwareTTSEngine:
    """Enhanced TTS engine with button-based interruption support and cloud audio streaming."""

    def __init__(self, maxi_ai=None, socket_server=None):
        self.maxi_ai = maxi_ai
        self.socket_server = socket_server
        self.voice = "en-US-EmmaNeural"
        self.rate = "+0%"
        self.pitch = "-2Hz"

        # Audio playback
        self.audio_queue: asyncio.Queue[Tuple[BytesIO,
                                              asyncio.Event]] = asyncio.Queue()
        self.is_playing = False
        self.continuous_play_task = None
        self.current_playback_event = None

        # Button-based interruption system
        self.interrupt_listener = None
        self.interrupt_event = asyncio.Event()
        self.is_interruptible = True

        # Check if we should use cloud streaming (tablet speakers) or local playback
        self.use_cloud_audio = os.getenv(
            "USE_CLOUD_AUDIO", "true").lower() == "true"

        # Initialize pygame mixer only if using local playback
        if not self.use_cloud_audio:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=22050, buffer=2048)
        else:
            log_info("🔊 Using cloud audio streaming (tablet speakers)")

    async def start_continuous_player(self):
        """Start the continuous audio player task if not already running."""
        if self.continuous_play_task is None:
            self.continuous_play_task = asyncio.create_task(
                self._continuous_player())

    async def _listen_for_button_interruption(self):
        """
        Listen for button-based interruption events from the socket server.
        """
        HUMOROUS_INTERRUPTIONS = [
            "I was telling a story here!",
            "Oya naaa, wetin you wan talk?",
            "Haba, you don cut my talk again!",
            "Abaaeg, let me finish!",
            "Wait make I complete my story!",
            "Okay okay, wetin you wan say?",
            "Haba! You no go let me talk?"
        ]

        if not self.socket_server:
            log_warning("No socket server available for button interruption")
            return

        try:
            log_info("🔘 Button interruption listener active")

            while self.is_playing and not self.interrupt_event.is_set():
                try:
                    # Wait for "interrupted" message from UI button click
                    await asyncio.wait_for(
                        self.socket_server.wait_for_message("interrupted"),
                        timeout=0.1  # Short timeout to check playing status regularly
                    )

                    # Button was clicked - trigger interruption
                    log_info("🔘 BUTTON INTERRUPTION DETECTED!")
                    self.interrupt_event.set()

                    # Play humorous interruption response
                    response = random.choice(HUMOROUS_INTERRUPTIONS)
                    asyncio.create_task(self._handle_interruption(response))
                    break

                except asyncio.TimeoutError:
                    # No button click yet, continue listening
                    continue
                except Exception as e:
                    log_error(f"Button interruption detection error: {e}")
                    await asyncio.sleep(0.1)

        except Exception as e:
            log_error(f"Failed to start button interruption listener: {e}")

    async def _handle_interruption(self, response: str):
        """Process the interruption with humorous response"""
        try:
            log_info(f"🎭 Playing interruption response: '{response}'")

            if self.socket_server:
                await self.socket_server.emit_state_change("interrupted")

            # Stop current playback immediately
            if not self.use_cloud_audio:
                pygame.mixer.music.stop()
            self.is_playing = False

            # Play interruption response (non-interruptible)
            await self.speak_text(response, interruptible=False)

            # Wait for the humorous response to finish completely
            while self.is_playing:
                await asyncio.sleep(0.1)

            # Now activate microphone for user input
            if self.maxi_ai:
                await self.maxi_ai.process_interruption()

        except Exception as e:
            log_error(f"Error while handling interrupt from TTS: {e}")

    async def _continuous_player(self):
        """
        Plays audio items from the queue with button-based interruption handling.
        Supports both local playback (pygame) and cloud streaming (WebSocket).
        """
        while True:
            try:
                audio_data, playback_complete = await self.audio_queue.get()

                # Store current playback event
                self.current_playback_event = playback_complete

                # Start button interruption listener if enabled
                if self.is_interruptible and self.socket_server:
                    self.interrupt_event.clear()
                    self.interrupt_listener = asyncio.create_task(
                        self._listen_for_button_interruption())

                # Choose playback method based on configuration
                if self.use_cloud_audio and self.socket_server:
                    # Stream audio to tablet browser
                    await self._play_via_websocket(audio_data)
                else:
                    # Play locally via pygame
                    await self._play_via_pygame(audio_data)

                # Wait for either playback completion or interruption
                playback_task = asyncio.create_task(
                    self._wait_for_playback_completion())

                if self.is_interruptible and self.socket_server:
                    done, pending = await asyncio.wait(
                        [playback_task, self.interrupt_listener],
                        return_when=asyncio.FIRST_COMPLETED
                    )

                    # Cancel remaining tasks
                    for task in pending:
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass

                    # Check if interrupted
                    if self.interrupt_event.is_set():
                        log_info(
                            "🛑 Speech interrupted by button - stopping playback")
                        if not self.use_cloud_audio:
                            pygame.mixer.music.stop()
                        self.is_playing = False

                        # Signal interruption to caller
                        playback_complete.set()
                        self.audio_queue.task_done()

                        # Clear remaining audio queue on interruption
                        while not self.audio_queue.empty():
                            try:
                                _, evt = self.audio_queue.get_nowait()
                                evt.set()
                                self.audio_queue.task_done()
                            except asyncio.QueueEmpty:
                                break

                        continue
                else:
                    await playback_task

                self.is_playing = False
                self.audio_queue.task_done()
                playback_complete.set()

            except Exception as e:
                log_error(f"Audio player error: {e}")
                if self.current_playback_event:
                    self.current_playback_event.set()
                await asyncio.sleep(0.1)

    async def _play_via_pygame(self, audio_data: BytesIO):
        """Play audio locally using pygame."""
        audio_data.seek(0)
        pygame.mixer.music.load(audio_data)
        pygame.mixer.music.play()
        self.is_playing = True

    async def _play_via_websocket(self, audio_data: BytesIO):
        """Stream audio to tablet browser via WebSocket."""
        try:
            # Convert audio to base64
            audio_data.seek(0)
            audio_bytes = audio_data.read()
            audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')

            # Send to tablet
            await self.socket_server.emit_audio_chunk(audio_base64, "mp3")

            # Estimate playback duration for timing
            estimated_duration = len(audio_bytes) / \
                (22050 * 2)  # 22050 Hz, 16-bit
            self.is_playing = True

            # Wait for estimated duration (actual playback happens on tablet)
            await asyncio.sleep(estimated_duration)

            log_info(f"🔊 Streamed {len(audio_bytes)} bytes to tablet")

        except Exception as e:
            log_error(f"WebSocket audio streaming error: {e}")

    async def _wait_for_playback_completion(self):
        """Wait for audio playback to complete (works for both pygame and cloud)."""
        if self.use_cloud_audio:
            # For cloud audio, we already waited in _play_via_websocket
            # Just a short delay to ensure completion
            await asyncio.sleep(0.1)
        else:
            # For pygame, wait until music finishes
            while pygame.mixer.music.get_busy():
                await asyncio.sleep(0.03)

    async def speak_text(self, text: str, interruptible: bool = True):
        """
        Speak text with optional button-based interruption support.

        Args:
            text: The text to convert to speech.
            interruptible: Whether this speech can be interrupted by button.
        """
        if not text.strip():
            return

        # Clean text
        clean_text = re.sub(r'[^\w\s.,?!:;()-]', '', text)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()

        if not clean_text:
            return

        # Set interruption mode
        self.is_interruptible = interruptible

        await self.start_continuous_player()

        try:
            communicate = edge_tts.Communicate(
                text=clean_text,
                voice=self.voice,
                rate=self.rate,
                pitch=self.pitch
            )

            audio_stream = BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_stream.write(chunk["data"])

            if audio_stream.tell() > 0:
                playback_complete = asyncio.Event()
                await self.audio_queue.put((audio_stream, playback_complete))
                await playback_complete.wait()

        except Exception as e:
            log_error(f"TTS Error: {e}")

    async def process_stream(self, text_stream: AsyncIterable[str], interruptible: bool = True):
        """
        Stream sentences into natural speech chunks with button-based interruption support.

        Args:
            text_stream: Async iterable of streamed text chunks.
            interruptible: Whether speech can be interrupted by button.
        """
        self.is_interruptible = interruptible

        buffer = ""
        sentence_pattern = re.compile(r'([.!?]\s+|\n+)')

        async for text_chunk in text_stream:
            # Check for interruption before processing new chunks
            if self.interrupt_event.is_set():
                log_info("🛑 Stream interrupted by button")
                break

            buffer += text_chunk
            print(text_chunk, end="", flush=True)

            if len(buffer) > 30:
                parts = sentence_pattern.split(buffer)
                complete_text = ""
                incomplete_text = ""

                for i in range(0, len(parts) - 1, 2):
                    complete_text += parts[i] + parts[i + 1]
                if len(parts) % 2 != 0:
                    incomplete_text = parts[-1]

                if complete_text:
                    await self.speak_text(complete_text, interruptible)

                    # Check for interruption after each sentence
                    if self.interrupt_event.is_set():
                        log_info("🛑 Stream interrupted by button")
                        break

                buffer = incomplete_text

        # Speak remaining buffer if not interrupted
        if buffer.strip() and not self.interrupt_event.is_set():
            await self.speak_text(buffer, interruptible)

        # Wait for queue to finish if not interrupted
        if not self.interrupt_event.is_set() and not self.audio_queue.empty():
            await self.audio_queue.join()

    def force_stop(self):
        """Immediately stop all speech playback."""
        log_info("🛑 Force stopping speech")
        self.interrupt_event.set()
        pygame.mixer.music.stop()
        self.is_playing = False

        # Clear audio queue
        while not self.audio_queue.empty():
            try:
                _, evt = self.audio_queue.get_nowait()
                evt.set()
                self.audio_queue.task_done()
            except asyncio.QueueEmpty:
                break

    def is_speech_active(self) -> bool:
        """Check if speech is currently active."""
        return self.is_playing

    def was_interrupted(self) -> bool:
        """Check if the last speech was interrupted."""
        return self.interrupt_event.is_set()

    def cleanup(self):
        """Clean up audio resources."""
        if self.interrupt_listener:
            self.interrupt_listener.cancel()
        if self.continuous_play_task:
            self.continuous_play_task.cancel()

# Drop-in replacement class for existing code


class SmoothTTSEngine(InterruptAwareTTSEngine):
    """Backward compatibility wrapper."""
    pass
