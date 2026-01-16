import requests
import time

BASE_URL = "http://192.168.31.156:5001"

FINGER_ORDER = ["index", "majeure", "ringfinger", "pinky", "thumb"]  # order to close/open

def smooth_close_hand(hand, delay_per_finger=0.25):
    """Close all fingers on one hand smoothly."""
    print(f"✊ Smooth closing {hand} hand...")
    for finger in FINGER_ORDER:
        r = requests.post(f"{BASE_URL}/move_finger", json={
            "hand": hand,
            "finger": finger,
            "state": "closed",
            "duration_ms": 250
        })
        if r.ok:
            print(f"  ✅ {hand} {finger} closed")
        else:
            print(f"  ❌ Error closing {hand} {finger}: {r.text}")
        time.sleep(delay_per_finger)  # small delay between each finger

def smooth_close_both_hands():
    """Close both hands smoothly."""
    smooth_close_hand("right")
    time.sleep(0.3)
    smooth_close_hand("left")
    print("✅ Both hands closed\n")

def show_number(hand, number, duration=500):
    """Send API request to show a number on a specific hand."""
    r = requests.post(f"{BASE_URL}/show_number", json={
        "hand": hand,
        "number": number,
        "duration_ms": duration
    })
    return r.ok, r.json()

def main():
    print("🤖 Maxi AI Hand Number Display (Smooth Flash Mode)")
    print("Hands stay closed, flash number, then close smoothly.\n")
    
    # Start with hands closed
    smooth_close_both_hands()

    while True:
        user_input = input("Enter number (1–10) or 'q' to quit: ").strip()

        if user_input.lower() == "q":
            print("👋 Goodbye!")
            smooth_close_both_hands()
            break

        if not user_input.isdigit():
            print("❌ Please enter a valid number.")
            continue

        number = int(user_input)
        if not (1 <= number <= 10):
            print("❌ Number must be between 1 and 10.")
            continue

        print(f"🎯 Flashing number: {number}")

        try:
            if number <= 5:
                print(f"🖐 Showing {number} on RIGHT hand")
                success, resp = show_number("right", number)
                print("✅ Right hand" if success else f"❌ Error: {resp}")

            else:
                right_number = 5
                left_number = number - 5
                print(f"🖐 Showing {right_number} on RIGHT hand")
                success_r, resp_r = show_number("right", right_number)
                print("✅ Right hand" if success_r else f"❌ Right error: {resp_r}")

                time.sleep(0.8)

                print(f"🖐 Showing {left_number} on LEFT hand")
                success_l, resp_l = show_number("left", left_number)
                print("✅ Left hand" if success_l else f"❌ Left error: {resp_l}")

            # Wait 1 second, then close smoothly
            time.sleep(1.0)
            smooth_close_both_hands()

        except Exception as e:
            print(f"💥 Error communicating with API: {e}")

        time.sleep(0.8)

if __name__ == "__main__":
    main()
