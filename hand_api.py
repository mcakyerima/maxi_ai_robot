from flask import Flask, request, jsonify
from adafruit_pca9685 import PCA9685
from board import SCL, SDA
import busio
import json
import os
import time

app = Flask(__name__)

# --- Constants for MG996R ---
SERVO_MIN_PULSE = 500  # in microseconds
SERVO_MAX_PULSE = 2500  # in microseconds
PWM_FREQ = 50  # Hz

# Setup I2C and PCA9685
i2c = busio.I2C(SCL, SDA)
pca = PCA9685(i2c)
pca.frequency = PWM_FREQ

# Define servo ports for left and right arms
servos = {
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

CALIBRATION_FILE = "inmoov_calibration.json"
STATE_FILE = "inmoov_state.json"

def load_calibration():
    if os.path.exists(CALIBRATION_FILE):
        try:
            with open(CALIBRATION_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return None

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {"calibration_saved": False, "use_saved_calibration": False}

def save_state(state):
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"Error saving state: {e}")

# Load initial state
system_state = load_state()

# Convert pulse in µs to 16-bit duty cycle
def pulse_to_duty_cycle_us(pulse_us):
    period_us = 1_000_000 / PWM_FREQ
    duty_cycle = int((pulse_us / period_us) * 65535)
    return min(max(duty_cycle, 0), 65535)

# Set servo angle
def set_servo_angle(channel, angle):
    angle = max(0, min(180, angle))
    pulse = SERVO_MIN_PULSE + (angle / 180.0) * (SERVO_MAX_PULSE - SERVO_MIN_PULSE)
    pca.channels[channel].duty_cycle = pulse_to_duty_cycle_us(pulse)
    return angle

def stop_all():
    for ch in range(16):
        pca.channels[ch].duty_cycle = 0

# API Endpoints
@app.route("/api/hand/move", methods=["POST"])
def move_hand():
    data = request.json
    arm = data.get("arm", "right")
    joint = data.get("joint")
    angle = data.get("angle")
    
    if joint not in servos[arm]:
        return jsonify({"success": False, "error": "Invalid joint"}), 400
    
    set_servo_angle(servos[arm][joint], angle)
    return jsonify({"success": True})

@app.route("/api/hand/gesture", methods=["POST"])
def perform_gesture():
    data = request.json
    gesture = data.get("gesture")
    arm = data.get("arm", "right")
    number = data.get("number")
    operation = data.get("operation")
    
    calibration = load_calibration()
    if not calibration:
        return jsonify({"success": False, "error": "Calibration not found"}), 400
    
    # Handle arithmetic gestures
    if operation in ["add", "subtract", "multiply", "divide"]:
        num1 = data.get("num1")
        num2 = data.get("num2")
        return perform_arithmetic(arm, operation, num1, num2, calibration)
    
    # Handle number display
    elif number is not None:
        return display_number(arm, number, calibration)
    
    # Handle predefined gestures
    elif gesture:
        if gesture == "fist":
            make_fist(arm, calibration)
        elif gesture == "peace":
            make_peace(arm, calibration)
        elif gesture == "count":
            count_to_ten(arm, calibration)
        elif gesture == "wave":
            wave(arm, calibration)
        else:
            return jsonify({"success": False, "error": "Unknown gesture"}), 400
        
        return jsonify({"success": True})
    
    return jsonify({"success": False, "error": "No gesture specified"}), 400

def perform_arithmetic(arm, operation, num1, num2, calibration):
    """Perform arithmetic operation with hand gestures"""
    try:
        num1 = int(num1)
        num2 = int(num2)
        
        if num1 < 0 or num1 > 10 or num2 < 0 or num2 > 10:
            return jsonify({"success": False, "error": "Numbers must be between 0-10"}), 400
        
        # Display first number
        display_number(arm, num1, calibration)
        time.sleep(1)
        
        # Display operation symbol
        if operation == "add":
            show_plus(arm, calibration)
        elif operation == "subtract":
            show_minus(arm, calibration)
        elif operation == "multiply":
            show_multiply(arm, calibration)
        elif operation == "divide":
            show_divide(arm, calibration)
        
        time.sleep(1)
        
        # Display second number
        display_number(arm, num2, calibration)
        time.sleep(1)
        
        # Calculate and display result
        if operation == "add":
            result = num1 + num2
        elif operation == "subtract":
            result = num1 - num2
        elif operation == "multiply":
            result = num1 * num2
        elif operation == "divide":
            result = num1 // num2 if num2 != 0 else 0
        
        if 0 <= result <= 10:
            display_number(arm, result, calibration)
        else:
            # For results > 10, show some indication
            for _ in range(3):
                display_number(arm, 10, calibration)
                time.sleep(0.5)
                all_to_rest(arm, calibration)
                time.sleep(0.5)
        
        return jsonify({"success": True, "result": result})
    
    except ValueError:
        return jsonify({"success": False, "error": "Invalid numbers"}), 400

def display_number(arm, number, calibration):
    """Show a number (0-10) using fingers"""
    number = int(number)
    if number < 0 or number > 10:
        return False
    
    all_to_rest(arm, calibration)
    
    if number == 0:
        make_fist(arm, calibration)
        return True
    
    fingers = ["thumb", "index", "majeure", "ringfinger", "pinky"]
    
    if number <= 5:
        # Open fingers one by one up to the number
        for i in range(number):
            joint = fingers[i]
            angle = calibration[arm][joint]["min"]
            set_servo_angle(servos[arm][joint], angle)
            time.sleep(0.2)
    else:
        # For 6-10, use thumb as 5 and show remaining fingers
        # Show thumb first (representing 5)
        angle = calibration[arm]["thumb"]["min"]
        set_servo_angle(servos[arm]["thumb"], angle)
        time.sleep(0.2)
        
        # Show remaining fingers (number - 5)
        for i in range(number - 5):
            joint = fingers[i+1]  # Skip thumb
            angle = calibration[arm][joint]["min"]
            set_servo_angle(servos[arm][joint], angle)
            time.sleep(0.2)
    
    return True

def show_plus(arm, calibration):
    """Show plus sign gesture"""
    # Open index and majeure fingers straight
    for joint in ["index", "majeure"]:
        angle = calibration[arm][joint]["min"]
        set_servo_angle(servos[arm][joint], angle)
    
    # Close other fingers
    for joint in ["thumb", "ringfinger", "pinky"]:
        angle = calibration[arm][joint]["max"]
        set_servo_angle(servos[arm][joint], angle)
    
    # Move wrist to center position
    wrist_center = (calibration[arm]["wrist"]["min"] + calibration[arm]["wrist"]["max"]) // 2
    set_servo_angle(servos[arm]["wrist"], wrist_center)
    time.sleep(0.5)

def show_minus(arm, calibration):
    """Show minus sign gesture"""
    # Open just the majeure finger straight
    angle = calibration[arm]["majeure"]["min"]
    set_servo_angle(servos[arm]["majeure"], angle)
    
    # Close other fingers
    for joint in ["thumb", "index", "ringfinger", "pinky"]:
        angle = calibration[arm][joint]["max"]
        set_servo_angle(servos[arm][joint], angle)
    
    # Move wrist to center position
    wrist_center = (calibration[arm]["wrist"]["min"] + calibration[arm]["wrist"]["max"]) // 2
    set_servo_angle(servos[arm]["wrist"], wrist_center)
    time.sleep(0.5)

def show_multiply(arm, calibration):
    """Show multiply sign gesture (crossed fingers)"""
    # Open index and majeure fingers
    for joint in ["index", "majeure"]:
        angle = calibration[arm][joint]["min"]
        set_servo_angle(servos[arm][joint], angle)
    
    # Close other fingers
    for joint in ["thumb", "ringfinger", "pinky"]:
        angle = calibration[arm][joint]["max"]
        set_servo_angle(servos[arm][joint], angle)
    
    # Move wrist to show crossed fingers
    wrist_angle = calibration[arm]["wrist"]["min"] + 20
    set_servo_angle(servos[arm]["wrist"], wrist_angle)
    time.sleep(0.5)

def show_divide(arm, calibration):
    """Show divide sign gesture (peace sign tilted)"""
    # Open index and majeure fingers
    for joint in ["index", "majeure"]:
        angle = calibration[arm][joint]["min"]
        set_servo_angle(servos[arm][joint], angle)
    
    # Close other fingers
    for joint in ["thumb", "ringfinger", "pinky"]:
        angle = calibration[arm][joint]["max"]
        set_servo_angle(servos[arm][joint], angle)
    
    # Tilt wrist to show division symbol
    wrist_angle = calibration[arm]["wrist"]["max"] - 20
    set_servo_angle(servos[arm]["wrist"], wrist_angle)
    time.sleep(0.5)

def make_fist(arm, calibration):
    """Close all fingers to make a fist"""
    for joint in ["thumb", "index", "majeure", "ringfinger", "pinky"]:
        angle = calibration[arm][joint]["max"]
        set_servo_angle(servos[arm][joint], angle)
        time.sleep(0.1)

def make_peace(arm, calibration):
    """Open index and majeure, close others"""
    # First reset all fingers to open position
    all_to_rest(arm, calibration)
    time.sleep(0.5)
    
    # Close thumb, ring finger, and pinky
    for joint in ["thumb", "ringfinger", "pinky"]:
        angle = calibration[arm][joint]["max"]
        set_servo_angle(servos[arm][joint], angle)
        time.sleep(0.1)

def count_to_ten(arm, calibration):
    """Perform counting gesture from 1 to 10"""
    # Start with closed fist
    make_fist(arm, calibration)
    time.sleep(1)
    
    # Count sequence
    count_sequence = [
        ["index"],  # 1
        ["index", "majeure"],  # 2
        ["index", "majeure", "ringfinger"],  # 3
        ["index", "majeure", "ringfinger", "pinky"],  # 4
        ["thumb", "index", "majeure", "ringfinger", "pinky"],  # 5
    ]
    
    for fingers in count_sequence:
        # Reset to fist
        make_fist(arm, calibration)
        time.sleep(0.3)
        
        # Open required fingers
        for finger in fingers:
            angle = calibration[arm][finger]["min"]
            set_servo_angle(servos[arm][finger], angle)
            time.sleep(0.1)
        
        time.sleep(1)  # Hold position
    
    # For 6-10, use both hands or extended gestures
    # For now, just return to rest position
    all_to_rest(arm, calibration)

def wave(arm, calibration):
    """Perform waving gesture"""
    # Start with open hand
    all_to_rest(arm, calibration)
    time.sleep(0.5)
    
    # Wave motion with wrist
    wrist_center = (calibration[arm]["wrist"]["min"] + calibration[arm]["wrist"]["max"]) // 2
    wrist_range = 30  # degrees of wrist movement
    
    for _ in range(3):  # 3 waves
        # Move wrist left
        angle = max(calibration[arm]["wrist"]["min"], wrist_center - wrist_range)
        set_servo_angle(servos[arm]["wrist"], angle)
        time.sleep(0.3)
        
        # Move wrist right
        angle = min(calibration[arm]["wrist"]["max"], wrist_center + wrist_range)
        set_servo_angle(servos[arm]["wrist"], angle)
        time.sleep(0.3)
    
    # Return to center
    set_servo_angle(servos[arm]["wrist"], wrist_center)

def all_to_rest(arm, calibration):
    """Move all joints to rest position"""
    for joint in servos[arm]:
        if joint == "wrist":
            angle = (calibration[arm]["wrist"]["min"] + calibration[arm]["wrist"]["max"]) // 2
        else:
            angle = calibration[arm][joint]["min"]
        set_servo_angle(servos[arm][joint], angle)

@app.route("/api/hand/stop", methods=["POST"])
def stop():
    stop_all()
    return jsonify({"success": True})

@app.route("/api/hand/status", methods=["GET"])
def status():
    return jsonify({
        "status": "ready",
        "calibration_loaded": load_calibration() is not None
    })

# Add these endpoints to hand_api.py (before the if __name__ == "__main__" block)

@app.route("/api/hand/get_calibration", methods=["GET"])
def get_calibration():
    calibration = load_calibration()
    return jsonify({
        "calibration": calibration,
        "state": system_state,
        "current_positions": {}  # Add if you need to track positions
    })

@app.route("/api/hand/set_state", methods=["POST"])
def set_state():
    global system_state
    data = request.json
    if "use_saved_calibration" in data:
        system_state["use_saved_calibration"] = data["use_saved_calibration"]
    save_state(system_state)
    return jsonify({"success": True})


# Update save_calibration endpoint
@app.route("/api/hand/save_calibration", methods=["POST"])
def save_calibration():
    global system_state
    system_state["calibration_saved"] = True
    save_state(system_state)
    
    data = request.json
    try:
        with open(CALIBRATION_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
    

@app.route("/api/hand/update_range", methods=["POST"])
def update_range():
    data = request.json
    arm = data.get("arm")
    joint = data.get("joint")
    min_val = data.get("min")
    max_val = data.get("max")
    
    calibration = load_calibration() or {}
    if arm not in calibration:
        calibration[arm] = {}
    if joint not in calibration[arm]:
        calibration[arm][joint] = {}
    
    calibration[arm][joint]["min"] = min_val
    calibration[arm][joint]["max"] = max_val
    
    try:
        with open(CALIBRATION_FILE, 'w') as f:
            json.dump(calibration, f, indent=2)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

if __name__ == "__main__":
    print("Hand Control API running on http://0.0.0.0:5001")
    app.run(host="0.0.0.0", port=5001, debug=False)