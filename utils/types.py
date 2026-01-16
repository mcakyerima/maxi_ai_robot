# Stub for types.py
"""
Shared data types for Maxi AI.
Defines common schemas and data structures.
"""

from dataclasses import dataclass
from typing import List, Dict, Optional, Any, Union
from enum import Enum

class IntentType(Enum):
    """Enumeration of supported intent types."""
    GENERAL = "general"
    HUMOR = "humor"
    WEATHER = "weather"
    VISION = "vision"
    MATH = "math"
    GESTURE = "gesture"

@dataclass
class Intent:
    """Intent detection result."""
    type: IntentType
    confidence: float
    entities: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.entities is None:
            self.entities = {}

@dataclass
class UserMessage:
    """User message with metadata."""
    text: str
    timestamp: float
    audio_duration: Optional[float] = None

@dataclass
class AssistantResponse:
    """Assistant response with metadata."""
    text: str
    timestamp: float
    intent: IntentType
    
@dataclass
class ConversationContext:
    """Conversation context container."""
    messages: List[Dict[str, str]]
    
    def add_user_message(self, message: str) -> None:
        """Add user message to context."""
        self.messages.append({"role": "user", "content": message})
    
    def add_assistant_message(self, message: str) -> None:
        """Add assistant message to context."""
        self.messages.append({"role": "assistant", "content": message})
    
    def get_messages(self) -> List[Dict[str, str]]:
        """Get all messages."""
        return self.messages
    
    def get_last_n_messages(self, n: int) -> List[Dict[str, str]]:
        """Get last n messages."""
        return self.messages[-n:] if n < len(self.messages) else self.messages
