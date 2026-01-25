# finger_controller_api.py
"""
Enhanced Raspberry Pi Finger Controller API for Maxi AI Robot Hand
Controls servo motors through PCA9685 with calibrated angles and smart state management
Runs on Raspberry Pi and provides REST API for finger control + CALIBRATION

Author: Mohammed Kaka / Maxeeton Technology
Date: 2025-08-14
Updated: 2025-08-15 - Added calibration endpoints
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from functools import wraps
from adafruit_pca9685 import PCA9685
from board import SCL, SDA
import busio
import json
import os
import time
import asyncio
import threading
from pathlib import Path
from datetime import datetime
import traceback
from typing import Dict, List, Optional, Tuple

app = Flask(__name__)

# --- Security Configuration ---
# API Key for authentication (load from environment variable)
API_KEY = os.getenv("MAXI_HAND_API_KEY",
                    "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6")

# Simulation mode (for testing without hardware)
SIMULATION_MODE = os.getenv("SIMULATION_MODE", "false").lower() == "true"

# CORS Configuration - Allow Railway domain and localhost
ALLOWED_ORIGINS = [
    "https://web-production-0cb67.up.railway.app",  # Railway production
    "http://localhost:5002",  # Local development
    "http://127.0.0.1:5002",  # Local development alternative
]

# Add more origins from environment variable if provided
EXTRA_ORIGINS = os.getenv("ALLOWED_ORIGINS", "")
if EXTRA_ORIGINS:
    ALLOWED_ORIGINS.extend([origin.strip()
                           for origin in EXTRA_ORIGINS.split(",")])

# Enable CORS with specific origins
CORS(app, origins=ALLOWED_ORIGINS, supports_credentials=True)

print(f"🔒 CORS enabled for origins: {ALLOWED_ORIGINS}")
print(
    f"🔑 API Key authentication: {'ENABLED' if API_KEY != 'your-secure-api-key-here-change-me' else 'USING DEFAULT KEY - CHANGE THIS!'}")

if SIMULATION_MODE:
    print("⚠️  SIMULATION MODE ENABLED - Hardware will not be initialized")
    print("   This is useful for testing without I2C hardware connected")

# --- Servo Configuration ---
SERVO_MIN_PULSE = 500  # microseconds
SERVO_MAX_PULSE = 2500  # microseconds
PWM_FREQ = 50  # Hz

# --- Servo Channel Mapping (matches pi_hand_calibrator.py) ---
SERVO_CHANNELS = {
    "left": {
        "thumb": 0,
        "index": 1,
        "majeure": 2,
        "ringfinger": 3,
        "pinky": 4,
        "wrist": 5
    },
    "right": {
        "thumb": 6,
        "index": 7,
        "majeure": 8,
        "ringfinger": 9,
        "pinky": 10,
        "wrist": 11
    }
}

# Default calibration ranges for new installations
DEFAULT_RANGES = {
    "left": {
        "thumb": {"min": 20, "max": 85},
        "index": {"min": 10, "max": 85},
        "majeure": {"min": 11, "max": 85},
        "ringfinger": {"min": 20, "max": 85},
        "pinky": {"min": 20, "max": 85},
        "wrist": {"min": 20, "max": 160}
    },
    "right": {
        "thumb": {"min": 20, "max": 85},
        "index": {"min": 20, "max": 85},
        "majeure": {"min": 20, "max": 85},
        "ringfinger": {"min": 20, "max": 85},
        "pinky": {"min": 20, "max": 85},
        "wrist": {"min": 20, "max": 160}
    }
}

# --- Global Variables ---
pca = None
# Start with closed positions (human-like initial state)
current_positions = {
    "left": {"thumb": 90, "index": 90, "majeure": 90, "ringfinger": 90, "pinky": 90, "wrist": 80},
    "right": {"thumb": 90, "index": 90, "majeure": 90, "ringfinger": 90, "pinky": 90, "wrist": 80}
}
calibration_data = {}
system_status = {
    "initialized": False,
    "hardware_connected": False,
    "last_error": None,
    "total_movements": 0,
    "startup_time": None,
    "calibration_saved": False,
    "use_saved_calibration": False
}

# Files for calibration and state
CALIBRATION_FILE = "hand_calibration.json"
STATE_FILE = "hand_state.json"


class EnhancedFingerControllerAPI:
    """Enhanced finger controller class with smart state management and calibration."""

    def __init__(self):
        self.pca = None
        self.calibration_file = CALIBRATION_FILE
        self.state_file = STATE_FILE
        self.emergency_stop_active = False
        self.movement_lock = threading.Lock()
        # Enhanced state tracking
        self.finger_states = {
            "left": {"thumb": 0, "index": 0, "majeure": 0, "ringfinger": 0, "pinky": 0},
            "right": {"thumb": 0, "index": 0, "majeure": 0, "ringfinger": 0, "pinky": 0}
        }
        self.movement_queue = []

    def initialize_hardware(self) -> bool:
        """Initialize PCA9685 hardware controller."""
        # Skip hardware initialization if in simulation mode
        if SIMULATION_MODE:
            print("🎭 Simulation mode - skipping hardware initialization")
            system_status["hardware_connected"] = False
            system_status["simulation_mode"] = True
            system_status["startup_time"] = datetime.now().isoformat()
            return True

        try:
            print("🔧 Initializing PCA9685 hardware controller...")

            # Initialize I2C and PCA9685
            i2c = busio.I2C(SCL, SDA)
            self.pca = PCA9685(i2c)
            self.pca.frequency = PWM_FREQ

            print(f"✅ PCA9685 initialized at {PWM_FREQ}Hz")
            system_status["hardware_connected"] = True
            system_status["simulation_mode"] = False
            system_status["startup_time"] = datetime.now().isoformat()

            return True

        except Exception as e:
            error_msg = f"Hardware initialization failed: {str(e)}"
            print(f"❌ {error_msg}")
            print(traceback.format_exc())
            system_status["last_error"] = error_msg
            system_status["hardware_connected"] = False
            return False

    def load_calibration(self) -> bool:
        """Load servo calibration angles from JSON file."""
        global calibration_data

        try:
            if not os.path.exists(self.calibration_file):
                print(
                    f"⚠️ Calibration file not found, using defaults: {self.calibration_file}")
                calibration_data = DEFAULT_RANGES.copy()
                system_status["calibration_saved"] = False
                return True

            with open(self.calibration_file, 'r') as f:
                calibration_data = json.load(f)

            # Validate calibration structure
            required_hands = ["left", "right"]
            required_joints = ["thumb", "index",
                               "majeure", "ringfinger", "pinky", "wrist"]

            for hand in required_hands:
                if hand not in calibration_data:
                    raise ValueError(f"Missing {hand} hand in calibration")

                for joint in required_joints:
                    if joint not in calibration_data[hand]:
                        print(
                            f"⚠️ Missing {joint} in {hand} hand calibration, using default")
                        calibration_data[hand][joint] = DEFAULT_RANGES[hand][joint].copy(
                        )

                    joint_data = calibration_data[hand][joint]
                    if "min" not in joint_data or "max" not in joint_data:
                        print(
                            f"⚠️ Missing min/max values for {hand} {joint}, using default")
                        calibration_data[hand][joint] = DEFAULT_RANGES[hand][joint].copy(
                        )

            print("✅ Calibration data loaded successfully")
            print(f"📊 Left hand joints: {len(calibration_data['left'])}")
            print(f"📊 Right hand joints: {len(calibration_data['right'])}")
            system_status["calibration_saved"] = True

            return True

        except Exception as e:
            error_msg = f"Failed to load calibration: {str(e)}"
            print(f"❌ {error_msg}")
            print(traceback.format_exc())
            system_status["last_error"] = error_msg
            # Use defaults on error
            calibration_data = DEFAULT_RANGES.copy()
            system_status["calibration_saved"] = False
            return True

    def save_calibration(self) -> bool:
        """Save current calibration data to JSON file."""
        try:
            with open(self.calibration_file, 'w') as f:
                json.dump(calibration_data, f, indent=2)

            system_status["calibration_saved"] = True
            print("✅ Calibration saved successfully")
            return True

        except Exception as e:
            error_msg = f"Failed to save calibration: {str(e)}"
            print(f"❌ {error_msg}")
            system_status["last_error"] = error_msg
            return False

    def load_state(self) -> dict:
        """Load system state from file."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {"calibration_saved": False, "use_saved_calibration": False}

    def save_state(self, state: dict) -> bool:
        """Save system state to file."""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
            return True
        except Exception as e:
            print(f"❌ Error saving state: {e}")
            return False

    def pulse_to_duty_cycle_us(self, pulse_us: int) -> int:
        """Convert pulse in microseconds to 16-bit duty cycle."""
        try:
            period_us = 1_000_000 / PWM_FREQ
            duty_cycle = int((pulse_us / period_us) * 65535)
            return max(0, min(65535, duty_cycle))
        except Exception as e:
            print(f"⚠️ Pulse conversion error: {e}")
            return 0

    def set_servo_angle(self, channel: int, angle: int) -> bool:
        """Set servo to specific angle with safety checks."""
        if self.emergency_stop_active:
            print("🛑 Emergency stop active - servo movement blocked")
            return False

        # If in simulation mode, just log and return success
        if SIMULATION_MODE:
            print(f"🎭 [SIMULATION] Set channel {channel} to {angle}°")
            return True

        if not self.pca:
            print("❌ PCA9685 not initialized")
            return False

        try:
            # Clamp angle to valid range
            angle = max(0, min(180, angle))

            # Convert angle to pulse width
            pulse = SERVO_MIN_PULSE + \
                (angle / 180.0) * (SERVO_MAX_PULSE - SERVO_MIN_PULSE)
            duty_cycle = self.pulse_to_duty_cycle_us(int(pulse))

            # Set PWM duty cycle
            self.pca.channels[channel].duty_cycle = duty_cycle

            return True

        except Exception as e:
            error_msg = f"Servo movement error (channel {channel}, angle {angle}): {str(e)}"
            print(f"❌ {error_msg}")
            system_status["last_error"] = error_msg
            return False

    def get_calibrated_position(self, hand: str, joint: str, state: str) -> int:
        """Get calibrated position for joint state (open/closed)."""
        try:
            if hand not in calibration_data or joint not in calibration_data[hand]:
                print(f"⚠️ No calibration for {hand} {joint}")
                return 20 if state == "open" else 90

            joint_cal = calibration_data[hand][joint]

            if state == "open":
                return joint_cal["min"]
            elif state == "closed":
                return joint_cal["max"]
            else:
                raise ValueError(f"Invalid state: {state}")

        except Exception as e:
            print(f"⚠️ Calibration lookup error: {e}")
            return 20 if state == "open" else 90

    def move_finger_smooth(self, hand: str, finger: str, target_state: str, duration_ms: int = 200) -> bool:
        """Move finger smoothly to target state with enhanced state tracking."""
        try:
            with self.movement_lock:
                if self.emergency_stop_active:
                    return False

                # Check if finger is already in target state
                current_state = self.finger_states[hand][finger]
                target_value = 1 if target_state == "open" else 0

                if current_state == target_value:
                    print(f"👆 {hand} {finger} already in {target_state} state")
                    return True

                # Get servo channel and positions
                channel = SERVO_CHANNELS[hand][finger]
                current_angle = current_positions[hand][finger]
                target_angle = self.get_calibrated_position(
                    hand, finger, target_state)

                # Calculate movement steps
                # ~67Hz update rate for smoother movement
                steps = max(1, duration_ms // 15)
                angle_diff = target_angle - current_angle

                print(
                    f"🤖 Moving {hand} {finger}: {current_angle}° → {target_angle}° in {steps} steps")

                for step in range(steps + 1):
                    if self.emergency_stop_active:
                        print("🛑 Movement stopped by emergency stop")
                        return False

                    # Enhanced easing function
                    progress = step / steps if steps > 0 else 1.0
                    eased_progress = self.ease_in_out_cubic(progress)

                    # Calculate interpolated angle
                    current_step_angle = current_angle + \
                        (angle_diff * eased_progress)

                    # Set servo position
                    if not self.set_servo_angle(channel, int(current_step_angle)):
                        return False

                    # Shorter delay for smoother movement
                    time.sleep(0.015)  # ~67Hz

                # Update position and state tracking
                current_positions[hand][finger] = target_angle
                self.finger_states[hand][finger] = target_value
                system_status["total_movements"] += 1

                return True

        except Exception as e:
            error_msg = f"Smooth movement error: {str(e)}"
            print(f"❌ {error_msg}")
            system_status["last_error"] = error_msg
            return False

    def move_joint_to_angle(self, hand: str, joint: str, angle: int) -> bool:
        """Move joint to specific angle (used for calibration)."""
        try:
            if self.emergency_stop_active:
                return False

            if hand not in SERVO_CHANNELS or joint not in SERVO_CHANNELS[hand]:
                return False

            channel = SERVO_CHANNELS[hand][joint]
            success = self.set_servo_angle(channel, angle)

            if success:
                current_positions[hand][joint] = angle
                system_status["total_movements"] += 1

            return success

        except Exception as e:
            error_msg = f"Joint movement error: {str(e)}"
            print(f"❌ {error_msg}")
            system_status["last_error"] = error_msg
            return False

    def ease_in_out_cubic(self, t: float) -> float:
        """Cubic easing function for smooth servo movement."""
        if t < 0.5:
            return 4 * t * t * t
        else:
            return 1 - pow(-2 * t + 2, 3) / 2

    def show_number_on_hand(self, hand: str, number: int, duration_ms: int = 250) -> bool:
        """Show a number (0-10) on specified hand using smart finger counting."""
        try:
            if not 0 <= number <= 10:
                raise ValueError(
                    f"Number must be 0-10 for single hand, got {number}")

            print(f"🔢 Showing number {number} on {hand} hand")

            if number <= 5:
                # Single hand counting (0-5)
                finger_order = ["index", "majeure",
                                "ringfinger", "pinky", "thumb"]

                # Close all fingers first
                for finger in finger_order:
                    if self.finger_states[hand][finger] == 1:
                        self.move_finger_smooth(
                            hand, finger, "closed", duration_ms // 5)
                        time.sleep(0.05)

                # Open required fingers
                for i in range(number):
                    if not self.move_finger_smooth(hand, finger_order[i], "open", duration_ms):
                        return False
                    time.sleep(0.08)
            else:
                # For 6-10, use both hands or extended gestures
                # Open all fingers on primary hand (5)
                finger_order = ["index", "majeure",
                                "ringfinger", "pinky", "thumb"]
                for finger in finger_order:
                    self.move_finger_smooth(
                        hand, finger, "open", duration_ms // 6)
                    time.sleep(0.05)

                # Show additional count on opposite hand
                other_hand = "right" if hand == "left" else "left"
                additional = number - 5
                for i in range(additional):
                    if not self.move_finger_smooth(other_hand, finger_order[i], "open", duration_ms):
                        return False
                    time.sleep(0.08)

            print(f"✅ Successfully showed {number}")
            return True

        except Exception as e:
            error_msg = f"Number display error: {str(e)}"
            print(f"❌ {error_msg}")
            system_status["last_error"] = error_msg
            return False

    def close_all_hands(self) -> bool:
        """Close all fingers on both hands intelligently."""
        try:
            print("🤲 Closing all hands intelligently")

            fingers = ["thumb", "index", "majeure", "ringfinger", "pinky"]
            success = True

            # Close both hands simultaneously with smart transitions
            for hand in ["left", "right"]:
                for finger in fingers:
                    # Only close open fingers
                    if self.finger_states[hand][finger] == 1:
                        finger_success = self.move_finger_smooth(
                            hand, finger, "closed", 150)
                        success &= finger_success
                        time.sleep(0.03)  # Brief delay

            print(
                f"✅ All hands closed {'successfully' if success else 'with some issues'}")
            return success

        except Exception as e:
            error_msg = f"Close all hands error: {str(e)}"
            print(f"❌ {error_msg}")
            system_status["last_error"] = error_msg
            return False

    def clear_hand(self, hand: str) -> bool:
        """Reset hand to closed position."""
        try:
            print(f"🤚 Clearing {hand} hand to closed position")

            fingers = ["thumb", "index", "majeure", "ringfinger", "pinky"]
            success = True

            for finger in fingers:
                if self.finger_states[hand][finger] == 1:  # Only close open fingers
                    finger_success = self.move_finger_smooth(
                        hand, finger, "closed", 150)
                    success &= finger_success
                    time.sleep(0.05)

            print(f"✅ {hand} hand cleared to closed position")
            return success

        except Exception as e:
            error_msg = f"Hand clearing error: {str(e)}"
            print(f"❌ {error_msg}")
            system_status["last_error"] = error_msg
            return False

    def set_initial_closed_state(self) -> bool:
        """Set initial state with all fingers closed."""
        try:
            print("🤲 Setting initial closed state for all fingers")

            joints = ["thumb", "index", "majeure",
                      "ringfinger", "pinky", "wrist"]
            success = True

            for hand in ["left", "right"]:
                for joint in joints:
                    # Set to closed position or neutral for wrist
                    if joint == "wrist":
                        target_angle = 80  # Neutral wrist position
                    else:
                        target_angle = self.get_calibrated_position(
                            hand, joint, "closed")

                    channel = SERVO_CHANNELS[hand][joint]

                    if self.set_servo_angle(channel, target_angle):
                        current_positions[hand][joint] = target_angle
                        if joint != "wrist":
                            self.finger_states[hand][joint] = 0  # Closed state
                    else:
                        success = False

                    time.sleep(0.05)  # Small delay between movements

            print(
                f"✅ Initial closed state {'set successfully' if success else 'set with issues'}")
            return success

        except Exception as e:
            error_msg = f"Initial state error: {str(e)}"
            print(f"❌ {error_msg}")
            system_status["last_error"] = error_msg
            return False

    def emergency_stop(self) -> bool:
        """Emergency stop - immediately disable all servos."""
        try:
            print("🚨 EMERGENCY STOP ACTIVATED")
            self.emergency_stop_active = True

            if self.pca:
                # Stop all PWM channels
                for channel in range(16):
                    self.pca.channels[channel].duty_cycle = 0

            # Reset state tracking to closed
            for hand in ["left", "right"]:
                for finger in ["thumb", "index", "majeure", "ringfinger", "pinky"]:
                    self.finger_states[hand][finger] = 0

            system_status["last_error"] = "Emergency stop activated"
            print("🛑 All servos stopped")
            return True

        except Exception as e:
            error_msg = f"Emergency stop error: {str(e)}"
            print(f"❌ {error_msg}")
            system_status["last_error"] = error_msg
            return False

    def reset_emergency_stop(self) -> bool:
        """Reset emergency stop and restore normal operation."""
        try:
            print("🔄 Resetting emergency stop")
            self.emergency_stop_active = False

            # Set to safe closed position
            success = self.set_initial_closed_state()

            if success:
                print("✅ Emergency stop reset - normal operation restored")
            else:
                print("⚠️ Emergency stop reset but some movements failed")

            return success

        except Exception as e:
            error_msg = f"Emergency stop reset error: {str(e)}"
            print(f"❌ {error_msg}")
            system_status["last_error"] = error_msg
            return False

    def get_finger_states(self) -> Dict:
        """Get current finger states (0=closed, 1=open)."""
        return {
            "finger_states": self.finger_states,
            "current_positions": current_positions,
            "timestamp": datetime.now().isoformat()
        }

    # CALIBRATION PRESET FUNCTIONS
    def preset_calibrate(self, hand: str) -> bool:
        """Move hand to calibration position (all joints to min)."""
        try:
            joints = ["thumb", "index", "majeure",
                      "ringfinger", "pinky", "wrist"]
            for joint in joints:
                if joint == "wrist":
                    angle = 80  # Neutral wrist
                else:
                    angle = calibration_data[hand][joint]["min"]

                success = self.move_joint_to_angle(hand, joint, angle)
                if not success:
                    return False
                time.sleep(0.1)

            return True
        except Exception as e:
            print(f"❌ Calibrate preset error: {e}")
            return False

    def preset_max(self, hand: str) -> bool:
        """Move hand to maximum position (all joints to max)."""
        try:
            joints = ["thumb", "index", "majeure",
                      "ringfinger", "pinky", "wrist"]
            for joint in joints:
                angle = calibration_data[hand][joint]["max"]
                success = self.move_joint_to_angle(hand, joint, angle)
                if not success:
                    return False
                time.sleep(0.1)

            return True
        except Exception as e:
            print(f"❌ Max preset error: {e}")
            return False


# Initialize enhanced controller instance
controller = EnhancedFingerControllerAPI()

# --- Authentication Decorator ---


def require_api_key(f):
    """Decorator to require API key authentication for endpoints."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Get API key from header
        provided_key = request.headers.get("X-API-Key")

        # Check if API key matches
        if provided_key != API_KEY:
            return jsonify({
                "success": False,
                "error": "Unauthorized - Invalid or missing API key",
                "message": "Please provide a valid X-API-Key header"
            }), 401

        return f(*args, **kwargs)

    return decorated_function


# --- Enhanced Flask API Routes ---

@app.route("/status", methods=["GET"])
@require_api_key
def get_status():
    """Get comprehensive system status and diagnostics."""
    return jsonify({
        "status": system_status,
        "current_positions": current_positions,
        "finger_states": controller.finger_states,
        "emergency_stop": controller.emergency_stop_active,
        "calibration_loaded": bool(calibration_data),
        "timestamp": datetime.now().isoformat()
    })

# CALIBRATION ENDPOINTS


@app.route("/get_calibration", methods=["GET"])
@require_api_key
def get_calibration():
    """Get current calibration data and system state."""
    return jsonify({
        "calibration": calibration_data,
        "state": system_status,
        "current_positions": current_positions
    })


@app.route("/save_calibration", methods=["POST"])
@require_api_key
def save_calibration_route():
    """Save current calibration data."""
    success = controller.save_calibration()
    if success:
        system_status["calibration_saved"] = True
        controller.save_state(system_status)

    return jsonify({"success": success})


@app.route("/set_use_calibration", methods=["POST"])
@require_api_key
def set_use_calibration():
    """Set whether to use saved calibration for gestures."""
    try:
        data = request.json
        system_status["use_saved_calibration"] = data.get(
            "use_calibration", False)
        controller.save_state(system_status)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/move", methods=["POST"])
@require_api_key
def move_joint():
    """Move specific joint to angle (for calibration)."""
    try:
        data = request.json
        hand = data.get("hand")
        joint = data.get("joint")
        angle = int(data.get("angle"))

        if hand in SERVO_CHANNELS and joint in SERVO_CHANNELS[hand]:
            success = controller.move_joint_to_angle(hand, joint, angle)
            return jsonify({"success": success})
        return jsonify({"success": False, "error": "Invalid hand or joint"}), 400

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/update_range", methods=["POST"])
@require_api_key
def update_range():
    """Update calibration range for a joint."""
    try:
        data = request.json
        hand = data.get("hand")
        joint = data.get("joint")
        min_val = int(data.get("min"))
        max_val = int(data.get("max"))

        if hand in calibration_data and joint in calibration_data[hand]:
            calibration_data[hand][joint]["min"] = min_val
            calibration_data[hand][joint]["max"] = max_val
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "Invalid hand or joint"}), 400

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/preset", methods=["POST"])
@require_api_key
def preset():
    """Execute calibration presets."""
    try:
        data = request.json
        hand = data.get("hand")
        action = data.get("action")

        if hand not in SERVO_CHANNELS:
            return jsonify({"success": False, "error": "Invalid hand"}), 400

        success = False
        if action in ["calibrate", "rest"]:
            success = controller.preset_calibrate(hand)
        elif action == "max":
            success = controller.preset_max(hand)
        elif action == "stop":
            success = controller.emergency_stop()

        return jsonify({"success": success})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# EXISTING ENDPOINTS


@app.route("/show_number", methods=["POST"])
@require_api_key
def show_number():
    """Show a number using intelligent finger counting."""
    try:
        data = request.json
        hand = data.get("hand", "right")
        number = int(data.get("number", 0))
        duration = int(data.get("duration_ms", 250))

        if hand not in ["left", "right"]:
            return jsonify({"success": False, "error": "Hand must be 'left' or 'right'"}), 400

        if not 0 <= number <= 10:
            return jsonify({"success": False, "error": "Number must be 0-10"}), 400

        success = controller.show_number_on_hand(hand, number, duration)

        return jsonify({
            "success": success,
            "hand": hand,
            "number": number,
            "finger_states": controller.finger_states[hand],
            "timestamp": datetime.now().isoformat()
        })

    except Exception as e:
        error_msg = f"Show number error: {str(e)}"
        print(f"❌ {error_msg}")
        return jsonify({"success": False, "error": error_msg}), 500


@app.route("/close_all_hands", methods=["POST"])
@require_api_key
def close_all_hands():
    """Close all fingers on both hands intelligently."""
    try:
        success = controller.close_all_hands()

        return jsonify({
            "success": success,
            "finger_states": controller.finger_states,
            "timestamp": datetime.now().isoformat()
        })

    except Exception as e:
        error_msg = f"Close all hands error: {str(e)}"
        print(f"❌ {error_msg}")
        return jsonify({"success": False, "error": error_msg}), 500


@app.route("/clear_hands", methods=["POST"])
@require_api_key
def clear_hands():
    """Clear specified hands to closed position."""
    try:
        data = request.json or {}
        hands = data.get("hands", ["left", "right"])

        success = True
        for hand in hands:
            if hand in ["left", "right"]:
                success &= controller.clear_hand(hand)

        return jsonify({
            "success": success,
            "hands_cleared": hands,
            "finger_states": controller.finger_states,
            "timestamp": datetime.now().isoformat()
        })

    except Exception as e:
        error_msg = f"Clear hands error: {str(e)}"
        print(f"❌ {error_msg}")
        return jsonify({"success": False, "error": error_msg}), 500


@app.route("/emergency_stop", methods=["POST"])
@require_api_key
def emergency_stop():
    """Activate emergency stop."""
    success = controller.emergency_stop()
    return jsonify({
        "success": success,
        "emergency_stop_active": controller.emergency_stop_active,
        "finger_states": controller.finger_states,
        "timestamp": datetime.now().isoformat()
    })


@app.route("/reset_emergency", methods=["POST"])
@require_api_key
def reset_emergency():
    """Reset emergency stop."""
    success = controller.reset_emergency_stop()
    return jsonify({
        "success": success,
        "emergency_stop_active": controller.emergency_stop_active,
        "finger_states": controller.finger_states,
        "timestamp": datetime.now().isoformat()
    })


@app.route("/move_finger", methods=["POST"])
@require_api_key
def move_finger():
    """Move specific finger to target state with smart tracking."""
    try:
        data = request.json
        hand = data.get("hand")
        finger = data.get("finger")
        state = data.get("state")  # "open" or "closed"
        duration = int(data.get("duration_ms", 200))

        if not all([hand, finger, state]):
            return jsonify({"success": False, "error": "Missing required parameters"}), 400

        if hand not in SERVO_CHANNELS:
            return jsonify({"success": False, "error": f"Invalid hand: {hand}"}), 400

        if finger not in SERVO_CHANNELS[hand]:
            return jsonify({"success": False, "error": f"Invalid finger: {finger}"}), 400

        if state not in ["open", "closed"]:
            return jsonify({"success": False, "error": "State must be 'open' or 'closed'"}), 400

        success = controller.move_finger_smooth(hand, finger, state, duration)

        return jsonify({
            "success": success,
            "hand": hand,
            "finger": finger,
            "state": state,
            "finger_states": controller.finger_states[hand],
            "timestamp": datetime.now().isoformat()
        })

    except Exception as e:
        error_msg = f"Move finger error: {str(e)}"
        print(f"❌ {error_msg}")
        return jsonify({"success": False, "error": error_msg}), 500


@app.route("/get_finger_states", methods=["GET"])
@require_api_key
def get_finger_states():
    """Get current finger states."""
    return jsonify(controller.get_finger_states())


@app.route("/health", methods=["GET"])
def health_check():
    """Enhanced health check endpoint."""
    return jsonify({
        "status": "healthy" if system_status["hardware_connected"] else "degraded",
        "emergency_stop": controller.emergency_stop_active,
        "total_movements": system_status["total_movements"],
        "timestamp": datetime.now().isoformat()
    })

# GESTURE ENDPOINTS


@app.route("/gesture", methods=["POST"])
@require_api_key
def gesture():
    """Execute predefined gestures."""
    try:
        data = request.json
        hand = data.get("hand", "right")
        gesture_type = data.get("gesture")

        if hand not in SERVO_CHANNELS:
            return jsonify({"success": False, "error": "Invalid hand"}), 400

        if not system_status.get("calibration_saved", False):
            return jsonify({"success": False, "error": "Calibration required"}), 400

        success = False
        if gesture_type == "fist":
            success = controller.make_fist(hand)
        elif gesture_type == "peace":
            success = controller.make_peace(hand)
        elif gesture_type == "wave":
            success = controller.wave(hand)
        elif gesture_type == "count":
            success = controller.count_to_ten(hand)
        else:
            return jsonify({"success": False, "error": "Unknown gesture"}), 400

        return jsonify({
            "success": success,
            "hand": hand,
            "gesture": gesture_type,
            "timestamp": datetime.now().isoformat()
        })

    except Exception as e:
        error_msg = f"Gesture error: {str(e)}"
        print(f"❌ {error_msg}")
        return jsonify({"success": False, "error": error_msg}), 500

    def make_fist(self, hand: str) -> bool:
        """Close all fingers to make a fist."""
        try:
            print(f"👊 Making fist with {hand} hand")
            fingers = ["thumb", "index", "majeure", "ringfinger", "pinky"]
            success = True

            for finger in fingers:
                finger_success = self.move_finger_smooth(
                    hand, finger, "closed", 150)
                success &= finger_success
                time.sleep(0.1)

            return success
        except Exception as e:
            print(f"❌ Fist gesture error: {e}")
            return False

    def make_peace(self, hand: str) -> bool:
        """Make peace sign (index and middle finger up)."""
        try:
            print(f"✌️ Making peace sign with {hand} hand")

            # First close all fingers
            fingers = ["thumb", "index", "majeure", "ringfinger", "pinky"]
            for finger in fingers:
                self.move_finger_smooth(hand, finger, "closed", 100)
                time.sleep(0.05)

            time.sleep(0.3)

            # Open index and majeure
            success = True
            success &= self.move_finger_smooth(hand, "index", "open", 200)
            time.sleep(0.1)
            success &= self.move_finger_smooth(hand, "majeure", "open", 200)

            return success
        except Exception as e:
            print(f"❌ Peace gesture error: {e}")
            return False

    def wave(self, hand: str) -> bool:
        """Perform waving gesture."""
        try:
            print(f"👋 Waving with {hand} hand")

            # Open all fingers first
            fingers = ["thumb", "index", "majeure", "ringfinger", "pinky"]
            for finger in fingers:
                self.move_finger_smooth(hand, finger, "open", 150)
                time.sleep(0.05)

            # Wave with wrist if available
            if "wrist" in SERVO_CHANNELS[hand]:
                wrist_center = 80
                for _ in range(3):  # 3 waves
                    self.move_joint_to_angle(hand, "wrist", wrist_center - 20)
                    time.sleep(0.3)
                    self.move_joint_to_angle(hand, "wrist", wrist_center + 20)
                    time.sleep(0.3)

                # Return to center
                self.move_joint_to_angle(hand, "wrist", wrist_center)

            return True
        except Exception as e:
            print(f"❌ Wave gesture error: {e}")
            return False

    def count_to_ten(self, hand: str) -> bool:
        """Perform counting gesture from 1 to 5."""
        try:
            print(f"🔢 Counting 1-5 with {hand} hand")

            for i in range(6):  # 0 to 5
                success = self.show_number_on_hand(hand, i, 200)
                if not success:
                    return False
                time.sleep(1)  # Hold each number

            return True
        except Exception as e:
            print(f"❌ Count gesture error: {e}")
            return False


# Add gesture methods to controller class
controller.make_fist = lambda hand: controller.__class__.make_fist(
    controller, hand)
controller.make_peace = lambda hand: controller.__class__.make_peace(
    controller, hand)
controller.wave = lambda hand: controller.__class__.wave(controller, hand)
controller.count_to_ten = lambda hand: controller.__class__.count_to_ten(
    controller, hand)

# --- Enhanced Initialization ---


def initialize_system():
    """Initialize the enhanced finger controller system."""
    print("🚀 Starting Enhanced Maxi AI Finger Controller API")
    print("=" * 60)

    # Load state first
    state = controller.load_state()
    system_status.update(state)

    # Load calibration
    if not controller.load_calibration():
        print("❌ Failed to load calibration - system will use defaults")
        return False

    # Initialize hardware
    if not controller.initialize_hardware():
        print("❌ Hardware initialization failed")
        return False

    # Set initial closed state
    print("🤲 Setting initial closed state...")
    if controller.set_initial_closed_state():
        print("✅ Initial closed state set successfully")
    else:
        print("⚠️ Initial closed state setup failed")

    # Test basic movement
    print("🧪 Testing basic movement...")
    if controller.show_number_on_hand("right", 2, 300):
        time.sleep(1)
        controller.clear_hand("right")
        print("✅ Basic movement test passed")
    else:
        print("⚠️ Basic movement test failed")

    system_status["initialized"] = True

    print("=" * 60)
    print("✅ Enhanced Finger Controller API ready!")
    print(f"🌍 Access at: http://0.0.0.0:5001")
    print("🤲 Initial state: All fingers closed (human-like)")
    print("🔧 Calibration endpoints available")
    print("=" * 60)

    return True


# --- Main Entry Point ---
if __name__ == "__main__":
    try:
        if initialize_system():
            app.run(host="0.0.0.0", port=5001, debug=False, threaded=True)
        else:
            print("❌ System initialization failed")
            exit(1)
    except KeyboardInterrupt:
        print("\n🛑 Shutting down finger controller...")
        if controller.pca:
            controller.emergency_stop()
        print("👋 Goodbye!")
    except Exception as e:
        print(f"💥 Fatal error: {str(e)}")
        print(traceback.format_exc())
        exit(1)
