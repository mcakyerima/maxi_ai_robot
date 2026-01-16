import serial
import json
import time
import asyncio

async def investigate_arduino_behavior():
    """Investigate why Arduino keeps sending initialization messages"""
    
    print("🔍 Investigating Arduino behavior...")
    
    try:
        ser = serial.Serial('COM7', 115200, timeout=1)
        print("✅ Serial connection opened")
        
        # Step 1: Wait and collect all initialization messages
        print("\n1. Collecting initialization messages...")
        await asyncio.sleep(3)
        
        init_messages = []
        while ser.in_waiting > 0:
            try:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    init_messages.append(line)
                    print(f"📨 Init: {line}")
            except Exception as e:
                print(f"Error reading: {e}")
        
        print(f"📊 Received {len(init_messages)} initialization messages")
        
        # Step 2: Send a simple command and monitor closely
        print("\n2. Sending command and monitoring response timing...")
        
        ser.reset_input_buffer()
        
        command = {"action": "get_status"}
        cmd_json = json.dumps(command) + '\n'
        
        print(f"📤 Sending at {time.time()}: {cmd_json.strip()}")
        ser.write(cmd_json.encode('utf-8'))
        ser.flush()
        
        # Monitor responses with precise timing
        start_time = time.time()
        responses = []
        
        for i in range(50):  # Monitor for 5 seconds with 0.1s intervals
            current_time = time.time()
            elapsed = current_time - start_time
            
            if ser.in_waiting > 0:
                try:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        responses.append((elapsed, line))
                        print(f"📨 {elapsed:.2f}s: {line}")
                except Exception as e:
                    print(f"Error at {elapsed:.2f}s: {e}")
            
            if elapsed > 5.0:  # Stop after 5 seconds
                break
                
            await asyncio.sleep(0.1)
        
        print(f"\n📊 Received {len(responses)} responses")
        
        # Step 3: Test with different commands
        print("\n3. Testing different command types...")
        
        test_commands = [
            {"action": "emergency_stop"},
            {"action": "reset_all"},
            {"action": "set_servo", "channel": 0, "angle": 90},
        ]
        
        for i, cmd in enumerate(test_commands):
            print(f"\n--- Test {i+1}: {cmd} ---")
            
            ser.reset_input_buffer()
            cmd_json = json.dumps(cmd) + '\n'
            
            print(f"📤 Sending: {cmd_json.strip()}")
            ser.write(cmd_json.encode('utf-8'))
            ser.flush()
            
            # Wait for response
            response_count = 0
            for attempt in range(20):  # 2 seconds
                if ser.in_waiting > 0:
                    try:
                        line = ser.readline().decode('utf-8', errors='ignore').strip()
                        if line:
                            response_count += 1
                            print(f"📨 Response {response_count}: {line}")
                            
                            # Check if it's the expected response vs init message
                            if "ready" in line and "initialized" in line:
                                print("⚠️  Arduino sent init message instead of command response!")
                            elif "status" in line and "success" in line:
                                print("✅ Proper command response received")
                    except Exception as e:
                        print(f"Error: {e}")
                
                await asyncio.sleep(0.1)
            
            if response_count == 0:
                print("❌ No response received")
        
        ser.close()
        return True
        
    except Exception as e:
        print(f"❌ Investigation failed: {e}")
        return False

async def test_arduino_stability():
    """Test if Arduino stays stable without resetting"""
    
    print("\n🔧 Testing Arduino stability...")
    
    try:
        ser = serial.Serial('COM7', 115200, timeout=1)
        print("✅ Serial connection opened")
        
        # Wait for any initial messages
        await asyncio.sleep(2)
        ser.reset_input_buffer()
        
        print("\n📡 Monitoring Arduino for unexpected resets...")
        print("(Watching for 10 seconds without sending commands)")
        
        unexpected_messages = []
        start_time = time.time()
        
        while time.time() - start_time < 10:
            if ser.in_waiting > 0:
                try:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        elapsed = time.time() - start_time
                        unexpected_messages.append((elapsed, line))
                        print(f"📨 {elapsed:.1f}s: {line}")
                        
                        if "ready" in line and "initialized" in line:
                            print("⚠️  Arduino reset detected!")
                except Exception as e:
                    print(f"Error: {e}")
            
            await asyncio.sleep(0.1)
        
        print(f"\n📊 Received {len(unexpected_messages)} unexpected messages")
        
        if len(unexpected_messages) > 0:
            print("❌ Arduino is unstable - it's resetting on its own")
            return False
        else:
            print("✅ Arduino appears stable")
            return True
        
        ser.close()
        
    except Exception as e:
        print(f"❌ Stability test failed: {e}")
        return False

