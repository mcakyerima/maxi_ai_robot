"""
maxi.actuators — Maxi's body. Each actuator wraps a physical limb behind a
clean async interface so skills never touch HTTP or servo details. Today: hands
(10 fingers + wrists) on the Raspberry Pi. Tomorrow: arms, head, eyes — same
pattern.
"""
from maxi.actuators.hands import HandsActuator

__all__ = ["HandsActuator"]
