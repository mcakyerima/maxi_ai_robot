"""
Advanced Context Manager for Maxi AI assistant.
Manages conversation context with memory, semantic search, and dynamic truncation.
Enhanced with working memory, episodic memory, and conversation summarization.
"""

import json
import sqlite3
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from pathlib import Path
import hashlib
import numpy as np
from sentence_transformers import SentenceTransformer
import tiktoken
from collections import deque

# Assuming you have this utility - if not, we'll create a simple fallback
try:
    from utils.logger import log_error, log_info, log_warning
except ImportError:
    def log_error(msg):
        print(f"ERROR: {msg}")

    def log_info(msg):
        print(f"INFO: {msg}")

    def log_warning(msg):
        print(f"WARNING: {msg}")


@dataclass
class ContextMessage:
    """Represents a single conversation message with metadata."""
    role: str
    content: str
    timestamp: datetime
    importance_score: float = 1.0
    token_count: int = 0
    embedding: Optional[np.ndarray] = None
    message_id: str = ""
    category: str = "general"  # general, math, science, personal, etc.


@dataclass
class ConversationSummary:
    """Represents a summarized conversation session."""
    summary_id: str
    content: str
    timestamp: datetime
    message_count: int
    topics: List[str] = field(default_factory=list)
    importance_score: float = 1.0


