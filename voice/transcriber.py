"""
Speech transcription module with prewarming for Maxi AI.
"""

import whisper
import numpy as np
import asyncio
from typing import Optional
from ui.socket_server import SocketServer
from utils.logger import log_info, log_error, log_warning

class Transcriber:
    def __init__(self, model_name: str = "base"):
        self._model = None
        self._model_name = model_name  # Store model name
        self._is_loaded = False
        self._load_task = None

    async def prewarm(self):
        """Prewarm the specified Whisper model"""
        if not self._is_loaded and self._load_task is None:
            log_info(f"🔥 Prewarming Whisper {self._model_name}...")
            self._load_task = asyncio.create_task(self._load_model())

    async def _load_model(self):
        """Load the specified model with validation"""
        try:
            valid_models = ["tiny", "base", "small", "medium", "large-v2", "large-v3"]
            if self._model_name not in valid_models:
                raise ValueError(f"Invalid model name. Choose from: {valid_models}")

            log_info(f"📦 Loading Whisper {self._model_name}...")
            self._model = whisper.load_model(self._model_name)
            self._is_loaded = True
            log_info(f"✅ Whisper {self._model_name} ready")
            
            # Verify GPU acceleration
            if next(self._model.parameters()).is_cuda:
                log_info("🚀 Using GPU acceleration")
            else:
                log_warning("⚠️  Using CPU (slow) - recommend CUDA if available")
                
        except Exception as e:
            log_error(f"❌ Model load failed: {e}")
            # Fallback to base model if large fails
            if self._model_name != "base":
                log_info("🔄 Falling back to base model...")
                self._model_name = "base"
                await self._load_model()
            else:
                raise

    async def verify_hardware(self):
        """Check if current hardware can handle large-v3"""
        if self._model_name == "large-v3":
            try:
                import torch
                if not torch.cuda.is_available():
                    log_warning("⚠️  No GPU detected - recommend using 'base' model")
                    return False
            except ImportError:
                log_warning("⚠️  PyTorch not available - using CPU")
                return False
        return True

    async def transcribe(self, audio_data: bytes, socket_server: SocketServer) -> str:
        """
        Transcribe audio with prewarmed model
        """
        if not self._is_loaded:
            if self._load_task:
                log_info("⏳ Waiting for Whisper model to finish loading...")
                await self._load_task
            else:
                await self.prewarm()
                await self._load_task

        try:
            log_info("🧠 Processing speech...")
            audio_np = np.frombuffer(audio_data, np.int16).astype(np.float32) / 32768.0
            result = self._model.transcribe(audio_np, fp16=False, language='en')
            transcribed_text = result['text'].strip()
            
            await socket_server.emit_transcription(transcribed_text)
            log_info(f"📝 Transcribed: '{transcribed_text}'")
            return transcribed_text
            
        except Exception as e:
            log_error(f"❌ Transcription error: {e}")
            await socket_server.emit_error("Speech recognition failed")
            return ""