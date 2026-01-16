"""
Enhanced Voice Activity Detection listener with smart interruption handling and WO Mic support.
This version automatically detects and uses the WO Mic device, just like the wake word detector.
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
SILENCE_DURATION = 1.2  # Reduced for more responsive stopping
MAX_SILENT_FRAMES = int(SILENCE_DURATION * 1000 / FRAME_DURATION)

# Device selection (matching wake_word.py)
TARGET_MIC_NAME = "Microphone (WO Mic Device)"

# Configurable timeout settings
DEFAULT_LISTENING_TIMEOUT = 15.0  # Default 15 seconds
DEFAULT_SHORT_TIMEOUT = 5.0      # For quick responses
DEFAULT_WAKE_TIMEOUT = 30.0      # For wake word responses
TIMEOUT_ENABLED = True           # Global timeout toggle

# Global instances with device awareness
_audio = None
_vad = None
_selected_device_index = None
_device_initialized = False

def _find_wo_mic():
    """Find the WO Mic device index, matching wake_word.py logic."""
    global _selected_device_index
    
    try:
        audio = pyaudio.PyAudio()
        selected = None
        log_info("🎙️ Scanning for available input devices...")
        
        for i in range(audio.get_device_count()):
            try:
                dev = audio.get_device_info_by_index(i)
                if dev.get('maxInputChannels', 0) > 0:
                    name = dev.get('name', '')
                    log_info(f"   {i}: {name}")
                    if TARGET_MIC_NAME.lower() in name.lower():
                        selected = i
                        log_info(f"✅ Found WO Mic at device {i}: {name}")
                        break
            except Exception as e:
                log_warning(f"Error checking device {i}: {e}")
                continue
        
        audio.terminate()
        
        if selected is not None:
            log_info(f"🎯 Selected WO Mic device {selected}")
            _selected_device_index = selected
        else:
            log_warning(f"⚠️ {TARGET_MIC_NAME} not found - will use default input device")
            _selected_device_index = None
            
        return selected
    except Exception as e:
        log_error(f"Device enumeration error: {e}")
        _selected_device_index = None
        return None

def get_audio():
    """Get or create PyAudio instance with device detection."""
    global _audio, _device_initialized
    
    if _audio is None:
        _audio = pyaudio.PyAudio()
    
    # Initialize device detection once
    if not _device_initialized:
        _find_wo_mic()
        _device_initialized = True
    
    return _audio

def get_vad():
    """Get or create VAD instance."""
    global _vad
    if _vad is None:
        _vad = webrtcvad.Vad(2)  # Aggressiveness level 2 (medium)
    return _vad

def get_selected_device_index():
    """Get the selected device index (WO Mic preferred)."""
    global _selected_device_index, _device_initialized
    
    if not _device_initialized:
        get_audio()  # This will trigger device detection
    
    return _selected_device_index

def _create_audio_stream(audio, max_retries=3):
    """Create audio stream with proper device selection and conflict resolution."""
    device_index = get_selected_device_index()
    
    # Enhanced stream parameters for better reliability and reduced latency
    stream_params = {
        'format': FORMAT,
        'channels': CHANNELS,
        'rate': RATE,
        'input': True,
        'frames_per_buffer': FRAME_SIZE,
        'input_device_index': device_index,
        'start': False  # Don't auto-start to avoid conflicts
    }
    
    for attempt in range(max_retries):
        try:
            # Add delay on retry to allow device cleanup
            if attempt > 0:
                time.sleep(0.2 * attempt)  # Progressive delay
                log_info(f"🔄 Retry {attempt + 1}/{max_retries} opening audio stream...")
            
            # First attempt with selected device
            stream = audio.open(**stream_params)
            
            # Manual start after successful creation
            stream.start_stream()
            
            device_name = TARGET_MIC_NAME if device_index is not None else "default device"
            log_info(f"✅ Audio stream opened on {device_name} (attempt {attempt + 1})")
            return stream
            
        except Exception as e:
            log_warning(f"Attempt {attempt + 1} failed to open stream with device {device_index}: {e}")
            
            # On first failure, try fallback to default device
            if attempt == 0 and device_index is not None:
                log_info("🔄 Trying default audio device...")
                stream_params['input_device_index'] = None
                device_index = None  # Update for logging
            elif attempt == max_retries - 1:
                # Final attempt failed
                log_error(f"All {max_retries} attempts failed to open audio stream")
                raise e
            
            # Clean up any partial resources before retry
            try:
                if 'stream' in locals():
                    stream.close()
            except:
                pass
    
    raise RuntimeError("Failed to create audio stream after all retries")

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
    on_interruption: Optional[Callable] = None,
    timeout: Optional[float] = None
) -> bytes:
    """
    Record audio until silence is detected using WO Mic device.
    
    Args:
        tts_engine: TTS engine instance (for interruption detection)
        on_interruption: Callback function when interruption is detected
        timeout: Recording timeout in seconds
    
    Returns:
        Audio data as bytes, or empty bytes if no speech was detected
    """
    if timeout is None:
        timeout = DEFAULT_LISTENING_TIMEOUT if TIMEOUT_ENABLED else None
    
    audio = get_audio()
    vad = get_vad()
    
    stream = None
    try:
        stream = _create_audio_stream(audio)
        log_info("🎤 Listening for speech...")
        
        if timeout and TIMEOUT_ENABLED:
            return await asyncio.wait_for(
                _continue_recording(stream, vad, []),
                timeout=timeout
            )
        else:
            return await _continue_recording(stream, vad, [])
            
    except asyncio.TimeoutError:
        log_info("⏰ Recording timeout reached")
        return b''
    except Exception as e:
        log_error(f"Recording error: {e}")
        return b''
    finally:
        if stream:
            try:
                stream.stop_stream()
                stream.close()
            except Exception as e:
                log_warning(f"Error closing stream: {e}")

async def _continue_recording(stream, vad, initial_frames: list) -> bytes:
    """Continue recording until silence is detected with improved reliability."""
    frames = initial_frames.copy()
    silent_frames = 0
    has_speech = len(initial_frames) > 0
    speech_started = False
    consecutive_speech_frames = 0
    
    # Enhanced detection parameters
    MIN_SPEECH_FRAMES = 2  # Minimum frames before considering speech started
    
    while True:
        try:
            frame = stream.read(FRAME_SIZE, exception_on_overflow=False)
            
            # Enhanced speech detection with volume check
            is_speech = vad.is_speech(frame, RATE)
            volume = _calculate_frame_volume_enhanced(frame)
            
            # Combine VAD with volume threshold for better detection
            volume_threshold = 0.01  # Adjusted for WO Mic sensitivity
            enhanced_speech = is_speech or volume > volume_threshold
            
            if enhanced_speech:
                consecutive_speech_frames += 1
                silent_frames = 0
                frames.append(frame)
                
                # Only mark as having speech after minimum consecutive frames
                if consecutive_speech_frames >= MIN_SPEECH_FRAMES:
                    if not speech_started:
                        log_info("🗣️ Speech detected, recording...")
                        speech_started = True
                    has_speech = True
                    
            elif has_speech and speech_started:
                consecutive_speech_frames = 0
                silent_frames += 1
                frames.append(frame)
                
                if silent_frames > MAX_SILENT_FRAMES:
                    log_info("🛑 Silence detected, stopping recording")
                    break
            else:
                consecutive_speech_frames = 0
                # Don't accumulate frames if no speech has started yet
                if not speech_started:
                    frames.clear()
            
            await asyncio.sleep(0.005)  # Reduced sleep for better responsiveness
            
        except Exception as e:
            if "Input overflowed" not in str(e):
                log_error(f"Recording error: {e}")
            await asyncio.sleep(0.01)
            
    result = b''.join(frames) if has_speech else b''
    if result:
        duration = len(frames) * FRAME_DURATION / 1000.0
        log_info(f"✅ Recorded {duration:.1f}s of speech")
    else:
        log_info("❌ No speech captured")
    
    return result

async def record_until_silence_with_quality_check(
    tts_engine: Optional['InterruptAwareTTSEngine'] = None, 
    on_interruption: Optional[Callable] = None,
    timeout: Optional[float] = None
) -> bytes:
    """
    Record audio until silence with enhanced quality checking optimized for WO Mic.
    Includes proper resource management to avoid conflicts with wake word detector.
    
    Args:
        tts_engine: TTS engine instance (for interruption detection)
        on_interruption: Callback function when interruption is detected
        timeout: Recording timeout in seconds
    
    Returns:
        Audio data as bytes, or empty bytes if no quality speech was detected
    """
    if timeout is None:
        timeout = DEFAULT_LISTENING_TIMEOUT if TIMEOUT_ENABLED else None
    
    audio = get_audio()
    vad = get_vad()
    
    stream = None
    try:
        # Add small delay to ensure wake word detector has fully released device
        await asyncio.sleep(0.3)
        
        stream = _create_audio_stream(audio)
        log_info("🎤 Listening with enhanced quality check (WO Mic optimized)...")
        
        if timeout and TIMEOUT_ENABLED:
            frames = await asyncio.wait_for(
                _continue_recording_with_wo_mic_optimization(stream, vad, []),
                timeout=timeout
            )
        else:
            frames = await _continue_recording_with_wo_mic_optimization(stream, vad, [])
            
        return frames
        
    except asyncio.TimeoutError:
        log_info("⏰ Recording timeout reached")
        return b''
    except Exception as e:
        log_error(f"Recording error: {e}")
        return b''
    finally:
        if stream:
            try:
                stream.stop_stream()
                stream.close()
                log_info("🧹 Audio stream properly closed")
            except Exception as e:
                log_warning(f"Error closing stream: {e}")

async def _continue_recording_with_wo_mic_optimization(stream, vad, initial_frames: list) -> bytes:
    """
    Continue recording with WO Mic specific optimizations.
    Accounts for wireless latency and phone microphone characteristics.
    """
    frames = initial_frames.copy()
    silent_frames = 0
    has_speech = len(initial_frames) > 0
    speech_quality_frames = 0
    total_speech_frames = 0
    peak_volume = 0.0
    speech_started = False
    
    # WO Mic optimized thresholds
    MIN_SPEECH_DURATION = 0.2      # Account for wireless latency
    MIN_QUALITY_RATIO = 0.15       # Phone mics can be noisy
    MIN_PEAK_VOLUME = 0.015        # Adjusted for phone mic sensitivity
    WO_MIC_VOLUME_THRESHOLD = 0.008  # WO Mic specific threshold
    
    # Adaptive noise handling for wireless transmission
    volume_samples = []
    noise_floor_samples = []
    adaptive_threshold = WO_MIC_VOLUME_THRESHOLD
    
    log_info("🔍 Starting WO Mic optimized recording...")
    
    while True:
        try:
            frame = stream.read(FRAME_SIZE, exception_on_overflow=False)
            
            # Enhanced volume calculation for phone microphones
            volume = _calculate_wo_mic_volume(frame)
            is_speech = vad.is_speech(frame, RATE)
            
            # Track volume history for adaptive thresholding
            volume_samples.append(volume)
            if len(volume_samples) > 30:  # Longer history for wireless stability
                volume_samples.pop(0)
            
            # Update adaptive threshold every few frames
            if len(volume_samples) >= 15:
                sorted_volumes = sorted(volume_samples)
                noise_floor = np.mean(sorted_volumes[:5])  # Bottom samples as noise
                adaptive_threshold = max(WO_MIC_VOLUME_THRESHOLD, noise_floor + 0.003)
            
            # Enhanced speech detection combining VAD and volume
            volume_speech = volume > adaptive_threshold
            combined_speech = is_speech or volume_speech
            
            if combined_speech:
                total_speech_frames += 1
                silent_frames = 0
                frames.append(frame)
                
                if not speech_started:
                    log_info("🎙️ WO Mic speech detected...")
                    speech_started = True
                    
                has_speech = True
                
                # Track peak volume
                if volume > peak_volume:
                    peak_volume = volume
                
                # Quality assessment optimized for WO Mic
                if (volume > adaptive_threshold * 1.2 or  # Good volume
                    is_speech or                          # VAD confirms
                    volume > MIN_PEAK_VOLUME):           # Decent volume
                    speech_quality_frames += 1
                    
            elif has_speech and speech_started:
                silent_frames += 1
                frames.append(frame)
                
                if silent_frames > MAX_SILENT_FRAMES:
                    log_info("🔍 Analyzing WO Mic recording quality...")
                    break
            else:
                # Pre-speech: clear buffer to avoid noise accumulation
                if not speech_started:
                    frames.clear()

            await asyncio.sleep(0.005)  # Responsive for real-time feel
            
        except Exception as e:
            if "Input overflowed" not in str(e):
                log_error(f"WO Mic recording error: {e}")
            await asyncio.sleep(0.01)
    
    # WO Mic optimized quality assessment
    if has_speech and total_speech_frames > 0:
        speech_duration = total_speech_frames * FRAME_DURATION / 1000.0
        quality_ratio = speech_quality_frames / total_speech_frames if total_speech_frames > 0 else 0
        
        log_info(f"📊 WO Mic analysis: duration={speech_duration:.2f}s, "
                f"quality={quality_ratio:.2f}, peak_vol={peak_volume:.4f}, "
                f"threshold={adaptive_threshold:.4f}")
        
        # WO Mic specific acceptance criteria
        acceptance_conditions = [
            # Duration check (account for wireless latency)
            speech_duration >= MIN_SPEECH_DURATION,
            # Quality ratio (more lenient for phone mics)
            quality_ratio >= MIN_QUALITY_RATIO,
            # Peak volume (adjusted for WO Mic)
            peak_volume >= MIN_PEAK_VOLUME,
            # Frame count (ensure sufficient data)
            total_speech_frames >= 6,  # ~180ms minimum
            # Trust high-confidence speech
            (quality_ratio >= 0.3 and speech_duration >= 0.1)
        ]
        
        if any(acceptance_conditions):
            log_info("✅ WO Mic speech accepted")
            return b''.join(frames)
        else:
            log_info("❌ WO Mic speech rejected - insufficient quality")
            log_info(f"📋 Details: dur={speech_duration:.2f}s, qual={quality_ratio:.2f}, "
                    f"peak={peak_volume:.4f}, frames={total_speech_frames}")
            return b''
    else:
        log_info("🔇 No WO Mic speech detected")
    
    return b''

def _calculate_wo_mic_volume(frame: bytes) -> float:
    """Calculate volume optimized for WO Mic phone microphone characteristics."""
    try:
        audio_data = np.frombuffer(frame, dtype=np.int16)
        
        # Remove DC offset (important for phone mics)
        audio_data = audio_data - np.mean(audio_data)
        
        # Apply gentle high-pass filter for phone mic optimization
        if len(audio_data) > 1:
            # Simple first-order high-pass filter
            filtered = np.diff(audio_data, prepend=audio_data[0])
            audio_data = filtered * 0.7 + audio_data * 0.3
        
        # Calculate RMS with phone mic considerations
        rms = np.sqrt(np.mean(audio_data.astype(np.float32) ** 2))
        normalized = rms / 32768.0
        
        # Phone mic compression compensation
        if normalized < 0.05:
            normalized = normalized * 2.0  # Boost very quiet sounds
        elif normalized < 0.2:
            normalized = normalized * 1.3  # Moderate boost
        
        return min(normalized, 1.0)
    except Exception:
        return 0.0

def _calculate_frame_volume_enhanced(frame: bytes) -> float:
    """Calculate volume with noise reduction and enhancement."""
    return _calculate_wo_mic_volume(frame)  # Use WO Mic optimized version

def _calculate_frame_volume(frame: bytes) -> float:
    """Calculate volume of a single audio frame (backward compatibility)."""
    return _calculate_wo_mic_volume(frame)

def get_timeout_status() -> dict:
    """Get current timeout configuration status."""
    return {
        "enabled": TIMEOUT_ENABLED,
        "default_timeout": DEFAULT_LISTENING_TIMEOUT,
        "short_timeout": DEFAULT_SHORT_TIMEOUT,
        "wake_timeout": DEFAULT_WAKE_TIMEOUT
    }

def cleanup_audio():
    """Cleanup PyAudio resources and reset device detection."""
    global _audio, _device_initialized, _selected_device_index
    
    if _audio is not None:
        try:
            _audio.terminate()
            _audio = None
            _device_initialized = False
            _selected_device_index = None
            log_info("🧹 Audio resources and device detection reset")
        except Exception as e:
            log_error(f"Error cleaning up audio: {e}")

def reset_device_detection():
    """Force re-detection of audio devices (useful if WO Mic is reconnected)."""
    global _device_initialized, _selected_device_index
    _device_initialized = False
    _selected_device_index = None
    log_info("🔄 Device detection reset - will re-scan on next use")

# Convenience function for testing device selection
def test_wo_mic_detection():
    """Test function to verify WO Mic detection is working."""
    log_info("🧪 Testing WO Mic detection...")
    device_index = get_selected_device_index()
    
    if device_index is not None:
        log_info(f"✅ WO Mic detected at device index {device_index}")
        return True
    else:
        log_warning("❌ WO Mic not detected - check connection")
        return False

if __name__ == "__main__":
    # Test the device detection
    import time
    print("Testing WO Mic detection...")
    test_wo_mic_detection()
    
    print("\nTesting audio recording...")
    async def test_record():
        audio_data = await record_until_silence_with_quality_check(timeout=10.0)
        if audio_data:
            print(f"✅ Recorded {len(audio_data)} bytes of audio")
        else:
            print("❌ No audio recorded")
    
    asyncio.run(test_record())