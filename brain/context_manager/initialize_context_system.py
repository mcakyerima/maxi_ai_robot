"""
Context Manager initialization and utility functions.
Run this to set up the context manager properly.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add the parent directory to sys.path to import the context manager
sys.path.append(str(Path(__file__).parent.parent.parent))

try:
    from brain.context_manager.context_manager import (
        AdvancedContextManager,
        get_context_stats,
        add_user_message,
        add_assistant_message,
        get_context_for_query
    )
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure the context_manager.py file is in the correct location")
    sys.exit(1)

async def initialize_context_system():
    """Initialize the context management system."""
    print("🚀 Initializing Advanced Context Manager...")
    
    try:
        # Create instance
        manager = AdvancedContextManager()
        
        # Initialize all components
        await manager.initialize()
        
        # Verify initialization
        if not await manager.is_initialized():
            raise RuntimeError("Initialization verification failed")
        
        # Clean up old memories
        await manager.cleanup_old_memories(days_old=30)
        
        # Get stats
        stats = manager.get_memory_stats()  # This is not async
        print(f"📊 Context System Status:")
        print(f"   • Short-term messages: {stats.get('short_term_messages', 0)}")
        print(f"   • Long-term messages: {stats.get('long_term_messages', 0)}")
        print(f"   • System prompt tokens: {stats.get('system_prompt_tokens', 0)}")
        print(f"   • Initialized: {stats.get('initialized', False)}")
        
        print("✅ Context Manager ready!")
        return manager
        
    except Exception as e:
        print(f"❌ Failed to initialize context manager: {e}")
        import traceback
        traceback.print_exc()
        return None

async def test_context_system():
    """Test the context management system."""
    print("\n🧪 Testing Context System...")
    
    try:
        # Test adding messages
        user_msg_id = await add_user_message("What is photosynthesis?")
        print(f"✅ Added user message: {user_msg_id}")
        
        assistant_msg_id = await add_assistant_message("Plants make food from sunlight, like magic cooking!")
        print(f"✅ Added assistant message: {assistant_msg_id}")
        
        # Test context retrieval
        context = await get_context_for_query("How do plants work?")
        print(f"✅ Context retrieval works: {len(context)} messages")
        
        # Show sample context
        print("📋 Sample context structure:")
        for i, msg in enumerate(context[:3]):
            role = msg['role']
            content = msg['content'][:50] + "..." if len(msg['content']) > 50 else msg['content']
            print(f"   {i+1}. [{role}]: {content}")
        
        # Test stats
        stats = await get_context_stats()
        print(f"📈 Final stats: {stats}")
        
        return True
        
    except Exception as e:
        print(f"❌ Context system test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Main initialization function."""
    print("🧠 Maxi AI Advanced Context Manager Setup")
    print("=" * 50)
    
    # Check dependencies
    try:
        import sentence_transformers
        import tiktoken
        import numpy as np
        import sqlite3
        print("✅ All dependencies available")
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("Please install required packages:")
        print("pip install sentence-transformers tiktoken numpy")
        return False
    
    # Check if database directory exists
    db_dir = Path(".")
    if not db_dir.exists():
        print(f"📁 Creating database directory: {db_dir}")
        db_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize system
    manager = await initialize_context_system()
    if not manager:
        return False
    
    # Test system
    test_success = await test_context_system()
    if not test_success:
        return False
    
    print("\n🎉 Context Manager is ready for use!")
    print("\nIntegration examples:")
    print("```python")
    print("from brain.context_manager.context_manager import (")
    print("    add_user_message, get_context_for_query,")
    print("    add_assistant_message, get_context_stats")
    print(")")
    print("")
    print("# In your handlers:")
    print("await add_user_message(user_input)")
    print("context = await get_context_for_query(user_input)")
    print("# Use context with your LLM...")
    print("await add_assistant_message(llm_response)")
    print("```")
    
    return True

if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n👋 Initialization cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)