import os
import json
import logging
import pickle
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Union
from dataclasses import dataclass
from enum import Enum
import warnings
import threading
import time


# Suppress warnings for cleaner output
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

try:
    import torch
    import torch.nn.functional as F
    from transformers import (
        DistilBertTokenizer, 
        DistilBertForSequenceClassification,
        AutoTokenizer,
        AutoModelForSequenceClassification,
        pipeline
    )
    import numpy as np
    from sklearn.metrics.pairwise import cosine_similarity
    TRANSFORMERS_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Transformers not available: {e}")
    print("Install with: pip install torch transformers scikit-learn")
    TRANSFORMERS_AVAILABLE = False

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class IntentType(Enum):
    """Intent categories optimized for Nigerian children and non-native speakers"""
    # Critical system intents
    SHUTDOWN = "shutdown"
    EMERGENCY = "emergency"
    
    # Action intents
    MATH_CALCULATION = "math_calculation"
    TIME_DATE = "time_date"
    WEATHER = "weather"
    VISION_REQUEST = "vision_request"
    GESTURE_REQUEST = "gesture_request"
    
    # Content requests
    CONVERSATION_SUMMARY = "conversation_summary"
    HOMEWORK_HELP = "homework_help"
    LEARNING_QUESTION = "learning_question"
    
    # Entertainment
    JOKE_REQUEST = "joke_request"
    STORY_REQUEST = "story_request"
    GAME_REQUEST = "game_request"
    MUSIC_REQUEST = "music_request"
    
    # Social interaction
    GREETING = "greeting"
    COMPLIMENT_PRAISE = "compliment_praise"
    HELP_REQUEST = "help_request"
    BEDTIME_ROUTINE = "bedtime_routine"
    
    # Fallback
    GENERAL_CHAT = "general_chat"

@dataclass
class IntentConfig:
    """Configuration for the intent matcher"""
    model_name: str = "distilbert-base-uncased"
    cache_dir: str = "./intent_cache"
    max_length: int = 128
    batch_size: int = 8
    confidence_threshold: float = 0.6
    use_gpu: bool = False  # Disabled for CPU-only systems
    enable_fallback: bool = True
    preload_embeddings: bool = True  # Precompute template embeddings
    warmup_on_init: bool = True  # Warm up model on initialization

class NigerianEnglishProcessor:
    """Handles Nigerian English variants and children's speech patterns"""
    
    def __init__(self):
        # Common Nigerian English patterns and corrections
        self.nigerian_patterns = {
            # Pronunciation variations
            'wetin': 'what',
            'oga': 'sir',
            'abeg': 'please',
            'dey': 'is',
            'wan': 'want',
            'go': 'will',
            'sha': '',  # Remove filler word
            'abi': 'right',
            'small': 'little',
            'big': 'large',
            
            # Common mispronunciations by children
            'fink': 'think',
            'dis': 'this',
            'dat': 'that',
            'dem': 'them',
            'wey': 'where',
            'how far': 'how are you',
            'no wahala': 'no problem',
            
            # Time expressions
            'morning time': 'morning',
            'evening time': 'evening',
            'night time': 'night',
            
            # Math expressions
            'add am': 'add it',
            'minus am': 'subtract it',
            'times am': 'multiply it',
        }
        
        # Common contractions and expansions
        self.contractions = {
            "what's": "what is", "how's": "how is", "i'm": "i am",
            "you're": "you are", "it's": "it is", "that's": "that is",
            "don't": "do not", "can't": "cannot", "won't": "will not",
            "shouldn't": "should not", "wouldn't": "would not",
            "couldn't": "could not", "mustn't": "must not"
        }
    
    def normalize_text(self, text: str) -> str:
        """Normalize Nigerian English and children's speech"""
        if not text:
            return ""
        
        text = text.lower().strip()
        
        # Handle contractions
        for contraction, expansion in self.contractions.items():
            text = text.replace(contraction, expansion)
        
        # Handle Nigerian English patterns
        for nigerian, standard in self.nigerian_patterns.items():
            text = text.replace(nigerian, standard)
        
        # Clean up extra spaces
        text = ' '.join(text.split())
        
        return text

