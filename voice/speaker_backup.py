"""
Text-to-Speech module for Maxi AI.
Uses Edge TTS for high-quality speech synthesis.
BACKUP VERSION - Original working implementation with local pygame playback
"""
import asyncio
import edge_tts
import re
from io import BytesIO
from typing import AsyncIterable, Tuple
from utils.logger import log_info, log_error

# Try to import pygame (only needed for local audio playback)
try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False
    log_info("⚠️ pygame not available in speaker_backup")


class SmoothTTSEngine:
    """Enhanced TTS engine for smoother speech output with playback blocking support."""

    def __init__(self):
        self.voice = "en-US-EmmaNeural"
        self.rate = "+0%"  # Normal speed
        self.pitch = "-2Hz"
        self.audio_queue: asyncio.Queue[Tuple[BytesIO,
                                              asyncio.Event]] = asyncio.Queue()
        self.is_playing = False
        self.continuous_play_task = None

        if PYGAME_AVAILABLE and not pygame.mixer.get_init():
            pygame.mixer.init(frequency=22050, buffer=2048)

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
                if PYGAME_AVAILABLE:
                    audio_data.seek(0)
                    pygame.mixer.music.load(audio_data)
                    pygame.mixer.music.play()

                    while pygame.mixer.music.get_busy():
                        await asyncio.sleep(0.05)
                else:
                    log_error("pygame not available - skipping audio playback")

                self.audio_queue.task_done()
                playback_complete.set()

            except Exception as e:
                log_error(f"Audio player error: {e}")
                await asyncio.sleep(0.1)

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
