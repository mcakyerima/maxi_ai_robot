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
from typing import Dict, List, Optional

import aiohttp

from maxi.config import settings

logger = logging.getLogger("maxi.hands")

FINGERS = ["index", "majeure", "ringfinger", "pinky", "thumb"]


class HandsActuator:
    def __init__(self) -> None:
        self.base_url = settings.hands.base_url
        self.api_key = settings.hands.api_key
        self.timeout = settings.hands.request_timeout
        self.simulation = settings.hands.simulation
        self.available = False
        self._pose: Dict[str, List[int]] = {"left": [0] * 5, "right": [0] * 5}

    # -- lifecycle -----------------------------------------------------------
    async def initialize(self) -> bool:
        """Probe the Pi. Returns True if hardware is live, False → simulation."""
        if self.simulation:
            logger.info("Hands: simulation mode (forced).")
            self.available = False
            return False
        self.available = await self._health()
        logger.info(
            "Hands: %s at %s",
            "hardware connected" if self.available else "simulation (Pi unreachable)",
            self.base_url,
        )
        return self.available

    async def _health(self) -> bool:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"{self.base_url}/health",
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as r:
                    return r.status == 200
        except Exception as exc:  # noqa: BLE001
            logger.debug("Pi health check failed: %s", exc)
            return False

    def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["X-API-Key"] = self.api_key
        return h

    async def _post(self, endpoint: str, data: Optional[dict] = None) -> Optional[dict]:
        if not self.available:
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
                        logger.error("Pi rejected API key; disabling hardware.")
                        self.available = False
                        return None
                    return await r.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("hand command %s failed: %s", endpoint, exc)
            return None

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
