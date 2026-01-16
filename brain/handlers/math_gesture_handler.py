# brain/handlers/math_gesture_handler.py
"""
Enhanced Math/Gesture Handler for Maxi AI with Human-like Finger Control
Fixed timing issues and proper speech-then-actuation sequence
"""

import json
import time
import uuid
import re
import asyncio
from datetime import datetime
from typing import Dict, Optional, Tuple, Any, List
import os
from dotenv import load_dotenv

from utils.logger import log_info, log_error, log_warning
from brain.safety import check_rate_limit, log_question, filter_input, log_filter_event

load_dotenv()


class MathGestureHandler:
    """
    Enhanced math handler with human-like hardware finger control that:
    1. Parses math questions from speech (both simple and complex)
    2. Determines if finger visualization is appropriate (0-10 range)
    3. Coordinates TTS, UI updates, and natural finger animations
    4. Handles both basic and advanced math problems with smart state tracking
    """

    def __init__(self, tts_engine, socket_server, context_manager=None, finger_controller=None):
        self.tts_engine = tts_engine
        self.socket_server = socket_server
        self.context_manager = context_manager
        self.finger_controller = finger_controller
        self.llm_provider = os.getenv("LLM_PROVIDER", "ollama").lower()

        # Initialize LLM client based on provider
        if self.llm_provider == "groq":
            from groq import Groq
            self.groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
            self.model_name = os.getenv(
                "GROQ_MODEL", "llama-3.3-70b-versatile")
        else:
            # Ollama will be imported when needed
            self.groq_client = None
            self.model_name = os.getenv("OLLAMA_MODEL", "llama3.2")

        # Finger state tracking - start with all fingers closed (human-like)
        self.current_finger_state = {
            # [index, middle, ring, pinky, thumb] - 0=closed, 1=open
            "left": [0, 0, 0, 0, 0],
            "right": [0, 0, 0, 0, 0]
        }
        self.fingers_initialized = False

        # Log finger controller availability
        if self.finger_controller:
            hardware_available = self.finger_controller.is_hardware_available()
            log_info(
                f"Math handler initialized with finger controller ({'Hardware' if hardware_available else 'Simulation'} mode)")
        else:
            log_warning(
                "Math handler initialized without finger controller - UI only mode")

    async def initialize_hands(self):
        """Initialize hands to closed position (human-like starting state)."""
        if not self.fingers_initialized:
            log_info("Initializing hands to closed position")
            if self.finger_controller:
                await self.finger_controller.close_all_fingers()
            await self.send_finger_pose_to_ui("clear")  # Closed position
            self.fingers_initialized = True

    async def process_math_question(self, user_input: str, session_id: str = None) -> Dict[str, Any]:
        """
        Main entry point for processing math questions with natural finger gestures.

        Args:
            user_input: The user's spoken math question
            session_id: Optional session ID for tracking

        Returns:
            Dict containing the processing result and metadata
        """
        # Generate session ID if not provided
        if not session_id:
            session_id = f"math_{uuid.uuid4().hex[:12]}"

        # Check rate limits
        is_allowed, rate_warning, rate_stats = check_rate_limit(
            session_id, mode="math")
        if not is_allowed:
            log_info(f"🛑 Rate limit exceeded for session {session_id}")
            await self.tts_engine.speak_text(rate_warning)
            return {"error": rate_warning, "rate_limited": True}

        # Display rate warning if exists (e.g., break reminders)
        if rate_warning:
            log_info(f"⏰ Rate warning: {rate_warning}")
            # Emit warning to UI (non-blocking)
            await self.socket_server.emit_notification(rate_warning)

        # Filter input for inappropriate content
        is_safe, filter_reason, fallback_response = filter_input(
            user_input, session_id)
        if not is_safe:
            log_info(f"🛡️ Blocked inappropriate math input: {filter_reason}")
            log_filter_event(session_id, "input",
                             user_input[:100], filter_reason)

            await self.tts_engine.speak_text(fallback_response)
            return {"error": fallback_response, "filtered": True}

        # Log the question
        log_question(session_id, user_input, "math", topic="mathematics")

        # Check if we're in a grace period (sync with socket_server.py)
        if hasattr(self.socket_server, '_last_mode_change_time'):
            grace_period = getattr(
                self.socket_server, '_mode_transition_grace_period', 1.5)
            elapsed = time.time() - self.socket_server._last_mode_change_time
            if elapsed < grace_period:
                log_warning(
                    "Ignoring math question during mode transition grace period")
                return {"error": "Please wait a moment..."}

        # Initialize hands if not done yet
        await self.initialize_hands()

        try:
            log_info(f"Processing math question: {user_input}")

            # Emit transcription to UI
            await self.socket_server.emit_transcription(user_input)
            await self.socket_server.emit_state_change("processing")

            # FIXED: Try simple pattern matching first for basic math to avoid LLM delays
            simple_math = self.try_simple_pattern_matching(user_input)
            if simple_math:
                log_info(
                    f"Using fast pattern matching: {simple_math.get('type', 'simple')}")

                # Check if it's multi-operand or should be shown as steps
                if simple_math.get("steps") and len(simple_math.get("steps", [])) > 0:
                    # Multi-operand expression - show as advanced with steps
                    return await self.handle_advanced_math(simple_math, user_input)
                elif simple_math.get("is_basic"):
                    # Basic finger counting math
                    return await self.handle_basic_math(simple_math, user_input)
                else:
                    # Numbers too large for fingers, show as advanced
                    return await self.handle_advanced_math(simple_math, user_input)

            # Fall back to LLM for complex problems
            parsed_math = await self.parse_math_utterance(user_input)

            if parsed_math.get("error"):
                return await self.handle_error(parsed_math["error"])

            # Determine if this is basic math (finger counting) or advanced
            is_basic_math = self.is_basic_math_problem(parsed_math)

            if is_basic_math:
                return await self.handle_basic_math(parsed_math, user_input)
            else:
                return await self.handle_advanced_math(parsed_math, user_input)

        except Exception as e:
            log_error(f"Error processing math question: {e}")
            return await self.handle_error(f"I had trouble understanding that math problem: {str(e)}")

    def try_simple_pattern_matching(self, utterance: str) -> Optional[Dict[str, Any]]:
        """
        Enhanced pattern matching for simple math including multi-operand expressions.
        Handles: 2+2+3, 5-1-2, 3*2*2, etc.
        """
        try:
            # Normalize the input
            text = utterance.lower().strip()

            # Word to number mapping
            word_to_num = {
                'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
                'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
                'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15,
                'sixteen': 16, 'seventeen': 17, 'eighteen': 18, 'nineteen': 19, 'twenty': 20
            }

            # Replace words with numbers
            for word, num in word_to_num.items():
                text = text.replace(word, str(num))

            # Try to detect the operation type
            operation = None
            if any(word in text for word in ['+', 'plus', 'add', 'and']):
                operation = '+'
            elif any(word in text for word in ['-', 'minus', 'subtract', 'take away']):
                operation = '-'
            elif any(word in text for word in ['*', 'times', 'multiply', 'multiplied']):
                operation = '*'
            elif any(word in text for word in ['/', 'divided by', 'divide']):
                operation = '/'

            if not operation:
                return None

            # Extract all numbers from the text
            numbers = re.findall(r'\d+', text)
            if len(numbers) < 2:
                return None

            # Convert to integers
            numbers = [int(n) for n in numbers]

            # Check if all numbers are kid-friendly (0-20)
            if not all(0 <= n <= 20 for n in numbers):
                return None  # Too large for kids

            # Handle multi-operand calculation
            if len(numbers) == 2:
                # Simple two-operand case
                a, b = numbers
                result = self._calculate(a, operation, b)

                if result is None or not (0 <= result <= 100):
                    return None

                # Check if suitable for finger counting (0-10)
                is_basic = (0 <= a <= 10 and 0 <= b <=
                            10 and 0 <= result <= 10)

                return {
                    "type": "simple",
                    "A": a,
                    "B": b,
                    "OP": operation,
                    "result": result,
                    "speech": f"{a} {self.op_to_word(operation)} {b} equals {result}",
                    "explanation": self.generate_dynamic_explanation(a, b, operation, result),
                    "original_question": utterance,
                    "is_basic": is_basic,
                    "steps": []
                }

            else:
                # Multi-operand case (2+2+3, 5-1-2, etc.)
                return self._handle_multi_operand(numbers, operation, utterance)

        except Exception as e:
            log_warning(f"Pattern matching failed: {e}")
            return None

    def _calculate(self, a: int, op: str, b: int) -> Optional[int]:
        """Perform basic calculation."""
        try:
            if op == '+':
                return a + b
            elif op == '-':
                return a - b
            elif op == '*':
                return a * b
            elif op == '/':
                if b == 0:
                    return None
                result = a / b
                return int(result) if result == int(result) else None
        except:
            return None

    def _handle_multi_operand(self, numbers: List[int], operation: str, utterance: str) -> Dict[str, Any]:
        """Handle multi-operand expressions like 2+2+3 or 5-1-2."""
        try:
            # Calculate step by step
            steps = []
            current_result = numbers[0]

            for i in range(1, len(numbers)):
                next_num = numbers[i]
                step_result = self._calculate(
                    current_result, operation, next_num)

                if step_result is None:
                    return None

                steps.append({
                    "step": i,
                    "operation": f"{current_result} {operation} {next_num}",
                    "result": step_result,
                    "description": f"{current_result} {self.op_to_word(operation)} {next_num}"
                })

                current_result = step_result

            final_result = current_result

            # Check if result is kid-appropriate
            if not (0 <= final_result <= 100):
                return None

            # Build expression string
            expression = f" {operation} ".join(map(str, numbers))

            # Generate explanation
            if len(steps) == 1:
                explanation = self.generate_dynamic_explanation(
                    numbers[0], numbers[1], operation, final_result)
            else:
                explanation = f"Let me solve this step by step! We get {final_result}."

            # Check if basic (can show with fingers) - only if 2 operands and all <= 10
            is_basic = (len(numbers) == 2 and
                        all(0 <= n <= 10 for n in numbers) and
                        0 <= final_result <= 10)

            return {
                "type": "multi_operand" if len(numbers) > 2 else "simple",
                "expression": expression,
                "numbers": numbers,
                "operation": operation,
                "result": final_result,
                "speech": f"{expression} equals {final_result}",
                "explanation": explanation,
                "original_question": utterance,
                "is_basic": is_basic,
                "steps": steps,
                # For compatibility with basic math handler
                "A": numbers[0] if len(numbers) == 2 else None,
                "B": numbers[1] if len(numbers) == 2 else None,
                "OP": operation
            }

        except Exception as e:
            log_error(f"Multi-operand calculation failed: {e}")
            return None

    def op_to_word(self, op: str) -> str:
        """Convert operator to word."""
        return {'+': 'plus', '-': 'minus', '*': 'times', '/': 'divided by'}.get(op, op)

    def generate_dynamic_explanation(self, a: int, b: int, op: str, result: int) -> str:
        """
        FIXED: Generate dynamic, child-friendly explanations instead of static ones.
        """
        explanations = {
            '+': [
                f"When we add {a} and {b} together, we get {result}!",
                f"If you have {a} things and get {b} more, you'll have {result} things total!",
                f"Counting up from {a} by {b} more gives us {result}!",
                f"Addition means putting numbers together - {a} plus {b} makes {result}!"
            ],
            '-': [
                f"When we take away {b} from {a}, we have {result} left!",
                f"If you start with {a} and remove {b}, you get {result}!",
                f"Subtraction means taking away - {a} minus {b} equals {result}!",
                f"Counting down from {a} by {b} gives us {result}!"
            ],
            '*': [
                f"When we multiply {a} by {b}, we get {result}!",
                f"That's like having {a} groups of {b}, which makes {result}!",
                f"Multiplication means repeated addition - {result} is our answer!",
                f"Times tables tell us that {a} times {b} equals {result}!"
            ],
            '/': [
                f"When we divide {a} by {b}, we get {result}!",
                f"That's like sharing {a} things equally into {b} groups!",
                f"Division means splitting up - {a} divided by {b} gives us {result}!",
                f"Each group would have {result} when we split {a} by {b}!"
            ]
        }

        import random
        return random.choice(explanations.get(op, [f"The answer is {result}!"]))

    async def parse_math_utterance(self, utterance: str) -> Dict[str, Any]:
        """
        Parse the user's spoken math question into structured data using LLM.
        Enhanced for both basic and advanced math problems including multi-step operations.
        """
        try:
            system_prompt = """You are a math solver for an educational robot. Analyze the user's math question and provide a JSON response.

For SIMPLE math (single operation like "2 + 3" or "what's 5 minus 2"):
{
  "type": "simple",
  "A": 2,
  "B": 3,
  "OP": "+",
  "result": 5,
  "speech": "Two plus three equals five",
  "explanation": "When we add 2 and 3 together, we get 5!",
  "original_question": "2 + 3",
  "is_basic": true,
  "steps": []
}

For COMPLEX math (multi-step, word problems, or advanced operations):
{
  "type": "complex", 
  "result": 7,
  "speech": "Ten plus five minus eight equals seven",
  "explanation": "First add ten and five to get fifteen, then subtract eight",
  "original_question": "10 + 5 - 8",
  "is_basic": false,
  "steps": [
    {"step": 1, "operation": "10 + 5", "result": 15, "description": "Add ten and five"},
    {"step": 2, "operation": "15 - 8", "result": 7, "description": "Subtract eight from fifteen"}
  ],
  "breakdown": "10 + 5 - 8 = 15 - 8 = 7"
}

RULES:
- Convert words to numbers ("two" → 2, "fifteen" → 15)
- For single operations with results 0-10, set "is_basic": true
- For multi-step, large numbers, decimals, fractions, set "is_basic": false  
- Always calculate correct results
- Provide clear step-by-step breakdown for complex problems
- Make explanations dynamic and child-friendly (avoid static phrases like "Easy addition!")
- If unclear, set "error" field with friendly message

Examples:
- "what is two plus three" → simple, is_basic: true
- "what's 25 times 4" → simple, is_basic: false (result > 10)
- "10 plus 5 minus 8" → complex, is_basic: false (multi-step)
- "if I have 12 apples and eat 3" → complex, is_basic: false (word problem)"""

            user_prompt = f'Solve this math problem: "{utterance}"'

            if self.llm_provider == "groq":
                response = await self.query_groq(system_prompt, user_prompt)
            else:
                response = await self.query_ollama(system_prompt, user_prompt)

            # Clean and parse JSON response
            try:
                # Remove any markdown formatting or extra text
                response = response.strip()

                # Handle various markdown formats
                if "```json" in response:
                    # Extract JSON from markdown code block
                    start = response.find("```json") + 7
                    end = response.find("```", start)
                    if end != -1:
                        response = response[start:end].strip()
                    else:
                        response = response[start:].strip()
                elif "```" in response:
                    # Handle plain code blocks
                    start = response.find("```") + 3
                    end = response.find("```", start)
                    if end != -1:
                        response = response[start:end].strip()
                    else:
                        response = response[start:].strip()
                elif response.startswith("Here's the JSON response:"):
                    # Handle descriptive responses - find the JSON part
                    lines = response.split('\n')
                    json_started = False
                    json_lines = []
                    for line in lines:
                        if line.strip().startswith('{'):
                            json_started = True
                        if json_started:
                            json_lines.append(line)
                            if line.strip().endswith('}') and line.count('}') >= line.count('{'):
                                break
                    response = '\n'.join(json_lines).strip()

                # Final cleanup
                response = response.strip()

                parsed = json.loads(response)

                # Validate required fields
                if "error" in parsed:
                    return parsed

                # Check for required fields based on type
                required_fields = ["result", "speech",
                                   "explanation", "original_question"]
                if not all(field in parsed for field in required_fields):
                    log_error(
                        f"Missing required fields in LLM response: {parsed}")
                    return {"error": "I couldn't understand that math problem completely. Can you try again?"}

                # Ensure result is numeric
                parsed["result"] = float(parsed["result"]) if isinstance(
                    parsed["result"], str) else parsed["result"]

                # Set default values for missing fields
                parsed.setdefault("is_basic", False)
                parsed.setdefault("type", "complex")
                parsed.setdefault("steps", [])

                # Validate complex math has proper structure
                if parsed.get("type") == "complex" and not parsed.get("steps"):
                    # Try to create basic steps from the problem
                    parsed["steps"] = [{"step": 1, "operation": utterance,
                                        "result": parsed["result"], "description": "Calculate the result"}]

                log_info(
                    f"Parsed math: {parsed.get('type', 'unknown')} type, result = {parsed['result']}")
                return parsed

            except json.JSONDecodeError as e:
                log_error(f"Invalid JSON from LLM: {response}")
                return {"error": "I had trouble understanding that. Can you ask your math question again?"}

        except Exception as e:
            log_error(f"Math parsing error: {e}")
            return {"error": "I couldn't understand that math question. Please try again."}

    def is_basic_math_problem(self, parsed: Dict[str, Any]) -> bool:
        """
        Determine if this is a basic math problem suitable for finger counting.
        """
        try:
            # Check explicit is_basic flag first
            if "is_basic" in parsed:
                return parsed["is_basic"]

            # For simple operations, check if all values are in 0-10 range
            if parsed.get("type") == "simple":
                A, B, result = parsed.get("A"), parsed.get(
                    "B"), parsed.get("result")
                if (A is not None and B is not None and result is not None):
                    if (isinstance(A, (int, float)) and isinstance(B, (int, float)) and isinstance(result, (int, float)) and
                        A == int(A) and B == int(B) and result == int(result) and
                            0 <= A <= 10 and 0 <= B <= 10 and 0 <= result <= 10):
                        return True

            # Complex problems are never basic (multi-step, word problems, etc.)
            return False

        except Exception as e:
            log_warning(f"Error determining if basic math: {e}")
            return False

    async def handle_basic_math(self, parsed: Dict[str, Any], user_input: str) -> Dict[str, Any]:
        """
        Handle basic math problems with natural finger visualization.
        """
        try:
            log_info(f"Handling basic math with human-like finger counting")

            A, B, op, result = int(parsed["A"]), int(
                parsed["B"]), parsed["OP"], int(parsed["result"])
            speech = parsed["speech"]
            explanation = parsed["explanation"]

            # Send math result to UI for visualization
            await self.socket_server.broadcast({
                "type": "math_result",
                "A": A,
                "B": B,
                "OP": op,
                "result": result,
                "explanation": explanation,
                "mode": "finger_counting",
                "original_question": user_input
            })

            # FIXED: Execute the corrected finger sequence with proper timing
            await self.execute_corrected_finger_sequence(A, B, op, result, speech, explanation)

            # Add to context if available
            if self.context_manager:
                await self.context_manager.add_message("user", user_input)
                await self.context_manager.add_message("assistant", f"{speech} {explanation}")

            return {
                "success": True,
                "mode": "finger_counting",
                "result": result,
                "explanation": explanation
            }

        except Exception as e:
            log_error(f"Error handling basic math: {e}")
            return await self.handle_error("I had trouble showing that with my fingers.")

    async def execute_corrected_finger_sequence(self, A: int, B: int, op: str, result: int, speech: str, explanation: str):
        """
        FIXED: Execute the corrected sequence with proper speech-then-actuation order and natural timing.
        """
        try:
            log_info(
                f"Executing corrected finger sequence: {A} {op} {B} = {result}")

            # Step 1: Speak operand A, then show it on fingers
            await self.socket_server.emit_state_change("show_operand_a")
            await self.tts_engine.speak_text(str(A))  # FIXED: Speak first
            await asyncio.sleep(0.05)  # Minimal pause
            await self.show_number_naturally(A, "right")  # FIXED: Then actuate
            await asyncio.sleep(0.1)  # Quick pause

            # Step 2: Speak operation
            op_speech = {
                "+": "plus",
                "-": "minus",
                "*": "times",
                "/": "divided by"
            }.get(op, op)

            await self.tts_engine.speak_text(op_speech)
            await asyncio.sleep(0.05)  # Minimal pause

            # Step 3: Speak operand B, then show it on fingers
            await self.socket_server.emit_state_change("show_operand_b")
            await self.tts_engine.speak_text(str(B))  # FIXED: Speak first
            await asyncio.sleep(0.05)  # Minimal pause
            await self.show_number_naturally(B, "left")  # FIXED: Then actuate
            await asyncio.sleep(0.1)  # Quick pause

            # Step 4: Speak "equals"
            await self.tts_engine.speak_text("equals")
            await asyncio.sleep(0.05)  # Minimal pause

            # Step 5: Speak result, then show it naturally
            await self.socket_server.emit_state_change("show_result")
            await self.tts_engine.speak_text(str(result))  # FIXED: Speak first
            await asyncio.sleep(0.05)  # Minimal pause
            # FIXED: Then actuate
            await self.show_result_naturally(A, B, result)

            # Step 6: Brief pause, then speak explanation
            await asyncio.sleep(0.15)  # Quick pause
            await self.socket_server.emit_state_change("speaking")
            await self.tts_engine.speak_text(explanation)

            # Hold result for a moment
            await asyncio.sleep(0.8)  # Shorter hold time

            # Step 7: Close all fingers after math session
            await self.close_all_fingers_naturally()

            await self.socket_server.emit_state_change("math_gesture_active")

        except Exception as e:
            log_error(f"Error in corrected finger sequence: {e}")
            # Ensure fingers are in safe state on error
            await self.close_all_fingers_naturally()
            await self.socket_server.emit_state_change("math_gesture_active")

    async def handle_advanced_math(self, parsed: Dict[str, Any], user_input: str) -> Dict[str, Any]:
        """
        Handle advanced math problems with dynamic UI visualization and step-by-step explanation.
        """
        try:
            log_info(f"Handling advanced math problem")

            speech = parsed["speech"]
            explanation = parsed["explanation"]
            result = parsed["result"]
            steps = parsed.get("steps", [])
            breakdown = parsed.get("breakdown", "")
            math_type = parsed.get("type", "complex")

            # Send advanced math result to UI with step-by-step data
            await self.socket_server.broadcast({
                "type": "math_result",
                "result": result,
                "explanation": explanation,
                "mode": "advanced",
                "original_question": user_input,
                "speech": speech,
                "steps": steps,
                "breakdown": breakdown,
                "math_type": math_type,
                "timestamp": datetime.now().isoformat()
            })

            # For multi-step problems, speak through the steps
            if steps and len(steps) > 1:
                await self.speak_step_by_step_solution(steps, result, explanation)
            else:
                # Single step or direct answer
                await self.socket_server.emit_state_change("speaking")
                full_response = f"{speech}. {explanation}"
                await self.tts_engine.speak_text(full_response)

            # Add to context if available
            if self.context_manager:
                context_response = f"{speech}. {explanation}"
                if breakdown:
                    context_response += f" The calculation was: {breakdown}"
                await self.context_manager.add_message("user", user_input)
                await self.context_manager.add_message("assistant", context_response)

            await self.socket_server.emit_state_change("math_gesture_active")

            return {
                "success": True,
                "mode": "advanced",
                "result": result,
                "explanation": explanation,
                "steps": steps,
                "math_type": math_type
            }

        except Exception as e:
            log_error(f"Error handling advanced math: {e}")
            return await self.handle_error("I had trouble solving that problem.")

    async def speak_step_by_step_solution(self, steps: List[Dict], final_result: Any, explanation: str):
        """
        Speak through a step-by-step solution for complex math problems.
        FIXED: Improved timing for step-by-step explanations.
        """
        try:
            await self.socket_server.emit_state_change("explaining_steps")

            # Introduce the solution
            if len(steps) > 1:
                await self.tts_engine.speak_text("Let me work through this step by step.")
                await asyncio.sleep(0.1)  # Quick pause

            # Go through each step
            for i, step in enumerate(steps):
                step_num = step.get("step", i + 1)
                operation = step.get("operation", "")
                step_result = step.get("result", "")
                description = step.get("description", f"Step {step_num}")

                # Highlight current step in UI
                await self.socket_server.broadcast({
                    "type": "highlight_step",
                    "step_number": step_num,
                    "operation": operation,
                    "result": step_result
                })

                # Speak the step
                step_text = f"Step {step_num}: {description}. That gives us {step_result}."
                await self.tts_engine.speak_text(step_text)
                await asyncio.sleep(0.2)  # Quick pause between steps

            # Conclude with final answer
            await self.socket_server.emit_state_change("speaking")
            final_text = f"So the final answer is {final_result}. {explanation}"
            await self.tts_engine.speak_text(final_text)

        except Exception as e:
            log_error(f"Error speaking step-by-step solution: {e}")
            # Fallback to simple speech
            await self.socket_server.emit_state_change("speaking")
            fallback_text = f"The answer is {final_result}. {explanation}"
            await self.tts_engine.speak_text(fallback_text)

    async def show_number_naturally(self, number: int, hand: str):
        """
        Show number with natural finger transitions (only open needed fingers).
        Always follows natural counting order: index → middle → ring → pinky → thumb
        """
        try:
            if not 0 <= number <= 5:
                log_warning(
                    f"Number {number} out of range for single hand display")
                return False

            log_info(
                f"Showing {number} naturally on {hand} hand (index→middle→ring→pinky→thumb)")

            # Natural counting order: index, middle, ring, pinky, thumb
            finger_names = ["index", "majeure", "ringfinger", "pinky", "thumb"]
            current_state = self.current_finger_state[hand]

            # Calculate target state following natural counting order
            target_state = [0, 0, 0, 0, 0]  # Start with all closed
            for i in range(number):
                # Open fingers in order: 0=index, 1=middle, 2=ring, 3=pinky, 4=thumb
                target_state[i] = 1

            # Only move fingers that need to change, in natural order
            changes_made = False

            # First pass: Open fingers that need to be opened (in counting order)
            for i in range(5):
                if target_state[i] == 1 and current_state[i] == 0:  # Need to open
                    if self.finger_controller:
                        await self.finger_controller.move_finger_smooth(hand, finger_names[i], "open", 200)

                    current_state[i] = 1
                    changes_made = True
                    # Minimal delay for snappy movement
                    await asyncio.sleep(0.02)

            # Second pass: Close fingers that need to be closed (in reverse order for natural look)
            for i in range(4, -1, -1):  # Reverse order: thumb → pinky → ring → middle → index
                if target_state[i] == 0 and current_state[i] == 1:  # Need to close
                    if self.finger_controller:
                        await self.finger_controller.move_finger_smooth(hand, finger_names[i], "closed", 200)

                    current_state[i] = 0
                    changes_made = True
                    # Minimal delay for snappy movement
                    await asyncio.sleep(0.02)

            # Update state tracking
            self.current_finger_state[hand] = current_state.copy()

            # Send to UI
            await self.send_current_state_to_ui()

            log_info(
                f"Naturally showed {number} on {hand} hand: {['closed' if x == 0 else 'open' for x in current_state]}")
            return True

        except Exception as e:
            log_error(f"Error showing number naturally: {e}")
            return False

    async def show_result_naturally(self, A: int, B: int, result: int):
        """
        Show result using smart finger transitions based on current state.
        """
        try:
            log_info(f"Showing result {result} naturally")

            if result == 0:
                # Close all fingers for zero
                await self.close_all_fingers_naturally()

            elif result <= 5:
                # Show on right hand, close left hand
                await self.show_number_naturally(0, "left")  # Close left
                await asyncio.sleep(0.1)  # FIXED: Reduced pause
                await self.show_result_on_right_hand(A, result)

            elif result <= 10:
                # Use both hands intelligently
                right_count = min(5, result)
                left_count = result - right_count

                # Smart transition based on current state
                if self.current_finger_state["left"] != [0, 0, 0, 0, 0]:
                    # Adjust left hand first
                    await self.show_number_naturally(left_count, "left")
                    await asyncio.sleep(0.1)  # FIXED: Reduced pause

                # Then adjust right hand
                await self.show_number_naturally(right_count, "right")

            else:
                # Result > 10, show maximum (shouldn't happen in basic math)
                await self.show_number_naturally(5, "left")
                await self.show_number_naturally(5, "right")

        except Exception as e:
            log_error(f"Error showing result naturally: {e}")

    async def show_result_on_right_hand(self, current_right: int, target: int):
        """
        Show result on right hand by smartly transitioning from current state.
        Always follows natural counting order: index → middle → ring → pinky → thumb
        """
        try:
            current_open = sum(self.current_finger_state["right"])
            finger_names = ["index", "majeure", "ringfinger", "pinky", "thumb"]

            if target > current_open:
                # Need to open more fingers in natural counting order
                fingers_to_open = target - current_open

                for i in range(5):
                    if fingers_to_open <= 0:
                        break
                    # Finger is closed
                    if self.current_finger_state["right"][i] == 0:
                        if self.finger_controller:
                            await self.finger_controller.move_finger_smooth("right", finger_names[i], "open", 200)
                        self.current_finger_state["right"][i] = 1
                        fingers_to_open -= 1
                        await asyncio.sleep(0.05)  # FIXED: Reduced delay

            elif target < current_open:
                # Need to close some fingers in reverse order (thumb → pinky → ring → middle → index)
                fingers_to_close = current_open - target

                for i in range(4, -1, -1):  # Reverse order
                    if fingers_to_close <= 0:
                        break
                    # Finger is open
                    if self.current_finger_state["right"][i] == 1:
                        if self.finger_controller:
                            await self.finger_controller.move_finger_smooth("right", finger_names[i], "closed", 200)
                        self.current_finger_state["right"][i] = 0
                        fingers_to_close -= 1
                        await asyncio.sleep(0.05)  # FIXED: Reduced delay

            # Send updated state to UI
            await self.send_current_state_to_ui()

            log_info(
                f"Right hand showing {target}: {['closed' if x == 0 else 'open' for x in self.current_finger_state['right']]}")

        except Exception as e:
            log_error(f"Error showing result on right hand: {e}")

    async def close_all_fingers_naturally(self):
        """
        Close all fingers naturally (only close open fingers).
        """
        try:
            log_info("Closing all fingers naturally")

            finger_names = ["index", "majeure", "ringfinger", "pinky", "thumb"]

            # Close fingers on both hands
            for hand in ["left", "right"]:
                for i in range(5):
                    # Only close open fingers
                    if self.current_finger_state[hand][i] == 1:
                        if self.finger_controller:
                            await self.finger_controller.move_finger_smooth(hand, finger_names[i], "closed", 150)
                        self.current_finger_state[hand][i] = 0
                        await asyncio.sleep(0.03)  # FIXED: Much faster closing

            # Send updated state to UI
            await self.send_current_state_to_ui()

        except Exception as e:
            log_error(f"Error closing fingers naturally: {e}")

    async def send_current_state_to_ui(self):
        """Send current finger state to UI."""
        try:
            await self.socket_server.broadcast({
                "type": "finger_pose",
                "pose": self.current_finger_state.copy(),
                "timestamp": datetime.now().timestamp(),
                "context": "current_state"
            })
        except Exception as e:
            log_error(f"Error sending state to UI: {e}")

    async def send_finger_pose_to_ui(self, command: str, pose_data: Dict = None):
        """
        Send finger pose to UI for visualization.
        """
        try:
            if command == "clear":
                pose = {"left": [0, 0, 0, 0, 0], "right": [0, 0, 0, 0, 0]}
            elif command == "custom" and pose_data:
                pose = pose_data
            else:
                log_warning(f"Unknown finger pose command: {command}")
                return

            await self.socket_server.broadcast({
                "type": "finger_pose",
                "pose": pose,
                "timestamp": datetime.now().timestamp(),
                "context": command
            })

        except Exception as e:
            log_error(f"Error sending finger pose to UI: {e}")

    async def handle_error(self, error_message: str) -> Dict[str, Any]:
        """Handle errors with user-friendly responses and finger safety."""
        try:
            # Safely close fingers on error
            await self.close_all_fingers_naturally()

            await self.socket_server.emit_error(error_message)
            await self.socket_server.emit_state_change("speaking")
            await self.tts_engine.speak_text(error_message)
            await self.socket_server.emit_state_change("math_gesture_active")

            return {
                "success": False,
                "error": error_message
            }
        except Exception as e:
            log_error(f"Error handling error: {e}")
            return {"success": False, "error": "Something went wrong."}

    async def query_groq(self, system_prompt: str, user_prompt: str) -> str:
        """Query Groq LLM."""
        try:
            completion = self.groq_client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,  # Low temperature for consistent parsing
                max_tokens=1024  # Increased for complex responses
            )
            return completion.choices[0].message.content.strip()

        except Exception as e:
            log_error(f"Groq query error: {e}")
            raise

    async def query_ollama(self, system_prompt: str, user_prompt: str) -> str:
        """Query Ollama LLM."""
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:11434/api/generate",
                    json={
                        "model": self.model_name,
                        "prompt": f"System: {system_prompt}\n\nUser: {user_prompt}",
                        "stream": False,
                        "options": {
                            "temperature": 0.1,
                            "num_predict": 1024  # Increased for complex responses
                        }
                    },
                    timeout=30.0
                )

                result = response.json()
                return result["response"].strip()

        except Exception as e:
            log_error(f"Ollama query error: {e}")
            raise


# Factory function for easy integration
async def create_math_handler(tts_engine, socket_server, context_manager=None, finger_controller=None):
    """Factory function to create math handler instance with finger controller."""
    return MathGestureHandler(tts_engine, socket_server, context_manager, finger_controller)