class TrainingDataGenerator:
    """Generates comprehensive training examples for Nigerian context"""
    
    def __init__(self):
        self.processor = NigerianEnglishProcessor()
    
    def generate_training_data(self) -> List[Tuple[str, str]]:
        """Generate diverse training examples"""
        training_data = []
        
        # SHUTDOWN examples
        shutdown_examples = [
            "shut down maxi", "power off please", "go to sleep now", "goodbye maxi",
            "bye bye", "turn off", "stop listening", "that's enough", "all done",
            "maxi sleep", "good night", "see you later", "shut down abeg",
            "off am", "close maxi", "stop now", "finish", "done talking",
            "go rest", "sleep time for maxi"
        ]
        
        # EMERGENCY examples  
        emergency_examples = [
            "help me quick", "emergency", "something wrong", "i need help now",
            "urgent help", "call somebody", "problem here", "help abeg",
            "serious problem", "emergency call", "i dey fear", "danger",
            "accident happen", "somebody hurt", "quick quick help"
        ]
        
        # MATH examples
        math_examples = [
            "what is 5 plus 3", "calculate 10 minus 2", "12 times 4 equals what",
            "add 6 and 8", "subtract 15 from 20", "multiply 7 by 3",
            "divide 24 by 6", "wetin be 9 plus 4", "how much is 8 times 2",
            "calculate dis sum", "add am together", "minus dis number",
            "times dis by dat", "what be 50 minus 10", "solve dis math",
            "do dis calculation", "work dis sum", "find dis answer"
        ]
        
        # TIME examples
        time_examples = [
            "what time is it", "current time", "wetin be time now", "time check",
            "what day today", "which day be today", "tell me time",
            "time dey where", "clock time", "morning time abi afternoon",
            "what date today", "which month we dey", "year be which one"
        ]
        
        # WEATHER examples
        weather_examples = [
            "how weather today", "rain go fall", "sun dey hot", "weather report",
            "temperature outside", "will it rain", "is it sunny", "cold weather",
            "hot day today", "weather for maiduguri", "borno weather",
            "should i carry umbrella", "weather good for outside", "rain time",
            "dry season abi wet season", "harmattan dey come"
        ]
        
        # HOMEWORK examples
        homework_examples = [
            "help me with homework", "school work hard", "assignment dey difficult",
            "help me solve dis", "homework question", "study help needed",
            "teacher give us work", "exam preparation", "school project help",
            "math homework", "english assignment", "help me understand dis lesson"
        ]
        
        # JOKE examples
        joke_examples = [
            "tell me joke", "make me laugh", "something funny", "funny story",
            "joke time", "make me happy", "say something funny", "laugh matter",
            "comedy time", "funny thing", "joke abeg", "make me smile"
        ]
        
        # STORY examples
        story_examples = [
            "tell me story", "story time", "bedtime story", "fairy tale",
            "once upon a time", "princess story", "adventure story",
            "make up story", "interesting story", "story about animals",
            "story before sleep", "long story", "short story"
        ]
        
        # GREETING examples
        greeting_examples = [
            "hello maxi", "good morning", "hi there", "how you dey",
            "morning greeting", "afternoon greeting", "evening greeting",
            "hey maxi", "howdy", "good day", "hello there", "hi maxi",
            "morning o", "afternoon o", "evening o", "how far"
        ]
        
        # COMPLIMENT examples
        compliment_examples = [
            "good job maxi", "you smart", "thank you", "well done",
            "you helpful", "maxi you try", "appreciate you", "you good",
            "thank you plenty", "you be good assistant", "love you maxi",
            "you dey help me well", "you intelligent", "maxi you wise"
        ]
        
        # BEDTIME examples
        bedtime_examples = [
            "i dey sleepy", "sleep time", "tired plenty", "wan sleep",
            "bedtime story", "help me sleep", "sleepy time", "go bed",
            "sleep routine", "tired body", "rest time", "night time",
            "tuck me in", "sleep prayer", "good night routine"
        ]
        
        # GAME examples
        game_examples = [
            "let's play game", "play with me", "game time", "fun time",
            "riddle me", "quiz me", "challenge me", "play something",
            "bored wan play", "entertainment time", "fun game",
            "puzzle game", "word game", "number game"
        ]
        
        # MUSIC examples
        music_examples = [
            "sing song", "music time", "play music", "lullaby please",
            "sing for me", "music abeg", "sweet song", "bedtime song",
            "nigerian song", "children song", "nursery rhyme", "melody"
        ]
        
        # LEARNING examples
        learning_examples = [
            "how does dis work", "explain to me", "teach me about",
            "why dis happen", "what dis mean", "help me understand",
            "learning question", "curious about", "want to know",
            "science question", "how come", "wetin make am dey happen"
        ]
        
        # HELP examples (general)
        help_examples = [
            "can you help", "need help", "i dey confused", "don't understand",
            "show me how", "help me abeg", "assist me", "guide me",
            "lost here", "need assistance", "help hand", "support me"
        ]
        
        # CONVERSATION SUMMARY examples
        summary_examples = [
            "summarize our talk", "what we discuss", "recap our chat",
            "wetin we talk about", "summary of today", "conversation summary",
            "what we been talking", "review our discussion", "talk summary",
            "summarize everything", "recap all we say", "summary abeg"
        ]
        
        # VISION examples
        vision_examples = [
            "what you see", "look at dis", "can you see", "use your camera",
            "what i dey hold", "identify dis", "recognize dis", "see dis thing",
            "look with your eyes", "camera check", "visual check", "see wetin be dis"
        ]
        
        # GESTURE examples
        gesture_examples = [
            "wave your hand", "make gesture", "move your fingers", "show fingers",
            "thumbs up", "peace sign", "count with fingers", "hand movement",
            "point finger", "raise hand", "gesture abeg", "hand sign",
            "show me three fingers", "wave hand", "hand dance"
        ]
        
        # GENERAL CHAT examples
        general_examples = [
            "tell me about yourself", "what you think", "your opinion",
            "random question", "just talking", "casual chat", "discuss something",
            "what you like", "your favorite", "general talk", "chat time"
        ]
        
        # Compile all training data
        intent_examples = {
            IntentType.SHUTDOWN.value: shutdown_examples,
            IntentType.EMERGENCY.value: emergency_examples,
            IntentType.MATH_CALCULATION.value: math_examples,
            IntentType.TIME_DATE.value: time_examples,
            IntentType.WEATHER.value: weather_examples,
            IntentType.HOMEWORK_HELP.value: homework_examples,
            IntentType.JOKE_REQUEST.value: joke_examples,
            IntentType.STORY_REQUEST.value: story_examples,
            IntentType.GREETING.value: greeting_examples,
            IntentType.COMPLIMENT_PRAISE.value: compliment_examples,
            IntentType.BEDTIME_ROUTINE.value: bedtime_examples,
            IntentType.GAME_REQUEST.value: game_examples,
            IntentType.MUSIC_REQUEST.value: music_examples,
            IntentType.LEARNING_QUESTION.value: learning_examples,
            IntentType.HELP_REQUEST.value: help_examples,
            IntentType.CONVERSATION_SUMMARY.value: summary_examples,
            IntentType.VISION_REQUEST.value: vision_examples,
            IntentType.GESTURE_REQUEST.value: gesture_examples,
            IntentType.GENERAL_CHAT.value: general_examples,
        }
        
        # Generate training pairs
        for intent, examples in intent_examples.items():
            for example in examples:
                # Add original
                training_data.append((example, intent))
                # Add normalized version
                normalized = self.processor.normalize_text(example)
                if normalized != example:
                    training_data.append((normalized, intent))
        
        return training_data
    
