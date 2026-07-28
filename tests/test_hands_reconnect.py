"""
tests/test_hands_reconnect.py — the hands must heal themselves.

The demo failure mode this guards against: Railway boots BEFORE the Pi's tunnel
exists (or the free quick-tunnel restarts mid-session), the one-shot startup probe
fails, and Maxi stays in simulation until someone redeploys. These tests run a
fake Pi on a real socket and check the actuator recovers on its own.

    venv/Scripts/python.exe tests/test_hands_reconnect.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from maxi.actuators.hands import HandsActuator  # noqa: E402

KEY = "test-key"
_state = {"up": True, "key": KEY, "calls": []}


class FakePi(BaseHTTPRequestHandler):
    def log_message(self, *_a):  # silence
        pass

    def _send(self, code: int, body: dict) -> None:
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if not _state["up"]:
            self._send(502, {"error": "tunnel down"})
            return
        if self.path == "/health":
            self._send(200, {"status": "healthy"})
        else:
            self._send(404, {})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        if not _state["up"]:
            self._send(502, {"error": "tunnel down"})
            return
        if self.headers.get("X-API-Key") != _state["key"]:
            self._send(401, {"success": False, "error": "Unauthorized"})
            return
        _state["calls"].append(self.path)
        self._send(200, {"success": True})


def start_fake_pi() -> tuple[HTTPServer, str]:
    srv = HTTPServer(("127.0.0.1", 0), FakePi)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def make_hands(base_url: str) -> HandsActuator:
    h = HandsActuator()
    h.base_url = base_url
    h.api_key = KEY
    h.simulation = False
    h.timeout = 3.0
    return h


PASS = FAIL = 0


def check(name: str, cond: bool) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [ OK ] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}")


async def main() -> int:
    srv, url = start_fake_pi()
    print(f"fake Pi at {url}\n")

    # 1. happy path
    print("1. Pi reachable at boot")
    h = make_hands(url)
    check("initialize() reports hardware", await h.initialize() is True)
    check("status() says hardware", h.status()["mode"] == "hardware")
    check("show_number reaches the Pi", await h.show_number(3) is True)
    check("the Pi got /show_number", "/show_number" in _state["calls"])

    # 2. THE demo case: brain boots first, tunnel comes up later.
    print("\n2. Pi unreachable at boot, appears later")
    _state["up"] = False
    h2 = make_hands(url)
    check("initialize() falls back to simulation", await h2.initialize() is False)
    check("commands still succeed (simulated)", await h2.show_number(3) is True)
    check("still marked unavailable", h2.available is False)
    _state["up"] = True                 # tunnel comes online
    check("cooldown blocks an instant re-probe", await h2._ensure_available() is False)
    h2._next_probe = 0.0                # pretend the cooldown elapsed
    _state["calls"].clear()
    check("next command reconnects", await h2.show_number(4) is True)
    check("now on real hardware", h2.available is True)
    check("the Pi actually got the command", "/show_number" in _state["calls"])

    # 3. tunnel dies mid-session
    print("\n3. tunnel drops mid-session, then returns")
    _state["up"] = False
    await h2.show_number(2)             # fails at the transport layer
    check("drops to simulation on failure", h2.available is False)
    check("an error was recorded", bool(h2.status()["last_error"]))
    _state["up"] = True
    h2._next_probe = 0.0
    _state["calls"].clear()
    check("recovers without a redeploy", await h2.show_number(5) is True)
    check("hardware again", h2.available is True)
    check("last_error cleared on recovery", h2.status()["last_error"] is None)

    # 4. wrong API key
    print("\n4. API key mismatch")
    h3 = make_hands(url)
    h3.api_key = "wrong-key"
    await h3.initialize()               # /health has no auth → looks connected
    check("health alone says connected", h3.available is True)
    check("command is not reported as moved", await h3.show_number(3) is False)
    check("401 drops to simulation", h3.available is False)
    check("auth failure is flagged", h3.status()["auth_failed"] is True)
    check("401 sets a long cooldown", await h3._ensure_available() is False)

    # 5. forced simulation never touches the network
    print("\n5. FINGER_SIMULATION_MODE")
    h4 = make_hands(url)
    h4.simulation = True
    check("initialize() → simulation", await h4.initialize() is False)
    _state["calls"].clear()
    check("commands succeed", await h4.show_number(3) is True)
    check("no network call made", _state["calls"] == [])
    check("status says forced", "forced" in str(h4.status()["mode"]))

    # 6. status() must never leak the key
    print("\n6. /hands/status payload")
    st = make_hands(url).status()
    check("no api_key in the payload", KEY not in json.dumps(st))
    check("but reports whether one is set", st["api_key_set"] is True)
    check("exposes base_url for debugging", st["base_url"] == url)

    srv.shutdown()
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
