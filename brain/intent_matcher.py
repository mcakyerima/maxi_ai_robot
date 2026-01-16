import re
import string
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
import logging
from collections import Counter
import math

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class IntentType(Enum):
    # Critical system intents (highest priority)
    SHUTDOWN = "shutdown"
    EMERGENCY = "emergency"
    
    # Specific action intents (high priority)
    MATH_CALCULATION = "math_calculation"
    TIME_DATE = "time_date"
    WEATHER = "weather"
    VISION_REQUEST = "vision_request"
    GESTURE_REQUEST = "gesture_request"
    
    # Content requests (medium-high priority)
    CONVERSATION_SUMMARY = "conversation_summary"
    HOMEWORK_HELP = "homework_help"
    LEARNING_QUESTION = "learning_question"
    
    # Entertainment (medium priority)
    JOKE_REQUEST = "joke_request"
    STORY_REQUEST = "story_request"
    GAME_REQUEST = "game_request"
    MUSIC_REQUEST = "music_request"
    
    # Social interaction (lower priority)
    GREETING = "greeting"
    COMPLIMENT_PRAISE = "compliment_praise"
    HELP_REQUEST = "help_request"
    BEDTIME_ROUTINE = "bedtime_routine"
    
    # Catch-all (lowest priority)
    GENERAL_CHAT = "general_chat"

@dataclass
class IntentSignature:
    """Advanced intent matching using multiple signal types"""
    # Exact phrase matching (guaranteed match)
    exact_phrases: List[str] = field(default_factory=list)
    
    # Required patterns (must have at least one)
    required_patterns: List[str] = field(default_factory=list)
    
    # Strong indicators (high confidence boost)
    strong_indicators: List[str] = field(default_factory=list)
    
    # Supporting context (moderate boost)
    context_words: List[str] = field(default_factory=list)
    
    # Exclusion patterns (strong negative signals)
    exclusions: List[str] = field(default_factory=list)
    
    # Weak exclusions (mild negative signals)
    weak_exclusions: List[str] = field(default_factory=list)
    
    # Minimum confidence threshold
    threshold: float = 1.5
    
    # Priority weight (1-10, higher = more important)
    priority: int = 5
    
    # Custom scoring function
    custom_scorer: Optional[callable] = None

