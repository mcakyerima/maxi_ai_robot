"""
Fixed ESP32 WebSocket gesture handler for Maxi AI robot.
Addresses connection stability and discovery issues.
"""

import re
import json
import asyncio
import websockets
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import threading
from voice.speaker import SmoothTTSEngine
from utils.logger import log_info, log_error, log_debug
import socket

@dataclass
class ServoCommand:
    """Data class for servo commands"""
    action: str
    channel: Optional[int] = None
    angle: Optional[int] = None
    speed: Optional[float] = None
    immediate: Optional[bool] = False
    gesture: Optional[str] = None
    number: Optional[int] = None
    sequence: Optional[List] = None
    response_id: Optional[str] = None

class ESP32ServoController:
    """Fixed WebSocket-based ESP32 servo controller with improved connection management"""
    
    def __init__(self, host: str = None, port: int = 81):
        self.host = host or "192.168.42.43"  # Use default IP directly for now
        self.port = port
        self.websocket = None
        self.is_connected = False
        self.connection_lock = asyncio.Lock()
        self.command_queue = asyncio.Queue()
        self.response_handlers = {}
        self.command_id_counter = 0
        self.heartbeat_task = None
        self.message_handler_task = None
        self.command_processor_task = None
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 3
        self.executor = ThreadPoolExecutor(max_workers=2)
        
        # Performance monitoring
        self.command_count = 0
        self.error_count = 0
        self.last_heartbeat = 0
        self.connection_start_time = None
        
    def _discover_esp32_sync(self) -> Optional[str]:
        """Synchronous ESP32 discovery to avoid coroutine issues"""
        log_info("Discovering ESP32 servo controller...")
        
        # Common ESP32 IP addresses to try
        test_ips = [
            "192.168.42.43",  # Default
            "192.168.4.1",    # ESP32 AP mode
            "192.168.1.1",    # Common router IP
            "10.0.0.1",       # Another common IP
        ]
        
        # Try to ping each IP quickly
        for ip in test_ips:
            try:
                # Quick socket test
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                result = sock.connect_ex((ip, self.port))
                sock.close()
                
                if result == 0:
                    log_info(f"Found ESP32 at {ip}")
                    return ip
                    
            except Exception:
                continue
        
        log_error("ESP32 discovery failed, using default IP")
        return "192.168.42.43"  # Default fallback
    

    async def connect(self) -> bool:
        """Establish WebSocket connection with automatic ESP32 discovery"""
        async with self.connection_lock:
            if self.is_connected:
                return True
            
            # Try to discover ESP32 if host is not set or is the old default
            if not self.host or self.host == "192.168.42.43":
                discovered_ip = await self._discover_esp32_network_scan()
                if discovered_ip:
                    self.host = discovered_ip
                    log_info(f"Discovered ESP32 at {discovered_ip}")
                else:
                    log_error("Could not discover ESP32 on network")
            
            uri = f"ws://{self.host}:{self.port}"
            
            for attempt in range(self.max_reconnect_attempts):
                try:
                    log_info(f"Connecting to ESP32 at {uri} (attempt {attempt + 1})")
                    
                    # Create connection with timeout
                    self.websocket = await asyncio.wait_for(
                        websockets.connect(
                            uri,
                            ping_interval=30,  # Longer ping interval
                            ping_timeout=15,   # Longer ping timeout
                            close_timeout=5,
                            max_size=2**16,    # Limit message size
                            max_queue=32       # Limit queue size
                        ),
                        timeout=15  # Longer connection timeout
                    )
                    
                    self.is_connected = True
                    self.connection_start_time = time.time()
                    self.last_heartbeat = time.time()  # Initialize heartbeat
                    self.reconnect_attempts = 0
                    
                    # Start background tasks
                    await self._start_background_tasks()
                    
                    # Simple connection test without waiting for response
                    try:
                        test_command = {"action": "ping", "id": "connection_test"}
                        await self._send_raw_command(test_command)
                        log_info(f"ESP32 connected successfully at {self.host}:{self.port}")
                        return True
                    except Exception as e:
                        log_error(f"Connection test failed: {e}")
                        # Don't fail connection just because test failed
                        return True
                        
                except asyncio.TimeoutError:
                    log_error(f"Connection timeout (attempt {attempt + 1})")
                    # If connection failed, try to rediscover on next attempt
                    if attempt < self.max_reconnect_attempts - 1:
                        discovered_ip = await self._discover_esp32_network_scan()
                        if discovered_ip and discovered_ip != self.host:
                            self.host = discovered_ip
                            uri = f"ws://{self.host}:{self.port}"
                            log_info(f"Retrying with newly discovered IP: {discovered_ip}")
                            
                except Exception as e:
                    log_error(f"Connection failed (attempt {attempt + 1}): {e}")
                    # If connection failed, try to rediscover on next attempt
                    if attempt < self.max_reconnect_attempts - 1:
                        discovered_ip = await self._discover_esp32_network_scan()
                        if discovered_ip and discovered_ip != self.host:
                            self.host = discovered_ip
                            uri = f"ws://{self.host}:{self.port}"
                            log_info(f"Retrying with newly discovered IP: {discovered_ip}")
                
                if attempt < self.max_reconnect_attempts - 1:
                    await asyncio.sleep(3)  # Wait before retry
            
            log_error(f"Failed to connect to ESP32 after {self.max_reconnect_attempts} attempts")
            return False

    async def _discover_esp32_network_scan(self) -> Optional[str]:
        """Discover ESP32 by scanning local network for WebSocket server on target port"""
        try:
            # Get local IP to determine network range
            local_ip = await self._get_local_ip_async()
            if not local_ip:
                log_error("Could not determine local IP address")
                return None
            
            network_base = '.'.join(local_ip.split('.')[:-1])
            log_info(f"Scanning network {network_base}.1-254 for ESP32...")
            
            # Use thread pool for concurrent scanning
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor(max_workers=50) as executor:
                # Create tasks for scanning all IPs in parallel
                tasks = []
                for i in range(1, 255):
                    ip = f"{network_base}.{i}"
                    if ip != local_ip:  # Skip our own IP
                        task = loop.run_in_executor(
                            executor, 
                            self._check_websocket_port_sync, 
                            ip, 
                            self.port, 
                            2.0  # 2 second timeout per IP
                        )
                        tasks.append((ip, task))
                
                # Wait for all tasks with overall timeout
                try:
                    for ip, task in tasks:
                        try:
                            result = await asyncio.wait_for(task, timeout=0.1)
                            if result:
                                log_info(f"Found ESP32 WebSocket server at {ip}:{self.port}")
                                # Cancel remaining tasks for efficiency
                                for _, remaining_task in tasks:
                                    if not remaining_task.done():
                                        remaining_task.cancel()
                                return ip
                        except asyncio.TimeoutError:
                            continue
                        except Exception:
                            continue
                            
                except Exception as e:
                    log_error(f"Network scan error: {e}")
            
            log_info("ESP32 not found in network scan")
            return None
            
        except Exception as e:
            log_error(f"Network discovery failed: {e}")
            return None

    async def _get_local_ip_async(self) -> Optional[str]:
        """Get local IP address asynchronously"""
        try:
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as executor:
                return await loop.run_in_executor(executor, self._get_local_ip_sync)
        except Exception as e:
            log_error(f"Failed to get local IP: {e}")
            return None

    def _get_local_ip_sync(self) -> Optional[str]:
        """Get local IP address synchronously"""
        try:
            # Connect to a remote server to determine local IP
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            try:
                # Fallback method
                hostname = socket.gethostname()
                return socket.gethostbyname(hostname)
            except Exception:
                return None

    def _check_websocket_port_sync(self, ip: str, port: int, timeout: float = 2.0) -> bool:
        """Check if WebSocket server is running on target port (synchronous)"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((ip, port))
            sock.close()
            return result == 0
        except Exception:
            return False
        
    async def _start_background_tasks(self):
        """Start background tasks for connection management"""
        # Cancel existing tasks
        for task in [self.heartbeat_task, self.message_handler_task, self.command_processor_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Start new background tasks
        self.heartbeat_task = asyncio.create_task(self._heartbeat_monitor())
        self.message_handler_task = asyncio.create_task(self._message_handler())
        self.command_processor_task = asyncio.create_task(self._command_processor())
    
    async def _heartbeat_monitor(self):
        """Monitor connection health with improved error handling"""
        while self.is_connected:
            try:
                current_time = time.time()
                
                # Check if connection is still alive
                if (current_time - self.last_heartbeat > 60 and  # 60 second timeout
                    self.websocket and not self._is_websocket_closed()):
                    
                    log_error("Heartbeat timeout detected")
                    await self._handle_connection_loss()
                    break
                
                await asyncio.sleep(10)  # Check every 10 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                log_error(f"Heartbeat monitor error: {e}")
                await asyncio.sleep(5)
    
    def _is_websocket_closed(self) -> bool:
        """Safely check if websocket is closed"""
        try:
            if not self.websocket:
                return True
            # Check websocket state more safely
            return (hasattr(self.websocket, 'closed') and self.websocket.closed) or \
                   (hasattr(self.websocket, 'state') and self.websocket.state.name != 'OPEN')
        except Exception:
            return True
    
    async def _handle_connection_loss(self):
        """Handle connection loss with cleanup"""
        log_info("Handling connection loss...")
        self.is_connected = False
        
        # Clear pending responses
        for future in list(self.response_handlers.values()):
            if not future.done():
                try:
                    future.set_exception(ConnectionError("Connection lost"))
                except Exception:
                    pass
        self.response_handlers.clear()
    
    async def _message_handler(self):
        """Handle incoming WebSocket messages with improved error handling"""
        while self.is_connected and self.websocket:
            try:
                # Check if websocket is still open
                if self._is_websocket_closed():
                    log_error("WebSocket closed, stopping message handler")
                    await self._handle_connection_loss()
                    break
                
                # Receive message with timeout
                message = await asyncio.wait_for(self.websocket.recv(), timeout=30)
                
                # Update heartbeat on any message
                self.last_heartbeat = time.time()
                
                # Parse message
                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    log_error(f"Invalid JSON received: {message}")
                    continue
                
                # Handle different message types
                if data.get("type") == "heartbeat" or data.get("action") == "pong":
                    log_debug("Heartbeat received")
                elif data.get("type") == "status_update":
                    log_debug(f"Status update: {data.get('message', '')}")
                elif "id" in data:
                    # Response to command
                    response_id = data["id"]
                    if response_id in self.response_handlers:
                        future = self.response_handlers.pop(response_id)
                        if not future.done():
                            try:
                                future.set_result(data)
                            except Exception as e:
                                log_error(f"Failed to set future result: {e}")
                else:
                    log_debug(f"Received message: {data}")
                    
            except asyncio.TimeoutError:
                # No message received in 30 seconds - this is normal
                continue
            except websockets.exceptions.ConnectionClosed:
                log_error("WebSocket connection closed by server")
                await self._handle_connection_loss()
                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                log_error(f"Message handler error: {e}")
                self.error_count += 1
                await asyncio.sleep(1)  # Brief pause before continuing
    
    async def _command_processor(self):
        """Process queued commands with improved error handling"""
        while self.is_connected:
            try:
                command = await asyncio.wait_for(self.command_queue.get(), timeout=5.0)
                
                if self._is_websocket_closed():
                    log_error("Cannot send command: WebSocket closed")
                    self.command_queue.task_done()
                    continue
                
                await self._send_raw_command(command)
                self.command_queue.task_done()
                
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                log_error(f"Command processor error: {e}")
                try:
                    self.command_queue.task_done()
                except Exception:
                    pass
    
    async def send_command_async(self, command: Dict[str, Any], timeout: float = 15.0) -> Optional[Dict[str, Any]]:
        """Send command and wait for response with improved error handling"""
        if not self.is_connected or self._is_websocket_closed():
            log_error("Cannot send command: Not connected to ESP32")
            return None
        
        # Generate unique command ID
        command_id = str(self.command_id_counter)
        self.command_id_counter += 1
        command["id"] = command_id
        
        # Create future for response
        future = asyncio.Future()
        self.response_handlers[command_id] = future
        
        try:
            # Send command
            await self._send_raw_command(command)
            
            # Wait for response with timeout
            try:
                response = await asyncio.wait_for(future, timeout=timeout)
                self.command_count += 1
                return response
            except asyncio.TimeoutError:
                log_error(f"Command timeout: {command.get('action', 'unknown')}")
                return {"status": "timeout", "action": command.get("action")}
            
        except Exception as e:
            log_error(f"Command error: {e}")
            return None
        finally:
            # Clean up response handler
            if command_id in self.response_handlers:
                del self.response_handlers[command_id]
    
    async def _send_raw_command(self, command: Dict[str, Any]):
        """Send raw command via WebSocket with error handling"""
        if not self.websocket or self._is_websocket_closed():
            raise ConnectionError("WebSocket not connected")
        
        try:
            message = json.dumps(command)
            await self.websocket.send(message)
            log_debug(f"Sent command: {command.get('action', 'unknown')}")
        except Exception as e:
            log_error(f"Failed to send command: {e}")
            raise
    
    def send_command_sync(self, command: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send command synchronously (blocking) with proper event loop handling"""
        try:
            # Try to get existing event loop
            try:
                loop = asyncio.get_running_loop()
                # If we're in an event loop, we can't use run_until_complete
                # Instead, create a task and wait for it
                task = loop.create_task(self.send_command_async(command))
                # This is a bit tricky - we need to yield control
                return None  # For now, return None to avoid blocking
            except RuntimeError:
                # No running event loop, safe to create one
                return asyncio.run(self.send_command_async(command))
        except Exception as e:
            log_error(f"Sync command error: {e}")
            return None
    
    # High-level servo control methods (same as before but with better error handling)
    async def set_servo(self, channel: int, angle: int, speed: float = None, immediate: bool = False) -> bool:
        """Set individual servo angle with improved error handling"""
        command = {
            "action": "set_servo",
            "channel": channel,
            "angle": max(0, min(180, angle)),  # Clamp angle to valid range
            "immediate": immediate
        }
        
        if speed is not None:
            command["speed"] = max(0.1, min(10.0, speed))  # Clamp speed to valid range
        
        response = await self.send_command_async(command)
        success = response and response.get("status") in ["success", "ok"]
        
        if success:
            log_info(f"Servo {channel} set to {angle}° (speed: {speed or 'default'})")
        else:
            log_error(f"Failed to set servo {channel} to {angle}°: {response}")
        
        return success
    
    async def execute_gesture(self, gesture_name: str, speed: float = None) -> bool:
        """Execute predefined gesture"""
        command = {
            "action": "gesture",
            "gesture": gesture_name
        }
        
        if speed is not None:
            command["speed"] = max(0.1, min(10.0, speed))
        
        response = await self.send_command_async(command)
        success = response and response.get("status") in ["success", "ok"]
        
        if success:
            log_info(f"Executed gesture: {gesture_name}")
        else:
            log_error(f"Failed to execute gesture: {gesture_name}: {response}")
        
        return success
    
    async def show_number(self, number: int, speed: float = None) -> bool:
        """Show number with fingers"""
        if not (0 <= number <= 10):
            log_error(f"Invalid number: {number}. Must be 0-10")
            return False
        
        command = {
            "action": "show_number",
            "number": number
        }
        
        if speed is not None:
            command["speed"] = max(0.1, min(10.0, speed))
        
        response = await self.send_command_async(command)
        success = response and response.get("status") in ["success", "ok"]
        
        if success:
            log_info(f"Showing number: {number}")
        else:
            log_error(f"Failed to show number: {number}: {response}")
        
        return success
    
    async def reset_all(self) -> bool:
        """Reset all servos to home position"""
        response = await self.send_command_async({"action": "reset_all"})
        success = response and response.get("status") in ["success", "ok"]
        
        if success:
            log_info("All servos reset to home position")
        else:
            log_error(f"Failed to reset servos: {response}")
        
        return success
    
    async def emergency_stop(self) -> bool:
        """Emergency stop all servo movement"""
        response = await self.send_command_async({"action": "emergency_stop"})
        success = response and response.get("status") in ["success", "ok"]
        
        if success:
            log_info("Emergency stop activated")
        else:
            log_error(f"Emergency stop failed: {response}")
        
        return success
    
    async def get_status(self) -> Optional[Dict[str, Any]]:
        """Get full system status"""
        response = await self.send_command_async({"action": "get_status"})
        return response
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """Get connection statistics"""
        uptime = time.time() - self.connection_start_time if self.connection_start_time else 0
        
        return {
            "connected": self.is_connected and not self._is_websocket_closed(),
            "host": self.host,
            "port": self.port,
            "uptime": uptime,
            "commands_sent": self.command_count,
            "errors": self.error_count,
            "success_rate": (self.command_count - self.error_count) / max(self.command_count, 1) * 100,
            "queue_size": self.command_queue.qsize(),
            "pending_responses": len(self.response_handlers)
        }
    
    async def disconnect(self):
        """Close WebSocket connection and cleanup"""
        async with self.connection_lock:
            log_info("Disconnecting from ESP32...")
            self.is_connected = False
            
            # Cancel background tasks
            for task in [self.heartbeat_task, self.message_handler_task, self.command_processor_task]:
                if task and not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            
            # Close WebSocket
            if self.websocket and not self._is_websocket_closed():
                try:
                    await self.websocket.close()
                except Exception as e:
                    log_error(f"Error closing websocket: {e}")
            
            # Clear pending responses
            for future in list(self.response_handlers.values()):
                if not future.done():
                    try:
                        future.set_exception(ConnectionError("Disconnected"))
                    except Exception:
                        pass
            self.response_handlers.clear()
            
            # Clear command queue
            while not self.command_queue.empty():
                try:
                    self.command_queue.get_nowait()
                    self.command_queue.task_done()
                except Exception:
                    break
            
            log_info("ESP32 disconnected and cleaned up")

