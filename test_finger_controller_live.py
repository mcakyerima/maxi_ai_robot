import pytest
import requests
import time

# Raspberry Pi API base URL
BASE_URL = "http://192.168.31.156:5001"

# Delay between actions for hardware safety
ACTION_DELAY = 1.0  # seconds

def log_step(message):
    """Simple logger for test steps."""
    print(f"\n[TEST LOG] {message}")

def test_status():
    log_step("Checking system status...")
    r = requests.get(f"{BASE_URL}/status")
    assert r.status_code == 200
    data = r.json()
    log_step(f"Status: {data['status']}")
    assert "status" in data
    assert "current_positions" in data
    time.sleep(ACTION_DELAY)

def test_show_number_both_hands():
    for hand in ["left", "right"]:
        log_step(f"Showing number 3 on {hand} hand...")
        payload = {"hand": hand, "number": 3, "duration_ms": 500}
        r = requests.post(f"{BASE_URL}/show_number", json=payload)
        assert r.status_code == 200
        assert r.json()["success"] is True
        log_step(f"✅ Number 3 displayed on {hand} hand")
        time.sleep(ACTION_DELAY)

def test_show_number_invalid_hand():
    log_step("Testing invalid hand name...")
    payload = {"hand": "middle", "number": 2}
    r = requests.post(f"{BASE_URL}/show_number", json=payload)
    assert r.status_code == 400
    log_step(f"Expected error: {r.json()['error']}")
    assert "error" in r.json()
    time.sleep(ACTION_DELAY)

def test_clear_hands():
    log_step("Clearing both hands...")
    payload = {"hands": ["left", "right"]}
    r = requests.post(f"{BASE_URL}/clear_hands", json=payload)
    assert r.status_code == 200
    assert r.json()["success"] is True
    log_step("✅ Both hands cleared to open position")
    time.sleep(ACTION_DELAY)

def test_emergency_stop_and_reset():
    log_step("Activating emergency stop...")
    r1 = requests.post(f"{BASE_URL}/emergency_stop")
    assert r1.status_code == 200
    assert r1.json()["success"] is True
    log_step("✅ Emergency stop activated")

    time.sleep(ACTION_DELAY)

    log_step("Resetting emergency stop...")
    r2 = requests.post(f"{BASE_URL}/reset_emergency")
    assert r2.status_code == 200
    assert r2.json()["success"] is True
    log_step("✅ Emergency stop reset")
    time.sleep(ACTION_DELAY)

def test_move_finger_both_hands():
    for hand in ["left", "right"]:
        log_step(f"Opening {hand} thumb...")
        payload = {"hand": hand, "finger": "thumb", "state": "open", "duration_ms": 400}
        r = requests.post(f"{BASE_URL}/move_finger", json=payload)
        assert r.status_code == 200
        assert r.json()["success"] is True
        log_step(f"✅ {hand} thumb opened")
        time.sleep(ACTION_DELAY)

        log_step(f"Closing {hand} thumb...")
        payload["state"] = "closed"
        r = requests.post(f"{BASE_URL}/move_finger", json=payload)
        assert r.status_code == 200
        assert r.json()["success"] is True
        log_step(f"✅ {hand} thumb closed")
        time.sleep(ACTION_DELAY)

def test_health():
    log_step("Checking system health...")
    r = requests.get(f"{BASE_URL}/health")
    assert r.status_code == 200
    log_step(f"Health Status: {r.json()['status']}")
    assert "status" in r.json()
    time.sleep(ACTION_DELAY)