class SmartIntentMatcher:
    def __init__(self):
        self._setup_intent_signatures()
        self._compile_patterns()
    
    def _setup_intent_signatures(self):
        """Define all intent signatures with improved patterns"""
        self.signatures = {
            IntentType.SHUTDOWN: IntentSignature(
                exact_phrases=[
                    "shut down", "power off", "turn off", "go to sleep", "stop listening",
                    "goodbye", "bye bye", "good night", "see you later", "that's enough",
                    "all done", "maxi sleep", "maxi bye", "maxi stop", "time to sleep"
                ],
                required_patterns=["shut|power|turn.*off|bye|goodbye|stop|quit|exit|done"],
                strong_indicators=["maxi", "maksi", "assistant", "now", "please"],
                # Fixed: Removed "sleep" from exclusions to avoid conflicts with bedtime
                exclusions=[
                        "story", "joke", "song", "game", "help", "what", "how", "why",
                        "time.*is.*it", "homework", "weather", "sleep.*time", "what.*time.*sleep"
                    ],
                threshold=2.0,
                priority=10
            ),
            
            IntentType.EMERGENCY: IntentSignature(
                exact_phrases=[
                    "help me", "emergency", "call for help", "something's wrong", "i'm hurt",
                    "need help now", "urgent", "911", "emergency call"
                ],
                required_patterns=["emergency|urgent|911|hurt|wrong"],
                strong_indicators=["now", "quickly", "fast", "immediate"],
                # Fixed: Added exclusions to prevent homework/general help from triggering emergency
                exclusions=["homework", "assignment", "study", "school", "learn", "math", "with.*homework"],
                threshold=2.0,  # Increased threshold
                priority=10
            ),
            
            IntentType.MATH_CALCULATION: IntentSignature(
                exact_phrases=[
                    "what is", "how much is", "calculate this", "solve this", "do the math",
                    "add up", "what's the sum", "what's the total"
                ],
                required_patterns=[r"\d+.*[\+\-\*\/\×\÷].*\d+|plus|minus|times|divided|multiply|subtract|add.*\d+|calculate|math|arithmetic"],
                strong_indicators=["equals", "answer", "result", "sum", "total", "problem"],
                context_words=["number", "digit", "equation"],
                # Fixed: Better exclusions to prevent weather/time conflicts
                exclusions=[
                        "weather", "rain", "sunny", "cloudy", "hot", "cold", "temperature",
                        "today.*is", "day.*is", "time.*sleep", "borno", "maiduguri", "outside"
                    ],
                threshold=1.8,
                priority=9,
                custom_scorer=self._score_math_intent
            ),
            
            IntentType.TIME_DATE: IntentSignature(
                exact_phrases=[
                    "what time is it", "current time", "what day is it", "what's today",
                    "what date is it", "tell me the time", "what's the time"
                ],
                required_patterns=["time.*is.*it|current.*time|what.*day.*is|today.*is|what.*date|tell.*time"],
                strong_indicators=["clock", "hour", "minute", "calendar", "now"],
                context_words=["exactly", "right now", "morning", "afternoon", "evening"],
                exclusions=["weather", "math", "story", "plus", "minus", "calculate", "summarize", "chart", "sleep.*time", "bedtime"],
                threshold=2.0,
                priority=8
            ),
            
            IntentType.WEATHER: IntentSignature(
                exact_phrases=[
                    "what's the weather", "how's the weather", "weather forecast",
                    "will it rain", "is it raining", "temperature outside",
                    "should i wear", "can we play outside"
                ],
                required_patterns=["weather|temperature|rain|sunny|cloudy|hot|cold|forecast|outside.*play|wear.*jacket|umbrella"],
                strong_indicators=["today", "tomorrow", "degrees", "celsius", "fahrenheit", "outside"],
                context_words=["maiduguri", "borno", "jacket", "umbrella", "coat"],
                # Fixed: Removed "what.*is" from exclusions to fix the false positive
                exclusions=["time.*is.*it", "math", "joke", "story", "calculate", "plus", "minus", "homework"],
                threshold=1.5,
                priority=8
            ),
            
            IntentType.VISION_REQUEST: IntentSignature(
                exact_phrases=[
                    "what do you see", "look at this", "can you see", "use your camera",
                    "what am i holding", "identify this", "recognize this"
                ],
                required_patterns=["see|look|camera|vision|holding|show|identify|recognize|visual"],
                strong_indicators=["front", "mirror", "picture", "image", "eyes"],
                exclusions=["math", "weather", "time", "joke", "story"],
                threshold=1.8,
                priority=7
            ),
            
            IntentType.GESTURE_REQUEST: IntentSignature(
                exact_phrases=[
                    "wave your hand", "make a gesture", "move your fingers",
                    "hold up three fingers", "display a number", "show me your fingers",
                    "give me a thumbs up", "make a peace sign", "reset your hands",
                    "go to neutral position", "emergency stop", "check your status",
                    "move to home position", "dance with your hands"
                ],
                required_patterns=[
                    r"\bwave\b", r"\bpoint\b", r"\bfist\b", r"\bpeace\b", r"\bthumbs?\s*up\b",
                    r"\bspread\s+fingers\b", r"\bshow\s+(zero|one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s*fingers?\b",
                    r"\bhold\s+up\s+(zero|one|two|three|four|five|six|seven|eight|nine|ten|\d+)\b",
                    r"\bnumber\s+(zero|one|two|three|four|five|six|seven|eight|nine|ten|\d+)\b",
                    r"\bcount\s+(to\s+)?(zero|one|two|three|four|five|six|seven|eight|nine|ten|\d+)\b",
                    r"\braise\s+(zero|one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s*fingers?\b",
                    r"\btwo\s+fingers\s+up\b", r"\beight\s+with\s+your\s+hands\b",
                    r"\breset\b.*(hand|servo)", r"\bneutral\s+position\b", r"\bemergency\s+stop\b",
                    r"\bcheck.*status\b", r"\bhome\s+position\b", r"\bgesture\b", r"\bdo\s+.*\bwrist\b"
                ],
                strong_indicators=[
                    "gesture", "motion", "wave", "point", "fingers", "hand", "movement", "sign",
                    "thumb", "peace", "fist", "servo", "raise", "hold", "open", "close", "number",
                    "dance", "spread", "reset", "neutral", "status", "home", "wrist"
                ],
                exclusions=[
                    "camera", "vision", "see", "look", "math", "weather", "time", "image", "photo"
                ],
                threshold=1.0,  # reduced threshold to make matching more sensitive
                priority=7
            ),


            IntentType.CONVERSATION_SUMMARY: IntentSignature(
                exact_phrases=[
                    "summarize our conversation", "what did we talk about",
                    "recap our chat", "summary of today", "what have we discussed",
                    "summarize the entire chart"
                ],
                required_patterns=["summarize|summary|recap|what.*talk|what.*discuss|entire.*chat|conversation.*today|chart.*today"],
                strong_indicators=["today", "earlier", "before", "previous", "entire", "whole", "our"],
                context_words=["chart", "conversation", "chat", "discussion"],
                exclusions=["math", "weather", "time.*is.*it", "joke", "homework"],
                threshold=1.5,
                priority=6
            ),
            
            IntentType.HOMEWORK_HELP: IntentSignature(
                exact_phrases=[
                    "help with homework", "school project", "assignment help",
                    "study for test", "homework question", "help me with math homework"
                ],
                required_patterns=["homework|assignment|school.*project|study.*test|exam.*prep|help.*with.*homework|help.*me.*with.*math"],
                strong_indicators=["due", "tomorrow", "teacher", "grade", "subject", "school"],
                context_words=["class", "student", "math", "english", "science"],
                exclusions=["joke", "story", "game", "play", "weather", "time"],
                threshold=1.5,  # Lowered threshold
                priority=8
            ),
            
            IntentType.LEARNING_QUESTION: IntentSignature(
                exact_phrases=[
                    "how does", "why does", "explain to me", "teach me about",
                    "help me understand", "what does this mean", "how does this work"
                ],
                required_patterns=["how.*does|why.*does|explain|teach.*me|help.*understand|what.*mean|how.*work"],
                strong_indicators=["because", "reason", "science", "learn", "knowledge"],
                context_words=["curious", "wonder", "education"],
                exclusions=["homework", "assignment", "test", "grade", "math.*calculation"],
                threshold=1.5,
                priority=6
            ),
            
            IntentType.JOKE_REQUEST: IntentSignature(
                exact_phrases=[
                    "tell me a joke", "make me laugh", "something funny",
                    "funny joke", "dad joke", "knock knock"
                ],
                required_patterns=["joke|funny|laugh|humor|silly|giggle|comedy"],
                strong_indicators=["make me", "tell me", "something"],
                context_words=["happy", "cheer up", "fun", "smile"],
                exclusions=["math", "weather", "time", "serious", "homework"],
                threshold=1.5,
                priority=5
            ),
            
            IntentType.STORY_REQUEST: IntentSignature(
                exact_phrases=[
                    "tell me a story", "story time", "bedtime story",
                    "fairy tale", "make up a story", "create a story"
                ],
                required_patterns=["story|tale|fairy|princess|adventure|hero|magic|once.*upon"],
                strong_indicators=["tell me", "bedtime", "sleepy", "imagination"],
                context_words=["character", "fantasy", "pretend"],
                exclusions=["math", "weather", "time", "homework"],
                threshold=1.5,
                priority=5
            ),
            
            IntentType.GAME_REQUEST: IntentSignature(
                exact_phrases=[
                    "let's play", "play a game", "want to play", "game time",
                    "quiz me", "riddle me", "challenge me"
                ],
                required_patterns=["play|game|riddle|puzzle|quiz|challenge|trivia"],
                strong_indicators=["let's", "want to", "fun", "entertainment"],
                context_words=["bored", "exciting", "interactive"],
                exclusions=["math", "weather", "time", "homework"],
                threshold=1.5,
                priority=5
            ),
            
            IntentType.MUSIC_REQUEST: IntentSignature(
                exact_phrases=[
                    "play music", "sing a song", "play a song", "music time",
                    "sing for me", "lullaby"
                ],
                required_patterns=["music|song|sing|lullaby|melody|tune"],
                strong_indicators=["play", "listen", "hear"],
                context_words=["bedtime", "sleepy", "peaceful"],
                exclusions=["math", "weather", "time"],
                threshold=1.5,
                priority=5
            ),
            
            IntentType.GREETING: IntentSignature(
                exact_phrases=[
                    "hello", "hi there", "good morning", "good afternoon",
                    "hey maxi", "hello maxi", "how are you"
                ],
                required_patterns=["^(hello|hi|hey|good.*(morning|afternoon|evening)|howdy)"],
                strong_indicators=["maxi", "maksi"],
                context_words=["nice", "good"],
                exclusions=["help", "math", "weather", "time", "joke", "story"],
                threshold=1.0,
                priority=3
            ),
            
            IntentType.COMPLIMENT_PRAISE: IntentSignature(
                exact_phrases=[
                    "good job", "well done", "you're awesome", "thank you",
                    "you're smart", "you're helpful", "love you", "you are awesome"
                ],
                required_patterns=["good.*job|well.*done|awesome|amazing|thank.*you|smart|helpful|love.*you|you.*are.*awesome"],
                strong_indicators=["maxi", "appreciate", "grateful"],
                context_words=["wonderful", "fantastic", "excellent"],
                exclusions=["question", "what", "how", "why", "help me"],
                threshold=1.0,  # Lowered threshold
                priority=3
            ),
            
            IntentType.HELP_REQUEST: IntentSignature(
                exact_phrases=[
                    "can you help", "need help", "i'm stuck",
                    "don't understand", "show me how"
                ],
                required_patterns=["can.*you.*help|need.*help|stuck|don.*understand|show.*me"],
                strong_indicators=["please", "need", "can you"],
                context_words=["confused", "lost", "don't know"],
                # Fixed: Exclude homework and emergency patterns to avoid conflicts
                exclusions=["homework", "school", "assignment", "emergency", "urgent", "911", "math.*homework"],
                threshold=1.5,
                priority=5
            ),
            
            IntentType.BEDTIME_ROUTINE: IntentSignature(
                exact_phrases=[
                    "i'm sleepy", "time for bed", "bedtime routine", "help me sleep",
                    "goodnight story", "tuck me in", "sweet dreams", "i am sleepy"
                ],
                required_patterns=[
                    "sleepy", "tired", "bedtime", "bed.*time", "dream", "night.*time",
                    "tuck.*me", "help.*sleep", "what.*time.*sleep", "when.*go.*to.*sleep"
                ],
                strong_indicators=["routine", "tuck", "lullaby", "sleepy", "tired"],
                context_words=["sleep", "rest", "night", "go to bed", "go to sleep"],
                exclusions=["homework", "math", "weather", "joke", "shut.*down", "power.*off"],
                threshold=1.0,
                priority=6
            )

        }
    
    def _compile_patterns(self):
        """Pre-compile regex patterns for better performance"""
        self.compiled_patterns = {}
        for intent_type, signature in self.signatures.items():
            compiled = {}
            
            # Compile required patterns
            if signature.required_patterns:
                compiled['required'] = [re.compile(pattern, re.IGNORECASE) 
                                     for pattern in signature.required_patterns]
            
            # Compile exclusion patterns
            if signature.exclusions:
                compiled['exclusions'] = [re.compile(f'\\b{pattern}\\b', re.IGNORECASE) 
                                        for pattern in signature.exclusions]
            
            self.compiled_patterns[intent_type] = compiled
    
    def _preprocess_text(self, text: str) -> str:
        """Advanced text preprocessing"""
        if not text:
            return ""
        
        # Convert to lowercase and strip
        text = text.lower().strip()
        
        # Handle contractions
        contractions = {
            "what's": "what is", "how's": "how is", "i'm": "i am",
            "you're": "you are", "it's": "it is", "that's": "that is",
            "don't": "do not", "can't": "can not", "won't": "will not"
        }
        
        for contraction, expansion in contractions.items():
            text = text.replace(contraction, expansion)
        
        # Handle number words
        number_words = {
            'zero': '0', 'one': '1', 'two': '2', 'three': '3', 'four': '4', 'five': '5',
            'six': '6', 'seven': '7', 'eight': '8', 'nine': '9', 'ten': '10',
            'eleven': '11', 'twelve': '12', 'thirteen': '13', 'fourteen': '14', 'fifteen': '15',
            'sixteen': '16', 'seventeen': '17', 'eighteen': '18', 'nineteen': '19', 'twenty': '20'
        }
        
        for word, num in number_words.items():
            text = re.sub(f'\\b{word}\\b', num, text)
        
        # Normalize whitespace
        text = ' '.join(text.split())
        
        return text
    
    def _score_math_intent(self, text: str) -> float:
        """Custom scoring for math detection"""
        score = 0.0
        
        # Look for numbers
        numbers = re.findall(r'-?\d*\.?\d+', text)
        if len(numbers) >= 2:
            score += 3.0  # Multiple numbers strongly suggest math
        elif len(numbers) == 1:
            score += 1.0  # Single number is weak indicator
        
        # Look for operators
        operators = ['+', '-', '*', '/', '×', '÷', 'plus', 'minus', 'times', 'divided', 'multiply', 'add', 'subtract']
        operator_count = sum(1 for op in operators if op in text)
        score += operator_count * 2.0
        
        # Look for math question patterns
        math_questions = ['what is', 'how much', 'calculate', 'solve', 'equals']
        question_matches = sum(1 for q in math_questions if q in text)
        score += question_matches * 1.5
        
        # Look for math context words
        math_words = ['equation', 'problem', 'solution', 'answer', 'result']
        context_matches = sum(1 for w in math_words if w in text)
        score += context_matches * 0.5
        
        return score
    
    def _calculate_intent_score(self, text: str, intent_type: IntentType) -> float:
        """Calculate confidence score for a specific intent"""
        if intent_type not in self.signatures:
            return 0.0
        
        signature = self.signatures[intent_type]
        score = 0.0
        
        # Check exact phrase matches (highest confidence)
        for phrase in signature.exact_phrases:
            if phrase in text:
                score += 5.0
                logger.debug(f"Exact phrase '{phrase}' matched for {intent_type.value}: +5.0")
        
        # Check required patterns (must have at least one)
        required_match = False
        if intent_type in self.compiled_patterns and 'required' in self.compiled_patterns[intent_type]:
            for pattern in self.compiled_patterns[intent_type]['required']:
                if pattern.search(text):
                    required_match = True
                    score += 3.0
                    logger.debug(f"Required pattern matched for {intent_type.value}: +3.0")
                    break
        elif not signature.required_patterns:
            required_match = True  # No required patterns means it's optional
        
        # If no required pattern matches, return 0 (unless exact phrase matched)
        if not required_match and score < 5.0:
            return 0.0
        
        # Check strong indicators
        for indicator in signature.strong_indicators:
            if indicator in text:
                score += 2.0
                logger.debug(f"Strong indicator '{indicator}' for {intent_type.value}: +2.0")
        
        # Check context words
        for word in signature.context_words:
            if word in text:
                score += 0.5
                logger.debug(f"Context word '{word}' for {intent_type.value}: +0.5")
        
        # Apply exclusions (strong negative signals)
        exclusion_penalty = 0.0
        if intent_type in self.compiled_patterns and 'exclusions' in self.compiled_patterns[intent_type]:
            for pattern in self.compiled_patterns[intent_type]['exclusions']:
                if pattern.search(text):
                    exclusion_penalty += 2.0
                    logger.debug(f"Exclusion pattern matched for {intent_type.value}: -2.0")
        
        # Apply weak exclusions
        for weak_exclusion in signature.weak_exclusions:
            if weak_exclusion in text:
                exclusion_penalty += 0.5
                logger.debug(f"Weak exclusion '{weak_exclusion}' for {intent_type.value}: -0.5")
        
        score -= exclusion_penalty
        
        # Apply custom scoring if available
        if signature.custom_scorer:
            custom_score = signature.custom_scorer(text)
            score += custom_score
            logger.debug(f"Custom scorer for {intent_type.value}: +{custom_score}")
        
        # Apply priority weighting
        priority_weight = signature.priority / 10.0
        final_score = score * priority_weight
        
        logger.debug(f"Final score for {intent_type.value}: {final_score} (base: {score}, priority: {priority_weight})")
        
        return max(0.0, final_score)
    
    def match_intent(self, user_input: str) -> str:
        """Main intent matching function"""
        if not user_input or not user_input.strip():
            return IntentType.GENERAL_CHAT.value
        
        text = self._preprocess_text(user_input)
        logger.info(f"Processing: '{user_input}' -> '{text}'")
        
        # Calculate scores for all intents
        intent_scores = {}
        for intent_type in IntentType:
            if intent_type != IntentType.GENERAL_CHAT:
                score = self._calculate_intent_score(text, intent_type)
                if score > 0:
                    intent_scores[intent_type] = score
        
        if not intent_scores:
            logger.info("No intent patterns matched, defaulting to general_chat")
            return IntentType.GENERAL_CHAT.value
        
        # Find the best intent
        best_intent, best_score = max(intent_scores.items(), key=lambda x: x[1])
        threshold = self.signatures[best_intent].threshold
        
        logger.info(f"Best match: {best_intent.value} (score: {best_score:.2f}, threshold: {threshold})")
        
        # Check if it meets the threshold
        if best_score >= threshold:
            return best_intent.value
        else:
            logger.info(f"Score {best_score:.2f} below threshold {threshold}, defaulting to general_chat")
            return IntentType.GENERAL_CHAT.value
    
    def get_intent_with_confidence(self, user_input: str) -> Tuple[str, float]:
        """Get intent with confidence score"""
        if not user_input or not user_input.strip():
            return IntentType.GENERAL_CHAT.value, 0.0
        
        text = self._preprocess_text(user_input)
        intent_scores = {}
        
        for intent_type in IntentType:
            if intent_type != IntentType.GENERAL_CHAT:
                score = self._calculate_intent_score(text, intent_type)
                if score > 0:
                    intent_scores[intent_type] = score
        
        if not intent_scores:
            return IntentType.GENERAL_CHAT.value, 0.5
        
        best_intent, best_score = max(intent_scores.items(), key=lambda x: x[1])
        threshold = self.signatures[best_intent].threshold
        
        if best_score >= threshold:
            return best_intent.value, best_score
        else:
            return IntentType.GENERAL_CHAT.value, 0.5
    
    def get_top_intents(self, user_input: str, n: int = 3) -> List[Tuple[str, float]]:
        """Get top N intents with their scores"""
        if not user_input or not user_input.strip():
            return [(IntentType.GENERAL_CHAT.value, 0.5)]
        
        text = self._preprocess_text(user_input)
        intent_scores = {}
        
        for intent_type in IntentType:
            if intent_type != IntentType.GENERAL_CHAT:
                score = self._calculate_intent_score(text, intent_type)
                if score > 0:
                    intent_scores[intent_type] = score
        
        if not intent_scores:
            return [(IntentType.GENERAL_CHAT.value, 0.5)]
        
        # Sort by score and return top N
        sorted_intents = sorted(intent_scores.items(), key=lambda x: x[1], reverse=True)
        results = []
        
        for intent_type, score in sorted_intents[:n]:
            threshold = self.signatures[intent_type].threshold
            if score >= threshold:
                results.append((intent_type.value, score))
        
        if not results:
            results.append((IntentType.GENERAL_CHAT.value, 0.5))
        
        return results

