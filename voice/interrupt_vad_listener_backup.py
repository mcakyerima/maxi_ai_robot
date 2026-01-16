"""
Enhanced Voice Activity Detection listener with smart interruption handling.
Simplified version without Alexa-style behaviors.
"""

import asyncio
import pyaudio
import webrtcvad
import numpy as np
import time
from typing import Optional, Callable, TYPE_CHECKING
from utils.logger import log_info, log_error, log_warning

# Type checking imports to avoid circular imports
if TYPE_CHECKING:
    from voice.interrupt_aware_speaker import InterruptAwareTTSEngine

# Audio Configuration
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
FRAME_DURATION = 30  # ms
FRAME_SIZE = int(RATE * FRAME_DURATION / 1000)
SILENCE_DURATION = 1.5  # seconds
MAX_SILENT_FRAMES = int(SILENCE_DURATION * 1000 / FRAME_DURATION)

# Configurable timeout settings
DEFAULT_LISTENING_TIMEOUT = 15.0  # Default 15 seconds
DEFAULT_SHORT_TIMEOUT = 5.0      # For quick responses
DEFAULT_WAKE_TIMEOUT = 30.0      # For wake word responses
TIMEOUT_ENABLED = True           # Global timeout toggle

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

def set_timeout_config(
    enabled: bool = True,
    default_timeout: float = 15.0,
    short_timeout: float = 5.0,
    wake_timeout: float = 30.0
):
    """Configure timeout settings globally."""
    global TIMEOUT_ENABLED, DEFAULT_LISTENING_TIMEOUT, DEFAULT_SHORT_TIMEOUT, DEFAULT_WAKE_TIMEOUT
    TIMEOUT_ENABLED = enabled
    DEFAULT_LISTENING_TIMEOUT = default_timeout
    DEFAULT_SHORT_TIMEOUT = short_timeout
    DEFAULT_WAKE_TIMEOUT = wake_timeout
    
    log_info(f"🔧 Timeout config updated: enabled={enabled}, "
             f"default={default_timeout}s, short={short_timeout}s, wake={wake_timeout}s")

async def record_until_silence(
    tts_engine: Optional['InterruptAwareTTSEngine'] = None, 
    on_interruption: Optional[Callable] = None
) -> bytes:
    """
    Record audio until silence is detected.
    
    Args:
        tts_engine: TTS engine instance (for interruption detection)
        on_interruption: Callback function when interruption is detected
    
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
        log_info("🎤 Listening... (speak now)")
        return await _continue_recording(stream, vad, [])
        
    finally:
        stream.stop_stream()
        stream.close()

async def _continue_recording(stream, vad, initial_frames: list) -> bytes:
    """Continue recording until silence is detected."""
    frames = initial_frames.copy()
    silent_frames = 0
    has_speech = len(initial_frames) > 0

    while True:
        try:
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
                    log_info("🛑 Silence detected, stopping recording")
                    break
            
            await asyncio.sleep(0.01)
        except Exception as e:
            if "Input overflowed" not in str(e):
                log_error(f"Recording error: {e}")
            await asyncio.sleep(0.01)
            
    return b''.join(frames) if has_speech else b''

async def record_until_silence_with_quality_check(
    tts_engine: Optional['InterruptAwareTTSEngine'] = None, 
    on_interruption: Optional[Callable] = None
) -> bytes:
    """
    Record audio until silence with ULTRA-SENSITIVE quality checking for noisy environments.
    Now accepts even very short utterances like "Hello" or "Stop".
    
    Args:
        tts_engine: TTS engine instance (for interruption detection)
        on_interruption: Callback function when interruption is detected
    
    Returns:
        Audio data as bytes, or empty bytes if no quality speech was detected
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
        log_info("🎤 Listening with ultra-sensitive quality check...")
        frames = await _continue_recording_with_ultra_sensitivity(stream, vad, [])
        return frames  # This now returns bytes directly
    except Exception as e:
        log_error(f"Recording error: {e}")
        return b''
    finally:
        stream.stop_stream()
        stream.close()

