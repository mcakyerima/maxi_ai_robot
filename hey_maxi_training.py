#!/usr/bin/env python3
"""
Custom "Hey Maxi" Model Training for OpenWakeWord
Complete pipeline: data collection → training → integration
"""

import os
import numpy as np
import sounddevice as sd
import soundfile as sf
import librosa
from pathlib import Path
import time
import json

# ============================================================================
# STEP 1: DATA COLLECTION
# ============================================================================

class AudioCollector:
    """Collect audio samples for training"""
    
    def __init__(self, output_dir="hey_maxi_data", sample_rate=16000, duration=1.5):
        self.output_dir = Path(output_dir)
        self.sample_rate = sample_rate
        self.duration = duration
        self.setup_directories()
    
    def setup_directories(self):
        """Create directory structure"""
        self.positive_dir = self.output_dir / "positive"
        self.negative_dir = self.output_dir / "negative"
        
        self.positive_dir.mkdir(parents=True, exist_ok=True)
        self.negative_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"📁 Created directories:")
        print(f"   Positive samples: {self.positive_dir}")
        print(f"   Negative samples: {self.negative_dir}")
    
    def record_audio(self, filename, countdown=3):
        """Record a single audio sample"""
        print(f"🎤 Recording {filename} in:", end=" ")
        for i in range(countdown, 0, -1):
            print(f"{i}...", end=" ", flush=True)
            time.sleep(1)
        print("🔴 RECORDING!")
        
        # Record audio
        audio = sd.rec(
            int(self.duration * self.sample_rate), 
            samplerate=self.sample_rate, 
            channels=1,
            dtype=np.float32
        )
        sd.wait()  # Wait for recording to complete
        
        # Save to file
        sf.write(filename, audio, self.sample_rate)
        print(f"✅ Saved: {filename}")
        
        return audio
    
    def collect_positive_samples(self, num_samples=50):
        """Collect positive samples (saying 'Hey Maxi')"""
        print(f"\n🎯 COLLECTING POSITIVE SAMPLES")
        print(f"📝 Say 'Hey Maxi' clearly {num_samples} times")
        print(f"💡 Vary your tone, speed, and volume slightly")
        
        for i in range(num_samples):
            filename = self.positive_dir / f"hey_maxi_{i:03d}.wav"
            print(f"\n[{i+1}/{num_samples}] ", end="")
            self.record_audio(filename)
            
            if i < num_samples - 1:
                input("Press Enter for next recording...")
    
    def collect_negative_samples(self, num_samples=100):
        """Collect negative samples (random speech/noise)"""
        print(f"\n❌ COLLECTING NEGATIVE SAMPLES")
        print(f"📝 Say random words, make noise, or stay silent {num_samples} times")
        print(f"💡 Include: other names, similar sounds, background noise")
        
        for i in range(num_samples):
            filename = self.negative_dir / f"negative_{i:03d}.wav"
            print(f"\n[{i+1}/{num_samples}] ", end="")
            self.record_audio(filename)
            
            if i < num_samples - 1:
                input("Press Enter for next recording...")
    
    def quick_collect(self):
        """Quick collection with minimal samples for testing"""
        print("🚀 QUICK COLLECTION MODE (for testing)")
        self.collect_positive_samples(10)
        self.collect_negative_samples(20)

# ============================================================================
# STEP 2: TRAINING SCRIPT
# ============================================================================

