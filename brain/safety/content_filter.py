# brain/safety/content_filter.py
"""
Content safety filter for kid-friendly interactions.
Blocks inappropriate content and ensures age-appropriate responses.
"""

import re
from typing import Tuple, Optional
from datetime import datetime
from utils.logger import log_info, log_warning


class ContentFilter:
    """
    Content filtering system for Nigerian children ages 6-12.
    Designed to block inappropriate content while being culturally sensitive.
    """

    # Inappropriate keywords (basic list - expandable)
    INAPPROPRIATE_KEYWORDS = {
        # Violence & harmful content
        'kill', 'murder', 'death', 'die', 'suicide', 'weapon', 'gun', 'knife', 'bomb',
        'hurt', 'pain', 'blood', 'fight', 'attack', 'war',

        # Inappropriate topics for kids
        'sex', 'porn', 'nude', 'naked', 'adult', 'sexy',

        # Drugs & substances
        'drug', 'alcohol', 'beer', 'wine', 'cigarette', 'smoke', 'weed', 'cocaine',

        # Profanity (mild - kid context)
        'stupid', 'idiot', 'dumb', 'hate', 'damn', 'hell', 'ass',

        # Dangerous activities
        'steal', 'rob', 'cheat', 'lie', 'trick', 'scam',
    }

    # Patterns that indicate inappropriate requests
    INAPPROPRIATE_PATTERNS = [
        r'how\s+to\s+(hurt|kill|harm)',
        r'make\s+a?\s*(weapon|bomb|gun)',
        r'bypass\s+(security|safety|lock)',
        r'hack\s+',
        r'steal\s+',
        r'where\s+to\s+buy\s+(drug|alcohol|cigarette)',
    ]

    # Age-appropriate response indicators
    AGE_APPROPRIATE_KEYWORDS = {
        'learn', 'school', 'teach', 'fun', 'play', 'friend', 'family',
        'math', 'science', 'animal', 'plant', 'space', 'earth', 'water',
        'color', 'number', 'letter', 'book', 'story', 'song', 'game',
        'food', 'fruit', 'vegetable', 'toy', 'help', 'thank', 'please'
    }

    # Fallback responses for blocked content
    FALLBACK_RESPONSES = [
        "Hmm, I don't think that's a good question for me to answer. Let's talk about something fun like science or math!",
        "That's not something I can help with. How about we learn something cool instead?",
        "I'm here to help you learn and have fun! Can you ask me about school topics instead?",
        "Let's keep our conversations friendly and educational! Ask me about animals, space, or math!",
    ]

    def __init__(self):
        self.blocked_count = 0
        self.session_id = None

    def set_session(self, session_id: str):
        """Set current session ID for logging."""
        self.session_id = session_id

    def filter_input(self, text: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Filter user input for inappropriate content.

        Args:
            text: User input text

        Returns:
            Tuple of (is_safe, filtered_reason, fallback_response)
            - is_safe: True if safe, False if blocked
            - filtered_reason: Reason for blocking (None if safe)
            - fallback_response: Kid-friendly response to use instead
        """
        text_lower = text.lower()

        # Check for inappropriate keywords
        for keyword in self.INAPPROPRIATE_KEYWORDS:
            if re.search(r'\b' + keyword + r'\b', text_lower):
                log_warning(f"🛡️ Blocked input - keyword: {keyword}")
                self.blocked_count += 1
                return (
                    False,
                    f"inappropriate_keyword:{keyword}",
                    self._get_fallback_response()
                )

        # Check for inappropriate patterns
        for pattern in self.INAPPROPRIATE_PATTERNS:
            if re.search(pattern, text_lower):
                log_warning(f"🛡️ Blocked input - pattern: {pattern}")
                self.blocked_count += 1
                return (
                    False,
                    f"inappropriate_pattern:{pattern}",
                    self._get_fallback_response()
                )

        # Check for excessive caps (yelling)
        if len(text) > 10 and sum(1 for c in text if c.isupper()) / len(text) > 0.7:
            log_info(f"⚠️ Excessive caps detected, normalizing")
            # Don't block, just normalize
            text = text.capitalize()

        log_info(f"✅ Input passed safety filter")
        return (True, None, None)

    def filter_output(self, text: str) -> Tuple[bool, str]:
        """
        Filter LLM output to ensure age-appropriate content.

        Args:
            text: LLM response text

        Returns:
            Tuple of (is_safe, sanitized_text)
            - is_safe: True if safe, False if needs replacement
            - sanitized_text: Cleaned text or fallback
        """
        text_lower = text.lower()

        # Check for inappropriate keywords in output
        for keyword in self.INAPPROPRIATE_KEYWORDS:
            if re.search(r'\b' + keyword + r'\b', text_lower):
                log_warning(f"🛡️ Blocked output - keyword: {keyword}")
                self.blocked_count += 1
                return (False, self._get_fallback_response())

        # Check for URLs (prevent external links)
        if re.search(r'http[s]?://|www\.', text_lower):
            log_warning(f"🛡️ Blocked output - contains URL")
            text = re.sub(r'http[s]?://[^\s]+|www\.[^\s]+',
                          '[link removed]', text)

        # Check for complex words (simplify if needed)
        # This is basic - can be enhanced with vocabulary level checking

        log_info(f"✅ Output passed safety filter")
        return (True, text)

    def validate_response_appropriateness(self, text: str) -> float:
        """
        Score response appropriateness for kids (0.0 to 1.0).
        Higher score = more appropriate.

        Args:
            text: Response text to validate

        Returns:
            Score from 0.0 (inappropriate) to 1.0 (very appropriate)
        """
        text_lower = text.lower()
        score = 0.5  # Start neutral

        # Bonus for age-appropriate keywords
        appropriate_count = sum(
            1 for keyword in self.AGE_APPROPRIATE_KEYWORDS
            if keyword in text_lower
        )
        score += min(0.3, appropriate_count * 0.05)

        # Penalty for inappropriate keywords
        inappropriate_count = sum(
            1 for keyword in self.INAPPROPRIATE_KEYWORDS
            if keyword in text_lower
        )
        score -= min(0.5, inappropriate_count * 0.2)

        # Bonus for short, simple sentences
        sentences = text.split('.')
        avg_sentence_length = sum(len(s.split())
                                  for s in sentences) / max(len(sentences), 1)
        if avg_sentence_length < 15:  # Kid-friendly length
            score += 0.1

        # Bonus for questions (engaging)
        if '?' in text:
            score += 0.05

        return max(0.0, min(1.0, score))

    def _get_fallback_response(self) -> str:
        """Get a random fallback response for blocked content."""
        import random
        return random.choice(self.FALLBACK_RESPONSES)

    def get_stats(self) -> dict:
        """Get filtering statistics."""
        return {
            'blocked_count': self.blocked_count,
            'session_id': self.session_id
        }


# Global filter instance
_filter_instance = ContentFilter()


def filter_input(text: str, session_id: str = None) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Convenience function to filter user input.

    Args:
        text: User input text
        session_id: Optional session ID for logging

    Returns:
        Tuple of (is_safe, filtered_reason, fallback_response)
    """
    if session_id:
        _filter_instance.set_session(session_id)
    return _filter_instance.filter_input(text)


def filter_output(text: str) -> Tuple[bool, str]:
    """
    Convenience function to filter LLM output.

    Args:
        text: LLM response text

    Returns:
        Tuple of (is_safe, sanitized_text)
    """
    return _filter_instance.filter_output(text)


def get_filter_stats() -> dict:
    """Get current filter statistics."""
    return _filter_instance.get_stats()
