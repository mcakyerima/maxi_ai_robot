"""
maxi.core.transport — the bridge between Flask-SocketIO (sync, threaded) and the
orchestrator (async, single event loop).

Flask-SocketIO handlers run on server threads; the brain runs on its own asyncio
loop in a dedicated thread. This class is the ONLY crossing point:

  * outbound: ``emit()`` is called from the async loop → ``socketio.emit`` (thread-safe).
  * inbound:  ``submit()`` is called from a Flask thread → hands the message to the
    loop via ``run_coroutine_threadsafe`` so the orchestrator sees it in-loop.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("maxi.transport")


class Transport:
    def __init__(self) -> None:
        self.socketio: Any = None                      # injected once the Flask app exists
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.inbound: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()

    def bind(self, socketio: Any, loop: asyncio.AbstractEventLoop) -> None:
        self.socketio = socketio
        self.loop = loop

    # -- outbound (async loop → tablet) --------------------------------------
    async def emit(self, message: Dict[str, Any]) -> None:
        """Send a message to all connected tablets."""
        if not self.socketio:
            logger.debug("emit before socketio bound: %s", message.get("type"))
            return
        event_type = message.get("type", "message")
        # Emit on the type-specific channel AND the generic 'message' channel,
        # matching the tablet client which may listen on either.
        self.socketio.emit(event_type, message)
        if event_type != "message":
            self.socketio.emit("message", message)

    # -- inbound (Flask thread → async loop) ---------------------------------
    def submit(self, message: Dict[str, Any]) -> None:
        """Thread-safe: enqueue an incoming tablet message onto the brain loop."""
        if not self.loop:
            logger.warning("submit before loop bound; dropping %s", message.get("type"))
            return
        asyncio.run_coroutine_threadsafe(self.inbound.put(message), self.loop)

    async def next_message(self) -> Dict[str, Any]:
        return await self.inbound.get()
