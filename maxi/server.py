"""
maxi.server — the v2 entry point. Flask + Socket.IO gateway around the brain.

  * Serves the tablet PWA (menu / chat / math / settings + manifest + service worker).
  * Runs the async Orchestrator on a dedicated thread with its own event loop.
  * Bridges Socket.IO ``message`` events into the brain via the Transport.

Run:  venv/Scripts/python.exe -m maxi.server      (or python start.py)
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import signal
import sys
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from flask import Flask, jsonify, make_response, render_template, send_from_directory
from flask_socketio import SocketIO

from maxi.config import settings
from maxi.core.events import Mode
from maxi.core.transport import Transport
from maxi.factory import build_orchestrator
from maxi.services import memory as memory_service
from maxi.services import models as model_service

# UTF-8 stdout so emoji logs don't crash on Windows consoles.
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("maxi.server")

_ROOT = Path(__file__).resolve().parent.parent
_UI = _ROOT / "ui"

app = Flask(
    __name__,
    template_folder=str(_UI / "templates"),
    static_folder=str(_UI / "static"),
    static_url_path="/static",
)
app.config["JSON_AS_ASCII"] = False

socketio = SocketIO(
    app, async_mode="threading", cors_allowed_origins="*",
    ping_timeout=60, ping_interval=25,
)

# Optional parent dashboard (kept from v1).
try:
    from ui.routes.parent_routes import dashboard_page_bp, parent_dashboard_bp
    app.register_blueprint(parent_dashboard_bp)
    app.register_blueprint(dashboard_page_bp)
except Exception as exc:  # noqa: BLE001
    logger.warning("parent dashboard routes unavailable: %s", exc)

# --- brain thread ------------------------------------------------------------
transport = Transport()
_orchestrator = None
_brain_ready = threading.Event()


def _start_brain() -> None:
    global _orchestrator
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    transport.bind(socketio, loop)
    _orchestrator = build_orchestrator(transport)
    _brain_ready.set()
    logger.info("Brain loop starting…")
    try:
        loop.run_until_complete(_orchestrator.run())
    except Exception as exc:  # noqa: BLE001
        logger.error("brain loop crashed: %s", exc)
    finally:
        loop.close()


def start_brain_thread() -> None:
    t = threading.Thread(target=_start_brain, name="maxi-brain", daemon=True)
    t.start()
    _brain_ready.wait(timeout=10)


# --- PWA + page routes -------------------------------------------------------
@app.route("/")
def menu():
    return render_template("menu.html")


@app.route("/chat")
def chat():
    return render_template("chat.html")


@app.route("/math")
def math():
    resp = make_response(render_template("math.html"))
    resp.headers["Cache-Control"] = "no-cache, max-age=0"
    return resp


@app.route("/settings")
def settings_page():
    return render_template("settings.html")


@app.route("/offline")
def offline():
    return render_template("offline.html")


@app.route("/manifest.json")
def manifest():
    return send_from_directory(str(_UI), "manifest.json", mimetype="application/manifest+json")


@app.route("/sw.js")
def service_worker():
    resp = make_response(send_from_directory(str(_UI), "sw.js"))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Service-Worker-Allowed"] = "/"
    return resp


@app.route("/models/<path:filename>")
def serve_model(filename: str):
    """Serve big ML assets (the Vosk model) from Maxi's drive (the Railway volume),
    same-origin so the browser worker has no CORS issue. 404 until the one-time
    boot download finishes."""
    resp = make_response(send_from_directory(model_service.model_dir(), filename))
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp


@app.route("/voice_config.js")
def voice_config_js():
    """Serve the tablet's wake-word config as a JS global (window.MAXI_VOICE_CONFIG).

    Kept out of the templates so the Picovoice AccessKey is injected at runtime from
    the environment, never committed. `wakeEngine` tells the page which provider to
    build: 'porcupine' | 'vosk' | 'none' (→ push-to-talk)."""
    v = settings.voice
    engine = v.resolved_wake_engine
    if engine == "vosk" and not model_service.vosk_model_ready():
        # Model still downloading on first boot — page falls back until it's ready.
        engine = "none"
    cfg: Dict[str, Any] = {
        "wakeEngine": engine,
        "wakeEnabled": engine != "none",
        # Porcupine
        "picovoiceAccessKey": v.picovoice_access_key,
        "keyword": v.keyword,
        "sensitivity": v.sensitivity,
        "keywordUrl": v.keyword_url,
        "keywordLabel": v.keyword_label,
        # Vosk
        "voskSdkUrl": v.vosk_sdk_url,
        "voskModelUrl": "/models/" + v.vosk_model_file,
        "wakePhrase": v.wake_phrase,
    }
    if v.model_url:
        cfg["modelUrl"] = v.model_url
    if v.sdk_porcupine_url:
        cfg["sdkPorcupineUrl"] = v.sdk_porcupine_url
    if v.sdk_vp_url:
        cfg["sdkVpUrl"] = v.sdk_vp_url
    body = "window.MAXI_VOICE_CONFIG = " + json.dumps(cfg) + ";"
    resp = make_response(body)
    resp.headers["Content-Type"] = "application/javascript; charset=utf-8"
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


@app.route("/set_mode/<mode>")
def set_mode(mode: str):
    wire = {"general": "general_chat", "math": "math_gesture", "idle": "idle"}.get(mode)
    if wire is None:
        return jsonify({"status": "error", "message": "invalid mode"})
    transport.submit({"type": "set_mode", "mode": wire})
    return jsonify({"status": "success", "mode": Mode.from_wire(wire).value})


# --- Socket.IO bridge --------------------------------------------------------
@socketio.on("connect")
def on_connect(auth: Optional[Any] = None):
    logger.info("tablet connected (auth=%s)", auth)


@socketio.on("disconnect")
def on_disconnect():
    logger.info("tablet disconnected")


@socketio.on("message")
def on_message(data: Dict[str, Any]):
    if isinstance(data, dict):
        transport.submit(data)


def main() -> None:
    logger.info("🚀🚀 MAXI BUILD MARKER: math-v2-stepbystep + kid-friendly word problems 🚀🚀")
    logger.info("🧠 %s", memory_service.describe_config())
    # Wake word: seed the Vosk model to the volume once if that engine is selected.
    if settings.voice.resolved_wake_engine == "vosk":
        model_service.ensure_vosk_model_async()
    logger.info("🎙️ %s", model_service.describe())
    start_brain_thread()
    logger.info("Maxi v2 serving on http://%s:%s", settings.server.host, settings.server.port)

    def _bye(*_a):
        logger.info("shutting down…")
        raise SystemExit(0)

    try:
        signal.signal(signal.SIGINT, _bye)
        signal.signal(signal.SIGTERM, _bye)
    except Exception:  # noqa: BLE001
        pass

    socketio.run(
        app, host=settings.server.host, port=settings.server.port,
        debug=False, use_reloader=False, allow_unsafe_werkzeug=True,
    )


if __name__ == "__main__":
    main()
