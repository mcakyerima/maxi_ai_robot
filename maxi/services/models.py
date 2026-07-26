"""
maxi.services.models — host big ML assets on Maxi's own drive (the Railway volume).

The Vosk wake-word model is ~40 MB. Rather than bloat the git repo or depend on a
CDN at runtime, we keep it on the persistent volume and serve it same-origin:

  1. resolve a model directory (the Railway volume if mounted, else <repo>/data/models),
  2. on boot, if the model isn't there yet, download it ONCE in a background thread,
  3. Flask serves it from /models/<file>; the tablet loads it same-origin (no CORS,
     no runtime CDN). Persists across redeploys because it's on the volume.

Everything is best-effort: a failed download just leaves the tablet on push-to-talk.
"""
from __future__ import annotations

import logging
import os
import threading
import time
import urllib.request
from pathlib import Path
from typing import Optional

from maxi.config import settings

logger = logging.getLogger("maxi.models")

_seed_lock = threading.Lock()
_seeding = False


def model_dir() -> str:
    """Where big assets live. Prefers an explicit dir, then the Railway volume,
    then a repo-local folder for laptop dev."""
    explicit = settings.voice.model_dir if hasattr(settings.voice, "model_dir") else ""
    if explicit:
        d = explicit
    else:
        volume = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "")
        if volume:
            d = os.path.join(volume, "models")
        else:
            d = str(Path(__file__).resolve().parents[2] / "data" / "models")
    os.makedirs(d, exist_ok=True)
    return d


def vosk_model_path() -> str:
    return os.path.join(model_dir(), settings.voice.vosk_model_file)


def vosk_model_ready() -> bool:
    p = vosk_model_path()
    try:
        return os.path.isfile(p) and os.path.getsize(p) > 1_000_000  # >1 MB sanity
    except OSError:
        return False


def ensure_vosk_model_async() -> None:
    """Kick off a one-time background download of the Vosk model to the volume.
    No-op if it's already present or a download is already running."""
    global _seeding
    if vosk_model_ready():
        return
    with _seed_lock:
        if _seeding:
            return
        _seeding = True
    threading.Thread(target=_download_vosk_model, name="vosk-model-seed", daemon=True).start()


def _download_vosk_model() -> None:
    global _seeding
    dest = vosk_model_path()
    src = settings.voice.vosk_model_source
    tmp = dest + ".part"
    try:
        logger.info("⬇️  seeding Vosk model to %s (from %s) — one time…", dest, src)
        t0 = time.time()
        req = urllib.request.Request(src, headers={"User-Agent": "maxi-robot/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as out:
            total = 0
            while True:
                chunk = resp.read(1 << 16)
                if not chunk:
                    break
                out.write(chunk)
                total += len(chunk)
        os.replace(tmp, dest)
        logger.info("✅ Vosk model ready (%.1f MB in %.1fs): %s",
                    total / 1e6, time.time() - t0, dest)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Vosk model seed failed (%s). Tablet stays on push-to-talk "
                       "until the model is present; set MAXI_VOSK_MODEL_SOURCE if the "
                       "URL is wrong.", exc)
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
    finally:
        with _seed_lock:
            _seeding = False


def describe() -> str:
    """One-line startup summary of the resolved wake engine + Vosk model state."""
    v = settings.voice
    eng = v.resolved_wake_engine
    if eng == "porcupine":
        return f"wake engine: porcupine (say '{v.keyword}') — beepless, on-device"
    if eng == "vosk":
        state = "ready" if vosk_model_ready() else "downloading on first boot…"
        return (f"wake engine: vosk (say '{v.wake_phrase}') — beepless, model served "
                f"from {model_dir()} [{state}]")
    return "wake engine: none — tablet uses push-to-talk (tap the mic)"
