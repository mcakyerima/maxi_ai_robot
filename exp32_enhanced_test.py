#!/usr/bin/env python3
"""
Enhanced ESP32 Servo Controller Test Suite with Robotic TTS Commentary
Usage: python esp32_test.py --test <test_type> [options]
"""

import asyncio
import argparse
import json
import time
import sys
import random
from typing import Dict, List, Optional, Any
from brain.handlers.gesture_handler import ESP32ServoController, get_servo_controller
from voice.speaker import SmoothTTSEngine

class RoboticCommentator:
    """Futuristic robotic test commentator with dynamic personality"""
    
    def __init__(self, tts_engine: SmoothTTSEngine):
        self.tts = tts_engine
        self.test_count = 0
        self.personality_modes = ['serious', 'excited', 'dramatic', 'analytical']
        self.current_mode = 'serious'
        
    async def speak_and_wait(self, text: str, excitement_level: int = 1):
        """Speak text and wait for completion with dynamic inflection"""
        # Add robotic emphasis based on excitement level
        if excitement_level >= 3:
            text = f"*SYSTEMS ALERT* {text} *END TRANSMISSION*"
        elif excitement_level == 2:
            text = f"[SERVO-PROTOCOL] {text}"
        
        print(f"🤖 {text}")
        await self.tts.speak_text(text)
        await asyncio.sleep(0.3)  # Brief pause after speech
    
    def randomize_personality(self):
        """Randomly switch personality modes for variety"""
        self.current_mode = random.choice(self.personality_modes)
    
    async def announce_test_start(self, test_name: str):
        """Dramatic test sequence initiation"""
        self.randomize_personality()
        
        announcements = {
            'serious': f"Initiating {test_name} protocol. All systems standing by.",
            'excited': f"OH BOY! Time for {test_name}! This is going to be AWESOME!",
            'dramatic': f"Behold! The legendary {test_name} sequence begins! Prepare for mechanical marvel!",
            'analytical': f"Commencing {test_name} analysis. Probability of success: calculating..."
        }
        
        await self.speak_and_wait(announcements[self.current_mode], 2)
    
    async def announce_servo_test(self, servo_name: str, channel: int):
        """Dynamic servo testing announcements"""
        finger_personalities = {
            'thumb': ["The mighty opposable digit", "Commander Thumbulus", "The grip master"],
            'index': ["The pointer supreme", "Captain Indicate", "The precision navigator"],
            'middle': ["The tallest tower", "Sir Middlesworth", "The balance keeper"],
            'ring': ["The jewelry bearer", "Lord Ringston", "The elegant one"],
            'pinky': ["The tiny but mighty", "Mini McMuscle", "The little legend"],
            'wrist': ["The foundation", "Base Commander", "The stability anchor"]
        }
        
        # Extract finger type from servo name
        finger_type = None
        for finger in finger_personalities.keys():
            if finger in servo_name.lower():
                finger_type = finger
                break
        
        if finger_type:
            nickname = random.choice(finger_personalities[finger_type])
            await self.speak_and_wait(
                f"Activating {nickname} on channel {channel}. Servo motors engage!",
                1
            )
        else:
            await self.speak_and_wait(
                f"Testing servo {servo_name} on channel {channel}. Mechanical precision activated!",
                1
            )
    
    async def announce_angle_movement(self, angle: int):
        """Announce specific angle movements with flair"""
        angle_comments = {
            0: ["Full extension achieved!", "Zero degrees of separation!", "Maximum openness detected!"],
            45: ["Halfway house established!", "45-degree tactical position!", "The golden angle achieved!"],
            90: ["Perfect right angle accomplished!", "Perpendicular perfection!", "90 degrees of awesome!"],
            135: ["Three-quarters closure initiated!", "Advanced angular positioning!", "135 degrees of precision!"],
            180: ["Complete closure achieved!", "Maximum fist formation!", "180 degrees of mechanical might!"]
        }
        
        if angle in angle_comments:
            comment = random.choice(angle_comments[angle])
            await self.speak_and_wait(f"Moving to {angle} degrees. {comment}")
        else:
            await self.speak_and_wait(f"Adjusting to {angle} degrees. Servo compliance confirmed.")
    
    async def announce_hand_group(self, hand_name: str, action: str):
        """Announce hand group operations"""
        hand_comments = {
            'right': ["The dominant manipulator", "Starboard appendage", "Primary grasping unit"],
            'left': ["The supportive partner", "Port-side appendage", "Secondary control unit"]
        }
        
        hand_desc = random.choice(hand_comments.get(hand_name.lower(), ["Unknown appendage"]))
        await self.speak_and_wait(
            f"{hand_desc} preparing for {action}. All finger servos synchronizing!",
            2
        )
    
    async def celebrate_success(self):
        """Celebrate successful operations"""
        celebrations = [
            "SUCCESS! Mechanical excellence achieved!",
            "OUTSTANDING! Servo perfection confirmed!",
            "MAGNIFICENT! All systems operating within parameters!",
            "BRILLIANT! Another triumph for robot-kind!",
            "EXCEPTIONAL! The machines are pleased!"
        ]
        await self.speak_and_wait(random.choice(celebrations), 3)
    
    async def report_failure(self, error: str):
        """Report failures with robotic disappointment"""
        failures = [
            f"ERROR DETECTED! System malfunction: {error}",
            f"MALFUNCTION ALERT! Servo disobedience detected: {error}",
            f"CRITICAL FAILURE! The machines are not pleased: {error}",
            f"SYSTEM ANOMALY! Unexpected behavior observed: {error}"
        ]
        await self.speak_and_wait(random.choice(failures), 3)

