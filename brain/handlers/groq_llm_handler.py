# brain/handlers/groq_llm_handler.py

"""
Updated Groq LLM handler for Maxi AI with advanced context management.
"""

import uuid
import asyncio
from datetime import datetime
import os
from groq import Groq
from voice.speaker import SmoothTTSEngine
from utils.logger import log_info, log_error, log_warning
from ui.socket_server import SocketServer
from brain.context_manager.context_manager import add_user_message, add_assistant_message, get_context_for_query
from brain.safety import filter_input, filter_output, check_rate_limit, log_question, log_filter_event
from dotenv import load_dotenv

load_dotenv()

# Load environment values
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "compound-beta-mini")

# Initialize Groq client
client = Groq(api_key=GROQ_API_KEY)


async def prewarm_model():
    """No prewarm needed for Groq, but simulate one for consistency."""
    log_info("🔥 Groq LLM ready (no warmup required)")
    return True


async def handle_llm(prompt: str, tts_engine: SmoothTTSEngine, socket: SocketServer, session_id: str = None):
    """
    Handle a general query using Groq LLM with streaming response and advanced context.

    Args:
        prompt: User input
        tts_engine: TTS engine for speech output
        socket: WebSocket server for UI output
        session_id: Optional session ID for tracking
    """
    try:
        log_info(f"⚡ Using Groq LLM for: {prompt[:50]}")

        # Generate session ID if not provided
        if not session_id:
            session_id = f"chat_{uuid.uuid4().hex[:12]}"

        # Step 1: Check rate limits
        is_allowed, rate_warning, rate_stats = check_rate_limit(
            session_id, mode="chat")
        if not is_allowed:
            log_info(f"🛑 Rate limit exceeded for session {session_id}")
            await socket.emit_response_start(f"rate_limit_{uuid.uuid4().hex[:8]}")
            await socket.emit_response_chunk(rate_warning, f"rate_limit_{uuid.uuid4().hex[:8]}")
            await socket.emit_response_complete(f"rate_limit_{uuid.uuid4().hex[:8]}")
            await tts_engine.speak_text(rate_warning)
            return rate_warning

        # Display rate warning if exists (e.g., break reminders)
        if rate_warning:
            log_info(f"⏰ Rate warning: {rate_warning}")
            await socket.emit_notification(rate_warning)

        # Step 2: Filter input for inappropriate content
        is_safe, filter_reason, fallback_response = filter_input(
            prompt, session_id)
        if not is_safe:
            log_info(f"🛡️ Blocked inappropriate input: {filter_reason}")

            # Log filter event
            log_filter_event(session_id, "input", prompt[:100], filter_reason)

            # Send fallback response
            await socket.emit_response_start(f"filtered_{uuid.uuid4().hex[:8]}")
            await socket.emit_response_chunk(fallback_response, f"filtered_{uuid.uuid4().hex[:8]}")
            await socket.emit_response_complete(f"filtered_{uuid.uuid4().hex[:8]}")
            await tts_engine.speak_text(fallback_response)

            # Still add to context for learning
            await add_user_message(f"[Filtered question]")
            await add_assistant_message(fallback_response)

            return fallback_response

        # Step 3: Log the question for tracking
        log_question(session_id, prompt, "chat", topic=None)

        # Get optimized context from context manager
        context = await get_context_for_query(prompt)
        log_info(f"📋 Using context with {len(context)} messages")

        # Debug: Log recent conversation context
        recent_messages = [msg for msg in context if msg["role"] in [
            "user", "assistant"]][-4:]
        for i, msg in enumerate(recent_messages):
            role_emoji = "👤" if msg["role"] == "user" else "🤖"
            content_preview = msg["content"][:60] + \
                "..." if len(msg["content"]) > 60 else msg["content"]
            log_info(f"  {role_emoji} {msg['role']}: {content_preview}")

        # Ensure last message is a user message (required by Groq API)
        if context and context[-1]["role"] != "user":
            context.append({"role": "user", "content": prompt})
            log_info("📝 Added current prompt as final user message")

        stream_id = f"groq_{uuid.uuid4().hex[:8]}"
        await socket.emit_response_start(stream_id)

        full_response = ""
        chunk_count = 0
        max_retries = 2
        retry_count = 0
        
        # Track when to start speaking (after first complete sentence)
        sentence_buffer = ""
        speaking_started = False
        sentences_to_speak = []  # Queue of sentences to speak
        speaking_task = None  # Track the TTS task

        # Detect if user wants a longer, more detailed answer
        longer_keywords = ['longer', 'more details',
                           'explain more', 'tell me more', 'go deeper', 'elaborate']
        wants_longer_answer = any(keyword in prompt.lower()
                                  for keyword in longer_keywords)

        # Adjust max_tokens based on user request
        # Short by default, longer if requested
        max_tokens = 350 if wants_longer_answer else 150

        if wants_longer_answer:
            log_info(
                f"📝 User requested longer answer - using {max_tokens} tokens")

        # Retry logic for empty responses (Groq sometimes has temporary issues)
        while retry_count <= max_retries:
            try:
                # Start streaming Groq response
                completion = client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=context,
                    temperature=0.7,
                    max_tokens=max_tokens,
                    top_p=1.0,
                    stream=True
                )

                for chunk in completion:
                    delta = chunk.choices[0].delta.content or ""
                    if delta:
                        # Stream text to UI immediately
                        await socket.emit_response_chunk(delta, stream_id)
                        full_response += delta
                        sentence_buffer += delta
                        chunk_count += 1
                        
                        # Start TTS as soon as we have a complete sentence
                        if any(punct in sentence_buffer for punct in ['. ', '! ', '? ', '\n\n']):
                            # Found complete sentence
                            complete_sentence = sentence_buffer.strip()
                            
                            if not speaking_started:
                                # First sentence - start speaking immediately
                                log_info(f"🎤 Starting speaking after first sentence ({len(complete_sentence)} chars)")
                                await socket.emit_state_change("speaking")
                                speaking_started = True
                                
                                # Start TTS for first sentence (track the task)
                                speaking_task = asyncio.create_task(tts_engine.speak_text(complete_sentence))
                            else:
                                # Subsequent sentences - queue them for later
                                sentences_to_speak.append(complete_sentence)
                            
                            sentence_buffer = ""  # Clear for next sentence

                # If we got a response, break out of retry loop
                if full_response.strip():
                    break

                # Empty response on first try - retry
                if retry_count < max_retries:
                    retry_count += 1
                    log_warning(
                        f"⚠️ Empty response from Groq, retry {retry_count}/{max_retries}")
                    await asyncio.sleep(0.5)  # Brief delay before retry
                    continue
                else:
                    # All retries exhausted
                    break

            except Exception as api_error:
                log_error(
                    f"❌ Groq API error on attempt {retry_count + 1}: {api_error}")
                if retry_count < max_retries:
                    retry_count += 1
                    await asyncio.sleep(0.5)
                    continue
                else:
                    raise  # Re-raise if all retries exhausted

        await socket.emit_response_complete(stream_id)

        # Log if we got an empty response to help debug
        if not full_response.strip():
            log_warning(
                f"⚠️ Groq returned empty response. Context length: {len(context)} messages, Last user message: '{prompt[:50]}...'")

        if full_response.strip():
            # Step 4: Filter output for age-appropriateness
            is_output_safe, sanitized_response = filter_output(
                full_response.strip())

            if not is_output_safe:
                log_info(f"🛡️ Filtered LLM output")
                log_filter_event(session_id, "output",
                                 full_response[:100], "inappropriate_content")
                final_response = sanitized_response
            else:
                final_response = full_response.strip()

            # Add assistant response to context manager
            await add_assistant_message(final_response)

            log_info(
                f"✅ Groq response: {len(full_response)} chars, {chunk_count} chunks")
            log_info(f"🤖 Response preview: {final_response[:100]}...")

            # Handle speaking based on what happened during streaming
            if speaking_started and speaking_task:
                # Wait for first sentence to finish speaking
                log_info("⏳ Waiting for first sentence to complete...")
                await speaking_task
                
                # Now speak all queued sentences
                if sentences_to_speak:
                    log_info(f"🎤 Speaking {len(sentences_to_speak)} remaining sentences")
                    for sentence in sentences_to_speak:
                        await tts_engine.speak_text(sentence)
                
                # Speak any remaining text that wasn't a complete sentence
                if sentence_buffer.strip():
                    log_info(f"🎤 Speaking final incomplete sentence ({len(sentence_buffer)} chars)")
                    await tts_engine.speak_text(sentence_buffer.strip())
            else:
                # Very short response (no complete sentences during streaming)
                log_info("🎤 Starting TTS for complete response")
                await socket.emit_state_change("speaking")
                await tts_engine.speak_text(final_response)

            # Return to listening after speaking completes
            await socket.emit_state_change("listening")

            return final_response
        else:
            raise ValueError("Empty response")

    except Exception as e:
        log_error(f"❌ Groq handler failed: {e}")
        fallback = "Hmm, I'm not sure right now. Can you try again?"

        # DON'T add error fallback to context - it pollutes the conversation history
        # and makes future responses more likely to fail
        # await add_assistant_message(fallback)  # REMOVED

        try:
            await socket.broadcast({
                "type": "response",
                "text": fallback,
                "streaming": False,
                "timestamp": datetime.now().isoformat()
            })
        except:
            pass
        await tts_engine.speak_text(fallback)
        return fallback