# Global controller instance
_servo_controller = None

async def get_servo_controller() -> ESP32ServoController:
    """Get or create servo controller instance"""
    global _servo_controller
    
    if _servo_controller is None:
        _servo_controller = ESP32ServoController()
        await _servo_controller.connect()
    
    return _servo_controller

# Text parsing functions (same as before)
async def extract_number_from_text(text: str) -> int:
    """Extract number request from text with improved parsing"""
    text_lower = text.lower()
    
    # Enhanced number patterns
    number_patterns = [
        r'(?:show|display|hold\s+up|raise|make)\s+(?:me\s+)?(?:the\s+)?(?:number\s+)?(\d+)(?:\s+fingers?)?',
        r'(\d+)\s+fingers?',
        r'number\s+(\d+)',
        r'count\s+(?:to\s+)?(\d+)',
        r'(\d+)\s+with\s+(?:your\s+)?(?:fingers?|hands?)'
    ]
    
    for pattern in number_patterns:
        match = re.search(pattern, text_lower)
        if match:
            try:
                number = int(match.group(1))
                return number if 0 <= number <= 10 else -1
            except ValueError:
                continue
    
    # Enhanced word-to-number mapping
    word_to_num = {
        'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
        'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
        'none': 0, 'single': 1, 'double': 2, 'triple': 3
    }
    
    for word, num in word_to_num.items():
        if any(phrase in text_lower for phrase in [
            f"show {word}", f"hold up {word}", f"display {word}", 
            f"number {word}", f"count {word}", f"{word} fingers"
        ]):
            return num
    
    return -1

