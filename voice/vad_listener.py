# Relative path: voice\vad_listener.py
"""
Voice Activity Detection listener for Maxi AI.
Records audio until silence is detected.
"""

import asyncio
import pyaudio
import webrtcvad
import numpy as np
from typing import Optional

# Audio Configuration
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
FRAME_DURATION = 30  # ms
FRAME_SIZE = int(RATE * FRAME_DURATION / 1000)
SILENCE_DURATION = 1.5  # seconds
MAX_SILENT_FRAMES = int(SILENCE_DURATION * 1000 / FRAME_DURATION)

# Initialize global PyAudio instance to avoid multiple initializations
_audio = None
_vad = None

def get_audio():
    """Get or create PyAudio instance."""
    global _audio
    if _audio is None:
        _audio = pyaudio.PyAudio()
    return _audio

def get_vad():
    """Get or create VAD instance."""
    global _vad
    if _vad is None:
        _vad = webrtcvad.Vad(2)  # Aggressiveness level 2 (medium)
    return _vad

async def record_until_silence() -> bytes:
    """
    Record audio until silence is detected.
    
    Returns:
        Audio data as bytes, or empty bytes if no speech was detected
    """
    audio = get_audio()
    vad = get_vad()
    
    stream = audio.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        input=True,
        frames_per_buffer=FRAME_SIZE
    )
    
    try:
        print("🎤 Listening... (speak now)")
        frames = []
        silent_frames = 0
        has_speech = False

        while True:
            frame = stream.read(FRAME_SIZE, exception_on_overflow=False)
            is_speech = vad.is_speech(frame, RATE)
            
            if is_speech:
                has_speech = True
                silent_frames = 0
                frames.append(frame)
            elif has_speech:
                silent_frames += 1
                frames.append(frame)
                if silent_frames > MAX_SILENT_FRAMES:
                    print("🛑 Silence detected")
                    break
                    
        return b''.join(frames) if has_speech else b''
        
    finally:
        stream.stop_stream()
        stream.close()

def cleanup_audio():
    """Cleanup PyAudio resources."""
    global _audio
    if _audio is not None:
        _audio.terminate()
        _audio = None