"""
Optimized Wake Word Detector with WO Mic Auto-Selection and stoppable listening.

This module provides:
- WakeWordEngine: the low-level detector (uses openwakeword + pyaudio)
- listen_for_wake_word(stop_event=None): blocking function that returns True when wake is detected.
  It can be safely run inside `asyncio.to_thread(listen_for_wake_word, stop_event)` so the event loop
  remains responsive. The stop_event is a threading.Event that, when set, will cause the listener
  to exit cleanly and return False.
"""

from collections import deque
import threading
import numpy as np
import pyaudio
import time

# If openwakeword import fails in your environment, keep your original import style.
try:
    import openwakeword
    from openwakeword.model import Model
except Exception:
    # If the environment isn't set up with openwakeword, we still keep the file importable.
    # Real runtime will only work if the dependency is available.
    Model = None
    openwakeword = None

# Configuration - adjust these to match your original values
MODEL_NAME = "hey_jarvis"
SAMPLE_RATE = 16000
CHUNK_SIZE = 1280
ENERGY_THRESHOLD = 300
CONFIDENCE_THRESHOLD = 0.30
SMOOTHING_WINDOW = 5
TARGET_MIC_NAME = "Microphone (WO Mic Device)"
READ_TIMEOUT = 0.01  # seconds to yield in busy loops

class WakeWordEngine:
    """
    Encapsulates the wake word detection engine and audio stream.
    Uses a small smoothing window to avoid false positives.
    """
    def __init__(self, stop_event: threading.Event = None):
        self.model = None
        self.audio = None
        self.stream = None
        self.prediction_history = deque(maxlen=SMOOTHING_WINDOW)
        self.selected_device_index = None
        self.stop_event = stop_event or threading.Event()
        self._initialized = False

    def _find_wo_mic(self):
        """Automatically find the best WO Mic device index; return None to use default device."""
        try:
            audio = pyaudio.PyAudio()
            selected = None
            print("\nAvailable Input Devices:")
            for i in range(audio.get_device_count()):
                dev = audio.get_device_info_by_index(i)
                if dev.get('maxInputChannels', 0) > 0:
                    name = dev.get('name', '')
                    print(f"{i}: {name}")
                    if TARGET_MIC_NAME.lower() in name.lower():
                        selected = i
                        break
            audio.terminate()
            if selected is not None:
                print(f"\n✅ Selected device {selected}: {TARGET_MIC_NAME}")
            else:
                print(f"\n⚠️ {TARGET_MIC_NAME} not found - using default input device")
            return selected
        except Exception as e:
            print(f"Device enumeration error: {e}")
            return None

    def initialize(self) -> bool:
        """Initialize the openwakeword model and audio stream."""
        try:
            if Model is None:
                raise RuntimeError("openwakeword Model unavailable in environment")

            self.model = Model(
                wakeword_models=[MODEL_NAME],
                inference_framework='onnx',
                vad_threshold=0.3
            )

            self.audio = pyaudio.PyAudio()
            self.selected_device_index = self._find_wo_mic()

            self.stream = self.audio.open(
                rate=SAMPLE_RATE,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                frames_per_buffer=CHUNK_SIZE,
                input_device_index=self.selected_device_index,
                start=True
            )
            self._initialized = True
            return True
        except Exception as e:
            print(f"Initialization error (wake word): {e}")
            self._initialized = False
            return False

    def stop(self):
        """Signal the listening loop to stop as soon as possible."""
        try:
            self.stop_event.set()
        except Exception:
            pass

    def process_frame(self) -> bool:
        """
        Read a single frame from the audio stream and return True if wake word likely present.
        This method is intentionally lightweight and returns False on read errors.
        """
        try:
            if not self.stream:
                return False

            # Check if we should stop before processing
            if self.stop_event.is_set():
                return False

            # Read raw bytes; guard overflow
            data = self.stream.read(CHUNK_SIZE, exception_on_overflow=False)
            frame = np.frombuffer(data, dtype=np.int16)

            # Quick energy check to avoid running model on silence
            if np.abs(frame).mean() < ENERGY_THRESHOLD:
                return False

            # Predict using model - get confidence for our wake model
            preds = self.model.predict(frame)
            confidence = float(preds.get(MODEL_NAME, 0.0))
            self.prediction_history.append(confidence)
            smoothed = float(sum(self.prediction_history) / len(self.prediction_history))

            # Visual confidence bar for CLI feedback (kept similar to your previous behaviour)
            bar = "#" * int(confidence * 50)
            print(f"\rConfidence: {confidence:.3f} [{bar:<50}]", end="", flush=True)

            return smoothed > CONFIDENCE_THRESHOLD

        except Exception as e:
            # Non-fatal - return False and continue
            print(f"\nDetection error: {e}")
            return False

    def cleanup(self):
        """Clean up audio resources."""
        try:
            if self.stream:
                try:
                    self.stream.stop_stream()
                    self.stream.close()
                except Exception:
                    pass
                self.stream = None
            if self.audio:
                try:
                    self.audio.terminate()
                except Exception:
                    pass
                self.audio = None
        except Exception:
            pass


def listen_for_wake_word(stop_event: threading.Event = None) -> bool:
    """
    Blocking wake word listener. Intended to be executed inside `asyncio.to_thread`.
    Accepts an optional `stop_event` (threading.Event) that can be set externally to abort listening.
    Returns True on detection, False if stopped or error occurs.
    """
    engine = WakeWordEngine(stop_event=stop_event)
    if not engine.initialize():
        print("❌ Failed to initialize wake word detector")
        return False

    print(f"\n🎙️ Listening for '{MODEL_NAME}' using WO Mic...")

    try:
        while True:
            # Allow external stop requests via stop_event
            if stop_event is not None and stop_event.is_set():
                print("\n🛑 Wake word listening stopped by request")
                return False

            # Run a single frame check
            detected = engine.process_frame()
            if detected:
                print(f"\n🎯 Detected '{MODEL_NAME}'")
                return True

            # Small sleep to reduce CPU in case audio.read is too fast
            time.sleep(READ_TIMEOUT)

    except KeyboardInterrupt:
        print("\n⛹ Stopped by user")
        return False
    except Exception as e:
        print(f"\n❌ Wake word detection error: {e}")
        return False
    finally:
        engine.cleanup()
        print("\n🧹 Wake word engine cleaned up")

    return False


if __name__ == "__main__":
    print("🎯 WO Mic Wake Word Detector")
    listen_for_wake_word()