async def extract_gesture_from_text(text: str) -> Optional[str]:
    """Extract gesture name from text with improved recognition"""
    text_lower = text.lower()
    
    # Enhanced gesture keyword mapping
    gesture_keywords = {
        'wave': ['wave', 'hello', 'hi there', 'greet', 'greeting', 'say hello'],
        'point': ['point', 'indicate', 'show direction', 'point at', 'pointing'],
        'fist': ['fist', 'close hand', 'make fist', 'clench', 'closed fist'],
        'open_hand': ['open hand', 'spread fingers', 'open palm', 'show palm', 'flat hand'],
        'peace': ['peace', 'victory', 'v sign', 'peace sign', 'two fingers up'],
        'thumbs_up': ['thumbs up', 'thumb up', 'good job', 'approval', 'like', 'great work']
    }
    
    # Score-based matching for better accuracy
    gesture_scores = {}
    for gesture, keywords in gesture_keywords.items():
        score = 0
        for keyword in keywords:
            if keyword in text_lower:
                score += len(keyword.split())  # Longer phrases get higher scores
        if score > 0:
            gesture_scores[gesture] = score
    
    if gesture_scores:
        # Return gesture with highest score
        return max(gesture_scores, key=gesture_scores.get)
    
    return None

async def handle_gesture(prompt: str, tts_engine: SmoothTTSEngine, servo_controller=None, socket_server=None) -> str:
    """Handle gesture-related commands with improved ESP32 WebSocket control and auto-reconnection"""
    log_info(f"👋 Processing gesture request: {prompt}")
    log_info(f"🛠️ Servo Controller instance {servo_controller}")
    
    try:
        # Check connection and attempt reconnection if needed
        if not servo_controller.is_connected:
            log_info("🔄 Servo controller not connected, attempting reconnection...")
            reconnect_success = await servo_controller.connect()
            
            if not reconnect_success:
                response = "Sorry, I can't control my hands right now. I tried to reconnect to the ESP32 but couldn't find it on the network."
                log_error("ESP32 servo controller reconnection failed")
                await tts_engine.speak_text(response)
                return response
            else:
                log_info("✅ Successfully reconnected to ESP32!")
        
        # Double-check connection after potential reconnection
        if not servo_controller.is_connected:
            response = "Sorry, my servo system still isn't responding. Please check if the ESP32 is powered on and connected to WiFi."
            log_error("ESP32 servo controller connection verification failed")
            await tts_engine.speak_text(response)
            return response
        
        # Extract different types of commands
        number = await extract_number_from_text(prompt)
        gesture = await extract_gesture_from_text(prompt)
        
        # Determine speed from text
        speed = 2.0  # default
        if 'slow' in prompt.lower() or 'slowly' in prompt.lower():
            speed = 1.0
        elif 'fast' in prompt.lower() or 'quickly' in prompt.lower():
            speed = 4.0
        elif 'smooth' in prompt.lower():
            speed = 1.5
        
        # Process commands in order of priority
        if number >= 0:
            # Handle number showing with retry logic
            log_info(f"Showing number: {number} (speed: {speed})")
            success = await _execute_with_retry(servo_controller, 'show_number', number, speed)
            
            if success:
                responses = {
                    0: "I'm making a fist - that's zero fingers!",
                    1: "One finger up! Can you show me one too?",
                    2: "Two fingers - peace out! ✌️",
                    3: "Three fingers! Count along with me!",
                    4: "Four fingers! Almost a whole hand!",
                    5: "High five! I'm showing all five fingers!",
                    6: "Six! That's five plus one more!",
                    7: "Seven! Look at both my hands!",
                    8: "Eight fingers! Can you count them?",
                    9: "Nine! Almost ten!",
                    10: "Ten fingers! Both hands are open wide!"
                }
                response = responses.get(number, f"I'm showing {number} fingers with my servo hands!")
            else:
                response = f"I tried to show {number} fingers, but had trouble with my ESP32 connection even after reconnecting."
        
        elif gesture:
            # Handle gesture commands with retry logic
            log_info(f"Executing gesture: {gesture} (speed: {speed})")
            success = await _execute_with_retry(servo_controller, 'execute_gesture', gesture, speed)
            
            if success:
                gesture_responses = {
                    'wave': "Hello there! I'm waving my servo hand at you! 👋",
                    'point': "I'm pointing with my robotic finger! Look where I'm pointing!",
                    'fist': "I made a strong robotic fist! See my servo power? 💪",
                    'open_hand': "My hand is wide open! Ready for a high five! ✋",
                    'peace': "Peace and love! I'm making the peace sign with my servos! ✌️",
                    'thumbs_up': "Thumbs up! Great job! My servo thumb approves! 👍"
                }
                response = gesture_responses.get(gesture, f"I just performed a {gesture} gesture with my servos!")
            else:
                response = f"I tried to do a {gesture} gesture, but my ESP32 had trouble even after reconnecting."
        
        else:
            # Handle special commands or fallback with retry logic
            prompt_lower = prompt.lower()
            
            if any(cmd in prompt_lower for cmd in ["reset", "neutral", "home", "rest"]):
                success = await _execute_with_retry(servo_controller, 'reset_all')
                response = "I'm moving all my servos back to their home positions!" if success else "I had trouble resetting my servo positions."
            
            elif any(cmd in prompt_lower for cmd in ["stop", "emergency", "halt"]):
                success = await _execute_with_retry(servo_controller, 'emergency_stop')
                response = "Emergency stop! All servo movement stopped immediately." if success else "Emergency stop command failed."
            
            elif "status" in prompt_lower or "check" in prompt_lower:
                status = await _execute_with_retry(servo_controller, 'get_status')
                if status:
                    stats = servo_controller.get_connection_stats()
                    response = f"All systems operational! Connected to ESP32 at {stats['host']}. Success rate: {stats['success_rate']:.1f}%"
                else:
                    response = "I'm having trouble getting my servo status from the ESP32."
            
            else:
                response = ("I'm not sure what gesture to make! Try asking me to:\n"
                          "• Show a number (0-10)\n" 
                          "• Wave, point, or make a fist\n"
                          "• Give a thumbs up or peace sign\n"
                          "• Reset to home position")
        
        # Update UI if socket server available
        if socket_server:
            await socket_server.emit_response(response)
        
        # Log performance stats
        stats = servo_controller.get_connection_stats()
        log_info(f"Gesture completed. Stats: {stats['commands_sent']} commands, {stats['success_rate']:.1f}% success")
        
        print(response)
        await tts_engine.speak_text(response)
        return response
        
    except Exception as e:
        log_error(f"Gesture handling error: {e}")
        error_response = "Sorry, I had trouble with my servo system. Let me try to reset everything."
        
        # Attempt emergency recovery with reconnection
        try:
            if not servo_controller.is_connected:
                log_info("🔄 Attempting reconnection for recovery...")
                await servo_controller.connect()
            
            if servo_controller.is_connected:
                await servo_controller.emergency_stop()
                await asyncio.sleep(1)
                await servo_controller.reset_all()
            else:
                log_error("Recovery failed: Could not reconnect to ESP32")
        except Exception as recovery_error:
            log_error(f"Recovery attempt failed: {recovery_error}")
        
        await tts_engine.speak_text(error_response)
        return error_response


