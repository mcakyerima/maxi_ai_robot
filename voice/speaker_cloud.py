"""
Cloud-Ready Text-to-Speech module for Maxi AI.
Streams audio to the tablet browser instead of playing on server.
Uses Edge TTS for high-quality speech synthesis.
"""
import asyncio
import edge_tts
import base64
from io import BytesIO
from typing import AsyncIterable, Optional
from utils.logger import log_info, log_error


class CloudTTSEngine:
    """
    Cloud-optimized TTS engine that streams audio to the client browser.
    Instead of playing audio on the server, it sends audio data via WebSocket.
    """

    def __init__(self, socket_server=None):
        self.voice = "en-US-EmmaNeural"
        self.rate = "+0%"  # Normal speed
        self.pitch = "-2Hz"
        self.socket_server = socket_server
        self.audio_queue: asyncio.Queue = asyncio.Queue()
        self.is_playing = False
        self.continuous_play_task = None

    def set_socket_server(self, socket_server):
        """Set the socket server for streaming audio."""
        self.socket_server = socket_server

    async def start_continuous_player(self):
        """Start the continuous audio streaming task if not already running."""
        if self.continuous_play_task is None:
            self.continuous_play_task = asyncio.create_task(
                self._continuous_streamer())

    async def _continuous_streamer(self):
        """
        Continuously streams audio chunks to the client via WebSocket.
        Client browser handles playback.
        """
        while True:
            try:
                audio_data, playback_complete = await self.audio_queue.get()

                if not self.socket_server:
                    log_error(
                        "❌ No socket server available for audio streaming")
                    playback_complete.set()
                    continue

                # Convert audio bytes to base64 for WebSocket transmission
                audio_data.seek(0)
                audio_bytes = audio_data.read()
                audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')

                # Send audio to client
                await self.socket_server.emit_audio_chunk(audio_base64)

                # Wait for client to finish playing
                # Estimate playback duration (rough calculation)
                estimated_duration = len(
                    audio_bytes) / (22050 * 2)  # 22050 Hz, 16-bit
                await asyncio.sleep(estimated_duration)

                self.audio_queue.task_done()
                playback_complete.set()

            except Exception as e:
                log_error(f"Audio streamer error: {e}")
                await asyncio.sleep(0.1)

    async def speak_text(self, text: str):
        """
        Convert text to speech and stream to the client.

        Args:
            text: The text to convert to speech.
        """
        if not text.strip():
            return

        # Clean text for TTS
        import re
        clean_text = re.sub(r'[^\w\s.,?!:;()-]', '', text)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()

        if not clean_text:
            return

        await self.start_continuous_player()

        try:
            # Generate audio using Edge TTS (Microsoft Cloud)
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
                # Queue audio for streaming to client
                playback_complete = asyncio.Event()
                await self.audio_queue.put((audio_stream, playback_complete))
                await playback_complete.wait()  # Wait until audio is streamed

        except Exception as e:
            log_error(f"TTS Error: {e}")

    async def process_stream(self, text_stream: AsyncIterable[str]):
        """
        Stream sentences into natural speech chunks with playback coordination.

        Args:
            text_stream: Async iterable of streamed text chunks.
        """
        import re
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


class HybridTTSEngine:
    """
    Hybrid TTS engine that can switch between local playback and cloud streaming.
    Useful during development and testing.
    """

    def __init__(self, mode="cloud", socket_server=None):
        """
        Initialize hybrid TTS engine.

        Args:
            mode: "local" for pygame playback, "cloud" for WebSocket streaming
            socket_server: WebSocket server for cloud mode
        """
        self.mode = mode
        self.socket_server = socket_server

        if mode == "local":
            # Use original pygame-based speaker
            from voice.speaker import SmoothTTSEngine
            self.engine = SmoothTTSEngine()
        else:
            # Use cloud streaming engine
            self.engine = CloudTTSEngine(socket_server)

    async def speak_text(self, text: str):
        """Speak text using the configured engine."""
        await self.engine.speak_text(text)

    async def process_stream(self, text_stream: AsyncIterable[str]):
        """Process streaming text."""
        await self.engine.process_stream(text_stream)

    def set_socket_server(self, socket_server):
        """Update socket server reference."""
        self.socket_server = socket_server
        if hasattr(self.engine, 'set_socket_server'):
            self.engine.set_socket_server(socket_server)