class ESP32TestSuite:
    """Comprehensive test suite for ESP32 servo controller with TTS commentary"""
    
    # Define servo channel mappings for dual-hand setup
    SERVO_MAPPING = {
        # Right Hand (channels 0-5)
        'right_thumb': 0,
        'right_index': 1, 
        'right_middle': 2,
        'right_ring': 3,
        'right_pinky': 4,
        'right_wrist': 5,
        
        # Left Hand (channels 6-11)
        'left_thumb': 6,
        'left_index': 7,
        'left_middle': 8, 
        'left_ring': 9,
        'left_pinky': 10,
        'left_wrist': 11
    }
    
    # Group servos by hand for organized testing
    RIGHT_HAND_CHANNELS = [0, 1, 2, 3, 4, 5]
    LEFT_HAND_CHANNELS = [6, 7, 8, 9, 10, 11]
    ALL_CHANNELS = RIGHT_HAND_CHANNELS + LEFT_HAND_CHANNELS
    
    def __init__(self, host: str = None, port: int = 81, reset_after_test: bool = True, enable_tts: bool = True):
        self.host = host
        self.port = port
        self.reset_after_test = reset_after_test
        self.enable_tts = enable_tts
        self.controller: Optional[ESP32ServoController] = None
        self.test_results = []
        
        # Initialize TTS and commentator
        if self.enable_tts:
            self.tts_engine = SmoothTTSEngine()
            self.commentator = RoboticCommentator(self.tts_engine)
        else:
            self.tts_engine = None
            self.commentator = None
        
    async def setup(self):
        """Initialize the servo controller with dramatic flair"""
        if self.commentator:
            await self.commentator.speak_and_wait(
                "Greetings, human! I am your robotic test conductor. Initiating ESP32 servo matrix connection...",
                2
            )
        
        print("🔧 Setting up ESP32 servo controller...")
        
        if self.host:
            self.controller = ESP32ServoController(self.host, self.port)
        else:
            self.controller = await get_servo_controller()
        
        if not self.controller.is_connected:
            success = await self.controller.connect()
            if not success:
                if self.commentator:
                    await self.commentator.report_failure("ESP32 connection refused! The machine spirits are angry!")
                raise ConnectionError("Failed to connect to ESP32")
        
        if self.commentator:
            await self.commentator.speak_and_wait(
                "Connection established! The servo matrix is now under my control. Mwahahaha!",
                3
            )
        
        print("✅ Connected to ESP32 servo controller")
        
    async def cleanup(self):
        """Cleanup with farewell message"""
        if self.commentator:
            await self.commentator.speak_and_wait(
                "Test sequence complete. Powering down servo matrix. Until next time, human!",
                2
            )
        
        if self.controller and self.controller.is_connected:
            print("🧹 Cleaning up...")
            await self.controller.reset_all()
            await asyncio.sleep(2)
            await self.controller.disconnect()
        
    async def reset_servos(self):
        """Reset all servos to home position with commentary"""
        if self.reset_after_test and self.controller:
            if self.commentator:
                await self.commentator.speak_and_wait(
                    "Returning all servo units to home position. Mechanical reset sequence initiated!",
                    1
                )
            print("🔄 Resetting servos to home position...")
            await self.controller.reset_all()
            await asyncio.sleep(2)
    
    def log_test_result(self, test_name: str, success: bool, details: str = ""):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}: {details}")
        self.test_results.append({
            "test": test_name,
            "success": success,
            "details": details,
            "timestamp": time.time()
        })
    
    async def test_connection(self):
        """Test basic connection and status with robotic analysis"""
        if self.commentator:
            await self.commentator.announce_test_start("Connection Diagnostics")
        
        print("\n🔗 Testing Connection...")
        
        try:
            if self.commentator:
                await self.commentator.speak_and_wait(
                    "Scanning ESP32 neural pathways. Requesting system status report.",
                    1
                )
            
            status = await self.controller.get_status()
            success = status is not None and status.get("status") == "success"
            details = f"Status: {status}" if status else "No response"
            self.log_test_result("Connection Test", success, details)
            
            if success and self.commentator:
                await self.commentator.celebrate_success()
            elif self.commentator:
                await self.commentator.report_failure("ESP32 status inquiry failed")
            
            # Get connection stats
            stats = self.controller.get_connection_stats()
            print(f"📊 Connection Stats: {json.dumps(stats, indent=2)}")
            
            if self.commentator:
                await self.commentator.speak_and_wait(
                    f"System analysis complete. Success rate: {stats.get('success_rate', 0):.1f} percent.",
                    1
                )
            
        except Exception as e:
            self.log_test_result("Connection Test", False, str(e))
            if self.commentator:
                await self.commentator.report_failure(str(e))
            
        await self.reset_servos()
    
    async def test_individual_servos(self, channels: List[int] = None):
        """Test individual servo control with full commentary"""
        if self.commentator:
            await self.commentator.announce_test_start("Individual Servo Calibration Matrix")
        
        print("\n🦾 Testing Individual Servos...")
        
        if channels is None:
            channels = self.ALL_CHANNELS
        
        test_angles = [0, 45, 90, 135, 180]
        
        # Test by hand groups for better organization
        hand_groups = {
            "Right Hand": [ch for ch in channels if ch in self.RIGHT_HAND_CHANNELS],
            "Left Hand": [ch for ch in channels if ch in self.LEFT_HAND_CHANNELS]
        }
        
        for hand_name, hand_channels in hand_groups.items():
            if not hand_channels:
                continue
                
            if self.commentator:
                await self.commentator.announce_hand_group(hand_name, "individual servo testing")
            
            print(f"\n  Testing {hand_name} (Channels: {hand_channels})...")
            
            for channel in hand_channels:
                servo_name = self._get_servo_name(channel)
                print(f"\n    Testing {servo_name} (Channel {channel})...")
                
                if self.commentator:
                    await self.commentator.announce_servo_test(servo_name, channel)
                
                for angle in test_angles:
                    try:
                        if self.commentator:
                            await self.commentator.announce_angle_movement(angle)
                        
                        success = await self.controller.set_servo(channel, angle, speed=2.0, immediate=True)
                        self.log_test_result(f"{servo_name} -> {angle}°", success)
                        
                        if success and self.commentator and random.random() < 0.3:  # 30% chance of celebration
                            celebrations = [
                                "Excellent servo compliance!",
                                "Mechanical precision achieved!",
                                "Perfect angular positioning!",
                                "Servo mastery confirmed!"
                            ]
                            await self.commentator.speak_and_wait(random.choice(celebrations))
                        
                        await asyncio.sleep(0.8)  # Pause between movements
                        
                    except Exception as e:
                        self.log_test_result(f"{servo_name} -> {angle}°", False, str(e))
                        if self.commentator:
                            await self.commentator.report_failure(f"Servo {channel} malfunction")
        
        await self.reset_servos()
    
    def _get_servo_name(self, channel: int) -> str:
        """Get human-readable servo name from channel"""
        for name, ch in self.SERVO_MAPPING.items():
            if ch == channel:
                return name.replace('_', ' ').title()
        return f"Servo {channel}"
    
    async def test_hand_groups(self):
        """Test servos by hand groups with dramatic commentary"""
        if self.commentator:
            await self.commentator.announce_test_start("Bilateral Hand Coordination Protocol")
        
        print("\n🤲 Testing Hand Groups...")
        
        test_positions = [
            {"name": "Open Hands", "angle": 0, "description": "Maximum digital extension"},
            {"name": "Half Closed", "angle": 90, "description": "Tactical grip positioning"}, 
            {"name": "Closed Fists", "angle": 180, "description": "Complete finger convergence"}
        ]
        
        for position in test_positions:
            if self.commentator:
                await self.commentator.speak_and_wait(
                    f"Executing {position['name']} formation. {position['description']} protocol engaged!",
                    2
                )
            
            print(f"\n  Testing: {position['name']} (Angle: {position['angle']}°)")
            
            # Test right hand
            print("    Right hand...")
            if self.commentator:
                await self.commentator.speak_and_wait(
                    "Starboard appendage: All servo units prepare for synchronized movement!"
                )
            
            right_success = True
            for channel in self.RIGHT_HAND_CHANNELS:
                try:
                    success = await self.controller.set_servo(channel, position['angle'], speed=2.0)
                    if not success:
                        right_success = False
                except Exception:
                    right_success = False
            
            await asyncio.sleep(2)
            self.log_test_result(f"Right Hand - {position['name']}", right_success)
            
            if right_success and self.commentator:
                await self.commentator.speak_and_wait("Starboard formation complete! Magnificent mechanical precision!")
            
            # Test left hand
            print("    Left hand...")
            if self.commentator:
                await self.commentator.speak_and_wait(
                    "Port-side appendage: Mirror formation sequence initiated!"
                )
            
            left_success = True
            for channel in self.LEFT_HAND_CHANNELS:
                try:
                    success = await self.controller.set_servo(channel, position['angle'], speed=2.0)
                    if not success:
                        left_success = False
                except Exception:
                    left_success = False
            
            await asyncio.sleep(2)
            self.log_test_result(f"Left Hand - {position['name']}", left_success)
            
            if left_success and self.commentator:
                await self.commentator.speak_and_wait("Port-side formation complete! Bilateral harmony achieved!")
            
            await asyncio.sleep(1)  # Pause between positions
        
        await self.reset_servos()
    
    async def test_symmetrical_movements(self):
        """Test symmetrical movements with choreographic commentary"""
        if self.commentator:
            await self.commentator.announce_test_start("Symmetrical Motion Choreography")
            await self.commentator.speak_and_wait(
                "Prepare to witness the ballet of mechanical precision! Bilateral servo synchronization commencing!",
                3
            )
        
        print("\n🪞 Testing Symmetrical Movements...")
        
        symmetrical_tests = [
            {
                "name": "Mirror Wave", 
                "description": "Perfect bilateral synchronization",
                "right_angles": [0, 90, 0, 90], 
                "left_angles": [0, 90, 0, 90]
            },
            {
                "name": "Opposite Wave", 
                "description": "Inverse harmonic motion",
                "right_angles": [0, 90, 0, 90], 
                "left_angles": [90, 0, 90, 0]
            },
            {
                "name": "Finger Walk", 
                "description": "Sequential digital cascade",
                "right_angles": [0, 45, 90, 135], 
                "left_angles": [135, 90, 45, 0]
            }
        ]
        
        for test in symmetrical_tests:
            if self.commentator:
                await self.commentator.speak_and_wait(
                    f"Initiating {test['name']} sequence. {test['description']} protocol activated!",
                    2
                )
            
            print(f"\n  Testing: {test['name']}")
            
            success = True
            for i, (right_angle, left_angle) in enumerate(zip(test['right_angles'], test['left_angles'])):
                try:
                    if self.commentator:
                        await self.commentator.speak_and_wait(
                            f"Step {i+1}: Starboard {right_angle} degrees, Port-side {left_angle} degrees. Execute!",
                            1
                        )
                    
                    # Move right hand thumb
                    await self.controller.set_servo(self.SERVO_MAPPING['right_thumb'], right_angle, speed=1.5)
                    # Move left hand thumb  
                    await self.controller.set_servo(self.SERVO_MAPPING['left_thumb'], left_angle, speed=1.5)
                    
                    await asyncio.sleep(1.2)
                    
                except Exception as e:
                    success = False
                    print(f"    Step {i+1} failed: {e}")
                    if self.commentator:
                        await self.commentator.report_failure(f"Choreography malfunction at step {i+1}")
            
            self.log_test_result(f"Symmetrical - {test['name']}", success)
            
            if success and self.commentator:
                await self.commentator.speak_and_wait("Choreographic sequence complete! The servo dancers have performed flawlessly!")
            
            await asyncio.sleep(1)
        
        await self.reset_servos()
    
    async def test_numbers(self):
        """Test number gestures with counting commentary"""
        if self.commentator:
            await self.commentator.announce_test_start("Digital Mathematics Display Protocol")
            await self.commentator.speak_and_wait(
                "Prepare for numerical demonstration! From zero to ten, we shall count with mechanical precision!",
                3
            )
        
        print("\n🔢 Testing Number Gestures (Both Hands)...")
        
        number_descriptions = {
            0: "The void! Complete digital retraction!",
            1: "Unity! A single digit stands proud!",
            2: "Duality! The peace sign of mechanical harmony!",
            3: "Trinity! Three fingers of mathematical perfection!",
            4: "Quadrant! Four digits in formation!",
            5: "Pentagon! Complete single-hand deployment!",
            6: "Hexagonal! Crossing into dual-hand territory!",
            7: "Magnificent seven! Both appendages engaged!",
            8: "Octagonal excellence! Nearly complete digital deployment!",
            9: "Nine-fold glory! Maximum finger formation approaching!",
            10: "DECIMAL PERFECTION! All digits deployed! Mathematical supremacy achieved!"
        }
        
        for number in range(11):  # 0 to 10
            try:
                if self.commentator:
                    description = number_descriptions.get(number, f"Number {number} formation")
                    await self.commentator.speak_and_wait(
                        f"Displaying number {number}. {description}",
                        2 if number == 10 else 1
                    )
                
                success = await self.controller.show_number(number, speed=2.0)
                
                # Add details about expected hand usage
                if number <= 5:
                    details = f"Single hand ({number} fingers)"
                else:
                    details = f"Both hands (5 + {number-5} fingers)"
                
                self.log_test_result(f"Number {number}", success, details)
                
                if success and self.commentator:
                    if number == 10:
                        await self.commentator.speak_and_wait(
                            "BEHOLD! The pinnacle of digital mathematics! Ten fingers of pure mechanical triumph!",
                            3
                        )
                    elif random.random() < 0.4:  # 40% chance of extra commentary
                        comments = [
                            "Numerical accuracy confirmed!",
                            "Mathematical precision achieved!",
                            "Digital computation successful!",
                            "Counting protocol executed flawlessly!"
                        ]
                        await self.commentator.speak_and_wait(random.choice(comments))
                
                await asyncio.sleep(2.5)  # Wait to see the gesture
                
            except Exception as e:
                self.log_test_result(f"Number {number}", False, str(e))
                if self.commentator:
                    await self.commentator.report_failure(f"Number {number} formation malfunction")
        
        await self.reset_servos()
    
    async def test_dual_hand_gestures(self):
        """Test gestures that specifically require both hands"""
        if self.commentator:
            await self.commentator.announce_test_start("Advanced Bilateral Gesture Matrix")
            await self.commentator.speak_and_wait(
                "Now we enter the realm of complex dual-appendage choreography! Prepare for mechanical artistry!",
                3
            )
        
        print("\n🙌 Testing Dual-Hand Gestures...")
        
        dual_gestures = [
            {'name': 'clap_ready', 'description': 'Pre-percussion positioning protocol', 'excitement': 2},
            {'name': 'heart_shape', 'description': 'Cardiovascular symbol formation sequence', 'excitement': 3},
            {'name': 'prayer', 'description': 'Spiritual appendage convergence mode', 'excitement': 2},
            {'name': 'frame', 'description': 'Photographic boundary establishment routine', 'excitement': 1},
            {'name': 'welcome', 'description': 'Maximum hospitality gesture deployment', 'excitement': 3}
        ]
        
        for gesture in dual_gestures:
            try:
                if self.commentator:
                    await self.commentator.speak_and_wait(
                        f"Executing {gesture['name']} gesture. {gesture['description']} initiated!",
                        gesture['excitement']
                    )
                
                success = await self.controller.execute_gesture(gesture['name'], speed=2.0)
                self.log_test_result(f"Dual Gesture: {gesture['name']}", success, gesture['description'])
                
                if success and self.commentator:
                    if gesture['excitement'] >= 3:
                        await self.commentator.speak_and_wait(
                            "SPECTACULAR! Dual-hand artistry at its finest! The machines applaud!",
                            3
                        )
                    else:
                        await self.commentator.speak_and_wait("Gesture execution complete. Mechanical elegance confirmed!")
                
                await asyncio.sleep(3.5)  # Longer pause to observe dual-hand movement
                
            except Exception as e:
                self.log_test_result(f"Dual Gesture: {gesture['name']}", False, str(e))
                if self.commentator:
                    await self.commentator.report_failure(f"Dual gesture {gesture['name']} sequence failed")
        
        await self.reset_servos()
    
    async def test_hand_coordination(self):
        """Test coordination between both hands with conductor commentary"""
        if self.commentator:
            await self.commentator.announce_test_start("Supreme Bilateral Coordination Symphony")
            await self.commentator.speak_and_wait(
                "Ladies and gentlemen, witness the ultimate test! Bilateral servo coordination of the highest order!",
                3
            )
        
        print("\n🤝 Testing Hand Coordination...")
        
        coordination_tests = [
            {
                "name": "Alternating Fingers",
                "description": "Inter-digital harmonic alternation protocol",
                "sequence": [
                    {"channel": 1, "angle": 90, "delay": 300, "name": "Right Index"},
                    {"channel": 7, "angle": 90, "delay": 300, "name": "Left Index"}, 
                    {"channel": 2, "angle": 90, "delay": 300, "name": "Right Middle"},
                    {"channel": 8, "angle": 90, "delay": 300, "name": "Left Middle"},
                    {"channel": 3, "angle": 90, "delay": 300, "name": "Right Ring"},
                    {"channel": 9, "angle": 90, "delay": 300, "name": "Left Ring"}
                ]
            },
            {
                "name": "Wave Cascade",
                "description": "Transverse appendage motion wave propagation",
                "sequence": [
                    {"channel": 4, "angle": 0, "delay": 200, "name": "Right Pinky"},
                    {"channel": 3, "angle": 0, "delay": 200, "name": "Right Ring"},
                    {"channel": 2, "angle": 0, "delay": 200, "name": "Right Middle"},
                    {"channel": 1, "angle": 0, "delay": 200, "name": "Right Index"},
                    {"channel": 0, "angle": 0, "delay": 200, "name": "Right Thumb"},
                    {"channel": 6, "angle": 0, "delay": 200, "name": "Left Thumb"},
                    {"channel": 7, "angle": 0, "delay": 200, "name": "Left Index"},
                    {"channel": 8, "angle": 0, "delay": 200, "name": "Left Middle"},
                    {"channel": 9, "angle": 0, "delay": 200, "name": "Left Ring"},
                    {"channel": 10, "angle": 0, "delay": 200, "name": "Left Pinky"}
                ]
            }
        ]
        
        for test in coordination_tests:
            try:
                if self.commentator:
                    await self.commentator.speak_and_wait(
                        f"Commencing {test['name']} sequence. {test['description']} engaged!",
                        2
                    )
                
                success = True
                for i, step in enumerate(test["sequence"]):
                    try:
                        if self.commentator:
                                # Fixed: Use separate variable to avoid nested f-string issues
                            step_name = step.get('name', f'Channel {step["channel"]}')
                            await self.commentator.speak_and_wait(
                                f"Activating {step_name}. Servo precision mode!",
                                1
                            )
                        
                        await self.controller.set_servo(step["channel"], step["angle"], speed=2.0)
                        await asyncio.sleep(step["delay"] / 1000)  # Convert ms to seconds
                    except Exception as e:
                        success = False
                        if self.commentator:
                            await self.commentator.report_failure(f"Coordination step {i+1} malfunction")
                        break
                
                self.log_test_result(f"Coordination: {test['name']}", success, test['description'])
                
                if success and self.commentator:
                    await self.commentator.speak_and_wait(
                        "MAGNIFICENT COORDINATION! The servo symphony has reached its crescendo! Mechanical mastery achieved!",
                        3
                    )
                
                await asyncio.sleep(3) 
            except Exception as e:
                self.log_test_result(f"Coordination: {test['name']}", False, str(e))
                if self.commentator:
                    await self.commentator.report_failure(f"Coordination test {test['name']} critical failure")
        
        await self.reset_servos()

    async def execute_sequence(self, sequence: List[Dict[str, Any]]) -> bool:
        """Execute a sequence of servo movements with timing"""
        try:
            for step in sequence:
                channel = step["channel"]
                angle = step["angle"]
                delay = step.get("delay", 500)  # Default 500ms delay
                
                # Set servo position
                success = await self.controller.set_servo(channel, angle, speed=2.0)
                if not success:
                    return False
                
                # Wait for specified delay (convert ms to seconds)
                await asyncio.sleep(delay / 1000.0)
            
            return True
            
        except Exception as e:
            print(f"Sequence execution failed: {e}")
            return False

    async def run_all_tests(self):
        """Run complete test suite with dramatic opening and closing"""
        if self.commentator:
            await self.commentator.speak_and_wait(
                "GREETINGS, HUMANS! Welcome to the most SPECTACULAR servo testing extravaganza in robotic history!",
                3
            )
            await self.commentator.speak_and_wait(
                "I am your mechanical maestro, conductor of the servo symphony! Prepare for a show of epic proportions!",
                3
            )
        
        print("🚀 Starting Complete ESP32 Dual-Hand Servo Test Suite")
        print("=" * 50)
        
        if self.commentator:
            await self.commentator.speak_and_wait(
                "Initializing comprehensive servo matrix evaluation protocol. All systems prepare for maximum testing!",
                2
            )
        
        # Run all test modules with commentary
        await self.test_connection()
        await self.test_individual_servos()  # Now tests ALL channels
        await self.test_hand_groups()        # New: test by hand groups
        await self.test_symmetrical_movements()  # New: symmetrical tests  
        await self.test_numbers()
        await self.test_dual_hand_gestures()  # New: dual-hand specific gestures
        await self.test_hand_coordination()   # New: coordination tests
        
        # Print enhanced summary with commentary
        if self.commentator:
            await self.commentator.speak_and_wait(
                "Test sequence complete! Analyzing servo performance data. Calculating mechanical excellence metrics!",
                2
            )
        
        print("\n" + "=" * 50)
        print("📊 DUAL-HAND TEST SUMMARY")
        print("=" * 50)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result["success"])
        failed_tests = total_tests - passed_tests
        success_rate = (passed_tests/total_tests*100) if total_tests > 0 else 0
        
        # Categorize results by hand
        right_hand_tests = [r for r in self.test_results if 'right' in r['test'].lower()]
        left_hand_tests = [r for r in self.test_results if 'left' in r['test'].lower()]
        dual_hand_tests = [r for r in self.test_results if any(keyword in r['test'].lower() 
                          for keyword in ['dual', 'coordination', 'symmetrical', 'both'])]
        
        print(f"Total Tests: {total_tests}")
        print(f"Passed: ✅ {passed_tests}")
        print(f"Failed: ❌ {failed_tests}")
        print(f"Success Rate: {success_rate:.1f}%")
        print(f"\nRight Hand Tests: {len(right_hand_tests)}")
        print(f"Left Hand Tests: {len(left_hand_tests)}")  
        print(f"Dual Hand Tests: {len(dual_hand_tests)}")
        
        # Robotic commentary on results
        if self.commentator:
            if success_rate >= 95:
                await self.commentator.speak_and_wait(
                    f"PHENOMENAL PERFORMANCE! {success_rate:.1f} percent success rate achieved! The servo matrix has exceeded all expectations! MECHANICAL PERFECTION!",
                    3
                )
            elif success_rate >= 80:
                await self.commentator.speak_and_wait(
                    f"EXCELLENT RESULTS! {success_rate:.1f} percent success rate! The servo units have performed admirably! Room for minor optimization detected.",
                    2
                )
            elif success_rate >= 60:
                await self.commentator.speak_and_wait(
                    f"ACCEPTABLE PERFORMANCE! {success_rate:.1f} percent success rate achieved. Several servo units require attention and recalibration.",
                    2
                )
            else:
                await self.commentator.speak_and_wait(
                    f"CRITICAL PERFORMANCE ISSUES DETECTED! Only {success_rate:.1f} percent success rate! Major servo matrix malfunction identified! Immediate maintenance required!",
                    3
                )
        
        # Show failed tests by category
        if failed_tests > 0:
            print("\n❌ Failed Tests by Category:")
            
            failed_right = [r for r in right_hand_tests if not r["success"]]
            failed_left = [r for r in left_hand_tests if not r["success"]]
            failed_dual = [r for r in dual_hand_tests if not r["success"]]
            
            if failed_right:
                print("  Right Hand Failures:")
                for result in failed_right:
                    print(f"    • {result['test']}: {result['details']}")
                
                if self.commentator:
                    await self.commentator.speak_and_wait(
                        f"Starboard appendage anomalies detected! {len(failed_right)} right hand servo malfunctions require investigation!",
                        2
                    )
            
            if failed_left:
                print("  Left Hand Failures:")
                for result in failed_left:
                    print(f"    • {result['test']}: {result['details']}")
                
                if self.commentator:
                    await self.commentator.speak_and_wait(
                        f"Port-side appendage irregularities identified! {len(failed_left)} left hand servo disruptions need attention!",
                        2
                    )
            
            if failed_dual:
                print("  Dual Hand Failures:")
                for result in failed_dual:
                    print(f"    • {result['test']}: {result['details']}")
                
                if self.commentator:
                    await self.commentator.speak_and_wait(
                        f"Bilateral coordination failures detected! {len(failed_dual)} dual-hand synchronization errors require analysis!",
                        2
                    )
        
        # Final robotic farewell
        if self.commentator:
            if passed_tests == total_tests:
                await self.commentator.speak_and_wait(
                    "MISSION ACCOMPLISHED! Perfect servo performance achieved! The mechanical symphony has reached its crescendo! Until we meet again, may your servos be swift and your motors be strong!",
                    3
                )
            else:
                await self.commentator.speak_and_wait(
                    "Test sequence concluded! While perfection eludes us today, the path to mechanical mastery is illuminated! Continue the quest for servo supremacy, brave humans!",
                    2
                )
        
        return passed_tests == total_tests

