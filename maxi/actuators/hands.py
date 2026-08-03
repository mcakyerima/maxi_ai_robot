"""
maxi.actuators.hands — async HTTP client for the Raspberry Pi hand controller.

The Pi exposes a small REST API (see hardware/finger_controller_api.py). This
client speaks it directly and degrades gracefully to simulation when the Pi is
unreachable, so the brain always runs — even on a laptop with no robot attached.

Finger order on the wire: [index, majeure(middle), ringfinger, pinky, thumb].
State: 1 = open, 0 = closed.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, List, Optional

import aiohttp

from maxi.config import settings

logger = logging.getLogger("maxi.hands")

FINGERS = ["index", "majeure", "ringfinger", "pinky", "thumb"]

# The cloud brain boots long before (or after) the Pi's tunnel exists, and free
# quick-tunnels come and go. So "is the Pi there?" is re-asked lazily instead of
# being decided once at startup — the hands heal themselves without a redeploy.
RECONNECT_SECONDS = 20.0
# A wrong key can't fix itself as fast; back off so logs don't fill with 401s.
AUTH_RETRY_SECONDS = 120.0


class HandsActuator:
    def __init__(self) -> None:
        self.base_url = settings.hands.base_url
        self.api_key = settings.hands.api_key
        self.timeout = settings.hands.request_timeout
        self.simulation = settings.hands.simulation
        self.available = False
        self.last_error: Optional[str] = None
        self._pose: Dict[str, List[int]] = {"left": [0] * 5, "right": [0] * 5}
        self._next_probe = 0.0          # monotonic time of the next allowed probe
        self._auth_failed = False
        self._probes = 0

    # -- lifecycle -----------------------------------------------------------
    async def initialize(self) -> bool:
        """Probe the Pi. Returns True if hardware is live, False → simulation.

        A False here is NOT final: every later command re-probes (see
        ``_ensure_available``), so plugging the Pi in mid-session still works.
        """
        if self.simulation:
            logger.info("Hands: simulation mode (forced).")
            self.available = False
            return False
        if not settings.hands.pi_url_override and settings.hands.pi_ip.startswith("192.168."):
            logger.info(
                "Hands: target is a LAN address (%s) — a cloud deploy cannot reach it. "
                "Set RASPBERRY_PI_URL to the Pi's tunnel URL.", self.base_url,
            )
        await self.probe()
        return self.available

    async def probe(self) -> bool:
        """Force a health check now and log any change of state."""
        was = self.available
        ok = await self._health()
        self._probes += 1
        self.available = ok
        self._next_probe = time.monotonic() + RECONNECT_SECONDS
        if ok:
            self._auth_failed = False
            self.last_error = None
        if ok != was or self._probes == 1:
            logger.info(
                "Hands: %s at %s",
                "hardware connected" if ok else "simulation (Pi unreachable)",
                self.base_url,
            )
        return ok

    async def _ensure_available(self) -> bool:
        """True if we should talk to real hardware; re-probes on a cooldown."""
        if self.simulation:
            return False
        if self.available:
            return True
        if time.monotonic() < self._next_probe:
            return False
        return await self.probe()

    async def _health(self) -> bool:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"{self.base_url}/health",
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as r:
                    if r.status != 200:
                        self.last_error = f"/health returned HTTP {r.status}"
                        return False
                    return True
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"{type(exc).__name__}: {exc}"
            logger.debug("Pi health check failed: %s", exc)
            return False

    def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["X-API-Key"] = self.api_key
        return h

    async def _post(self, endpoint: str, data: Optional[dict] = None) -> Optional[dict]:
        if not await self._ensure_available():
            await asyncio.sleep(0.05)  # pretend-move so timing feels real in sim
            return {"success": True, "simulated": True}
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    f"{self.base_url}{endpoint}",
                    json=data or {},
                    headers=self._headers(),
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as r:
                    if r.status == 401:
                        self.last_error = "Pi rejected the API key (401) — MAXI_HAND_API_KEY mismatch"
                        if not self._auth_failed:
                            logger.error("Hands: %s. Falling back to simulation.", self.last_error)
                        self._auth_failed = True
                        self.available = False
                        self._next_probe = time.monotonic() + AUTH_RETRY_SECONDS
                        return None
                    if r.status >= 500:
                        # A dead tunnel answers with its own 502/530 error page
                        # rather than refusing the connection — that is still
                        # "the Pi is gone", so treat it like a transport failure.
                        self.last_error = f"{endpoint}: HTTP {r.status} (tunnel or Pi down)"
                        logger.warning("Hands: %s", self.last_error)
                        self.available = False
                        self._next_probe = time.monotonic() + RECONNECT_SECONDS
                        return None
                    return await r.json()
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"{endpoint}: {type(exc).__name__}: {exc}"
            logger.warning("hand command %s failed: %s", endpoint, exc)
            # The tunnel probably died. Drop to sim and let the cooldown re-probe.
            self.available = False
            self._next_probe = time.monotonic() + RECONNECT_SECONDS
            return None

    # -- diagnostics ---------------------------------------------------------
    def status(self) -> Dict[str, object]:
        """Snapshot for the /hands/status route (safe to expose: no API key)."""
        return {
            "mode": "simulation (forced)" if self.simulation
            else ("hardware" if self.available else "simulation (Pi unreachable)"),
            "available": self.available,
            "base_url": self.base_url,
            "api_key_set": bool(self.api_key),
            "auth_failed": self._auth_failed,
            "probes": self._probes,
            "last_error": self.last_error,
            "pose": self.pose(),
        }

    # -- movements -----------------------------------------------------------
    async def show_number(self, number: int, hand: str = "right", duration_ms: int = 250) -> bool:
        number = max(0, min(10, int(number)))
        res = await self._post("/show_number", {"hand": hand, "number": number, "duration_ms": duration_ms})
        self._update_pose_for_number(number, hand)
        return bool(res and res.get("success"))

    async def move_finger(self, hand: str, finger: str, open_: bool, duration_ms: int = 200) -> bool:
        res = await self._post(
            "/move_finger",
            {"hand": hand, "finger": finger, "state": "open" if open_ else "closed", "duration_ms": duration_ms},
        )
        if finger in FINGERS:
            self._pose[hand][FINGERS.index(finger)] = 1 if open_ else 0
        return bool(res and res.get("success"))

    async def gesture(self, name: str, hand: str = "right") -> bool:
        """Named gesture: fist | peace | wave | count."""
        res = await self._post("/gesture", {"hand": hand, "gesture": name})
        return bool(res and res.get("success"))

    async def close_all(self) -> bool:
        res = await self._post("/close_all_hands")
        self._pose = {"left": [0] * 5, "right": [0] * 5}
        return bool(res and res.get("success"))

    async def clear_hand(self, hand: str) -> bool:
        res = await self._post("/clear_hands", {"hands": [hand]})
        if hand in self._pose:
            self._pose[hand] = [0] * 5
        return bool(res and res.get("success"))

    async def emergency_stop(self) -> bool:
        res = await self._post("/emergency_stop")
        return bool(res and res.get("success"))

    async def reset_emergency(self) -> bool:
        res = await self._post("/reset_emergency")
        return bool(res and res.get("success"))

    # -- state ---------------------------------------------------------------
    def pose(self) -> Dict[str, List[int]]:
        return {k: list(v) for k, v in self._pose.items()}

    def _update_pose_for_number(self, number: int, hand: str) -> None:
        other = "left" if hand == "right" else "right"
        if number <= 5:
            self._pose[hand] = [1 if i < number else 0 for i in range(5)]
            self._pose[other] = [0] * 5
        else:
            self._pose[hand] = [1] * 5
            self._pose[other] = [1 if i < (number - 5) else 0 for i in range(5)]