def create_training_script():
    """Generate the training script"""
    training_code = '''

# OpenWakeWord Training Script for "Hey Maxi"
# Run this after collecting data with the AudioCollector

import os
import numpy as np
import tensorflow as tf
from openwakeword.train import train_model
from openwakeword.data_generator import WakeWordDataGenerator
import json

def train_hey_maxi_model():
    """Train the Hey Maxi wake word model"""
    
    # Configuration
    config = {
        "model_name": "hey_maxi",
        "data_dir": "hey_maxi_data",
        "output_dir": "hey_maxi_model", 
        "epochs": 10,
        "batch_size": 32,
        "learning_rate": 0.001,
        "validation_split": 0.2
    }
    
    print("🏋️ Training Hey Maxi model...")
    print(f"📊 Config: {json.dumps(config, indent=2)}")
    
    # Create data generator
    data_gen = WakeWordDataGenerator(
        positive_data_dir=f"{config['data_dir']}/positive",
        negative_data_dir=f"{config['data_dir']}/negative",
        target_phrase="hey_maxi"
    )
    
    # Train the model
    model = train_model(
        data_generator=data_gen,
        model_name=config["model_name"],
        epochs=config["epochs"],
        batch_size=config["batch_size"],
        learning_rate=config["learning_rate"],
        validation_split=config["validation_split"],
        output_dir=config["output_dir"]
    )
    
    print(f"✅ Model trained and saved to: {config['output_dir']}")
    return model

if __name__ == "__main__":
    train_hey_maxi_model()
'''
    
    with open("train_hey_maxi.py", "w") as f:
        f.write(training_code)
    
    print("📄 Created train_hey_maxi.py")

# ============================================================================
# STEP 3: INTEGRATION WITH YOUR DETECTOR
# ============================================================================

def update_detector_for_custom_model():
    """Update your detector to use the custom model"""
    
    integration_code = '''
#!/usr/bin/env python3
"""
Updated OpenWakeWord Implementation with Custom "Hey Maxi" Model
"""

import openwakeword
from openwakeword import Model
import pyaudio
import numpy as np
import time
import os

# Configuration with custom model
CUSTOM_MODEL_PATH = "hey_maxi_model/hey_maxi.onnx"  # Path to your trained model
WAKE_MODELS = [
    "alexa",           # Keep some built-in models for testing
    "hey_jarvis",      
]

# Add custom model if it exists
if os.path.exists(CUSTOM_MODEL_PATH):
    WAKE_MODELS.append(CUSTOM_MODEL_PATH)
    print(f"✅ Custom Hey Maxi model found: {CUSTOM_MODEL_PATH}")
else:
    print(f"⚠️  Custom model not found at: {CUSTOM_MODEL_PATH}")
    print("   Using built-in models only")

# Audio configuration
CHUNK = 1280
RATE = 16000
CHANNELS = 1
CONFIDENCE_THRESHOLD = 0.6  # Higher threshold for custom models

class CustomWakeWordDetector:
    """Enhanced detector with custom model support"""
    
    def __init__(self, models=None, threshold=0.6, debug=False):
        self.models = models or WAKE_MODELS
        self.threshold = threshold
        self.debug = debug
        self.model = None
        self.audio_stream = None
        self.pa = None
        
    def initialize(self):
        """Initialize with custom and built-in models"""
        try:
            print("🔄 Initializing OpenWakeWord with custom model...")
            
            # Load models (mix of custom and built-in)
            model_dict = {}
            
            for model_path in self.models:
                if os.path.exists(model_path) and model_path.endswith('.onnx'):
                    # Custom model
                    model_name = os.path.basename(model_path).replace('.onnx', '')
                    model_dict[model_name] = model_path
                    print(f"📦 Loading custom model: {model_name}")
                else:
                    # Built-in model
                    print(f"📦 Loading built-in model: {model_path}")
            
            # Initialize OpenWakeWord
            if model_dict:
                self.model = Model(
                    wakeword_models=list(model_dict.keys()),
                    inference_framework='onnx'
                )
            else:
                self.model = Model(
                    wakeword_models=[m for m in self.models if not m.endswith('.onnx')],
                    inference_framework='onnx'
                )
            
            available_models = list(self.model.prediction_buffer.keys())
            print(f"✅ Active models: {available_models}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error initializing: {e}")
            return False
    
    def setup_audio(self):
        """Setup audio input"""
        try:
            self.pa = pyaudio.PyAudio()
            self.audio_stream = self.pa.open(
                format=pyaudio.paInt16,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK
            )
            print(f"✅ Audio ready: {RATE}Hz")
            return True
        except Exception as e:
            print(f"❌ Audio error: {e}")
            return False
    
    def listen_once(self):
        """Single detection cycle"""
        try:
            audio_data = self.audio_stream.read(CHUNK, exception_on_overflow=False)
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            
            predictions = self.model.predict(audio_array)
            
            for wake_word, confidence in predictions.items():
                confidence_bar = "#" * int(confidence * 50)
                print(f"\r{wake_word}: {confidence:.3f} [{confidence_bar:<50}]", end="")
                if confidence > self.threshold:
                    print(f"🗣 ✅ WAKE WORD: '{wake_word}' ({confidence:.3f})")
                    
                    # Special handling for Hey Maxi
                    if "hey_maxi" in wake_word.lower():
                        print("👋 Hey there! Maxi detected successfully!")
                    
                    return True
                elif self.debug and confidence > 0.2:
                    print(f"🔍 '{wake_word}': {confidence:.3f}")
                    
            return False
            
        except Exception as e:
            if self.debug:
                print(f"❌ Detection error: {e}")  
            return False
    
    def cleanup(self):
        """Cleanup resources"""
        try:
            if self.audio_stream:
                self.audio_stream.stop_stream()
                self.audio_stream.close()
            if self.pa:
                self.pa.terminate()
            print("🔇 Cleanup complete")
        except:
            pass

def listen_for_wake_word():
    """Drop-in replacement with Hey Maxi support"""
    detector = CustomWakeWordDetector(
        models=WAKE_MODELS,
        threshold=CONFIDENCE_THRESHOLD,
        debug=False
    )
    
    if not detector.initialize() or not detector.setup_audio():
        detector.cleanup()
        return False
    
    print("👂 Listening for 'Hey Maxi' and other wake words...")
    
    try:
        while True:
            if detector.listen_once():
                detector.cleanup()
                return True
    except KeyboardInterrupt:
        print("\\n⏹ Stopping...")
    finally:
        detector.cleanup()
    
    return False

if __name__ == "__main__":
    # Test the custom model
    listen_for_wake_word()
'''
    
    with open("custom_hey_maxi_detector.py", "w") as f:
        f.write(integration_code)
    
    print("📄 Created custom_hey_maxi_detector.py")

