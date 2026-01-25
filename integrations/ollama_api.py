"""
Ollama API integration for Maxi AI
Handles communication with the local Ollama server
"""

import asyncio
import aiohttp
import json
from typing import AsyncGenerator, Dict, List, Optional

from utils.logger import log_info, log_error


class OllamaAPI:
    def __init__(self, base_url: str = "http://localhost:11434"):
        """
        Initialize Ollama API client.

        Args:
            base_url: URL of the Ollama server (default: http://localhost:11434)
        """
        self.base_url = base_url
        self.session = None
        self.timeout = aiohttp.ClientTimeout(total=300)  # 5 minute timeout

    async def connect(self):
        """Initialize the HTTP session."""
        if not self.session:
            self.session = aiohttp.ClientSession(timeout=self.timeout)
            log_info("🔗 Connected to Ollama API")

    async def close(self):
        """Close the HTTP session."""
        if self.session:
            await self.session.close()
            self.session = None
            log_info("🔌 Disconnected from Ollama API")

    async def prewarm_model(self, model: str = "maxi-phi3") -> bool:
        """
        Prewarm the model by sending a simple prompt.

        Args:
            model: Model name to prewarm

        Returns:
            bool: True if prewarm succeeded, False otherwise
        """
        try:
            if not self.session:
                await self.connect()

            url = f"{self.base_url}/api/generate"
            payload = {
                "model": model,
                "prompt": "Hello",
                "stream": False
            }

            async with self.session.post(url, json=payload) as response:
                if response.status == 200:
                    log_info(f"Successfully prewarmed model: {model}")
                    return True
                else:
                    error = await response.text()
                    log_error(f"Failed to prewarm model: {error}")
                    return False

        except Exception as e:
            log_error(f"Error prewarming model: {e}")
            return False

    async def list_models(self) -> Optional[List[str]]:
        """
        List available models from Ollama.

        Returns:
            List of available model names or None if failed
        """
        try:
            if not self.session:
                await self.connect()

            url = f"{self.base_url}/api/tags"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return [model['name'] for model in data.get('models', [])]
                return None

        except Exception as e:
            log_error(f"Error listing models: {e}")
            return None

    async def generate_response(
        self,
        model: str,
        prompt: str,
        context: List[Dict[str, str]]
    ) -> AsyncGenerator[str, None]:
        """
        Generate a streaming response from Ollama.

        Args:
            model: The model to use (e.g., 'maxi-phi3')
            prompt: User's input prompt
            context: Conversation history with system prompt

        Yields:
            Response chunks from Ollama
        """
        if not self.session:
            await self.connect()

        # Add the current user prompt to context
        messages = context + [{"role": "user", "content": prompt}]

        url = f"{self.base_url}/api/chat"
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": 0.7,
                "top_p": 0.9,
                "num_predict": 150,  # Increased for slightly longer responses
                "stop": ["<|end|>", "<|assistant|>", "<|user|>", "\n\n"]
            }
        }

        try:
            log_info(f"🤖 Sending request to Ollama model: {model}")

            async with self.session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    log_error(
                        f"❌ Ollama API error {response.status}: {error_text}")
                    yield "Sorry, I'm having trouble thinking right now."
                    return

                # Process streaming response
                buffer = ""
                async for chunk in response.content:
                    if not chunk:
                        continue

                    # Decode and buffer chunks
                    buffer += chunk.decode('utf-8')

                    # Process complete JSON lines
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        if not line.strip():
                            continue

                        try:
                            data = json.loads(line)

                            # Check if response is complete
                            if data.get('done', False):
                                log_info("✅ Ollama response completed")
                                return

                            # Extract content from message
                            if 'message' in data and 'content' in data['message']:
                                content = data['message']['content']
                                if content:  # Only yield non-empty content
                                    yield content

                        except json.JSONDecodeError as e:
                            log_error(f"⚠️ Failed to decode JSON chunk: {e}")
                            continue

        except aiohttp.ClientError as e:
            log_error(f"❌ HTTP client error: {e}")
            yield "Sorry, I lost connection to my brain. Can you try again?"

        except asyncio.TimeoutError:
            log_error("⏰ Request timeout")
            yield "Sorry, I'm thinking too slowly. Can you ask again?"

        except Exception as e:
            log_error(f"❌ Unexpected error in Ollama generation: {e}")
            yield "Sorry, something went wrong in my thinking process."
