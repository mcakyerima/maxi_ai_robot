# Stub for servo_controller.py
"""
Servo Controller Module for Maxi AI
Handles direct control of servo motors using PCA9685 driver.
"""
import board
import busio
import time
import logging
from math import cos, pi
from adafruit_pca9685 import PCA9685

logger = logging.getLogger("hardware.servo")

# --- Servo Configuration (MG996R specific) ---
NUM_SERVOS = 16
PWM_FREQUENCY = 50  # Hz (MG996R works best at 50Hz)
SERVO_MIN_PULSE = 500    # µs (MG996R minimum pulse width)
SERVO_MAX_PULSE = 2500   # µs (MG996R maximum pulse width)
SERVO_MID_PULSE = 1500   # µs (MG996R center position)

# Movement constraints (degrees)
SERVO_CONSTRAINTS = {
    # Right arm fingers (0-4)
    0: {'min': 0, 'max': 180, 'start': 0},    # Right thumb
    1: {'min': 0, 'max': 180, 'start': 0},    # Right index
    2: {'min': 0, 'max': 180, 'start': 0},    # Right middle
    3: {'min': 0, 'max': 180, 'start': 0},    # Right ring
    4: {'min': 0, 'max': 180, 'start': 0},    # Right pinky
    5: {'min': -90, 'max': 90, 'start': 0},   # Right wrist (0° is upright)
    6: {'min': -90, 'max': 90, 'start': 0},   # Left wrist (0° is upright)
    # Left arm fingers (7-11)
    7: {'min': 0, 'max': 180, 'start': 0},    # Left thumb
    8: {'min': 0, 'max': 180, 'start': 0},    # Left index
    9: {'min': 0, 'max': 180, 'start': 0},    # Left middle
    10: {'min': 0, 'max': 180, 'start': 0},   # Left ring
    11: {'min': 0, 'max': 180, 'start': 0}    # Left pinky
}

class ServoController:
    """Controls servo motors via PCA9685 PWM controller."""
    
    def __init__(self):
        """Initialize ServoController class."""
        self.pca = None
        self.current_positions = {i: 0 for i in range(NUM_SERVOS)}
        self.is_initialized = False
    
    def initialize(self):
        """Initialize PCA9685 PWM controller."""
        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            self.pca = PCA9685(i2c)
            self.pca.frequency = PWM_FREQUENCY
            self.is_initialized = True
            logger.info("PCA9685 initialized successfully")
            
            # Initialize servos to starting positions
            self.initialize_servos()
            return True
        except Exception as e:
            logger.error(f"PCA9685 initialization failed: {e}")
            return False
    
    def pulse_to_duty_cycle(self, pulse):
        """
        Convert pulse width in µs to 16-bit duty cycle.
        
        Args:
            pulse: Pulse width in microseconds
            
        Returns:
            16-bit duty cycle value (0-65535)
        """
        return min(max(int(pulse * 65535 / (1000000 / PWM_FREQUENCY)), 0), 65535)
    
    def constrain_angle(self, channel, angle):
        """
        Ensure angle stays within safe limits.
        
        Args:
            channel: Servo channel number
            angle: Target angle in degrees
            
        Returns:
            Constrained angle in degrees
        """
        constraints = SERVO_CONSTRAINTS.get(channel, {'min': 0, 'max': 180})
        return max(constraints['min'], min(angle, constraints['max']))
    
    def set_servo_angle(self, channel, angle, immediate=False):
        """
        Set servo angle with smooth movement and safety checks.
        
        Args:
            channel: Servo channel (0-15)
            angle: Target angle in degrees
            immediate: If True, move directly without smoothing
            
        Returns:
            Boolean indicating success
        """
        if not self.is_initialized or channel < 0 or channel >= NUM_SERVOS:
            return False

        # Apply constraints
        angle = self.constrain_angle(channel, angle)
        
        # Calculate pulse width
        if channel in [5, 6]:  # Wrist servos (-90° to 90° range)
            pulse = SERVO_MID_PULSE + (angle * (SERVO_MAX_PULSE - SERVO_MIN_PULSE) / 180)
        else:  # Finger servos (0° to 180° range)
            pulse = SERVO_MIN_PULSE + (angle * (SERVO_MAX_PULSE - SERVO_MIN_PULSE) / 180)
        
        # Convert to duty cycle
        duty_cycle = self.pulse_to_duty_cycle(pulse)
        
        # Execute movement
        try:
            if immediate:
                # Immediate movement
                self.pca.channels[channel].duty_cycle = duty_cycle
                self.current_positions[channel] = angle
            else:
                # Smooth movement (cosine easing)
                start_angle = self.current_positions[channel]
                steps = 20  # Number of steps for smooth movement
                for i in range(steps + 1):
                    # Cosine easing for smooth start/stop
                    progress = 0.5 - 0.5 * cos(pi * i / steps)
                    interp_angle = start_angle + progress * (angle - start_angle)
                    
                    if channel in [5, 6]:  # Wrist servos
                        interp_pulse = SERVO_MID_PULSE + (interp_angle * (SERVO_MAX_PULSE - SERVO_MIN_PULSE) / 180)
                    else:  # Finger servos
                        interp_pulse = SERVO_MIN_PULSE + (interp_angle * (SERVO_MAX_PULSE - SERVO_MIN_PULSE) / 180)
                        
                    self.pca.channels[channel].duty_cycle = self.pulse_to_duty_cycle(interp_pulse)
                    time.sleep(0.02)  # ~50fps movement
                
                self.current_positions[channel] = angle
            
            logger.debug(f"Servo {channel} moved to {angle}° (pulse: {pulse}µs)")
            return True
            
        except Exception as e:
            logger.error(f"Servo {channel} movement error: {e}")
            return False
    
    def initialize_servos(self):
        """Initialize all servos to their starting positions."""
        logger.info("Initializing servos to default positions...")
        for channel, constraints in SERVO_CONSTRAINTS.items():
            self.set_servo_angle(channel, constraints['start'], immediate=True)
            time.sleep(0.1)
        logger.info("Servo initialization complete")
    
    def reset_all(self):
        """Reset all servos to their default positions."""
        results = {}
        
        # Reset fingers to open position (0°)
        for finger in range(12):  # All fingers and wrists
            results[finger] = self.set_servo_angle(finger, SERVO_CONSTRAINTS[finger]['start'])
        
        return all(results.values())
    
    def emergency_stop(self):
        """Immediately stop all servo movement."""
        try:
            if self.is_initialized:
                # Release all servos
                for channel in range(NUM_SERVOS):
                    self.pca.channels[channel].duty_cycle = 0
                logger.info("Emergency stop activated")
                return True
            return False
        except Exception as e:
            logger.error(f"Emergency stop error: {e}")
            return False
    
    def get_status(self):
        """Get current status of all servos."""
        return {
            'hardware_initialized': self.is_initialized,
            'current_positions': self.current_positions,
            'constraints': SERVO_CONSTRAINTS
        }
    
    def shutdown(self):
        """Graceful shutdown procedure."""
        logger.info("Shutting down servos...")
        
        if self.is_initialized:
            # Return to safe positions
            for channel, constraints in SERVO_CONSTRAINTS.items():
                self.set_servo_angle(channel, constraints['start'], immediate=True)
            time.sleep(1)
            
            # Release all servos
            for channel in range(NUM_SERVOS):
                self.pca.channels[channel].duty_cycle = 0
            
            self.pca.deinit()
            self.is_initialized = False
        
        logger.info("Servos released")