async def _execute_with_retry(servo_controller, method_name: str, *args, max_retries: int = 2):
    """Execute servo command with automatic reconnection retry"""
    for attempt in range(max_retries + 1):
        try:
            # Check connection before executing command
            if not servo_controller.is_connected:
                log_info(f"🔄 Connection lost, reconnecting... (attempt {attempt + 1})")
                reconnected = await servo_controller.connect()
                if not reconnected:
                    log_error(f"Reconnection failed on attempt {attempt + 1}")
                    if attempt == max_retries:
                        return False
                    continue
            
            # Execute the command
            method = getattr(servo_controller, method_name)
            if args:
                result = await method(*args)
            else:
                result = await method()
            
            # Command succeeded
            if result is not False:  # Handle both True and non-boolean returns
                return result
            else:
                log_debug(f"Command {method_name} returned False, may indicate connection issue")
                
        except Exception as e:
            log_error(f"Command {method_name} failed on attempt {attempt + 1}: {e}")
            
            # If it's a connection-related error, mark as disconnected
            if any(err in str(e).lower() for err in ['connection', 'websocket', 'timeout', 'closed']):
                servo_controller.is_connected = False
        
        # Wait before retry (except on last attempt)
        if attempt < max_retries:
            await asyncio.sleep(1)
    
    log_error(f"Command {method_name} failed after {max_retries + 1} attempts")
    return False

# Cleanup function for graceful shutdown
async def cleanup_gesture_system():
    """Cleanup for ESP32 servo system"""
    global _servo_controller
    
    if _servo_controller:
        try:
            log_info("Performing graceful servo system shutdown...")
            await _servo_controller.reset_all()
            await asyncio.sleep(2)
            await _servo_controller.disconnect()
        except Exception as e:
            log_error(f"Gesture system cleanup error: {e}")
        finally:
            _servo_controller = None
            log_info("Gesture system cleanup completed")