async def _continue_recording_with_ultra_sensitivity(stream, vad, initial_frames: list) -> bytes:
    """
    Continue recording with ULTRA-SENSITIVE quality assessment.
    Designed to work perfectly in noisy environments and accept short utterances.
    """
    frames = initial_frames.copy()
    silent_frames = 0
    has_speech = len(initial_frames) > 0
    speech_quality_frames = 0
    total_speech_frames = 0
    peak_volume = 0.0
    
    # ULTRA-SENSITIVE thresholds - much more lenient
    MIN_SPEECH_DURATION = 0.1      # Accept even 100ms of speech
    MIN_QUALITY_RATIO = 0.05       # Only 5% of frames need "good" quality
    MIN_PEAK_VOLUME = 0.01         # Very low peak volume threshold
    NOISE_FLOOR = 0.005            # Adaptive noise floor
    
    # Adaptive volume thresholds
    volume_samples = []
    adaptive_threshold = NOISE_FLOOR
    
    while True:
        try:
            frame = stream.read(FRAME_SIZE, exception_on_overflow=False)
            is_speech = vad.is_speech(frame, RATE)
            
            # Calculate volume with noise reduction
            volume = _calculate_frame_volume_enhanced(frame)
            volume_samples.append(volume)
            
            # Keep only recent samples for adaptive threshold
            if len(volume_samples) > 20:
                volume_samples.pop(0)
            
            # Update adaptive threshold (noise floor + small buffer)
            if len(volume_samples) >= 10:
                sorted_volumes = sorted(volume_samples)
                noise_floor = np.mean(sorted_volumes[:5])  # Bottom 25% as noise floor
                adaptive_threshold = max(NOISE_FLOOR, noise_floor + 0.002)
            
            if is_speech:
                has_speech = True
                total_speech_frames += 1
                silent_frames = 0
                frames.append(frame)
                
                # Track peak volume
                if volume > peak_volume:
                    peak_volume = volume
                
                # ULTRA-LENIENT quality assessment
                # Accept frame as "good quality" if:
                # 1. Volume is above adaptive threshold, OR
                # 2. Volume is above minimum peak, OR  
                # 3. VAD detected speech (trust VAD more)
                if (volume > adaptive_threshold or 
                    volume > MIN_PEAK_VOLUME or 
                    is_speech):
                    speech_quality_frames += 1
                    
            elif has_speech:
                silent_frames += 1
                frames.append(frame)
                if silent_frames > MAX_SILENT_FRAMES:
                    log_info("🔍 Silence detected, assessing speech quality...")
                    break

            await asyncio.sleep(0.01)
        except Exception as e:
            if "Input overflowed" not in str(e):
                log_error(f"Recording error: {e}")
            await asyncio.sleep(0.01)
    
    # ULTRA-LENIENT quality assessment
    if has_speech and total_speech_frames > 0:
        speech_duration = total_speech_frames * FRAME_DURATION / 1000.0
        quality_ratio = speech_quality_frames / total_speech_frames if total_speech_frames > 0 else 0
        
        log_info(f"🔍 Speech quality: duration={speech_duration:.2f}s, "
                f"quality={quality_ratio:.2f}, peak_vol={peak_volume:.4f}, "
                f"threshold={adaptive_threshold:.4f}")
        
        # ACCEPT speech if ANY of these conditions are met:
        acceptance_conditions = [
            # Duration-based acceptance (very short utterances OK)
            speech_duration >= MIN_SPEECH_DURATION,
            # Quality-based acceptance (very lenient)
            quality_ratio >= MIN_QUALITY_RATIO,
            # Peak volume acceptance (even quiet speech)
            peak_volume >= MIN_PEAK_VOLUME,
            # Trust VAD if it detected speech frames
            total_speech_frames >= 3  # At least 3 speech frames (~90ms)
        ]
        
        if any(acceptance_conditions):
            log_info("✅ Speech accepted (ultra-sensitive mode)")
            return b''.join(frames)
        else:
            log_info("❌ Speech rejected - extremely low quality")
            log_info(f"Analysis: dur={speech_duration:.2f}s, qual={quality_ratio:.2f}, "
                    f"peak={peak_volume:.4f}, frames={total_speech_frames}")
            return b''
    else:
        log_info("🔍 No speech detected")
    
    return b''

def _calculate_frame_volume_enhanced(frame: bytes) -> float:
    """Calculate volume with noise reduction and enhancement."""
    try:
        audio_data = np.frombuffer(frame, dtype=np.int16)
        
        # Apply simple noise reduction
        # Remove DC offset
        audio_data = audio_data - np.mean(audio_data)
        
        # Calculate RMS with slight emphasis on higher frequencies
        rms = np.sqrt(np.mean(audio_data.astype(np.float32) ** 2))
        
        # Normalize and apply slight compression for quiet sounds
        normalized = rms / 32768.0
        
        # Compress quiet sounds less (make them relatively louder)
        if normalized < 0.1:
            normalized = normalized * 1.5  # Boost quiet sounds
        
        return min(normalized, 1.0)  # Cap at 1.0
    except:
        return 0.0

def _calculate_frame_volume(frame: bytes) -> float:
    """Calculate volume of a single audio frame (backward compatibility)."""
    return _calculate_frame_volume_enhanced(frame)

def get_timeout_status() -> dict:
    """Get current timeout configuration status."""
    return {
        "enabled": TIMEOUT_ENABLED,
        "default_timeout": DEFAULT_LISTENING_TIMEOUT,
        "short_timeout": DEFAULT_SHORT_TIMEOUT,
        "wake_timeout": DEFAULT_WAKE_TIMEOUT
    }

def cleanup_audio():
    """Cleanup PyAudio resources."""
    global _audio
    if _audio is not None:
        try:
            _audio.terminate()
            _audio = None
            log_info("🧹 Audio resources cleaned up")
        except Exception as e:
            log_error(f"Error cleaning up audio: {e}")