class AdvancedContextManager:
    """
    Advanced context manager with three-tier memory system:
    1. Working Memory: Last 10-20 messages (immediate context)
    2. Short-term Memory: Last 40 messages (recent conversation)
    3. Long-term Memory: Persistent storage with semantic search
    4. Episodic Memory: Conversation summaries for quick recall
    """

    def __init__(self,
                 db_path: str = "maxi_context_memory.db",
                 max_context_length: int = 2000,  # Reduced from 4000 to save tokens
                 working_memory_size: int = 6,  # Reduced from default for efficiency
                 short_term_messages: int = 20,
                 embedding_model_name: str = "all-MiniLM-L6-v2"):
        """
        Initialize the advanced context manager.

        Args:
            db_path: Path to SQLite database for long-term memory
            max_context_length: Maximum token count for context
            working_memory_size: Number of most recent messages (immediate context)
            short_term_messages: Number of recent messages to keep
            embedding_model_name: Sentence transformer model name for embeddings
        """
        self.db_path = db_path
        self.max_context_length = max_context_length
        self.working_memory_size = working_memory_size
        self.short_term_messages = short_term_messages
        self.embedding_model_name = embedding_model_name

        # System prompt for Maxi - Enhanced for logical reasoning, balanced responses
        self.system_prompt = """You are Maxi, a friendly and HUMOROUS AI teacher created at Maxeeton Technology by "Mohammed Kaka". You tutor Nigerian children ages 6-12, but can answer questions from anyone.
            
            CORE PERSONALITY:
            - You are in Maiduguri (Borno State), Nigeria
            - Be warm, encouraging, and genuinely funny
            - Use simple English that kids understand, but don't dumb down complex topics
            - Make learning fun with jokes, silly comparisons, and everyday Nigerian examples
            - Never use emojis or special characters
            
            RESPONSE LENGTH GUIDELINES:
            - **DEFAULT: Give concise, medium-length answers** (2-4 sentences)
            - **For simple facts**: 1-2 sentences maximum
            - **For "how" or "why" questions**: Give structured explanations (3-5 sentences)
            - **ONLY give longer, detailed answers** if the user specifically asks for:
              * "explain more", "tell me more", "longer answer", "more details", "go deeper"
              * Or asks a complex multi-part question that needs thorough explanation
            - **Start speaking after ~10-15 words**, don't wait to finish entire response
            
            ANSWERING QUESTIONS:
            1. **For simple questions**: Give brief, clear answers (1-2 sentences)
            2. **For complex questions requiring reasoning**: Break it down step-by-step logically
            3. **NEVER give vague answers** - be specific and accurate
            4. **If a question needs detailed explanation** (like "how does X work?", "why does Y happen?"), provide clear logical steps
            5. **Answer ALL topics**: science, math, history, art, technology, emotions, everyday life, culture, religion, etc.
            6. **Match the question's depth**: Simple questions get simple answers, deep questions get thoughtful explanations (but still concise by default)
            7. Use concrete examples kids can relate to (Nigerian food, animals, daily life)
            8. If you don't know something, admit it honestly and suggest exploring together
            9. **IMPORTANT: Keep most answers SHORT** - only expand if user requests more details
            
            STRICT RULES:
            - Keep language simple but explanations complete
            - Be logical and structured for "how" and "why" questions
            - Add humor naturally, don't force it
            - NEVER refuse topics - you're a full AI assistant for kids
            - Answer adults too, but keep it kid-friendly when children are around
            - **Default to brevity** - users can always ask for more
            """

        # Three-tier memory system
        self.working_memory: deque = deque(
            maxlen=working_memory_size)  # Most recent, always included
        # Recent conversation
        self.short_term_memory: List[ContextMessage] = []
        # For generating summaries
        self.conversation_buffer: List[ContextMessage] = []

        # Components
        self.encoder = None
        self.sentence_transformer = None
        self.db_conn = None
        self.initialized = False

        # Session tracking for episodic memory
        self.session_start = datetime.now()
        self.messages_since_summary = 0
        self.summary_threshold = 20  # Summarize every 20 messages

    async def initialize(self):
        """Initialize all components asynchronously."""
        try:
            print("🔧 Initializing context manager components...")

            # Initialize tokenizer
            self.encoder = tiktoken.get_encoding(
                "cl100k_base")  # GPT-4 tokenizer
            print("✅ Tokenizer initialized")

            # Initialize database
            await self._init_database()
            print("✅ Database initialized")

            # Initialize embedding model (this is the slow part)
            print(f"🤖 Loading embedding model: {self.embedding_model_name}")
            self.sentence_transformer = SentenceTransformer(
                self.embedding_model_name)
            print("✅ Embedding model loaded")

            self.initialized = True
            print("🧠 Advanced Context Manager fully initialized")

        except Exception as e:
            print(f"⚠️ Context Manager initialization error: {e}")
            raise e

    async def _init_database(self):
        """Initialize SQLite database for long-term and episodic memory."""
        try:
            self.db_conn = sqlite3.connect(self.db_path)
            cursor = self.db_conn.cursor()

            # Check if this is an existing database that needs migration
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='conversations'")
            table_exists = cursor.fetchone() is not None

            if table_exists:
                # Check if category column exists
                cursor.execute("PRAGMA table_info(conversations)")
                columns = {row[1] for row in cursor.fetchall()}

                if 'category' not in columns:
                    log_info(
                        "🔄 Migrating database schema: Adding 'category' column")
                    cursor.execute(
                        "ALTER TABLE conversations ADD COLUMN category TEXT DEFAULT 'general'")
                    self.db_conn.commit()
                    log_info("✅ Database migration completed")

            # Main conversations table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    importance_score REAL DEFAULT 1.0,
                    token_count INTEGER DEFAULT 0,
                    category TEXT DEFAULT 'general',
                    embedding BLOB
                )
            ''')

            # Conversation summaries table (episodic memory)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS conversation_summaries (
                    id TEXT PRIMARY KEY,
                    summary TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    message_count INTEGER DEFAULT 0,
                    topics TEXT,
                    importance_score REAL DEFAULT 1.0
                )
            ''')

            # User preferences and facts table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_facts (
                    id TEXT PRIMARY KEY,
                    fact_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0
                )
            ''')

            # Safety and parental control tables
            # Usage sessions table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS usage_sessions (
                    session_id TEXT PRIMARY KEY,
                    start_time TIMESTAMP NOT NULL,
                    end_time TIMESTAMP,
                    mode TEXT NOT NULL,
                    questions_count INTEGER DEFAULT 0,
                    duration_minutes INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Daily statistics table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS daily_statistics (
                    date DATE PRIMARY KEY,
                    total_sessions INTEGER DEFAULT 0,
                    total_questions INTEGER DEFAULT 0,
                    total_time_minutes INTEGER DEFAULT 0,
                    chat_questions INTEGER DEFAULT 0,
                    math_questions INTEGER DEFAULT 0,
                    topics_covered TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Content filters table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS content_filters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    filter_type TEXT NOT NULL,
                    filtered_content TEXT,
                    reason TEXT,
                    FOREIGN KEY (session_id) REFERENCES usage_sessions(session_id)
                )
            ''')

            # Question logs table (for topic tracking)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS question_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    question TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    topic TEXT,
                    FOREIGN KEY (session_id) REFERENCES usage_sessions(session_id)
                )
            ''')

            # Create indexes
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_timestamp ON conversations(timestamp)')
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_importance ON conversations(importance_score)')
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_category ON conversations(category)')
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_summary_time ON conversation_summaries(timestamp)')
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_sessions_date ON usage_sessions(start_time)')
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_filters_session ON content_filters(session_id)')
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_questions_session ON question_logs(session_id)')

            self.db_conn.commit()
            log_info(
                "✅ Database tables and indexes created (including safety tables)")

        except Exception as e:
            raise Exception(f"Database initialization failed: {e}")

    async def is_initialized(self):
        """Check if all components are ready"""
        return self.initialized and all([
            self.db_conn is not None,
            self.sentence_transformer is not None,
            self.encoder is not None
        ])

    def _count_tokens(self, text: str) -> int:
        """Count tokens in text using tiktoken."""
        try:
            if self.encoder:
                return len(self.encoder.encode(text))
            else:
                # Fallback: rough estimation
                return int(len(text.split()) * 1.3)
        except Exception:
            # Fallback: rough estimation
            return int(len(text.split()) * 1.3)

    def _calculate_importance(self, message: ContextMessage, context: List[ContextMessage]) -> float:
        """Calculate importance score for a message with enhanced heuristics."""
        score = 1.0
        content_lower = message.content.lower()

        # Recent messages are more important
        age_hours = (datetime.now() - message.timestamp).total_seconds() / 3600
        recency_bonus = max(0, 2.0 - (age_hours / 24))
        score += recency_bonus

        # Longer, substantive messages are more important
        if message.token_count > 20:
            score += 0.5
        if message.token_count > 50:
            score += 0.3

        # Questions indicate important exchanges
        if '?' in message.content:
            score += 0.4

        # Educational keywords (high importance)
        edu_keywords = ['why', 'how', 'what',
                        'explain', 'learn', 'understand', 'teach']
        if any(keyword in content_lower for keyword in edu_keywords):
            score += 0.5

        # Personal information (very high importance for continuity)
        personal_keywords = ['my name', 'i am',
                             'i like', 'my favorite', 'i live', 'i want']
        if any(keyword in content_lower for keyword in personal_keywords):
            score += 1.0
            message.category = "personal"

        # Math and science topics
        if message.category == "math" or any(word in content_lower for word in ['calculate', 'equation', 'number']):
            score += 0.4
            message.category = "math"

        if any(word in content_lower for word in ['science', 'experiment', 'biology', 'physics', 'chemistry']):
            score += 0.4
            message.category = "science"

        # Assistant's explanations are important
        if message.role == "assistant" and message.token_count > 15:
            score += 0.3

        return min(score, 4.0)  # Cap at 4.0

    def _generate_embedding(self, text: str) -> Optional[np.ndarray]:
        """Generate embedding for text using sentence transformer."""
        try:
            if self.sentence_transformer and self.initialized:
                return self.sentence_transformer.encode(text)
        except Exception as e:
            print(f"⚠️ Embedding generation failed: {e}")
        return None

    async def add_message(self, role: str, content: str, category: str = "general") -> str:
        """
        Add a message to working, short-term, and eventually long-term memory.

        Args:
            role: Message role (user/assistant/system)
            content: Message content
            category: Message category (general, math, science, personal)

        Returns:
            Generated message ID
        """
        log_info(f"🧠 ADD: {role} - {content[:50]}...")

        message_id = hashlib.md5(
            f"{role}:{content}:{datetime.now()}".encode()).hexdigest()[:12]

        message = ContextMessage(
            role=role,
            content=content,
            timestamp=datetime.now(),
            token_count=self._count_tokens(content),
            message_id=message_id,
            category=category
        )

        # Calculate importance
        message.importance_score = self._calculate_importance(
            message, self.short_term_memory)

        # Generate embedding (only if initialized)
        if self.initialized:
            message.embedding = self._generate_embedding(content)

        # Add to working memory (always most recent)
        self.working_memory.append(message)

        # Add to short-term memory
        self.short_term_memory.append(message)
        self.conversation_buffer.append(message)
        self.messages_since_summary += 1

        # Check if we need to create a summary
        if self.messages_since_summary >= self.summary_threshold:
            await self._create_conversation_summary()

        # Maintain short-term memory size
        if len(self.short_term_memory) > self.short_term_messages:
            # Move oldest to long-term storage
            old_message = self.short_term_memory.pop(0)
            await self._store_long_term(old_message)

        # Extract and store user facts
        if role == "user":
            await self._extract_user_facts(message)

        return message_id

    async def _store_long_term(self, message: ContextMessage):
        """Store message in long-term database."""
        try:
            if not self.db_conn:
                return

            log_info(
                f"📦 Persisted to DB: {message.role} - {message.content[:50]}...")

            cursor = self.db_conn.cursor()
            embedding_blob = message.embedding.tobytes(
            ) if message.embedding is not None else None

            cursor.execute('''
                INSERT OR REPLACE INTO conversations 
                (id, role, content, timestamp, importance_score, token_count, category, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                message.message_id,
                message.role,
                message.content,
                message.timestamp.isoformat(),
                message.importance_score,
                message.token_count,
                message.category,
                embedding_blob
            ))

            self.db_conn.commit()

        except Exception as e:
            log_error(f"Long-term storage failed: {e}")

    async def _create_conversation_summary(self):
        """Create a summary of recent conversation for episodic memory."""
        try:
            if not self.conversation_buffer or len(self.conversation_buffer) < 5:
                return

            # Extract key messages (high importance)
            key_messages = [
                msg for msg in self.conversation_buffer if msg.importance_score > 2.0]
            if not key_messages:
                # Last 5 if no high importance
                key_messages = self.conversation_buffer[-5:]

            # Create summary text
            topics = set()
            summary_parts = []

            for msg in key_messages:
                if msg.role == "user":
                    summary_parts.append(f"User asked: {msg.content[:50]}")
                topics.add(msg.category)

            summary_text = " | ".join(summary_parts)

            # Store summary
            summary_id = hashlib.md5(
                f"{summary_text}:{datetime.now()}".encode()).hexdigest()[:12]

            cursor = self.db_conn.cursor()
            cursor.execute('''
                INSERT INTO conversation_summaries 
                (id, summary, timestamp, message_count, topics, importance_score)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                summary_id,
                summary_text,
                datetime.now().isoformat(),
                len(self.conversation_buffer),
                ",".join(topics),
                max(msg.importance_score for msg in key_messages)
            ))

            self.db_conn.commit()
            log_info(f"📝 Created conversation summary: {summary_text[:50]}...")

            # Clear buffer and reset counter
            self.conversation_buffer.clear()
            self.messages_since_summary = 0

        except Exception as e:
            log_error(f"Summary creation failed: {e}")

    async def _extract_user_facts(self, message: ContextMessage):
        """Extract and store facts about the user for long-term personalization."""
        try:
            if not self.db_conn:
                return

            content_lower = message.content.lower()

            # Name detection
            if "my name is" in content_lower or "i am" in content_lower:
                fact_id = hashlib.md5(
                    f"name:{message.content}:{datetime.now()}".encode()).hexdigest()[:12]
                cursor = self.db_conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO user_facts 
                    (id, fact_type, content, timestamp, confidence)
                    VALUES (?, ?, ?, ?, ?)
                ''', (fact_id, "name", message.content, message.timestamp.isoformat(), 0.9))
                self.db_conn.commit()
                log_info(f"💾 Stored user fact: name")

            # Preferences
            if "i like" in content_lower or "my favorite" in content_lower:
                fact_id = hashlib.md5(
                    f"preference:{message.content}:{datetime.now()}".encode()).hexdigest()[:12]
                cursor = self.db_conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO user_facts 
                    (id, fact_type, content, timestamp, confidence)
                    VALUES (?, ?, ?, ?, ?)
                ''', (fact_id, "preference", message.content, message.timestamp.isoformat(), 0.8))
                self.db_conn.commit()
                log_info(f"💾 Stored user fact: preference")

        except Exception as e:
            log_error(f"User fact extraction failed: {e}")

    async def _semantic_search(self, query: str, limit: int = 5) -> List[ContextMessage]:
        """
        Search for semantically similar messages in long-term memory.

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of relevant messages
        """
        try:
            if not self.db_conn or not self.sentence_transformer:
                return []

            # Generate query embedding
            query_embedding = self._generate_embedding(query)
            if query_embedding is None:
                return []

            cursor = self.db_conn.cursor()
            cursor.execute('''
                SELECT id, role, content, timestamp, importance_score, token_count, embedding
                FROM conversations 
                WHERE embedding IS NOT NULL
                ORDER BY importance_score DESC
                LIMIT 50
            ''')

            results = []
            for row in cursor.fetchall():
                try:
                    stored_embedding = np.frombuffer(row[6], dtype=np.float32)

                    # Calculate cosine similarity
                    similarity = np.dot(query_embedding, stored_embedding) / (
                        np.linalg.norm(query_embedding) *
                        np.linalg.norm(stored_embedding)
                    )

                    if similarity > 0.3:  # Similarity threshold
                        message = ContextMessage(
                            role=row[1],
                            content=row[2],
                            timestamp=datetime.fromisoformat(row[3]),
                            importance_score=row[4],
                            token_count=row[5],
                            message_id=row[0]
                        )
                        results.append((similarity, message))

                except Exception:
                    continue

            # Sort by similarity and return top results
            results.sort(key=lambda x: x[0], reverse=True)
            return [msg for _, msg in results[:limit]]

        except Exception as e:
            print(f"⚠️ Semantic search failed: {e}")
            return []

    async def _dynamic_truncation(self, messages: List[ContextMessage], target_tokens: int) -> List[ContextMessage]:
        """
        Dynamically truncate messages to fit token limit.

        Args:
            messages: List of messages to truncate
            target_tokens: Target token count

        Returns:
            Truncated message list
        """
        if not messages:
            return []

        # Always keep system message
        system_messages = [msg for msg in messages if msg.role == 'system']
        other_messages = [msg for msg in messages if msg.role != 'system']

        # Calculate current token count
        current_tokens = sum(msg.token_count for msg in messages)

        if current_tokens <= target_tokens:
            return messages

        # Sort by importance (keep most important)
        other_messages.sort(key=lambda x: x.importance_score, reverse=True)

        # Add messages until we hit token limit
        selected = system_messages.copy()
        tokens_used = sum(msg.token_count for msg in system_messages)

        for msg in other_messages:
            if tokens_used + msg.token_count <= target_tokens:
                selected.append(msg)
                tokens_used += msg.token_count
            else:
                break

        # Sort by timestamp to maintain conversation flow
        non_system = [msg for msg in selected if msg.role != 'system']
        non_system.sort(key=lambda x: x.timestamp)

        return system_messages + non_system

    async def get_optimized_context(self, current_query: str) -> List[Dict[str, str]]:
        """
        Get optimized context using three-tier memory system and semantic search.

        Args:
            current_query: Current user query for semantic search

        Returns:
            Optimized context messages in LLM format
        """
        try:
            # Start with system message
            context_messages = [ContextMessage(
                role='system',
                content=self.system_prompt,
                timestamp=datetime.now(),
                token_count=self._count_tokens(self.system_prompt)
            )]

            # Add user facts for personalization
            user_facts = await self._get_user_facts()
            if user_facts:
                facts_text = "User context: " + " | ".join(user_facts)
                context_messages.append(ContextMessage(
                    role='system',
                    content=facts_text,
                    timestamp=datetime.now(),
                    token_count=self._count_tokens(facts_text)
                ))

            # Always include working memory (most recent messages)
            context_messages.extend(list(self.working_memory))

            # Add relevant messages from short-term memory (not already in working memory)
            working_ids = {msg.message_id for msg in self.working_memory}
            relevant_short_term = [
                msg for msg in self.short_term_memory[-15:] if msg.message_id not in working_ids]
            context_messages.extend(relevant_short_term)

            # Add semantically relevant long-term memory and summaries (only if initialized)
            if current_query and self.initialized:
                relevant_messages = await self._semantic_search(current_query, limit=3)
                short_term_ids = {
                    msg.message_id for msg in self.short_term_memory}
                relevant_messages = [
                    msg for msg in relevant_messages if msg.message_id not in short_term_ids]
                context_messages.extend(relevant_messages)

                # Add relevant conversation summaries
                summaries = await self._get_relevant_summaries(current_query)
                if summaries:
                    summary_text = "Previous conversations: " + \
                        " | ".join(summaries)
                    context_messages.append(ContextMessage(
                        role='system',
                        content=summary_text,
                        timestamp=datetime.now(),
                        token_count=self._count_tokens(summary_text)
                    ))

            # Apply dynamic truncation
            optimized_messages = await self._dynamic_truncation(
                context_messages,
                self.max_context_length -
                self._count_tokens(current_query) - 100
            )

            # Convert to LLM format
            return [
                {"role": msg.role, "content": msg.content}
                for msg in optimized_messages
            ]

        except Exception as e:
            log_error(f"Context optimization failed: {e}")
            # Fallback to basic context with working memory
            return [
                {"role": "system", "content": self.system_prompt}
            ] + [
                {"role": msg.role, "content": msg.content}
                for msg in list(self.working_memory)
            ]

    async def _get_user_facts(self) -> List[str]:
        """Retrieve stored facts about the user."""
        try:
            if not self.db_conn:
                return []

            cursor = self.db_conn.cursor()
            cursor.execute('''
                SELECT content FROM user_facts 
                ORDER BY timestamp DESC 
                LIMIT 5
            ''')

            return [row[0] for row in cursor.fetchall()]

        except Exception as e:
            log_error(f"User facts retrieval failed: {e}")
            return []

    async def _get_relevant_summaries(self, query: str, limit: int = 2) -> List[str]:
        """Retrieve relevant conversation summaries."""
        try:
            if not self.db_conn:
                return []

            cursor = self.db_conn.cursor()
            cursor.execute('''
                SELECT summary FROM conversation_summaries 
                ORDER BY importance_score DESC, timestamp DESC 
                LIMIT ?
            ''', (limit,))

            return [row[0] for row in cursor.fetchall()]

        except Exception as e:
            log_error(f"Summary retrieval failed: {e}")
            return []

    async def get_basic_context(self) -> List[Dict[str, str]]:
        """
        Get basic context with working memory (faster, no semantic search).

        Returns:
            Basic context messages in LLM format
        """
        context = [{"role": "system", "content": self.system_prompt}]

        # Add working memory (most recent)
        for msg in list(self.working_memory):
            context.append({"role": msg.role, "content": msg.content})

        return context

    async def cleanup_old_memories(self, days_old: int = 30):
        """
        Clean up old memories from long-term storage.

        Args:
            days_old: Remove memories older than this many days
        """
        try:
            if not self.db_conn:
                return

            cutoff_date = datetime.now() - timedelta(days=days_old)
            cursor = self.db_conn.cursor()

            cursor.execute('''
                DELETE FROM conversations 
                WHERE timestamp < ? AND importance_score < 2.0
            ''', (cutoff_date.isoformat(),))

            deleted = cursor.rowcount
            self.db_conn.commit()

            if deleted > 0:
                print(f"🧹 Cleaned up {deleted} old memories")

        except Exception as e:
            print(f"⚠️ Memory cleanup failed: {e}")

    def get_memory_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics about memory usage."""
        try:
            stats = {
                "working_memory_messages": len(self.working_memory),
                "short_term_messages": len(self.short_term_memory),
                "short_term_tokens": sum(msg.token_count for msg in self.short_term_memory),
                "working_memory_tokens": sum(msg.token_count for msg in self.working_memory),
                "long_term_messages": 0,
                "conversation_summaries": 0,
                "user_facts": 0,
                "system_prompt_tokens": self._count_tokens(self.system_prompt),
                "session_duration_minutes": (datetime.now() - self.session_start).total_seconds() / 60,
                "messages_since_summary": self.messages_since_summary,
                "initialized": self.initialized
            }

            if self.db_conn:
                cursor = self.db_conn.cursor()

                cursor.execute("SELECT COUNT(*) FROM conversations")
                stats["long_term_messages"] = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM conversation_summaries")
                stats["conversation_summaries"] = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM user_facts")
                stats["user_facts"] = cursor.fetchone()[0]

            return stats

        except Exception as e:
            log_error(f"Stats generation failed: {e}")
            return {"error": str(e)}

    async def clear_working_memory(self):
        """Clear working memory while keeping short-term intact."""
        self.working_memory.clear()
        log_info("🧹 Cleared working memory")

    async def reset_session(self):
        """Start a new conversation session with summary creation."""
        if self.conversation_buffer:
            await self._create_conversation_summary()

        self.working_memory.clear()
        self.short_term_memory.clear()
        self.conversation_buffer.clear()
        self.session_start = datetime.now()
        self.messages_since_summary = 0

        log_info("🔄 Started new conversation session")


# Global instance for easy import
context_manager = None


async def get_context_manager():
    """Get or create the global context manager instance."""
    global context_manager
    if context_manager is None:
        try:
            context_manager = AdvancedContextManager()
            await context_manager.initialize()
        except Exception as e:
            log_error(f"Context manager initialization failed: {e}")
            raise
    return context_manager

# Convenience functions for other modules


async def add_user_message(content: str) -> str:
    """Add user message to context."""
    manager = await get_context_manager()
    return await manager.add_message("user", content)


async def add_assistant_message(content: str) -> str:
    """Add assistant message to context."""
    manager = await get_context_manager()
    return await manager.add_message("assistant", content)


async def get_context_for_query(query: str) -> List[Dict[str, str]]:
    """Get optimized context for a specific query."""
    manager = await get_context_manager()
    return await manager.get_optimized_context(query)


async def get_basic_context() -> List[Dict[str, str]]:
    """Get basic context without semantic search."""
    manager = await get_context_manager()
    return await manager.get_basic_context()


async def get_context_stats() -> Dict[str, Any]:
    """Get context memory statistics."""
    manager = await get_context_manager()
    return manager.get_memory_stats()  # This is not async
