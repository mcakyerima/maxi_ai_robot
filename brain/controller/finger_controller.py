# brain/controller/finger_controller.py
"""
Optimized Finger Controller Wrapper for Maxi AI Robot Hand
Improved timing and performance for natural finger movements
"""

import asyncio
import aiohttp
import json
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime
import os
from pathlib import Path

from utils.logger import log_info, log_error, log_warning


class FingerController:
    """
    Optimized robotic hand controller with improved timing and performance.
    """
    
    def __init__(self, pi_ip: str = None, pi_port: int = 5001, simulation_mode: bool = False):
        """
        Initialize finger controller with Raspberry Pi connection.
        """
        self.pi_ip = pi_ip or os.getenv("RASPBERRY_PI_IP", "192.168.1.100")
        self.pi_port = pi_port
        self.base_url = f"http://{self.pi_ip}:{self.pi_port}"
        self.simulation_mode = simulation_mode
        self.hardware_available = False
        self.connection_status = "disconnected"
        self.last_error = None
        
        # Enhanced state tracking with actual finger positions
        self.current_pose = {"left": [0, 0, 0, 0, 0], "right": [0, 0, 0, 0, 0]}
        self.target_pose = {"left": [0, 0, 0, 0, 0], "right": [0, 0, 0, 0, 0]}
        self.fingers_moving = {"left": [False] * 5, "right": [False] * 5}
        
        # OPTIMIZATION: Reduce connection timeouts for faster responses
        self.connection_timeout = 3.0  # Reduced from 5.0
        self.request_timeout = 5.0     # Reduced from 10.0
        
        log_info(f"FingerController initialized: {self.base_url}")
        
    async def initialize(self) -> bool:
        """
        Initialize connection to Raspberry Pi API and set initial closed state.
        OPTIMIZED: Faster initialization with reduced timeouts.
        """
        if self.simulation_mode:
            log_info("Finger controller running in simulation mode (forced)")
            await self.set_initial_closed_state()
            return False
        
        try:
            log_info(f"Connecting to finger controller at {self.base_url}...")
            
            # OPTIMIZED: Reduced timeout for faster initialization
            timeout = aiohttp.ClientTimeout(total=self.connection_timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{self.base_url}/health") as response:
                    if response.status == 200:
                        data = await response.json()
                        self.hardware_available = True
                        self.connection_status = "connected"
                        
                        # Get detailed status and reset if needed
                        async with session.get(f"{self.base_url}/status") as status_response:
                            if status_response.status == 200:
                                status_data = await status_response.json()
                                emergency = status_data.get("emergency_stop", False)
                                
                                if emergency:
                                    log_warning("Hardware in emergency stop mode - attempting reset...")
                                    await self._reset_emergency_stop()
                        
                        # Set hands to initial closed state
                        await self.set_initial_closed_state()
                        
                        log_info("Finger controller hardware ready!")
                        return True
                    else:
                        raise Exception(f"Health check failed: {response.status}")
                        
        except Exception as e:
            self.last_error = str(e)
            self.hardware_available = False
            self.connection_status = "failed"
            log_warning(f"Hardware connection failed: {e}")
            log_info("Falling back to simulation mode")
            await self.set_initial_closed_state()
            return False
    
    async def set_initial_closed_state(self):
        """Set initial state to all fingers closed (human-like starting position)."""
        try:
            log_info("Setting initial closed state for all fingers")
            
            if self.hardware_available:
                # Use hardware API to close all fingers
                await self._make_api_request("POST", "/close_all_hands")
            
            # Update internal state tracking
            self.current_pose = {"left": [0, 0, 0, 0, 0], "right": [0, 0, 0, 0, 0]}
            self.target_pose = {"left": [0, 0, 0, 0, 0], "right": [0, 0, 0, 0, 0]}
            self.fingers_moving = {"left": [False] * 5, "right": [False] * 5}
            
            log_info("Initial closed state set")
            
        except Exception as e:
            log_error(f"Error setting initial closed state: {e}")
    
    async def _make_api_request(self, method: str, endpoint: str, data: Dict = None) -> Optional[Dict]:
        """
        Make API request to Raspberry Pi with error handling.
        OPTIMIZED: Reduced timeout for faster responses.
        """
        log_info(f"Making API request: {method} {endpoint} with data: {data}")
        if not self.hardware_available:
            log_warning("Hardware not available, skipping API request")
            return None
        
        try:
            # OPTIMIZED: Reduced timeout for faster API responses
            timeout = aiohttp.ClientTimeout(total=self.request_timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                url = f"{self.base_url}{endpoint}"
                
                if method.upper() == "GET":
                    async with session.get(url) as response:
                        if response.status == 200:
                            return await response.json()
                        else:
                            log_error(f"API request failed: {response.status}")
                            return None
                
                elif method.upper() == "POST":
                    headers = {"Content-Type": "application/json"}
                    async with session.post(url, json=data, headers=headers) as response:
                        if response.status == 200:
                            return await response.json()
                        else:
                            log_error(f"API request failed: {response.status}")
                            return None
                            
        except Exception as e:
            log_error(f"API request error: {e}")
            self.last_error = str(e)
            return None
    
    async def _reset_emergency_stop(self) -> bool:
        """Reset emergency stop on hardware."""
        try:
            result = await self._make_api_request("POST", "/reset_emergency")
            if result and result.get("success"):
                log_info("Emergency stop reset successful")
                return True
            else:
                log_warning("Emergency stop reset failed")
                return False
        except Exception as e:
            log_error(f"Emergency stop reset error: {e}")
            return False
    
    async def move_finger_smooth(self, hand: str, finger: str, state: str, duration_ms: int = 180) -> bool:
        """
        Move specific finger smoothly with state tracking.
        OPTIMIZED: Reduced default duration for faster movements.
        """
        try:
            if hand not in ["left", "right"]:
                raise ValueError(f"Invalid hand: {hand}")
            
            finger_names = ["index", "majeure", "ringfinger", "pinky", "thumb"]
            if finger not in finger_names:
                raise ValueError(f"Invalid finger: {finger}")
            
            finger_index = finger_names.index(finger)
            target_value = 1 if state == "open" else 0
            current_value = self.current_pose[hand][finger_index]
            
            # Skip if already in target state
            if current_value == target_value:
                log_info(f"{hand} {finger} already in {state} state")
                return True
            
            log_info(f"Moving {hand} {finger} to {state}")
            
            # Mark finger as moving
            self.fingers_moving[hand][finger_index] = True
            
            try:
                if self.hardware_available:
                    success = await self._hardware_finger_movement(hand, finger, state, duration_ms)
                else:
                    success = await self._simulate_finger_movement(hand, finger, state, duration_ms)
                
                if success:
                    # Update state tracking
                    self.current_pose[hand][finger_index] = target_value
                    self.target_pose[hand][finger_index] = target_value
                
                return success
            
            finally:
                # Always clear moving flag
                self.fingers_moving[hand][finger_index] = False
            
        except Exception as e:
            log_error(f"Error moving finger: {e}")
            return False
    
    async def _hardware_finger_movement(self, hand: str, finger: str, state: str, duration_ms: int) -> bool:
        """Execute single finger movement on hardware."""
        try:
            result = await self._make_api_request("POST", "/move_finger", {
                "hand": hand,
                "finger": finger,
                "state": state,
                "duration_ms": duration_ms
            })
            
            success = result and result.get("success", False)
            if success:
                log_info(f"Hardware {hand} {finger} -> {state}")
            else:
                log_warning(f"Hardware movement failed for {hand} {finger}")
            
            return success
            
        except Exception as e:
            log_error(f"Hardware finger movement error: {e}")
            return False
    
    async def _simulate_finger_movement(self, hand: str, finger: str, state: str, duration_ms: int) -> bool:
        """
        Simulate single finger movement with realistic timing.
        OPTIMIZED: More realistic simulation timing.
        """
        log_info(f"Simulating {hand} {finger} -> {state} over {duration_ms}ms")
        
        # OPTIMIZED: More realistic servo movement simulation
        # Most servos complete movement in 150-200ms
        simulation_time = min(duration_ms / 1000.0, 0.2)  # Cap at 200ms
        await asyncio.sleep(simulation_time)
        
        log_info(f"Simulated {hand} {finger} movement complete")
        return True
    
    async def set_finger_pose(self, hand: str, pose: List[int], duration_ms: int = 300) -> bool:
        """
        Set finger pose for specified hand with intelligent state transitions.
        OPTIMIZED: Improved timing and parallel movements where possible.
        """
        try:
            if hand not in ["left", "right"]:
                raise ValueError(f"Invalid hand: {hand}")
            
            if len(pose) != 5:
                raise ValueError(f"Pose must have 5 values, got {len(pose)}")
            
            # Validate pose values
            for i, value in enumerate(pose):
                if value not in [0, 1]:
                    raise ValueError(f"Pose values must be 0 or 1, got {value} at index {i}")
            
            log_info(f"Setting {hand} hand pose: {pose}")
            
            # Calculate which fingers need to move
            current_pose = self.current_pose[hand]
            finger_names = ["index", "majeure", "ringfinger", "pinky", "thumb"]
            movements_needed = []
            
            for i in range(5):
                if pose[i] != current_pose[i]:
                    state = "open" if pose[i] == 1 else "closed"
                    movements_needed.append((finger_names[i], state))
            
            if not movements_needed:
                log_info(f"{hand} hand already in target pose")
                return True
            
            # OPTIMIZED: Execute movements with better timing
            success = True
            # Reduced individual duration for faster overall execution
            individual_duration = max(120, duration_ms // max(1, len(movements_needed)))
            
            for finger, state in movements_needed:
                finger_success = await self.move_finger_smooth(hand, finger, state, individual_duration)
                success &= finger_success
                # OPTIMIZED: Reduced delay between finger movements
                await asyncio.sleep(0.03)
            
            if success:
                self.current_pose[hand] = pose.copy()
                self.target_pose[hand] = pose.copy()
            
            return success
            
        except Exception as e:
            log_error(f"Error setting finger pose: {e}")
            return False
    
    async def show_number(self, number: int, hand_preference: str = "right") -> bool:
        """
        Show a number (0-10) using finger counting with intelligent state transitions.
        OPTIMIZED: Improved performance for number display.
        """
        try:
            if not 0 <= number <= 10:
                raise ValueError(f"Number must be 0-10, got {number}")
            
            log_info(f"Showing number {number} with {hand_preference} hand preference")
            
            if number == 0:
                # Zero - ensure all fingers are closed
                return await self.close_all_fingers()
            
            elif number <= 5:
                # Show on preferred hand only, close other hand
                other_hand = "left" if hand_preference == "right" else "right"
                
                # Close other hand first if it has open fingers
                if sum(self.current_pose[other_hand]) > 0:
                    await self.set_finger_pose(other_hand, [0, 0, 0, 0, 0], 180)  # OPTIMIZED: Faster
                    await asyncio.sleep(0.05)  # OPTIMIZED: Reduced delay
                
                # Show number on preferred hand
                pose = [1 if i < number else 0 for i in range(5)]
                return await self.set_finger_pose(hand_preference, pose, 250)  # OPTIMIZED: Faster
            
            else:  # number 6-10
                # Use both hands intelligently
                remainder = number - 5
                
                full_hand_pose = [1, 1, 1, 1, 1]
                partial_hand_pose = [1 if i < remainder else 0 for i in range(5)]
                
                other_hand = "left" if hand_preference == "right" else "right"
                
                # OPTIMIZED: Execute both hands with minimal delay
                task1 = self.set_finger_pose(hand_preference, full_hand_pose, 250)
                await asyncio.sleep(0.05)  # OPTIMIZED: Reduced delay
                task2 = self.set_finger_pose(other_hand, partial_hand_pose, 250)
                
                results = await asyncio.gather(task1, task2, return_exceptions=True)
                success = all(r is True for r in results if not isinstance(r, Exception))
                
                return success
                    
        except Exception as e:
            log_error(f"Error showing number {number}: {e}")
            return False
    
    async def set_both_hands(self, left_pose: List[int], right_pose: List[int], 
                           duration_ms: int = 300) -> bool:
        """
        Set pose for both hands with smart coordination.
        OPTIMIZED: Better parallel execution.
        """
        try:
            # OPTIMIZED: Execute both movements with minimal offset
            task1 = self.set_finger_pose("left", left_pose, duration_ms)
            await asyncio.sleep(0.03)  # OPTIMIZED: Minimal offset
            task2 = self.set_finger_pose("right", right_pose, duration_ms)
            
            results = await asyncio.gather(task1, task2, return_exceptions=True)
            
            # Check if all movements succeeded
            success = all(result is True for result in results if not isinstance(result, Exception))
            
            if not success:
                for result in results:
                    if isinstance(result, Exception):
                        log_error(f"Hand movement error: {result}")
            
            return success
            
        except Exception as e:
            log_error(f"Error setting both hands: {e}")
            return False
    
    async def close_all_fingers(self) -> bool:
        """
        Close all fingers intelligently (only close open fingers).
        OPTIMIZED: Faster closing operation.
        """
        try:
            log_info("Closing all fingers intelligently")
            
            if self.hardware_available:
                # Use hardware API if available
                result = await self._make_api_request("POST", "/close_all_hands")
                success = result and result.get("success", False)
            else:
                # Use individual finger control with optimized timing
                success = await self.set_both_hands([0, 0, 0, 0, 0], [0, 0, 0, 0, 0])
            
            if success:
                self.current_pose = {"left": [0, 0, 0, 0, 0], "right": [0, 0, 0, 0, 0]}
                self.target_pose = {"left": [0, 0, 0, 0, 0], "right": [0, 0, 0, 0, 0]}
            
            return success
            
        except Exception as e:
            log_error(f"Error closing fingers: {e}")
            return False
    
    async def emergency_stop(self) -> bool:
        """Emergency stop - immediately stop all servos."""
        try:
            log_warning("Emergency stop activated")
            
            if self.hardware_available:
                result = await self._make_api_request("POST", "/emergency_stop")
                success = result and result.get("success", False)
                if success:
                    log_info("Hardware emergency stop successful")
            else:
                success = True
                log_info("Simulation emergency stop")
            
            # Update internal state
            self.current_pose = {"left": [0, 0, 0, 0, 0], "right": [0, 0, 0, 0, 0]}
            self.target_pose = {"left": [0, 0, 0, 0, 0], "right": [0, 0, 0, 0, 0]}
            self.fingers_moving = {"left": [False] * 5, "right": [False] * 5}
            
            return success
            
        except Exception as e:
            log_error(f"Emergency stop error: {e}")
            return False
    
    async def get_hardware_status(self) -> Dict[str, Any]:
        """Get detailed hardware status from Raspberry Pi."""
        if not self.hardware_available:
            return {
                "connected": False,
                "mode": "simulation",
                "error": self.last_error,
                "current_pose": self.current_pose,
                "fingers_moving": self.fingers_moving
            }
        
        try:
            result = await self._make_api_request("GET", "/status")
            if result:
                return {
                    "connected": True,
                    "mode": "hardware",
                    "pi_status": result.get("status", {}),
                    "emergency_stop": result.get("emergency_stop", False),
                    "current_positions": result.get("current_positions", {}),
                    "calibration_loaded": result.get("calibration_loaded", False),
                    "current_pose": self.current_pose,
                    "fingers_moving": self.fingers_moving
                }
            else:
                return {
                    "connected": False,
                    "mode": "hardware_error",
                    "error": "Failed to get status from Pi",
                    "current_pose": self.current_pose
                }
                
        except Exception as e:
            log_error(f"Status check error: {e}")
            return {
                "connected": False,
                "mode": "hardware_error", 
                "error": str(e),
                "current_pose": self.current_pose
            }
    
    def get_current_pose(self) -> Dict[str, List[int]]:
        """Get current finger pose."""
        return self.current_pose.copy()
    
    def get_target_pose(self) -> Dict[str, List[int]]:
        """Get target finger pose."""
        return self.target_pose.copy()
    
    def is_finger_moving(self, hand: str, finger_index: int) -> bool:
        """Check if specific finger is currently moving."""
        if hand in self.fingers_moving and 0 <= finger_index < 5:
            return self.fingers_moving[hand][finger_index]
        return False
    
    def is_hardware_available(self) -> bool:
        """Check if hardware is available."""
        return self.hardware_available
    
    def get_connection_info(self) -> Dict[str, Any]:
        """Get connection information."""
        return {
            "pi_ip": self.pi_ip,
            "pi_port": self.pi_port,
            "base_url": self.base_url,
            "hardware_available": self.hardware_available,
            "connection_status": self.connection_status,
            "simulation_mode": not self.hardware_available,
            "last_error": self.last_error,
            "current_pose": self.current_pose,
            "fingers_moving": self.fingers_moving
        }


# Factory function for easy integration
def create_finger_controller(pi_ip: str = None, pi_port: int = 5001, 
                           simulation_mode: bool = False) -> FingerController:
    """
    Factory function to create finger controller.
    """
    return FingerController(pi_ip=pi_ip, pi_port=pi_port, simulation_mode=simulation_mode)


# OPTIMIZED: Faster test function
async def test_finger_controller():
    """Test the optimized finger controller."""
    controller = create_finger_controller()
    
    log_info("Testing optimized finger controller...")
    
    # Initialize connection
    await controller.initialize()
    
    # Test showing numbers 0-5 with faster timing
    for i in range(6):
        await controller.show_number(i, "right")
        await asyncio.sleep(1.0)  # Reduced test delay
    
    # Test showing numbers 6-10 with faster timing
    for i in range(6, 11):
        await controller.show_number(i, "right")
        await asyncio.sleep(1.0)  # Reduced test delay
    
    # Test closing all fingers
    await controller.close_all_fingers()
    
    # Get status
    status = await controller.get_hardware_status()
    log_info(f"Hardware status: {status}")
    
    log_info("Optimized finger controller test complete")


if __name__ == "__main__":
    asyncio.run(test_finger_controller())