async def test_simple_echo():
    """Test with a very simple command to see if processing works"""
    
    print("\n🗣️  Testing simple echo-style communication...")
    
    try:
        ser = serial.Serial('COM7', 115200, timeout=2)
        print("✅ Serial connection opened")
        
        # Wait for initialization
        await asyncio.sleep(3)
        
        # Clear any existing messages
        while ser.in_waiting > 0:
            ser.readline()
        
        print("\n📤 Sending very simple JSON command...")
        
        # Send the simplest possible command
        simple_cmd = '{"action":"emergency_stop"}\n'
        print(f"Sending: {simple_cmd.strip()}")
        
        ser.write(simple_cmd.encode('utf-8'))
        ser.flush()
        
        print("⏳ Waiting for response...")
        
        # Wait longer and check more carefully
        response_received = False
        for attempt in range(30):  # 3 seconds total
            if ser.in_waiting > 0:
                try:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        print(f"📨 Received: {line}")
                        
                        # Parse the response
                        try:
                            response_data = json.loads(line)
                            print(f"✅ Valid JSON response: {response_data}")
                            
                            if response_data.get('status') == 'success':
                                print("🎉 Command processed successfully!")
                                response_received = True
                                break
                            elif 'ready' in response_data.get('message', ''):
                                print("⚠️  Received init message instead of command response")
                            else:
                                print("❓ Unexpected response content")
                                
                        except json.JSONDecodeError:
                            print(f"❌ Invalid JSON: {line}")
                            
                except Exception as e:
                    print(f"Error reading response: {e}")
            
            await asyncio.sleep(0.1)
        
        ser.close()
        return response_received
        
    except Exception as e:
        print(f"❌ Simple echo test failed: {e}")
        return False

async def main():
    print("🚀 Targeted Arduino Debugging")
    print("=" * 50)
    print("Goal: Find out why Arduino sends init messages instead of processing commands")
    print("=" * 50)
    
    # Investigation 1: Detailed behavior analysis
    print("\n🔍 INVESTIGATION 1: Detailed Behavior Analysis")
    await investigate_arduino_behavior()
    
    print("\n" + "=" * 50)
    
    # Investigation 2: Stability test
    print("\n🔍 INVESTIGATION 2: Arduino Stability Test")
    stability_ok = await test_arduino_stability()
    
    print("\n" + "=" * 50)
    
    # Investigation 3: Simple echo test
    print("\n🔍 INVESTIGATION 3: Simple Echo Test")
    echo_success = await test_simple_echo()
    
    print("\n" + "=" * 50)
    print("📊 DIAGNOSTIC SUMMARY:")
    print(f"Arduino stability: {'✅ STABLE' if stability_ok else '❌ UNSTABLE'}")
    print(f"Command processing: {'✅ WORKING' if echo_success else '❌ NOT WORKING'}")
    
    print("\n🔍 LIKELY ISSUES:")
    if not stability_ok:
        print("1. ❌ Arduino is resetting unexpectedly")
        print("   - Check power supply stability")
        print("   - Verify PCA9685 connections")
        print("   - Check for short circuits")
        print("   - Try without servos connected")
    
    if not echo_success:
        print("2. ❌ Arduino not processing commands properly")
        print("   - Main loop might not be running")
        print("   - Serial parsing may have issues")
        print("   - Memory problems causing crashes")
        print("   - Timing issues in the code")
    
    if stability_ok and not echo_success:
        print("3. 🤔 Arduino is stable but not processing commands")
        print("   - This suggests a software issue in the sketch")
        print("   - Try uploading a simpler test sketch")
        print("   - Check Serial.available() logic")

if __name__ == "__main__":
    asyncio.run(main())