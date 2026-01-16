# voice/groq_transcriber.py

"""
Groq Whisper transcription module for Maxi AI (streamlined, no disk write).
"""

import asyncio
import tempfile
import wave
import aiohttp
from typing import Optional
from ui.socket_server import SocketServer
from utils.logger import log_info, log_error, log_warning
import os

class GroqTranscriber:
    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise RuntimeError("❌ Missing GROQ_API_KEY environment variable.")
        self.api_url = "https://api.groq.com/openai/v1/audio/transcriptions"

    async def prewarm(self):
        """For compatibility — no model loading needed for Groq."""
        log_info("🧠 Groq Whisper STT ready (cloud-hosted)")

    async def verify_hardware(self):
        """Skip for Groq cloud model."""
        return True

    async def transcribe(self, audio_data: bytes, socket_server) -> str:
        try:
            log_info("🔁 Preparing audio upload to Groq...")

            # Manually create and close the file to avoid Windows lock
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                tmp_path = tmp.name
                with wave.open(tmp_path, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(16000)
                    wf.writeframes(audio_data)

            # Now open it again for upload
            with open(tmp_path, "rb") as file:
                data = aiohttp.FormData()
                data.add_field("file", file, filename="input.wav", content_type="audio/wav")
                data.add_field("model", "whisper-large-v3")
                data.add_field("response_format", "verbose_json")

                headers = {
                    "Authorization": f"Bearer {self.api_key}"
                }

                async with aiohttp.ClientSession() as session:
                    async with session.post(self.api_url, headers=headers, data=data) as resp:
                        if resp.status == 200:
                            response = await resp.json()
                            text = response["text"].strip()
                            await socket_server.emit_transcription(text)
                            log_info(f"📝 Transcribed: '{text}'")
                            return text
                        else:
                            err = await resp.text()
                            log_error(f"❌ Groq STT failed: {resp.status} {err}")
                            await socket_server.emit_error("Groq STT failed")
                            return ""

        except Exception as e:
            log_error(f"❌ Exception during Groq transcription: {e}")
            await socket_server.emit_error("Groq transcription error")
            return ""

        finally:
            # Clean up temp file manually
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception as cleanup_err:
                    log_warning(f"⚠️ Failed to clean up temp file: {cleanup_err}")