# common/enums.py
from enum import Enum, auto

class AppMode(Enum):
    IDLE = auto()
    GENERAL_CHAT = auto()
    MATH_GESTURE = auto()
    
    def __str__(self):
        return self.name.replace('_', ' ').title()