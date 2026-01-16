import asyncio
import whisper
import numpy as np
from ui.socket_server import SocketServer
from utils.logger import log_info
import sounddevice as sd
from queue import Queue
import threading

# Audio configuration
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_SIZE = 48000  # 3 seconds of audio
AUDIO_FORMAT = 'float32'

class AudioTranscriber:
    def __init__(self, socket_server):
        self.socket_server = socket_server
        self.audio_queue = Queue()
        self.model = whisper.load_model("base")
        self.running = True
        log_info("Whisper model loaded")
        
        # Start processing thread
        self.thread = threading.Thread(target=self.process_audio)
        self.thread.start()

    def process_audio(self):
        """Process audio chunks from queue"""
        while self.running:
            audio_np = self.audio_queue.get()
            if audio_np is None:  # Stop signal
                break
                
            try:
                # Normalize audio
                audio_np = audio_np.astype(np.float32)
                audio_np /= np.max(np.abs(audio_np))
                
                # Transcribe
                result = self.model.transcribe(audio_np, fp16=False)
                text = result["text"].strip()
                
                # Send to WebSocket
                asyncio.run_coroutine_threadsafe(
                    self.socket_server.emit_transcription(text),
                    asyncio.get_event_loop()
                )
            except Exception as e:
                log_info(f"Transcription error: {str(e)}")

    def add_audio(self, audio_np):
        """Add audio to processing queue"""
        if audio_np.shape[0] >= CHUNK_SIZE:
            self.audio_queue.put(audio_np)

    def stop(self):
        """Stop the transcriber"""
        self.running = False
        self.audio_queue.put(None)
        self.thread.join()

async def main():
    socket_server = SocketServer()
    await socket_server.start()
    
    transcriber = AudioTranscriber(socket_server)
    
    def audio_callback(indata, frames, time, status):
        """Audio input callback"""
        if status:
            log_info(f"Audio status: {status}")
        transcriber.add_audio(indata.copy())
    
    try:
        log_info("Starting audio stream...")
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            callback=audio_callback,
            blocksize=CHUNK_SIZE,
            dtype=AUDIO_FORMAT
        ):
            log_info("🎤 Listening - speak now (Ctrl+C to stop)")
            print("Whisper transcription running. Connect to WebSocket UI to see results.")
            while True:
                await asyncio.sleep(1)
                
    except KeyboardInterrupt:
        log_info("Stopping...")
    finally:
        transcriber.stop()
        await socket_server.stop()

if __name__ == "__main__":
    asyncio.run(main())