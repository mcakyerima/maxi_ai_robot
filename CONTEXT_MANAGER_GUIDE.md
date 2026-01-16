# Advanced Context Manager - Professional Memory System

## Overview
Maxi's context manager now uses a **three-tier memory architecture** inspired by human cognitive psychology, providing superior short-term and long-term memory capabilities.

## Memory Architecture

### 1. **Working Memory** (Immediate Context)
- **Size**: Last 10 messages
- **Purpose**: Always-accessible immediate conversation context
- **Speed**: Instant access
- **Use case**: Current conversation flow

### 2. **Short-term Memory** (Recent Conversation)
- **Size**: Last 40 messages
- **Purpose**: Recent conversation history
- **Speed**: Fast access
- **Use case**: Maintaining conversation continuity

### 3. **Long-term Memory** (Persistent Storage)
- **Storage**: SQLite database with embeddings
- **Purpose**: Persistent knowledge across sessions
- **Speed**: Semantic search retrieval
- **Use case**: Recalling past conversations and learning

### 4. **Episodic Memory** (Conversation Summaries)
- **Storage**: Conversation summaries every 20 messages
- **Purpose**: Quick recall of past conversation topics
- **Speed**: Fast lookup
- **Use case**: Understanding conversation history at a glance

### 5. **User Facts Database**
- **Storage**: Extracted personal information
- **Purpose**: Personalization and continuity
- **Examples**: User's name, preferences, interests
- **Use case**: Creating personalized responses

## Key Features

### ✅ Intelligent Importance Scoring
Messages are scored based on:
- **Recency**: Newer messages score higher
- **Content length**: Substantive messages are more important
- **Educational keywords**: Science/learning topics prioritized
- **Personal information**: User details highly prioritized
- **Questions**: Indicate important exchanges
- **Categories**: Math, science, personal topics tracked

### ✅ Semantic Search
- Uses sentence transformers (all-MiniLM-L6-v2) for embeddings
- Finds relevant past conversations based on meaning, not just keywords
- Retrieves top 3 most relevant messages for any query

### ✅ Dynamic Truncation
- Automatically manages token limits (4000 tokens max)
- Keeps system prompts and high-importance messages
- Maintains conversation flow chronologically
- Never exceeds LLM context window

### ✅ Automatic Summarization
- Creates summaries every 20 messages
- Extracts key topics and questions
- Stores in episodic memory for quick recall
- Reduces long-term storage needs

### ✅ User Fact Extraction
- Automatically detects and stores:
  - User's name ("my name is...", "I am...")
  - Preferences ("I like...", "my favorite...")
  - Personal information
- High confidence scoring
- Used for personalized responses

## Usage Examples

### Adding Messages
```python
# Add user message with category
await context_manager.add_message("user", "What is gravity?", category="science")

# Add assistant response
await context_manager.add_message("assistant", "Gravity is like a big magnet that pulls things down!")
```

### Getting Context
```python
# Get optimized context with semantic search
context = await context_manager.get_optimized_context("Tell me about space")

# Get basic context (faster, no semantic search)
basic_context = await context_manager.get_basic_context()
```

### Memory Statistics
```python
stats = context_manager.get_memory_stats()
# Returns:
# {
#   "working_memory_messages": 10,
#   "short_term_messages": 25,
#   "long_term_messages": 150,
#   "conversation_summaries": 7,
#   "user_facts": 3,
#   "session_duration_minutes": 45.2
# }
```

### Session Management
```python
# Clear working memory
await context_manager.clear_working_memory()

# Start new session (creates summary of current session)
await context_manager.reset_session()

# Clean up old memories (>30 days, low importance)
await context_manager.cleanup_old_memories(days_old=30)
```

## Database Schema

### conversations table
```sql
- id: Message ID (primary key)
- role: user/assistant/system
- content: Message text
- timestamp: When message was created
- importance_score: 0.0 - 4.0
- token_count: Number of tokens
- category: general/math/science/personal
- embedding: Vector embedding (binary)
```

### conversation_summaries table
```sql
- id: Summary ID (primary key)
- summary: Summary text
- timestamp: When summary was created
- message_count: Number of messages summarized
- topics: Comma-separated topics
- importance_score: Overall importance
```

### user_facts table
```sql
- id: Fact ID (primary key)
- fact_type: name/preference/personal
- content: Fact content
- timestamp: When fact was extracted
- confidence: 0.0 - 1.0
```

## Performance Characteristics

| Operation | Speed | Token Cost |
|-----------|-------|------------|
| Add message | ~5ms | N/A |
| Get basic context | ~10ms | ~500 tokens |
| Get optimized context | ~50ms | ~2000 tokens |
| Semantic search | ~100ms | N/A |
| Create summary | ~200ms | N/A |

## Memory Flow Diagram

```
User Input
    ↓
Working Memory (10 msgs) ← Always included
    ↓
Short-term Memory (40 msgs) ← Recent context
    ↓
Long-term Storage (DB) ← Semantic search
    ↓
Episodic Summaries (DB) ← Topic recall
    ↓
User Facts (DB) ← Personalization
    ↓
Optimized Context → LLM
```

## Configuration

Adjust these parameters in initialization:

```python
context_manager = AdvancedContextManager(
    db_path="context_memory.db",           # Database location
    max_context_length=4000,                # Max tokens for LLM
    working_memory_size=10,                 # Most recent messages
    short_term_messages=40,                 # Recent conversation
    embedding_model_name="all-MiniLM-L6-v2" # Sentence transformer
)
```

## Benefits

### For Users:
✅ Maxi remembers their name and preferences  
✅ Can recall past conversations  
✅ Provides consistent, personalized responses  
✅ Maintains context across long interactions  

### For System:
✅ Efficient token usage  
✅ Fast retrieval with semantic search  
✅ Automatic memory management  
✅ Scales to thousands of messages  

### For Deployment:
✅ Works offline (local database)  
✅ Low memory footprint  
✅ Portable (SQLite)  
✅ Easy to back up and restore  

## Maintenance

### Daily
- Automatic: Summaries created every 20 messages
- Automatic: User facts extracted from conversations

### Weekly
- Optional: Review memory statistics
- Optional: Check database size

### Monthly
```python
# Clean up old, low-importance memories
await context_manager.cleanup_old_memories(days_old=30)
```

## Troubleshooting

### Slow Context Retrieval
- Reduce `short_term_messages` (40 → 30)
- Disable semantic search for speed: use `get_basic_context()`
- Check database size: `get_memory_stats()`

### High Memory Usage
- Run cleanup: `cleanup_old_memories()`
- Reduce `working_memory_size` (10 → 5)
- Check for embedding model memory

### Missing Memories
- Verify database file exists: `context_memory.db`
- Check initialization: `await context_manager.is_initialized()`
- Review importance scores in logs

---

**Status**: ✅ Production Ready  
**Version**: 2.0 Enhanced  
**Last Updated**: January 16, 2026
