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

import asyncio
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

_ack_lock = threading.Lock()
_acking = False

# Short wake acknowledgements, spoken in Maxi's OWN voice (edge-tts). Pre-rendered
# once on boot to the volume and served from /acks, so the tablet plays a cached
# clip instantly (fast) instead of an off-brand browser voice.
ACK_PHRASES = [
    "Yes?", "Yeah?", "I'm here!", "Go ahead!",
    "What's up?", "I'm listening!", "Uh huh?", "Mm-hmm?",
]


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


def _asset_base() -> str:
    volume = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "")
    if volume:
        return volume
    return str(Path(__file__).resolve().parents[2] / "data")


def ack_dir() -> str:
    d = os.path.join(_asset_base(), "acks")
    os.makedirs(d, exist_ok=True)
    return d


def ack_count() -> int:
    """How many wake-ack clips are rendered and non-empty."""
    n = 0
    for i in range(len(ACK_PHRASES)):
        p = os.path.join(ack_dir(), f"ack{i + 1}.mp3")
        try:
            if os.path.isfile(p) and os.path.getsize(p) > 500:
                n += 1
        except OSError:
            pass
    return n


def ensure_ack_clips_async() -> None:
    """Render the wake-ack clips (Maxi's voice) to the volume once, in the
    background. No-op if already present or a render is in flight."""
    global _acking
    if ack_count() >= len(ACK_PHRASES):
        return
    with _ack_lock:
        if _acking:
            return
        _acking = True
    threading.Thread(target=_render_ack_clips, name="wake-ack-render", daemon=True).start()


def _render_ack_clips() -> None:
    global _acking
    try:
        from maxi.services.tts import SpeechService  # local import: avoids a cycle at import time
        svc = SpeechService()

        async def _go() -> None:
            for i, phrase in enumerate(ACK_PHRASES):
                path = os.path.join(ack_dir(), f"ack{i + 1}.mp3")
                if os.path.isfile(path) and os.path.getsize(path) > 500:
                    continue
                audio = await svc.synthesize(phrase)
                if audio:
                    with open(path, "wb") as fh:
                        fh.write(audio)
                    logger.info("wake-ack clip %d rendered (%d bytes): %r", i + 1, len(audio), phrase)
                else:
                    logger.warning("wake-ack clip %d came back empty: %r", i + 1, phrase)

        asyncio.run(_go())
        logger.info("🔊 wake-ack clips ready: %d/%d in %s", ack_count(), len(ACK_PHRASES), ack_dir())
    except Exception as exc:  # noqa: BLE001
        logger.warning("wake-ack render failed (%s); tablet uses a short silent settle", exc)
    finally:
        with _ack_lock:
            _acking = False


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
