"""
tools/check_hands.py — prove the Pi hands are reachable BEFORE involving Railway.

Talks straight to the finger API (locally, over the LAN, or through the tunnel)
the same way the cloud brain does: same endpoints, same X-API-Key header. If this
passes, the only thing left that can go wrong is the Railway variables.

Stdlib only — runs on the Pi, on Windows, with any python3.

    # from the laptop, through the tunnel (the real pre-flight)
    python tools/check_hands.py https://xxxx.trycloudflare.com --key YOURKEY

    # on the Pi itself
    python3 tools/check_hands.py http://localhost:5001 --key YOURKEY

    --move   also move real fingers (show 3, then 5, then close)
    --key    defaults to $MAXI_HAND_API_KEY
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

OK, BAD, WARN = "[ OK ]", "[FAIL]", "[WARN]"


def call(url: str, path: str, key: str, method: str = "GET", body: dict | None = None,
         timeout: float = 20.0):
    """Return (status_code, parsed_json_or_text). Raises only on transport errors."""
    data = json.dumps(body or {}).encode() if method == "POST" else None
    req = urllib.request.Request(url.rstrip("/") + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if key:
        req.add_header("X-API-Key", key)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            try:
                return r.status, json.loads(raw)
            except json.JSONDecodeError:
                return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


def main() -> int:
    p = argparse.ArgumentParser(description="Pre-flight the Maxi hand controller.")
    p.add_argument("url", help="base URL, e.g. https://xxxx.trycloudflare.com")
    p.add_argument("--key", default=os.getenv("MAXI_HAND_API_KEY", ""),
                   help="X-API-Key (default: $MAXI_HAND_API_KEY)")
    p.add_argument("--move", action="store_true", help="actually move the fingers")
    p.add_argument("--hand", default="right", choices=["left", "right"])
    args = p.parse_args()

    url = args.url.rstrip("/")
    print(f"\n🖐  Checking {url}\n" + "-" * 60)
    failures = []

    # 1. /health — unauthenticated; proves the tunnel + Flask are alive.
    try:
        code, health = call(url, "/health", "")
    except Exception as exc:  # noqa: BLE001
        print(f"{BAD} /health unreachable: {type(exc).__name__}: {exc}")
        print("\n     → the tunnel is down, or the API isn't running on :5001.")
        return 1
    if code != 200:
        print(f"{BAD} /health returned HTTP {code}: {health}")
        return 1
    print(f"{OK} /health  {json.dumps(health) if isinstance(health, dict) else health}")
    if isinstance(health, dict):
        if health.get("status") == "degraded":
            print(f"{WARN} status=degraded → the PCA9685 did not initialise "
                  "(I2C off? no power? check the Pi console). Servos will NOT move.")
            failures.append("hardware not connected on the Pi")
        if health.get("emergency_stop"):
            print(f"{WARN} emergency stop is ACTIVE — servos are limp until you reset it.")
            failures.append("emergency stop active")

    # 2. /status — authenticated; this is what proves the API key matches.
    if not args.key:
        print(f"{WARN} no --key given, skipping the auth check "
              "(the cloud brain WILL need one).")
    else:
        code, status = call(url, "/status", args.key)
        if code == 401:
            print(f"{BAD} /status → 401. The key does not match the Pi's MAXI_HAND_API_KEY.")
            return 1
        if code != 200:
            print(f"{BAD} /status → HTTP {code}: {status}")
            failures.append(f"/status HTTP {code}")
        else:
            st = status.get("status", {}) if isinstance(status, dict) else {}
            print(f"{OK} /status  auth accepted  "
                  f"(initialized={st.get('initialized')}, "
                  f"hardware={st.get('hardware_connected')}, "
                  f"calibration_saved={st.get('calibration_saved')}, "
                  f"movements={st.get('total_movements')})")
            if not st.get("calibration_saved"):
                print(f"{WARN} no saved calibration on the Pi — it is using DEFAULT ranges. "
                      "Run finger_callibrator.py (:5000) and SAVE, or fingers may "
                      "over-drive into their stops.")
                failures.append("calibration not saved")

    # 3. optional: move something.
    if args.move and args.key:
        print("-" * 60)
        for n in (3, 5, 0):
            t0 = time.time()
            code, res = call(url, "/show_number", args.key, "POST",
                             {"hand": args.hand, "number": n, "duration_ms": 250})
            dt = time.time() - t0
            ok = code == 200 and isinstance(res, dict) and res.get("success")
            print(f"{OK if ok else BAD} show_number({n}) → HTTP {code} in {dt:.1f}s"
                  f"{'' if ok else ' ' + str(res)}")
            if not ok:
                failures.append(f"show_number({n}) failed")
            if dt > 8.0:
                print(f"{WARN} that took {dt:.1f}s — longer than the brain's default "
                      "HANDS_TIMEOUT of 8s. Raise HANDS_TIMEOUT on Railway.")
                failures.append("slower than HANDS_TIMEOUT")
            time.sleep(0.5)
        call(url, "/close_all_hands", args.key, "POST")
        print(f"{OK} hands closed")
    elif args.move:
        print(f"{WARN} --move needs --key (movement endpoints are authenticated).")

    print("-" * 60)
    if failures:
        print("⚠️  reachable, but fix these first:")
        for f in failures:
            print(f"     • {f}")
        return 2
    print("✅ ALL GOOD. Now set on Railway and redeploy:\n")
    print(f"     RASPBERRY_PI_URL={url}")
    print(f"     MAXI_HAND_API_KEY={args.key or '<the Pi key>'}\n")
    print("   Then: https://<railway-app>/hands/status?probe=1  →  \"mode\":\"hardware\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