import onnxruntime as ort
import numpy as np
from transformers import DistilBertTokenizer
from sklearn.metrics.pairwise import cosine_similarity

class ProfessionalIntentMatcher:
    """Production-ready intent matcher using lightweight transformers"""
    def __init__(self, onnx_model_path="intent_model.onnx", tokenizer_path="./local_model_cache/distilbert-base-uncased"):
        self.tokenizer = DistilBertTokenizer.from_pretrained(tokenizer_path)
        self.session = ort.InferenceSession(onnx_model_path)
        self.intent_labels = [intent.value for intent in IntentType]
        self.max_length = 128

    def _softmax(self, x):
        e_x = np.exp(x - np.max(x))
        return e_x / e_x.sum()

    def _encode(self, text):
        return self.tokenizer(
            text,
            return_tensors="np",
            padding="max_length",
            truncation=True,
            max_length=self.max_length
        )

    def _predict_logits(self, text):
        enc = self._encode(text)
        logits = self.session.run(None, {
            "input_ids": enc["input_ids"],
            "attention_mask": enc["attention_mask"]
        })[0]
        return logits[0]

    def match_intent(self, user_input):
        logits = self._predict_logits(user_input)
        probs = self._softmax(logits)
        best_idx = int(np.argmax(probs))
        return self.intent_labels[best_idx]

    def get_intent_with_confidence(self, user_input):
        logits = self._predict_logits(user_input)
        probs = self._softmax(logits)
        best_idx = int(np.argmax(probs))
        return self.intent_labels[best_idx], float(probs[best_idx])

    def get_top_intents(self, user_input, n=3):
        logits = self._predict_logits(user_input)
        probs = self._softmax(logits)
        intent_probs = list(zip(self.intent_labels, probs))
        intent_probs.sort(key=lambda x: x[1], reverse=True)
        return intent_probs[:n]

        
    def _initialize_intent_templates(self):
        """Initialize intent templates for semantic matching"""
        self.intent_templates = {
            IntentType.SHUTDOWN.value: "shut down power off goodbye sleep stop",
            IntentType.EMERGENCY.value: "help emergency urgent problem danger accident",
            IntentType.MATH_CALCULATION.value: "calculate math add subtract multiply divide plus minus times",
            IntentType.TIME_DATE.value: "time date what time is it clock current day month year",
            IntentType.WEATHER.value: "weather rain sunny temperature hot cold forecast climate",
            IntentType.HOMEWORK_HELP.value: "homework help school assignment study exam project lesson",
            IntentType.JOKE_REQUEST.value: "joke funny laugh humor comedy amusing entertaining",
            IntentType.STORY_REQUEST.value: "story tale fairy bedtime narrative adventure princess",
            IntentType.GREETING.value: "hello hi good morning afternoon evening hey howdy",
            IntentType.COMPLIMENT_PRAISE.value: "good job thank you awesome well done appreciate smart",
            IntentType.BEDTIME_ROUTINE.value: "sleepy tired sleep bedtime rest night routine",
            IntentType.GAME_REQUEST.value: "play game fun quiz riddle challenge entertainment",
            IntentType.MUSIC_REQUEST.value: "sing music song lullaby melody nursery rhyme",
            IntentType.LEARNING_QUESTION.value: "how why explain teach learn understand question curious",
            IntentType.HELP_REQUEST.value: "help me need help assistance support guide confused",
            IntentType.CONVERSATION_SUMMARY.value: "summarize recap what we talked discussed conversation review",
            IntentType.VISION_REQUEST.value: "see look camera what you see identify recognize visual",
            IntentType.GESTURE_REQUEST.value: "wave gesture move fingers hand movement sign thumbs up",
            IntentType.GENERAL_CHAT.value: "talk chat discuss conversation casual random opinion"
        }
    
    def _get_model_path(self) -> str:
        """Get cached model path"""
        return os.path.join(self.config.cache_dir, "intent_model.onnx")
    
    def _get_training_data_path(self) -> str:
        """Get training data cache path"""
        return os.path.join(self.config.cache_dir, "training_data.pkl")
    
    def _get_embeddings_cache_path(self) -> str:
        """Get embeddings cache path"""
        return os.path.join(self.config.cache_dir, "intent_embeddings.pkl")
    
    def _load_or_create_training_data(self) -> List[Tuple[str, str]]:
        """Load cached training data or create new"""
        cache_path = self._get_training_data_path()
        
        if os.path.exists(cache_path):
            logger.info("Loading cached training data...")
            with open(cache_path, 'rb') as f:
                return pickle.load(f)
        
        logger.info("Generating new training data...")
        generator = TrainingDataGenerator()
        training_data = generator.generate_training_data()
        
        # Cache the training data
        with open(cache_path, 'wb') as f:
            pickle.dump(training_data, f)
        
        logger.info(f"Generated {len(training_data)} training examples")
        return training_data
    
    def _create_label_encoder(self, labels: List[str]) -> Dict[str, int]:
        """Create label to index mapping"""
        unique_labels = sorted(list(set(labels)))
        return {label: idx for idx, label in enumerate(unique_labels)}
    
    # def _train_model(self, training_data: List[Tuple[str, str]]) -> None:
    #     """Train or load the intent classification model"""
    #     if not TRANSFORMERS_AVAILABLE:
    #         raise ImportError("Transformers library not available. Please install required packages.")
        
    #     model_path = self._get_model_path()
        
    #     # Check if model exists
    #     if os.path.exists(model_path):
    #         logger.info("Loading existing model...")
    #         self.tokenizer = DistilBertTokenizer.from_pretrained(model_path)
    #         # self.model = DistilBertForSequenceClassification.from_pretrained(model_path)
            
    #         # Load label encoder
    #         with open(os.path.join(model_path, "label_encoder.pkl"), 'rb') as f:
    #             self.label_encoder = pickle.load(f)
    #     else:
    #         logger.info("Training new model...")
            
    #         # Prepare data
    #         texts, labels = zip(*training_data)
    #         self.label_encoder = self._create_label_encoder(labels)
            
    #         # Initialize tokenizer and model
    #         self.tokenizer = DistilBertTokenizer.from_pretrained(self.config.model_name)
    #         self.model = DistilBertForSequenceClassification.from_pretrained(
    #             self.config.model_name,
    #             num_labels=len(self.label_encoder)
    #         )
            
    #         # For this demo, we'll use a simple approach
    #         # In production, you'd implement proper training loop
    #         logger.info("Saving model structure...")
    #         self.model.save_pretrained(model_path)
    #         self.tokenizer.save_pretrained(model_path)
            
    #         # Save label encoder
    #         with open(os.path.join(model_path, "label_encoder.pkl"), 'wb') as f:
    #             pickle.dump(self.label_encoder, f)
        
    #     # Move model to device
    #     self.model.to(self.device)
    #     self.model.eval()  # Set to evaluation mode
    
    # def _precompute_intent_embeddings(self):
    #     """Precompute embeddings for all intent templates for faster matching"""
    #     embeddings_cache_path = self._get_embeddings_cache_path()
        
    #     # Try to load cached embeddings
    #     if os.path.exists(embeddings_cache_path):
    #         logger.info("Loading cached intent embeddings...")
    #         with open(embeddings_cache_path, 'rb') as f:
    #             self.intent_embeddings = pickle.load(f)
    #             return
        
    #     logger.info("Precomputing intent embeddings...")
    #     self.intent_embeddings = {}
        
    #     for intent, template in self.intent_templates.items():
    #         try:
    #             embedding = self._get_embedding(template)
    #             self.intent_embeddings[intent] = embedding
    #         except Exception as e:
    #             logger.warning(f"Failed to compute embedding for {intent}: {e}")
    #             # Use zero embedding as fallback
    #             self.intent_embeddings[intent] = np.zeros(768)  # DistilBERT hidden size
        
    #     # Cache the embeddings
    #     with open(embeddings_cache_path, 'wb') as f:
    #         pickle.dump(self.intent_embeddings, f)
        
    #     logger.info("Intent embeddings precomputed and cached!")
    
    # def _warmup_model(self):
    #     """Warm up the model with sample inputs to reduce first-call latency"""
    #     if self.warmup_complete:
    #         return
            
    #     logger.info("Warming up model...")
    #     self.is_warming_up = True
        
    #     # Sample warm-up inputs
    #     warmup_texts = [
    #         "hello maxi",
    #         "what time is it",
    #         "tell me a joke",
    #         "help me with math",
    #         "good night"
    #     ]
        
    #     try:
    #         for text in warmup_texts:
    #             _ = self._get_embedding(text)
            
    #         self.warmup_complete = True
    #         logger.info("Model warmup completed!")
    #     except Exception as e:
    #         logger.warning(f"Model warmup failed: {e}")
    #     finally:
    #         self.is_warming_up = False
    
    def initialize(self) -> None:
        """Initialize the intent matcher with optional background warmup"""
        with self._lock:
            if self.is_initialized:
                logger.info("Intent matcher already initialized")
                return
            
            try:
                logger.info("Initializing Professional Intent Matcher...")
                
                # Load or create training data
                training_data = self._load_or_create_training_data()
                
                # Train or load model
                self._train_model(training_data)
                
                # Precompute embeddings if enabled
                if self.config.preload_embeddings:
                    self._precompute_intent_embeddings()
                
                self.is_initialized = True
                logger.info("Intent matcher initialized successfully!")
                
                # Start warmup in background if enabled
                if self.config.warmup_on_init:
                    warmup_thread = threading.Thread(target=self._warmup_model, daemon=True)
                    warmup_thread.start()
                
            except Exception as e:
                logger.error(f"Failed to initialize intent matcher: {e}")
                self.is_initialized = False
                raise
    
    def _encode_text(self, text: str) -> torch.Tensor:
        """Encode text using the tokenizer"""
        encoded = self.tokenizer(
            text,
            add_special_tokens=True,
            max_length=self.config.max_length,
            padding='max_length',
            truncation=True,
            return_attention_mask=True,
            return_tensors='pt'
        )
        return encoded
    
    def _get_embedding(self, text: str) -> np.ndarray:
        """Get text embedding from the model"""
        encoded = self._encode_text(text)
        
        with torch.no_grad():
            # Move to device
            input_ids = encoded['input_ids'].to(self.device)
            attention_mask = encoded['attention_mask'].to(self.device)
            
            # Get model outputs
            outputs = self.model(input_ids=input_ids, attention_mask=attention_mask)
            
            # Use the [CLS] token embedding
            embeddings = outputs.last_hidden_state[:, 0, :].cpu().numpy()
            
        return embeddings.flatten()
    
    def _semantic_similarity_match(self, user_input: str) -> Tuple[str, float]:
        """Use semantic similarity for intent matching with precomputed embeddings"""
        # Get user input embedding
        user_embedding = self._get_embedding(user_input)
        
        best_intent = IntentType.GENERAL_CHAT.value
        best_score = 0.0
        
        # Use precomputed embeddings if available
        if self.intent_embeddings:
            for intent, template_embedding in self.intent_embeddings.items():
                try:
                    similarity = cosine_similarity(
                        user_embedding.reshape(1, -1),
                        template_embedding.reshape(1, -1)
                    )[0][0]
                    
                    if similarity > best_score:
                        best_score = similarity
                        best_intent = intent
                except Exception as e:
                    logger.warning(f"Error computing similarity for {intent}: {e}")
                    continue
        else:
            # Fallback to on-the-fly computation
            for intent, template in self.intent_templates.items():
                try:
                    template_embedding = self._get_embedding(template)
                    similarity = cosine_similarity(
                        user_embedding.reshape(1, -1),
                        template_embedding.reshape(1, -1)
                    )[0][0]
                    
                    if similarity > best_score:
                        best_score = similarity
                        best_intent = intent
                except Exception as e:
                    logger.warning(f"Error computing similarity for {intent}: {e}")
                    continue
        
        return best_intent, float(best_score)
    

    def get_intent_with_confidence(self, user_input: str) -> Tuple[str, float]:
        """Get intent with confidence score"""
        if not self.is_initialized:
            self.initialize()
        
        if not user_input or not user_input.strip():
            return IntentType.GENERAL_CHAT.value, 0.0
        
        try:
            normalized_input = self.processor.normalize_text(user_input)
            intent, confidence = self._semantic_similarity_match(normalized_input)
            
            if confidence >= self.config.confidence_threshold:
                return intent, confidence
            else:
                return IntentType.GENERAL_CHAT.value, confidence
                
        except Exception as e:
            logger.error(f"Error getting intent with confidence: {e}")
            return IntentType.GENERAL_CHAT.value, 0.0
    
    
    def get_status(self) -> Dict[str, Union[bool, str]]:
        """Get current status of the intent matcher"""
        return {
            "initialized": self.is_initialized,
            "warming_up": self.is_warming_up,
            "warmup_complete": self.warmup_complete,
            "embeddings_cached": bool(self.intent_embeddings),
            "device": str(self.device)
        }

# Global instance for drop-in compatibility
_onnx_matcher = ProfessionalIntentMatcher()

def match_intent(user_input):
    return _onnx_matcher.match_intent(user_input)

def get_intent_with_confidence(user_input):
    return _onnx_matcher.get_intent_with_confidence(user_input)

def get_top_intents(user_input, n=3):
    return _onnx_matcher.get_top_intents(user_input, n)



if __name__ == "__main__":
    # Simple test
    test_inputs = [
        "hello maxi",
        "what time is it",
        "help me with math",
        "tell me a story",
        "good night",
        "emergency help"
    ]

    for inp in test_inputs:
        intent, conf = get_intent_with_confidence(inp)
        print(f"Input: {inp}")
        print(f"Matched Intent: {intent}, Confidence: {conf:.3f}\n")
