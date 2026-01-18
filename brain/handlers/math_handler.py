# handlers/math_handler.py
"""
Math handler for Maxi AI.
Processes and solves basic mathematical problems with LLM fallback.
"""

import re
import random
from word2number import w2n
from ui.socket_server import SocketServer
from voice.speaker import SmoothTTSEngine
from utils.logger import log_info, log_error
from brain.context_manager.context_manager import context_manager

def text_to_number(text):
    try:
        return w2n.word_to_num(text)
    except Exception:
        return None

def extract_math_problem(text: str):
    text = (
        text.lower()
        .replace("dollars", "")
        .replace("dollar", "")
        .replace("naira", "")
        .replace("₦", "")
        .strip()
    )

    # Word-based multi-step support (add A and B then divide by C)
    multi_step_match = re.search(r'add\s+([a-z\s\-\d]+)\s+and\s+([a-z\s\-\d]+)\s+then\s+divide\s+by\s+([a-z\s\-\d]+)', text)
    if multi_step_match:
        a = text_to_number(multi_step_match.group(1))
        b = text_to_number(multi_step_match.group(2))
        c = text_to_number(multi_step_match.group(3))
        if a is not None and b is not None and c is not None and c != 0:
            total = a + b
            return '/', total, c

    # Word-based expression
    word_expr = re.search(r'(what\s+is\s+)?([a-z\s\-\d]+)\s+(plus|minus|times|divided by|multiplied by|over|add|subtract|multiply|divide|greater than|less than|equals|equal to|is)\s+([a-z\s\-\d]+)', text)
    if word_expr:
        num1 = text_to_number(word_expr.group(2))
        op_word = word_expr.group(3)
        num2 = text_to_number(word_expr.group(4))
        if num1 is not None and num2 is not None:
            op_map = {
                'plus': '+', 'add': '+',
                'minus': '-', 'subtract': '-',
                'times': '*', 'multiply': '*', 'multiplied by': '*',
                'divided by': '/', 'divide': '/', 'over': '/',
                'greater than': '>', 'less than': '<', 'equals': '=', 'equal to': '=', 'is': '='
            }
            return op_map.get(op_word), num1, num2

    # Numeric pattern
    direct_pattern = r'(\d+)\s*([\+\-\*/x><=])\s*(\d+)'
    direct_match = re.search(direct_pattern, text)
    if direct_match:
        num1 = int(direct_match.group(1))
        op = direct_match.group(2)
        num2 = int(direct_match.group(3))
        if op == 'x':
            op = '*'
        return op, num1, num2

    return None

def solve_math_problem(operation: str, num1: int, num2: int):
    try:
        if operation == '+':
            return num1 + num2
        elif operation == '-':
            return num1 - num2
        elif operation == '*':
            return num1 * num2
        elif operation == '/':
            if num2 == 0:
                return None
            if num1 % num2 == 0:
                return num1 / num2
            else:
                return (num1 // num2, num1 % num2)
        elif operation == '>':
            return f"Yes, {num1} is greater than {num2}" if num1 > num2 else f"No, {num1} is not greater than {num2}"
        elif operation == '<':
            return f"Yes, {num1} is less than {num2}" if num1 < num2 else f"No, {num1} is not less than {num2}"
        elif operation == '=':
            return f"Yes, {num1} is equal to {num2}" if num1 == num2 else f"No, {num1} is not equal to {num2}"
        else:
            return None
    except Exception:
        return None

def create_math_response(operation: str, num1: int, num2: int, result) -> str:
    op_names = {
        '+': 'plus',
        '-': 'minus',
        '*': 'times',
        '/': 'divided by',
        '>': 'greater than',
        '<': 'less than',
        '=': 'equal to'
    }

    op_name = op_names.get(operation, operation)

    if operation == '/' and isinstance(result, tuple):
        quotient, remainder = result
        if remainder == 0:
            return f"When you divide {num1} by {num2}, you get {quotient}. That's as clean as slicing cake!"
        else:
            return f"If you divide {num1} by {num2}, you get {quotient} with {remainder} leftover. Like sharing sweets and still having some in your pocket!"
    elif isinstance(result, str):
        return result

    fun_responses = [
        f"{num1} {op_name} {num2} equals {result}. Easy peasy lemon squeezy!",
        f"The answer is {result}! Just like counting your favorite toys!",
        f"{num1} {op_name} {num2} is {result}. You're getting sharper than a pencil!",
        f"That's {result}! Like having {result} biscuits in your lunchbox!",
        f"{result} is correct! Maxi is proud of your smart brain!",
        f"Zing! {num1} {op_name} {num2} makes {result}. Like magic math!",
        f"If we put {num1} and {num2} together with {op_name}, we get {result}! Isn't math fun?",
        f"Ding ding! Answer is {result}. That's what a genius like you gets!"
    ]

    return random.choice(fun_responses)

async def handle_math(prompt: str, tts_engine: SmoothTTSEngine, socket: SocketServer):
    """
    Handle math questions by always using LLM (Groq) instead of regex parser.
    This ensures accurate answers for ALL types of math questions including word problems.
    
    Returns None to indicate LLM should handle the question (no longer tries regex parsing).
    """
    log_info(f"🔢 Math question detected: {prompt}")
    log_info("📚 Passing to LLM for accurate math reasoning (no regex parser)")
    
    # Always return None to let LLM handle it
    # LLM is much better at math reasoning than regex patterns
    return None