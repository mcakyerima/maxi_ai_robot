from flask import Flask, request, jsonify, render_template_string
from adafruit_pca9685 import PCA9685
from board import SCL, SDA
import busio
import json
import os
import time

app = Flask(__name__)

# --- Constants for MG996R ---
SERVO_MIN_PULSE = 500 # in microseconds
SERVO_MAX_PULSE = 2500 # in microseconds
PWM_FREQ = 50 # Hz

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

# Default calibration ranges
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

# Files for calibration and state
CALIBRATION_FILE = "hand_calibration.json"
STATE_FILE = "hand_state.json"

# Current joint positions
current_positions = {
    "left": {"thumb": 20, "index": 10, "majeure": 11, "ringfinger": 20, "pinky": 20, "wrist": 80},
    "right": {"thumb": 20, "index": 20, "majeure": 20, "ringfinger": 20, "pinky": 20, "wrist": 80}
}

def load_calibration():
    if os.path.exists(CALIBRATION_FILE):
        try:
            with open(CALIBRATION_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return DEFAULT_RANGES.copy()

def save_calibration(ranges):
    try:
        with open(CALIBRATION_FILE, 'w') as f:
            json.dump(ranges, f, indent=2)
    except Exception as e:
        print(f"Error saving calibration: {e}")

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

# Load initial calibration and state
calibration_ranges = load_calibration()
system_state = load_state()

# Convert pulse in µs to 16-bit duty cycle
def pulse_to_duty_cycle_us(pulse_us):
    period_us = 1_000_000 / PWM_FREQ
    duty_cycle = int((pulse_us / period_us) * 65535)
    return min(max(duty_cycle, 0), 65535)

# Set servo angle and track position
def set_servo_angle(channel, angle):
    angle = max(0, min(180, angle))
    pulse = SERVO_MIN_PULSE + (angle / 180.0) * (SERVO_MAX_PULSE - SERVO_MIN_PULSE)
    pca.channels[channel].duty_cycle = pulse_to_duty_cycle_us(pulse)
    return angle

# Get open position for a joint (using calibration if available)
def get_open_position(arm, joint):
        if system_state.get("use_saved_calibration", False):
                if joint == "wrist":
                        return 80
                return calibration_ranges[arm][joint]["min"]
        return 80 if joint == "wrist" else 20

# Get closed position for a joint (using calibration if available)
def get_closed_position(arm, joint):
    if system_state.get("calibration_saved", False):
        return calibration_ranges[arm][joint]["max"]
    return 160 if joint == "wrist" else 180

# Preset positions
def alltovirtual(arm):
        for joint in servos[arm]:
                if joint == "wrist":
                        angle = 80
                elif system_state.get("calibration_saved", False):
                        angle = calibration_ranges[arm][joint]["min"]
                else:
                        angle = 20
                current_positions[arm][joint] = set_servo_angle(servos[arm][joint], angle)

def alltorest(arm):
        for joint in servos[arm]:
                if joint == "wrist":
                        angle = 80
                elif system_state.get("calibration_saved", False):
                        angle = calibration_ranges[arm][joint]["min"]
                else:
                        angle = 20
                current_positions[arm][joint] = set_servo_angle(servos[arm][joint], angle)

def alltomax(arm):
    for joint in servos[arm]:
        if system_state.get("calibration_saved", False):
            angle = calibration_ranges[arm][joint]["max"]
        else:
            angle = 160 if joint == "wrist" else 160
        current_positions[arm][joint] = set_servo_angle(servos[arm][joint], angle)

def stop_all():
    for ch in range(16):
        pca.channels[ch].duty_cycle = 0

# Gesture functions
def make_fist(arm):
    """Close all fingers to make a fist"""
    for joint in ["thumb", "index", "majeure", "ringfinger", "pinky"]:
        angle = get_closed_position(arm, joint)
        current_positions[arm][joint] = set_servo_angle(servos[arm][joint], angle)
        time.sleep(0.1)  # Small delay for smooth movement

def make_peace(arm):
    """Open index and majeure, close others"""
    # First reset all fingers to open position
    alltorest(arm)
    time.sleep(0.5)

    # Close thumb, ring finger, and pinky
    for joint in ["thumb", "ringfinger", "pinky"]:
        angle = get_closed_position(arm, joint)
        current_positions[arm][joint] = set_servo_angle(servos[arm][joint], angle)
        time.sleep(0.1)

def count_to_ten(arm):
    """Perform counting gesture from 1 to 10"""
    # Start with closed fist
    make_fist(arm)
    time.sleep(1)

    # Count sequence
    count_sequence = [
        ["index"],  # 1
        ["index", "majeure"],  # 2
        ["index", "majeure", "ringfinger"],  # 3
        ["index", "majeure", "ringfinger", "pinky"],  # 4
        ["thumb", "index", "majeure", "ringfinger", "pinky"],  # 5
    ]

    for i, fingers in enumerate(count_sequence):
        # Reset to fist
        make_fist(arm)
        time.sleep(0.3)

        # Open required fingers
        for finger in fingers:
            angle = get_open_position(arm, finger)
            current_positions[arm][finger] = set_servo_angle(servos[arm][finger], angle)
            time.sleep(0.1)

        time.sleep(1)  # Hold position

    # For 6-10, use both hands or extended gestures
    # For now, just return to rest position
    alltorest(arm)

def wave(arm):
    """Perform waving gesture"""
    # Start with open hand
    alltorest(arm)
    time.sleep(0.5)

    # Wave motion with wrist
    wrist_center = (calibration_ranges[arm]["wrist"]["min"] + calibration_ranges[arm]["wrist"]["max"]) // 2
    wrist_range = 30  # degrees of wrist movement

    for _ in range(3):  # 3 waves
        # Move wrist left
        angle = max(calibration_ranges[arm]["wrist"]["min"], wrist_center - wrist_range)
        current_positions[arm]["wrist"] = set_servo_angle(servos[arm]["wrist"], angle)
        time.sleep(0.3)

        # Move wrist right
        angle = min(calibration_ranges[arm]["wrist"]["max"], wrist_center + wrist_range)
        current_positions[arm]["wrist"] = set_servo_angle(servos[arm]["wrist"], angle)
        time.sleep(0.3)

    # Return to center
    current_positions[arm]["wrist"] = set_servo_angle(servos[arm]["wrist"], wrist_center)

# Flask routes
@app.route("/")
def index():
    return render_template_string(PAGE_HTML)

@app.route("/get_calibration")
def get_calibration():
    return jsonify({
        "calibration": calibration_ranges,
        "state": system_state,
        "current_positions": current_positions
    })

@app.route("/save_calibration", methods=["POST"])
def save_calibration_route():
    global system_state
    system_state["calibration_saved"] = True
    save_state(system_state)
    save_calibration(calibration_ranges)
    return jsonify({"success": True})

@app.route("/set_use_calibration", methods=["POST"])
def set_use_calibration():
    global system_state
    data = request.json
    system_state["use_saved_calibration"] = data.get("use_calibration", False)
    save_state(system_state)
    return jsonify({"success": True})

@app.route("/move", methods=["POST"])
def move():
    data = request.json
    arm = data.get("arm")
    joint = data.get("joint")
    angle = int(data.get("angle"))
    if arm in servos and joint in servos[arm]:
        current_positions[arm][joint] = set_servo_angle(servos[arm][joint], angle)
        return jsonify({"success": True})
    return jsonify({"success": False}), 400


@app.route("/update_range", methods=["POST"])
def update_range():
    data = request.json
    arm = data.get("arm")
    joint = data.get("joint")
    min_val = int(data.get("min"))
    max_val = int(data.get("max"))

    if arm in calibration_ranges and joint in calibration_ranges[arm]:
        calibration_ranges[arm][joint]["min"] = min_val
        calibration_ranges[arm][joint]["max"] = max_val
        return jsonify({"success": True})
    return jsonify({"success": False}), 400


@app.route("/preset", methods=["POST"])
def preset():
    data = request.json
    arm = data.get("arm")
    action = data.get("action")

    if arm not in servos:
        return jsonify({"success": False}), 400

    if action in ["calibrate", "rest"]:
        alltovirtual(arm)
        current_positions[arm]["wrist"] = set_servo_angle(servos[arm]["wrist"], 80)
    elif action == "max":
        alltomax(arm)
    elif action == "stop":
        stop_all()

    return jsonify({"success": True})


@app.route("/gesture", methods=["POST"])
def gesture():
    data = request.json
    arm = data.get("arm")
    gesture_type = data.get("gesture")

    if arm not in servos:
        return jsonify({"success": False}), 400

    if not system_state.get("use_saved_calibration", False):
        return jsonify({"success": False, "error": "Calibration required"}), 400

    if gesture_type == "fist":
        make_fist(arm)
    elif gesture_type == "peace":
        make_peace(arm)
    elif gesture_type == "count":
        count_to_ten(arm)
    elif gesture_type == "wave":
        wave(arm)
    else:
        return jsonify({"success": False, "error": "Unknown gesture"}), 400

    return jsonify({"success": True})

# HTML UI
PAGE_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>InMoov Enhanced Calibration System</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            background: linear-gradient(135deg, #0a0a0a 0%, #1a1a2e 50%, #16213e 100%);
            color: #00ffcc;
            font-family: "Orbitron", "Arial", sans-serif;
            padding: 20px;
            min-height: 100vh;
            overflow-x: auto;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            display: grid;
            grid-template-columns: 400px 1fr;
            gap: 30px;
            height: calc(100vh - 40px);
        }

        .panel {
            background: linear-gradient(145deg, #1a1a2e, #16213e);
            border: 2px solid #00ffcc;
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 10px 30px rgba(0, 255, 204, 0.1);
            position: relative;
            overflow: hidden;
        }

        .panel.fixed {
            position: sticky;
            top: 20px;
            height: fit-content;
            overflow-y: auto;
            max-height: calc(100vh - 40px);
        }

        .panel.scrollable {
            overflow-y: auto;
        }

        .panel::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 3px;
            background: linear-gradient(90deg, transparent, #00ffcc, transparent);
            animation: scan 2s linear infinite;
        }

        @keyframes scan {
            0% { transform: translateX(-100%); }
            100% { transform: translateX(100%); }
        }

        h2 {
            text-align: center;
            font-size: 28px;
            color: #00ffcc;
            margin-bottom: 30px;
            text-shadow: 0 0 10px rgba(0, 255, 204, 0.5);
        }

        .arm-selector {
            display: flex;
            justify-content: center;
            margin-bottom: 30px;
        }

        .arm-btn {
            background: linear-gradient(45deg, #2a2a3e, #3a3a5e);
            color: #00ffcc;
            border: 2px solid #00ffcc;
            padding: 15px 30px;
            font-size: 18px;
            margin: 0 10px;
            cursor: pointer;
            border-radius: 10px;
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }

        .arm-btn.active {
            background: linear-gradient(45deg, #00ffcc, #00ccaa);
            color: #000;
            box-shadow: 0 0 20px rgba(0, 255, 204, 0.5);
        }

        .preset-controls {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 15px;
            margin-bottom: 30px;
        }

        .gesture-controls {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 15px;
            margin-bottom: 30px;
        }

        .preset-btn, .gesture-btn {
            background: linear-gradient(45deg, #2a2a3e, #3a3a5e);
            color: #00ffcc;
            border: 2px solid #00ffcc;
            padding: 15px;
            font-size: 16px;
            cursor: pointer;
            border-radius: 10px;
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }

        .preset-btn:hover, .gesture-btn:hover {
            background: linear-gradient(45deg, #00ffcc, #00ccaa);
            color: #000;
            box-shadow: 0 0 15px rgba(0, 255, 204, 0.5);
        }

        .gesture-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        .save-btn {
            background: linear-gradient(45deg, #ff6b35, #ff8e53);
            color: #fff;
            border: 2px solid #ff6b35;
            padding: 15px;
            font-size: 16px;
            cursor: pointer;
            border-radius: 10px;
            transition: all 0.3s ease;
            width: 100%;
            margin-bottom: 20px;
        }

        .save-btn:hover {
            box-shadow: 0 0 15px rgba(255, 107, 53, 0.5);
        }

        .joint-control {
            margin-bottom: 40px;
            padding: 20px;
            background: rgba(0, 255, 204, 0.05);
            border-radius: 15px;
            border: 1px solid rgba(0, 255, 204, 0.2);
        }

        .joint-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }

        .joint-name {
            font-size: 20px;
            font-weight: bold;
            text-transform: uppercase;
            color: #00ffcc;
        }

        .joint-value {
            font-size: 18px;
            color: #fff;
            background: rgba(0, 255, 204, 0.1);
            padding: 5px 15px;
            border-radius: 20px;
            border: 1px solid #00ffcc;
        }

        .range-controls {
            display: flex;
            align-items: center;
            gap: 20px;
            margin-bottom: 20px;
        }

        .knob-container {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 10px;
        }

        .knob {
            width: 80px;
            height: 80px;
            border-radius: 50%;
            background: conic-gradient(from 0deg, #00ffcc, #00ccaa, #00ffcc);
            position: relative;
            cursor: pointer;
            transition: all 0.3s ease;
        }

        .knob::before {
            content: '';
            position: absolute;
            top: 50%;
            left: 50%;
            width: 65px;
            height: 65px;
            background: #1a1a2e;
            border-radius: 50%;
            transform: translate(-50%, -50%);
        }

        .knob::after {
            content: '';
            position: absolute;
            top: 12%;
            left: 50%;
            width: 4px;
            height: 25px;
            background: #00ffcc;
            border-radius: 2px;
            transform: translateX(-50%);
            transform-origin: bottom center;
        }

        .knob:hover {
            box-shadow: 0 0 20px rgba(0, 255, 204, 0.5);
        }

        .knob-label {
            font-size: 12px;
            color: #00ffcc;
            text-transform: uppercase;
        }

        .knob-value {
            font-size: 14px;
            color: #fff;
            background: rgba(0, 255, 204, 0.1);
            padding: 2px 8px;
            border-radius: 10px;
            border: 1px solid #00ffcc;
        }

        .main-slider {
            flex: 1;
            -webkit-appearance: none;
            appearance: none;
            height: 8px;
            border-radius: 5px;
            background: linear-gradient(90deg, #2a2a3e, #3a3a5e);
            outline: none;
            border: 1px solid #00ffcc;
        }

        .main-slider::-webkit-slider-thumb {
            -webkit-appearance: none;
            appearance: none;
            width: 25px;
            height: 25px;
            border-radius: 50%;
            background: linear-gradient(45deg, #00ffcc, #00ccaa);
            cursor: pointer;
            box-shadow: 0 0 10px rgba(0, 255, 204, 0.5);
        }

        .main-slider::-moz-range-thumb {
            width: 25px;
            height: 25px;
            border-radius: 50%;
            background: linear-gradient(45deg, #00ffcc, #00ccaa);
            cursor: pointer;
            border: none;
            box-shadow: 0 0 10px rgba(0, 255, 204, 0.5);
        }

        .status-indicator {
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 10px 20px;
            background: rgba(0, 255, 204, 0.1);
            border: 1px solid #00ffcc;
            border-radius: 20px;
            color: #00ffcc;
            font-size: 14px;
            z-index: 1000;
        }

        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0, 0, 0, 0.8);
        }

        .modal-content {
            background: linear-gradient(145deg, #1a1a2e, #16213e);
            margin: 15% auto;
            padding: 30px;
            border: 2px solid #00ffcc;
            border-radius: 20px;
            width: 400px;
            color: #00ffcc;
            text-align: center;
            box-shadow: 0 10px 30px rgba(0, 255, 204, 0.3);
        }

        .modal-buttons {
            display: flex;
            justify-content: space-around;
            margin-top: 30px;
        }

        .modal-btn {
            background: linear-gradient(45deg, #2a2a3e, #3a3a5e);
            color: #00ffcc;
            border: 2px solid #00ffcc;
            padding: 15px 30px;
            font-size: 16px;
            cursor: pointer;
            border-radius: 10px;
            transition: all 0.3s ease;
        }

        .modal-btn:hover {
            background: linear-gradient(45deg, #00ffcc, #00ccaa);
            color: #000;
        }

        .gesture-section {
            margin-bottom: 30px;
        }

        .gesture-section h3 {
            color: #00ffcc;
            margin-bottom: 15px;
            font-size: 20px;
        }

        @media (max-width: 768px) {
            .container {
                grid-template-columns: 1fr;
                height: auto;
            }

            .panel.fixed {
                position: static;
                max-height: none;
            }

            .preset-controls, .gesture-controls {
                grid-template-columns: 1fr;
            }

            .range-controls {
                flex-direction: column;
                gap: 15px;
            }
        }
    </style>
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&display=swap" rel="stylesheet">
</head>
<body>
    <div class="status-indicator">
        <span id="status">System Ready</span>
    </div>

    <!-- Calibration Modal -->
    <div id="calibrationModal" class="modal">
        <div class="modal-content">
            <h3>Calibration Check</h3>
            <p>Use saved calibration for gestures?</p>
            <div class="modal-buttons">
                <button class="modal-btn" onclick="setCalibrationChoice(true)">Yes</button>
                <button class="modal-btn" onclick="setCalibrationChoice(false)">No</button>
            </div>
        </div>
    </div>

    <div class="container">
        <div class="panel fixed">
            <h2>ARM CONTROL SYSTEM</h2>

            <div class="arm-selector">
                <button class="arm-btn active" onclick="selectArm('left')">LEFT ARM</button>
                <button class="arm-btn" onclick="selectArm('right')">RIGHT ARM</button>
            </div>

            <button class="save-btn" onclick="saveCalibration()">SAVE CALIBRATION</button>

            <div class="preset-controls">
                <button class="preset-btn" onclick="sendPreset('calibrate')">CALIBRATE</button>
                <button class="preset-btn" onclick="sendPreset('rest')">REST</button>
                <button class="preset-btn" onclick="sendPreset('max')">MAX</button>
                <button class="preset-btn" onclick="sendPreset('stop')">STOP ALL</button>
            </div>

            <div class="gesture-section">
                <h3>GESTURES</h3>
                <div class="gesture-controls">
                    <button class="gesture-btn" onclick="sendGesture('fist')">FIST</button>
                    <button class="gesture-btn" onclick="sendGesture('peace')">PEACE</button>
                    <button class="gesture-btn" onclick="sendGesture('count')">COUNT 1-5</button>
                    <button class="gesture-btn" onclick="sendGesture('wave')">WAVE</button>
                </div>
            </div>
        </div>

        <div class="panel scrollable">
            <h2>JOINT CALIBRATION</h2>
            <div id="joint-controls"></div>
        </div>
    </div>

    <script>
        let currentArm = 'left';
        let calibrationData = {};
        let systemState = {};
        let currentPositions = {};
        let isDragging = false;
        let currentKnob = null;
        let hasShownModal = false;

        // Initialize the system
        async function init() {
            const response = await fetch('/get_calibration');
            const data = await response.json();
            calibrationData = data.calibration;
            systemState = data.state;
            currentPositions = data.current_positions;
            updateUI();
            updateGestureButtons();
        }

        function selectArm(arm) {
                        currentArm = arm;
                        document.querySelectorAll('.arm-btn').forEach(btn => btn.classList.remove('active'));
                        event.target.classList.add('active');
                        hasShownModal = false;  // Add this line
                        updateUI();
                }

        function updateUI() {
            const container = document.getElementById('joint-controls');
            container.innerHTML = '';

            const joints = ['thumb', 'index', 'majeure', 'ringfinger', 'pinky', 'wrist'];

            joints.forEach(joint => {
                const range = calibrationData[currentArm][joint];
                const currentValue = currentPositions[currentArm][joint] || range.min;

                const jointDiv = document.createElement('div');
                jointDiv.className = 'joint-control';
                jointDiv.innerHTML = `
                    <div class="joint-header">
                        <span class="joint-name">${joint}</span>
                        <span class="joint-value" id="value-${joint}">${currentValue}°</span>
                    </div>
                    <div class="range-controls">
                        <div class="knob-container">
                            <div class="knob" id="min-knob-${joint}"
                                 data-joint="${joint}"
                                 data-type="min"
                                 data-value="${range.min}"
                                 onmousedown="startKnobDrag(event)"
                                 ontouchstart="startKnobDrag(event)">
                            </div>
                            <span class="knob-label">MIN</span>
                            <span class="knob-value" id="min-value-${joint}">${range.min}°</span>
                        </div>
                        <input type="range" class="main-slider"
                               id="slider-${joint}"
                               min="${range.min}"
                               max="${range.max}"
                               value="${currentValue}"
                               oninput="updateJoint('${joint}', this.value)">
                        <div class="knob-container">
                            <div class="knob" id="max-knob-${joint}"
                                 data-joint="${joint}"
                                 data-type="max"
                                 data-value="${range.max}"
                                 onmousedown="startKnobDrag(event)"
                                 ontouchstart="startKnobDrag(event)">
                            </div>
                            <span class="knob-label">MAX</span>
                            <span class="knob-value" id="max-value-${joint}">${range.max}°</span>
                        </div>
                    </div>
                `;
                container.appendChild(jointDiv);

                // Update knob rotations
                updateKnobRotation(`min-knob-${joint}`, range.min, 0, 180);
                updateKnobRotation(`max-knob-${joint}`, range.max, 0, 180);
            });
        }

        function updateKnobRotation(knobId, value, min, max) {
            const knob = document.getElementById(knobId);
            const angle = ((value - min) / (max - min)) * 270 - 135; // 270 degrees range, starting at -135
            knob.style.transform = `rotate(${angle}deg)`;
        }

        function startKnobDrag(event) {
            isDragging = true;
            currentKnob = event.target;
            event.preventDefault();

            document.addEventListener('mousemove', handleKnobDrag);
            document.addEventListener('mouseup', stopKnobDrag);
            document.addEventListener('touchmove', handleKnobDrag);
            document.addEventListener('touchend', stopKnobDrag);
        }

        function handleKnobDrag(event) {
            if (!isDragging || !currentKnob) return;

            const rect = currentKnob.getBoundingClientRect();
            const centerX = rect.left + rect.width / 2;
            const centerY = rect.top + rect.height / 2;

            const clientX = event.clientX || event.touches[0].clientX;
            const clientY = event.clientY || event.touches[0].clientY;

            const angle = Math.atan2(clientY - centerY, clientX - centerX) * 180 / Math.PI;
            let normalizedAngle = angle + 135; // Adjust for starting position

            if (normalizedAngle < 0) normalizedAngle += 360;
            if (normalizedAngle > 270) normalizedAngle = 270;

            const value = Math.round((normalizedAngle / 270) * 180);
            const joint = currentKnob.dataset.joint;
            const type = currentKnob.dataset.type;

            updateKnobValue(joint, type, value);
        }

        function stopKnobDrag() {
            isDragging = false;
            currentKnob = null;
            document.removeEventListener('mousemove', handleKnobDrag);
            document.removeEventListener('mouseup', stopKnobDrag);
            document.removeEventListener('touchmove', handleKnobDrag);
            document.removeEventListener('touchend', stopKnobDrag);
        }

        async function updateKnobValue(joint, type, value) {
            const range = calibrationData[currentArm][joint];

            if (type === 'min') {
                range.min = Math.min(value, range.max - 1);
            } else {
                range.max = Math.max(value, range.min + 1);
            }

            // Update UI
            document.getElementById(`${type}-value-${joint}`).textContent = `${range[type]}°`;
            updateKnobRotation(`${type}-knob-${joint}`, range[type], 0, 180);

            // Update slider range
            const slider = document.getElementById(`slider-${joint}`);
            slider.min = range.min;
            slider.max = range.max;
            slider.value = Math.max(range.min, Math.min(range.max, slider.value));

            // Save to server
            await fetch('/update_range', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    arm: currentArm,
                    joint: joint,
                    min: range.min,
                    max: range.max
                })
            });

            updateStatus(`Updated ${joint} ${type}: ${range[type]}°`);
        }

        async function updateJoint(joint, value) {
            document.getElementById(`value-${joint}`).textContent = `${value}°`;
            currentPositions[currentArm][joint] = parseInt(value);

            await fetch('/move', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    arm: currentArm,
                    joint: joint,
                    angle: parseInt(value)
                })
            });

            updateStatus(`${joint}: ${value}°`);
        }

        async function saveCalibration() {
                        const response = await fetch('/save_calibration', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({})
                        });

                        if (response.ok) {
                                systemState.calibration_saved = true;
                                hasShownModal = false;  // Reset modal flag
                                updateStatus('Calibration saved - Ready for gestures');
                                updateGestureButtons();
                        } else {
                                updateStatus('Failed to save calibration');
                        }
                }
        async function sendPreset(action) {
            await fetch('/preset', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    arm: currentArm,
                    action: action
                })
            });

            updateStatus(`Preset: ${action.toUpperCase()}`);

            // Update current positions and UI after preset
            setTimeout(async () => {
                const response = await fetch('/get_calibration');
                const data = await response.json();
                currentPositions = data.current_positions;
                updateSliderValues();
            }, 100);
        }

        function updateSliderValues() {
            const joints = ['thumb', 'index', 'majeure', 'ringfinger', 'pinky', 'wrist'];
            joints.forEach(joint => {
                const slider = document.getElementById(`slider-${joint}`);
                const value = currentPositions[currentArm][joint];
                if (slider && value !== undefined) {
                    slider.value = value;
                    document.getElementById(`value-${joint}`).textContent = `${value}°`;
                }
            });
        }

        function updateGestureButtons() {
            const gestureButtons = document.querySelectorAll('.gesture-btn');
            // const isCalibrated = systemState.use_saved_calibration;
            const isCalibrated = systemState.calibration_saved;

            gestureButtons.forEach(btn => {
                btn.disabled = !isCalibrated;
                if (!isCalibrated) {
                    btn.title = 'Calibrate hands first';
                } else {
                    btn.title = '';
                }
            });
        }

        async function sendGesture(gestureType) {
                        // Check if calibration modal should be shown
                        if (systemState.calibration_saved && !systemState.use_saved_calibration && !hasShownModal) {
                                showCalibrationModal();
                                return;
                        }

                        if (!systemState.calibration_saved) {
                                updateStatus('Please save calibration first');
                                return;
                        }

                        if (!systemState.use_saved_calibration) {
                                updateStatus('Please enable saved calibration first');
                                return;
                        }

                        updateStatus(`Executing gesture: ${gestureType.toUpperCase()}`);

                        const response = await fetch('/gesture', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                        arm: currentArm,
                                        gesture: gestureType
                                })
                        });

                        if (response.ok) {
                                updateStatus(`Gesture ${gestureType.toUpperCase()} completed`);
                                // Update current positions after gesture
                                setTimeout(async () => {
                                        const response = await fetch('/get_calibration');
                                        const data = await response.json();
                                        currentPositions = data.current_positions;
                                        updateSliderValues();
                                }, 1000);
                        } else {
                                const error = await response.json();
                                updateStatus(`Gesture error: ${error.error}`);
                        }
                }

        function showCalibrationModal() {
            document.getElementById('calibrationModal').style.display = 'block';
        }

        function hideCalibrationModal() {
            document.getElementById('calibrationModal').style.display = 'none';
        }

        async function setCalibrationChoice(useCalibration) {
            hasShownModal = true;
            hideCalibrationModal();

            await fetch('/set_use_calibration', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    use_calibration: useCalibration
                })
            });

            systemState.use_saved_calibration = useCalibration;
            updateGestureButtons();

            if (useCalibration) {
                updateStatus('Using saved calibration for gestures');
            } else {
                updateStatus('Calibrate hands first before using gestures');
            }
        }

        function updateStatus(message) {
            document.getElementById('status').textContent = message;
            setTimeout(() => {
                document.getElementById('status').textContent = 'System Ready';
            }, 3000);
        }

        // Close modal when clicking outside
        window.onclick = function(event) {
            const modal = document.getElementById('calibrationModal');
            if (event.target === modal) {
                hideCalibrationModal();
            }
        }

        // Initialize on page load
        window.addEventListener('load', init);
    </script>
</body>
</html>
'''

if __name__ == "__main__":
    print("InMoov Enhanced Calibration System running on http://0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)