# ============================================================================
# MAIN WORKFLOW
# ============================================================================

def main():
    """Complete workflow for custom Hey Maxi model"""
    print("🎯 Custom 'Hey Maxi' Wake Word Training")
    print("=" * 50)
    
    print("\nChoose an option:")
    print("1. Collect training data")
    print("2. Quick collect (10 positive, 20 negative)")
    print("3. Generate training script")
    print("4. Generate integration code")
    print("5. Full setup (all steps)")
    
    choice = input("\nEnter choice (1-5): ").strip()
    
    if choice == "1":
        collector = AudioCollector()
        collector.collect_positive_samples(50)
        collector.collect_negative_samples(100)
        
    elif choice == "2":
        collector = AudioCollector()
        collector.quick_collect()
        
    elif choice == "3":
        create_training_script()
        
    elif choice == "4":
        update_detector_for_custom_model()
        
    elif choice == "5":
        print("🚀 Full setup mode")
        
        # Step 1: Collect data
        collector = AudioCollector()
        collector.quick_collect()
        
        # Step 2: Create training script
        create_training_script()
        
        # Step 3: Create integration code
        update_detector_for_custom_model()
        
        print("\n✅ Setup complete! Next steps:")
        print("1. Run: python train_hey_maxi.py")
        print("2. Test: python custom_hey_maxi_detector.py")
        
    else:
        print("❌ Invalid choice")

if __name__ == "__main__":
    main()