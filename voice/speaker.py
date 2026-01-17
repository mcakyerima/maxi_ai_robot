"""
Text-to-Speech module for Maxi AI.
Uses Edge TTS for high-quality speech synthesis.
Supports both local playback (laptop speakers) and cloud streaming (tablet speakers).
"""
import asyncio
import edge_tts
import re
import base64
import os
from io import BytesIO
from typing import AsyncIterable, Tuple, Optional
from utils.logger import log_info, log_error

# Try to import pygame (only needed for local audio playback)
try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False
    log_info("⚠️ pygame not available - using cloud audio only")


class SmoothTTSEngine:
    """Enhanced TTS engine for smoother speech output with playback blocking support."""

    def __init__(self, socket_server=None, **kwargs):
        # Accept **kwargs for backward compatibility with interrupt_aware_speaker signature
        self.voice = "en-US-EmmaNeural"
        self.rate = "+0%"  # Normal speed
        self.pitch = "-2Hz"
        self.audio_queue: asyncio.Queue[Tuple[BytesIO,
                                              asyncio.Event]] = asyncio.Queue()
        self.is_playing = False
        self.continuous_play_task = None
        self.socket_server = socket_server

        # Check if we should use cloud audio (tablet speakers) or local playback (laptop speakers)
        self.use_cloud_audio = os.getenv(
            "USE_CLOUD_AUDIO", "true").lower() == "true"

        # Initialize pygame mixer only if using local playback AND pygame is available
        if not self.use_cloud_audio and PYGAME_AVAILABLE:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=22050, buffer=2048)
            log_info("🔊 Using local audio playback (laptop speakers)")
        else:
            log_info("🔊 Using cloud audio streaming (tablet speakers)")

    def set_socket_server(self, socket_server):
        """Set socket server for cloud audio streaming."""
        self.socket_server = socket_server

    async def start_continuous_player(self):
        """Start the continuous audio player task if not already running."""
        if self.continuous_play_task is None:
            self.continuous_play_task = asyncio.create_task(
                self._continuous_player())

    async def _continuous_player(self):
        """Plays audio items from the queue, one at a time, and signals when done."""
        while True:
            try:
                audio_data, playback_complete = await self.audio_queue.get()

                # Choose playback method based on configuration
                if self.use_cloud_audio and self.socket_server:
                    # Stream to tablet browser
                    await self._play_via_websocket(audio_data)
                else:
                    # Play locally via pygame
                    await self._play_via_pygame(audio_data)

                self.audio_queue.task_done()
                playback_complete.set()

            except Exception as e:
                log_error(f"Audio player error: {e}")
                await asyncio.sleep(0.1)

    async def _play_via_pygame(self, audio_data: BytesIO):
        """Play audio locally using pygame (laptop speakers)."""
        if not PYGAME_AVAILABLE:
            log_error("pygame not available - cannot play audio locally")
            return
        audio_data.seek(0)
        pygame.mixer.music.load(audio_data)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            await asyncio.sleep(0.05)

    async def _play_via_websocket(self, audio_data: BytesIO):
        """Stream audio to tablet browser via WebSocket (tablet speakers)."""
        try:
            # Convert audio to base64
            audio_data.seek(0)
            audio_bytes = audio_data.read()
            audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')

            # Send to tablet
            await self.socket_server.emit_audio_chunk(audio_base64, "mp3")

            # Estimate playback duration for synchronization
            estimated_duration = len(audio_bytes) / \
                (22050 * 2)  # 22050 Hz, 16-bit

            # Wait for estimated duration (actual playback happens on tablet)
            await asyncio.sleep(estimated_duration)

            log_info(f"🔊 Streamed {len(audio_bytes)} bytes to tablet")

        except Exception as e:
            log_error(f"WebSocket audio streaming error: {e}")

    async def speak_text(self, text: str):
        """
        Speak text and wait for it to be fully played.

        Args:
            text: The text to convert to speech.
        """
        if not text.strip():
            return

        clean_text = re.sub(r'[^\w\s.,?!:;()-]', '', text)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()

        if not clean_text:
            return

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
                # Create event for playback completion
                playback_complete = asyncio.Event()
                await self.audio_queue.put((audio_stream, playback_complete))
                await playback_complete.wait()  # ✅ Wait until audio is finished playing

        except Exception as e:
            log_error(f"TTS Error: {e}")

    async def process_stream(self, text_stream: AsyncIterable[str]):
        """
        Stream sentences into natural speech chunks with playback coordination.

        Args:
            text_stream: Async iterable of streamed text chunks.
        """
        buffer = ""
        sentence_pattern = re.compile(r'([.!?]\s+|\n+)')

        async for text_chunk in text_stream:
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
                    await self.speak_text(complete_text)

                buffer = incomplete_text

        if buffer.strip():
            await self.speak_text(buffer)

        if not self.audio_queue.empty():
            await self.audio_queue.join()
