"""
Configuration module for Maxi AI.
Loads and manages configuration settings.
"""

import os
from dotenv import load_dotenv
from typing import Dict, Any

# Load environment variables from .env file
load_dotenv()

# Wake word detection configuration
WAKE_WORD_CONFIG = {
    "ACCESS_KEY": os.getenv("ACCESS_KEY", "XfAmeyEu0q6ce+DWkzWIk+pjTats3spIfXpRALD52YgGf/h7QXmFJA=="),
    "MODEL_PATH": os.getenv("HEY_MAXI_MODEL_PATH", "./Hey-Maxi_en_windows_v3_0_0.ppn")
}

# Audio configuration
AUDIO_CONFIG = {
    "FORMAT": "int16",
    "CHANNELS": 1,
    "RATE": 16000,
    "FRAME_DURATION_MS": 30,
    "SILENCE_DURATION_SEC": 1.5,
    "VAD_AGGRESSIVENESS": 2  # 0-3, 3 being most aggressive
}

# TTS configuration
TTS_CONFIG = {
    "VOICE": os.getenv("TTS_VOICE", "en-US-EmmaNeural"),
    "RATE": os.getenv("TTS_RATE", "+0%"),
    "PITCH": os.getenv("TTS_PITCH", "-2Hz")
}

# Speech recognition configuration
STT_CONFIG = {
    "MODEL": os.getenv("WHISPER_MODEL", "base"),
    "LANGUAGE": os.getenv("LANGUAGE", "en")
}

# LLM configuration
LLM_CONFIG = {
    "MODEL": os.getenv("OLLAMA_MODEL", "maxi-phi3"),
    "TEMPERATURE": float(os.getenv("LLM_TEMPERATURE", "0.7")),
    "MAX_TOKENS": int(os.getenv("LLM_MAX_TOKENS", "80")),
    "TOP_P": float(os.getenv("LLM_TOP_P", "0.9"))
}

# UI Server configuration
SERVER_CONFIG = {
    "HOST": os.getenv("SERVER_HOST", "localhost"),
    "PORT": int(os.getenv("SERVER_PORT", "8080")),
    "DEBUG": os.getenv("DEBUG", "False").lower() == "true"
}

def get_config(config_name: str) -> Dict[str, Any]:
    """
    Get configuration by name.
    
    Args:
        config_name: Name of the configuration to retrieve
        
    Returns:
        Configuration dictionary
    """
    configs = {
        "wake_word": WAKE_WORD_CONFIG,
        "audio": AUDIO_CONFIG,
        "tts": TTS_CONFIG,
        "stt": STT_CONFIG,
        "llm": LLM_CONFIG,
        "server": SERVER_CONFIG
    }
    
    return configs.get(config_name, {})
