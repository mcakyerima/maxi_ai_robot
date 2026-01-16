# import os
# import pvporcupine
# import pyaudio
# import struct
# import asyncio
# from dotenv import load_dotenv
# from utils.logger import logger

# class WakeWordDetector:
#     def __init__(self):
#         load_dotenv()
#         self.porcupine = pvporcupine.create(
#             access_key=os.getenv("ACCESS_KEY"),
#             keyword_paths=[os.getenv("HEY_MAXI_MODEL_PATH")]
#         )
#         self.audio = pyaudio.PyAudio()
#         self.stream = None
#         self._stop_event = asyncio.Event()

#     async def listen(self):
#         """Async method to detect wake word"""
#         self.stream = self.audio.open(
#             rate=self.porcupine.sample_rate,
#             channels=1,
#             format=pyaudio.paInt16,
#             input=True,
#             frames_per_buffer=self.porcupine.frame_length,
#             stream_callback=self._callback
#         )
        
#         logger.info("🔊 Listening for 'Hey Maxi'...")
#         try:
#             while not self._stop_event.is_set():
#                 await asyncio.sleep(0.1)
#         finally:
#             self.cleanup()

#     def _callback(self, in_data, frame_count, time_info, status):
#         """Audio callback for wake word detection"""
#         pcm = struct.unpack_from("h" * self.porcupine.frame_length, in_data)
#         if self.porcupine.process(pcm) >= 0:
#             logger.info("🗣 Wake word detected!")
#             self._stop_event.set()
#         return (None, pyaudio.paContinue)

#     def cleanup(self):
#         """Release resources"""
#         if self.stream:
#             self.stream.stop_stream()
#             self.stream.close()
#         if self.porcupine:
#             self.porcupine.delete()
#         if self.audio:
#             self.audio.terminate()
#         logger.info("🔇 Wake word detector stopped")

# async def test_detection():
#     detector = WakeWordDetector()
#     await detector.listen()

# if __name__ == "__main__":
#     asyncio.run(test_detection())

import os
import json
import pyaudio
import asyncio
import vosk
import threading
from collections import deque
import time
from utils.logger import logger

class OptimizedWakeWordDetector:
    def __init__(self):
        # Model configuration
        self.model_path = "vosk-model-small-en-us-0.15"
        
        if not os.path.exists(self.model_path):
            logger.error(f"Model not found at {self.model_path}")
            raise FileNotFoundError(f"Vosk model not found at {self.model_path}")
        
        # Suppress Vosk logs
        vosk.SetLogLevel(-1)
        
        # Initialize Vosk
        self.model = vosk.Model(self.model_path)
        self.recognizer = vosk.KaldiRecognizer(self.model, 16000)
        
        # Audio settings - optimized for wake word detection
        self.sample_rate = 16000
        self.chunk_size = 2048  # Smaller chunks for responsiveness
        self.audio = pyaudio.PyAudio()
        self.stream = None
        
        # Threading for better performance
        self._stop_event = asyncio.Event()
        self._audio_queue = deque(maxlen=10)  # Buffer recent audio
        
        # Wake word detection
        self.wake_phrases = [
            "hey maxi",
            "a maxi",
            "hey maxie", 
            "maxi",
            "hey max"
        ]
        
        # Performance optimization
        self._last_detection_time = 0
        self._detection_cooldown = 2.0  # Prevent multiple detections
        
        logger.info("🤖 Optimized Vosk Wake Word Detector initialized")

    async def listen(self):
        """Async method to detect wake word with better performance"""
        self.stream = self.audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.chunk_size,
            stream_callback=self._audio_callback
        )
        
        self.stream.start_stream()
        logger.info("🔊 Listening for 'Hey Maxi' (optimized)...")
        
        try:
            while not self._stop_event.is_set():
                # Process queued audio data
                if self._audio_queue:
                    data = self._audio_queue.popleft()
                    await self._process_audio(data)
                else:
                    await asyncio.sleep(0.01)  # Small delay when no data
                    
        except Exception as e:
            logger.error(f"Error during wake word detection: {e}")
        finally:
            self.cleanup()

    def _audio_callback(self, in_data, frame_count, time_info, status):
        """Non-blocking audio callback"""
        if not self._stop_event.is_set():
            self._audio_queue.append(in_data)
        return (None, pyaudio.paContinue)

    async def _process_audio(self, data):
        """Process audio data for wake word detection"""
        try:
            if self.recognizer.AcceptWaveform(data):
                result = json.loads(self.recognizer.Result())
                text = result.get('text', '').lower().strip()
                
                if text and self._is_wake_word(text):
                    current_time = time.time()
                    
                    # Cooldown to prevent multiple detections
                    if current_time - self._last_detection_time > self._detection_cooldown:
                        logger.info(f"🗣 Wake word detected: '{text}'")
                        self._last_detection_time = current_time
                        self._stop_event.set()
                        
        except Exception as e:
            logger.error(f"Error processing audio: {e}")

    def _is_wake_word(self, text):
        """Enhanced wake word detection with fuzzy matching"""
        # Direct phrase matching
        for phrase in self.wake_phrases:
            if phrase in text:
                return True
        
        # Word-by-word matching for better accuracy
        words = text.split()
        if len(words) >= 2:
            # Check for "hey" + any variant of "maxi"
            for i in range(len(words) - 1):
                if words[i] in ["hey", "hi", "a"] and any(
                    variant in words[i + 1] for variant in ["maxi", "maxie", "max"]
                ):
                    return True
        
        return False

    def cleanup(self):
        """Release resources"""
        if self.stream:
            self.stream.stop_stream() 
            self.stream.close()
        if self.audio:
            self.audio.terminate()
        logger.info("🔇 Optimized wake word detector stopped")

# Simple drop-in replacement that matches your original interface
class WakeWordDetector(OptimizedWakeWordDetector):
    """Drop-in replacement for Porcupine-based WakeWordDetector"""
    pass

async def test_detection():
    detector = WakeWordDetector()
    await detector.listen()

if __name__ == "__main__":
    asyncio.run(test_detection())