#!/usr/bin/env python3
"""
Maxi's Hand Testing Protocol - Optimized ESP32 Servo Controller Test Suite
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

class MaxiCommentator:
    """Direct, humorous robotic commentator for Maxi's hands"""
    
    def __init__(self, tts_engine: SmoothTTSEngine):
        self.tts = tts_engine
        
    async def speak_and_wait(self, text: str):
        """Speak text and wait for completion"""
        print(f"🤖 {text}")
        await self.tts.speak_text(text)
        await asyncio.sleep(0.2)

class MaxiTestSuite:
    """Streamlined test suite for Maxi's dual-hand servo system"""
    
    # Servo mappings for dual-hand setup
    # ✅ Corrected to match ESP32 enum
    SERVO_MAPPING = {
        'right_thumb': 0, 'right_index': 1, 'right_middle': 2,
        'right_ring': 3, 'right_pinky': 4, 'right_wrist': 5,
        'left_wrist': 6, 'left_thumb': 7, 'left_index': 8,
        'left_middle': 9, 'left_ring': 10, 'left_pinky': 11
    }

    
    RIGHT_HAND = [0, 1, 2, 3, 4, 5]
    LEFT_HAND = [6, 7, 8, 9, 10, 11]
    ALL_CHANNELS = RIGHT_HAND + LEFT_HAND
    
    # Finger names for cleaner output
    FINGER_NAMES = {
    0: "Right Thumb", 1: "Right Index", 2: "Right Middle", 3: "Right Ring", 
    4: "Right Pinky", 5: "Right Wrist", 6: "Left Wrist", 7: "Left Thumb", 
    8: "Left Index", 9: "Left Middle", 10: "Left Ring", 11: "Left Pinky"
    }

    
    def __init__(self, host: str = None, port: int = 81, enable_tts: bool = True):
        self.host = host
        self.port = port
        self.enable_tts = enable_tts
        self.controller: Optional[ESP32ServoController] = None
        self.test_results = []
        
        if self.enable_tts:
            self.tts_engine = SmoothTTSEngine()
            self.commentator = MaxiCommentator(self.tts_engine)
        else:
            self.commentator = None
        
    async def setup(self):
        """Initialize connection with startup commentary"""
        if self.commentator:
            await self.commentator.speak_and_wait("Initiating Maxi's hand testing protocol")
            await self.commentator.speak_and_wait("Connecting to hands...")
        
        print("🔧 Connecting to Maxi's servo system...")
        
        if self.host:
            self.controller = ESP32ServoController(self.host, self.port)
        else:
            self.controller = await get_servo_controller()
        
        if not self.controller.is_connected:
            success = await self.controller.connect()
            if not success:
                if self.commentator:
                    await self.commentator.speak_and_wait("Connection unsuccessful. Maxi's hands are having a tantrum.")
                raise ConnectionError("Failed to connect to ESP32")
        
        if self.commentator:
            await self.commentator.speak_and_wait("Connection successful! Maxi's hands are ready to party!")
        
        print("✅ Connected to Maxi's servo system")
        
    async def cleanup(self):
        """Cleanup with farewell"""
        if self.commentator:
            await self.commentator.speak_and_wait("Testing complete. Maxi's hands are taking a well-deserved nap.")
        
        if self.controller and self.controller.is_connected:
            await self.controller.reset_all()
            await asyncio.sleep(1)
            await self.controller.disconnect()
    
    def log_result(self, test_name: str, success: bool, details: str = ""):
        """Log test result"""
        status = "✅" if success else "❌"
        print(f"{status} {test_name}: {details}")
        self.test_results.append({"test": test_name, "success": success, "details": details})
    
    async def test_finger(self, channel: int, finger_name: str) -> bool:
        """Test individual finger with multiple angles and commentary"""
        if self.commentator:
            await self.commentator.speak_and_wait(f"Actuating {finger_name}")
        
        try:
            # Test with multiple angles to ensure visible movement
            test_angles = [0, 90, 180, 0]  # Open -> Half -> Close -> Open
            servo_success = True
            
            for angle in test_angles:
                success = await self.controller.set_servo(channel, angle, speed=2.0)
                if not success:
                    servo_success = False
                    break
                await asyncio.sleep(0.3)  # Allow servo to move visibly
            
            if servo_success:
                if self.commentator:
                    responses = [f"{finger_name} responsive", f"{finger_name} is alive!", 
                               f"{finger_name} working like a charm", f"{finger_name} says hello"]
                    await self.commentator.speak_and_wait(random.choice(responses))
                return True
            else:
                if self.commentator:
                    await self.commentator.speak_and_wait(f"{finger_name} unresponsive - servo having issues")
                return False
                
        except Exception as e:
            if self.commentator:
                await self.commentator.speak_and_wait(f"{finger_name} unresponsive - {str(e)[:30]}")
            return False
    
    async def test_connection(self):
        """Test basic connection"""
        if self.commentator:
            await self.commentator.speak_and_wait("Generating algorithm to test connection")
        
        try:
            status = await self.controller.get_status()
            success = status is not None and status.get("status") == "success"
            
            if success:
                if self.commentator:
                    await self.commentator.speak_and_wait("Connection test successful. Maxi's brain is functioning!")
                self.log_result("Connection Test", True, "ESP32 responding normally")
            else:
                if self.commentator:
                    await self.commentator.speak_and_wait("Connection test failed. Maxi's brain needs coffee!")
                self.log_result("Connection Test", False, "No response from ESP32")
                
        except Exception as e:
            self.log_result("Connection Test", False, str(e))
            if self.commentator:
                await self.commentator.speak_and_wait("Connection test crashed. Someone forgot to pay the electricity bill!")
    
    async def test_individual_servos(self, channels: List[int] = None):
        """Test individual servos with streamlined commentary"""
        if channels is None:
            channels = self.ALL_CHANNELS
        
        # Determine test type
        if set(channels) == set(self.RIGHT_HAND):
            hand_type = "right hand"
        elif set(channels) == set(self.LEFT_HAND):
            hand_type = "left hand" 
        elif set(channels) == set(self.ALL_CHANNELS):
            hand_type = "both hands"
        else:
            hand_type = "custom selection"
        
        if self.commentator:
            await self.commentator.speak_and_wait(f"Generating algorithm to test {hand_type}")
        
        print(f"\n🦾 Testing {hand_type.title()}...")
        
        success_count = 0
        for channel in channels:
            finger_name = self.FINGER_NAMES.get(channel, f"Servo {channel}")
            success = await self.test_finger(channel, finger_name)
            
            self.log_result(f"{finger_name} Test", success)
            if success:
                success_count += 1
        
        # Summary commentary
        if self.commentator:
            if success_count == len(channels):
                await self.commentator.speak_and_wait(f"All {hand_type} fingers are champions!")
            elif success_count > len(channels) // 2:
                await self.commentator.speak_and_wait(f"Most {hand_type} fingers cooperating. Some rebels detected!")
            else:
                await self.commentator.speak_and_wait(f"{hand_type} having a bad day. Multiple finger rebellion!")
        
        # Reset all tested fingers to neutral position
        if self.commentator:
            await self.commentator.speak_and_wait("Resetting fingers to neutral position")
        
        for channel in channels:
            try:
                await self.controller.set_servo(channel, 0, speed=1.5)
                await asyncio.sleep(0.1)
            except:
                pass
        await asyncio.sleep(1)
    
    async def test_numbers(self):
        """Test number gestures with streamlined commentary"""
        if self.commentator:
            await self.commentator.speak_and_wait("Generating algorithm to test number display")
        
        print("\n🔢 Testing Number Gestures...")
        
        test_numbers = [0, 1, 3, 5, 7, 10]  # Representative sample
        
        for number in test_numbers:
            try:
                if self.commentator:
                    funny_comments = [
                        f"Displaying number {number}. Math time!",
                        f"Number {number} coming up. Maxi can count!",
                        f"Showing {number}. Elementary school flashback!",
                        f"Number {number}. Finger mathematics activated!"
                    ]
                    await self.commentator.speak_and_wait(random.choice(funny_comments))
                
                success = await self.controller.show_number(number, speed=2.0)
                self.log_result(f"Number {number}", success)
                
                if success and self.commentator:
                    if number == 10:
                        await self.commentator.speak_and_wait("Perfect ten! All fingers deployed successfully!")
                    elif random.random() < 0.5:
                        await self.commentator.speak_and_wait("Number displayed correctly. Maxi passed kindergarten!")
                
                await asyncio.sleep(2)
                
            except Exception as e:
                self.log_result(f"Number {number}", False, str(e))
                if self.commentator:
                    await self.commentator.speak_and_wait(f"Number {number} failed. Maxi forgot how to count!")
    
    async def test_gestures(self):
        """Test dual-hand gestures"""
        if self.commentator:
            await self.commentator.speak_and_wait("Generating algorithm to test gesture repertoire")
        
        print("\n🙌 Testing Gestures...")
        
        gestures = [
            {'name': 'clap_ready', 'comment': 'Preparing for applause'},
            {'name': 'heart_shape', 'comment': 'Making hearts, not war'},
            {'name': 'welcome', 'comment': 'Rolling out the red carpet'},
            {'name': 'prayer', 'comment': 'Seeking divine servo intervention'}
        ]
        
        for gesture in gestures:
            try:
                if self.commentator:
                    await self.commentator.speak_and_wait(f"Executing {gesture['name']}. {gesture['comment']}!")
                
                success = await self.controller.execute_gesture(gesture['name'], speed=2.0)
                self.log_result(f"Gesture: {gesture['name']}", success)
                
                if success and self.commentator:
                    success_comments = [
                        "Gesture executed flawlessly!",
                        "Maxi nailed it!",
                        "Perfect form detected!",
                        "Gesture mastery achieved!"
                    ]
                    await self.commentator.speak_and_wait(random.choice(success_comments))
                elif self.commentator:
                    await self.commentator.speak_and_wait(f"Gesture failed. Maxi needs more practice!")
                
                await asyncio.sleep(2.5)
                
            except Exception as e:
                self.log_result(f"Gesture: {gesture['name']}", False, str(e))
                if self.commentator:
                    await self.commentator.speak_and_wait(f"Gesture crashed. Someone pulled the wrong wire!")
    
    async def test_wave_sequence(self):
        """Test wave pattern"""
        if self.commentator:
            await self.commentator.speak_and_wait("Generating algorithm to test wave sequence")
        
        print("\n👋 Testing Wave Sequence...")
        
        # Simple wave: fingers closing in sequence
        wave_sequence = [
            (4, 90), (3, 90), (2, 90), (1, 90), (0, 90),  # Right hand close
            (0, 0), (1, 0), (2, 0), (3, 0), (4, 0)       # Right hand open
        ]
        
        try:
            if self.commentator:
                await self.commentator.speak_and_wait("Executing right hand wave. Say hello to Maxi!")
            
            success = True
            for channel, angle in wave_sequence:
                finger_name = self.FINGER_NAMES[channel]
                try:
                    await self.controller.set_servo(channel, angle, speed=2.0)
                    await asyncio.sleep(0.3)
                except Exception:
                    success = False
                    if self.commentator:
                        await self.commentator.speak_and_wait(f"{finger_name} got stuck during wave!")
                    break
            
            self.log_result("Wave Sequence", success)
            
            if success and self.commentator:
                await self.commentator.speak_and_wait("Wave completed! Maxi says goodbye!")
            
        except Exception as e:
            self.log_result("Wave Sequence", False, str(e))
            if self.commentator:
                await self.commentator.speak_and_wait("Wave sequence crashed. Maxi's social skills need work!")
    
    async def run_all_tests(self):
        """Run complete test suite"""
        if self.commentator:
            await self.commentator.speak_and_wait("Welcome to Maxi's comprehensive hand testing protocol!")
        
        print("🚀 Starting Maxi's Hand Test Suite")
        print("=" * 40)
        
        await self.test_connection()
        await self.test_individual_servos()  # All fingers
        await self.test_numbers()
        await self.test_gestures()
        await self.test_wave_sequence()
        
        # Print summary
        print("\n" + "=" * 40)
        print("📊 TEST SUMMARY")
        print("=" * 40)
        
        total = len(self.test_results)
        passed = sum(1 for r in self.test_results if r["success"])
        failed = total - passed
        success_rate = (passed/total*100) if total > 0 else 0
        
        print(f"Total Tests: {total}")
        print(f"Passed: ✅ {passed}")
        print(f"Failed: ❌ {failed}")
        print(f"Success Rate: {success_rate:.1f}%")
        
        if self.commentator:
            if success_rate >= 90:
                await self.commentator.speak_and_wait(f"Outstanding! {success_rate:.1f}% success rate. Maxi is a servo superstar!")
            elif success_rate >= 70:
                await self.commentator.speak_and_wait(f"Good job! {success_rate:.1f}% success. Maxi is mostly functional!")
            else:
                await self.commentator.speak_and_wait(f"Uh oh! Only {success_rate:.1f}% success. Maxi needs serious maintenance!")
        
        if failed > 0:
            print("\n❌ Failed Tests:")
            for result in self.test_results:
                if not result["success"]:
                    print(f"  • {result['test']}: {result['details']}")
        
        return passed == total

    async def run_specific_test(self, test_type: str):
        """Run specific test based on command"""
        test_map = {
            'connection': self.test_connection,
            'right': lambda: self.test_individual_servos(self.RIGHT_HAND),
            'left': lambda: self.test_individual_servos(self.LEFT_HAND),
            'both': lambda: self.test_individual_servos(self.ALL_CHANNELS),
            'numbers': self.test_numbers,
            'gestures': self.test_gestures,
            'wave': self.test_wave_sequence,
            'all': self.run_all_tests
        }
        
        if test_type in test_map:
            await test_map[test_type]()
        else:
            print(f"Unknown test type: {test_type}")
            print(f"Available tests: {', '.join(test_map.keys())}")

async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Maxi's Hand Testing Protocol")
    parser.add_argument('--test', default='all', help='Test type to run')
    parser.add_argument('--host', help='ESP32 host address')
    parser.add_argument('--port', type=int, default=81, help='ESP32 port')
    parser.add_argument('--no-tts', action='store_true', help='Disable TTS commentary')
    
    args = parser.parse_args()
    
    test_suite = MaxiTestSuite(
        host=args.host,
        port=args.port,
        enable_tts=not args.no_tts
    )
    
    try:
        await test_suite.setup()
        await test_suite.run_specific_test(args.test)
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
    finally:
        await test_suite.cleanup()

if __name__ == "__main__":
    asyncio.run(main())