# Global instance
advanced_matcher = SmartIntentMatcher()

def match_intent(user_input: str) -> str:
    """Main function for intent matching (compatible with existing code)"""
    return advanced_matcher.match_intent(user_input)

def get_intent_with_confidence(user_input: str) -> Tuple[str, float]:
    """Get intent with confidence score"""
    return advanced_matcher.get_intent_with_confidence(user_input)

def get_top_intents(user_input: str, n: int = 3) -> List[Tuple[str, float]]:
    """Get top N intents with scores"""
    return advanced_matcher.get_top_intents(user_input, n)

# Comprehensive testing
if __name__ == "__main__":
    test_cases = [
        # The problematic case from your log
        ("summarize the entire chart that i had with you today", "conversation_summary"),
        
        # Math tests
        ("What is 5 plus 3?", "math_calculation"),
        ("Twelve minus four", "math_calculation"),
        ("Six times seven", "math_calculation"),
        ("Calculate 24 x 3", "math_calculation"),
        ("What is 100 - 40?", "math_calculation"),
        
        # Time tests (should NOT match summary requests)
        ("What time is it?", "time_date"),
        ("What's the current time?", "time_date"),
        ("What day is today?", "time_date"),
        ("Tell me the time", "time_date"),
        
        # Weather tests - FIXED
        ("What's the weather in Borno state?", "weather"),
        ("How's the weather in Maiduguri?", "weather"),
        ("Will it rain tomorrow?", "weather"),
        ("Should I wear a jacket this morning?", "weather"),
        
        # Conversation summary tests
        ("What did we talk about today?", "conversation_summary"),
        ("Recap our conversation", "conversation_summary"),
        ("Summary of our chat", "conversation_summary"),
        ("What have we discussed?", "conversation_summary"),
        
        # Shutdown tests
        ("Maxi shut down", "shutdown"),
        ("Power off please", "shutdown"),
        ("Go to sleep", "shutdown"),
        ("Goodbye Maxi", "shutdown"),
        
        # Other intents
        ("Tell me a joke", "joke_request"),
        ("Tell me a story", "story_request"),
        ("Let's play a game", "game_request"),
        ("Help me with homework", "homework_help"),  # FIXED
        ("How does photosynthesis work?", "learning_question"),
        ("Hello Maxi", "greeting"),
        ("You're awesome", "compliment_praise"),  # FIXED
        ("I need help", "help_request"),
        ("I'm sleepy", "bedtime_routine"),  # FIXED
        
        # Edge cases - FIXED
        ("Can you help me with math homework?", "homework_help"),
        ("What time should I go to sleep?", "bedtime_routine"),
        ("Is the weather good for sleeping outside?", "weather"),
        
        # General chat fallbacks
        ("Tell me about your day", "general_chat"),
        ("What do you think about robots?", "general_chat"),
    ]
    
    print("🧠 Fixed Advanced Intent Matcher Testing")
    print("=" * 70)
    
    correct = 0
    total = len(test_cases)
    
    for test_input, expected in test_cases:
        detected = match_intent(test_input)
        intent, confidence = get_intent_with_confidence(test_input)
        top_intents = get_top_intents(test_input, 3)
        
        is_correct = detected == expected
        status = "✅" if is_correct else "❌"
        
        if is_correct:
            correct += 1
        
        print(f"{status} '{test_input}'")
        print(f"    Expected: {expected}")
        print(f"    Detected: {detected} (confidence: {confidence:.2f})")
        
        if len(top_intents) > 1:
            print(f"    Top alternatives: {top_intents[1:3]}")
        
        if not is_correct:
            print(f"    ⚠️  MISMATCH!")
        print()
    
    accuracy = (correct / total) * 100
    print(f"🎯 Overall Accuracy: {correct}/{total} ({accuracy:.1f}%)")
    
    if accuracy < 90:
        print("🔧 Consider adjusting thresholds or patterns for better accuracy")
    else:
        print("🎉 Excellent accuracy achieved!")