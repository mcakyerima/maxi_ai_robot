# Jarvis Voice Assistant (Offline)

## Features
- Wake word detection: "Jarvis" using Porcupine
- Speech-to-text: Whisper
- Text-to-speech: Piper
- Works completely offline

## Installation

1. Install Python 3.8 or higher.
2. Create a virtual environment (optional):
   ```
   python -m venv venv
   source venv/bin/activate  # or venv\Scripts\activate on Windows
   ```
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
4. Download and place in the same directory:
   - Piper binary and model (e.g. `en_US-amy-medium.onnx`) from https://github.com/rhasspy/piper/releases
   - Porcupine keyword `.ppn` file (e.g. `jarvis.ppn`) from https://console.picovoice.ai

5. Run the assistant:
   ```
   python jarvis.py
   ```

Say “Jarvis” to wake the assistant.


python -m http.server 8080
