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
import hashlib
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

_inflight: set = set()  # ack filenames currently being rendered (dedupe)

# Short wake acknowledgements, spoken in Maxi's OWN voice (edge-tts). Pre-rendered
# once on boot to the volume and served from /acks, so the tablet plays a cached
# clip instantly (fast) instead of an off-brand browser voice.
# NOTE: filenames are content-hashed, so editing a phrase auto-renders a new clip.
ACK_PHRASES = [
    "Yes?", "Yeah?", "I'm here!", "Go ahead!",
    "What's up?", "I'm listening!", "Uh huh?", "Mmm hmm!",
    "Sannu!",  # Hausa "hello" — a warm local touch
]

# Personalised greetings, filled with the child's remembered name when known.
NAME_ACK_TEMPLATES = ["Hi {name}!", "Hey {name}!", "Yes {name}?"]


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


def _short(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:8]


def _present(filename: str) -> bool:
    p = os.path.join(ack_dir(), filename)
    try:
        return os.path.isfile(p) and os.path.getsize(p) > 500
    except OSError:
        return False


def _base_ack_items() -> list:
    """(filename, text) for each generic ack. Filename is content-hashed so a phrase
    edit produces a NEW file (auto-regenerated) instead of reusing a stale clip."""
    return [(f"ack_{_short(p)}.mp3", p) for p in ACK_PHRASES]


def current_child_name() -> Optional[str]:
    """The child's remembered name, if a valid one is on file (read from the same
    SQLite the long-term memory uses)."""
    try:
        from maxi.services.memory import MemoryStore, _default_db_path, _looks_like_name
        store = MemoryStore(_default_db_path(settings.memory.db_path), settings.memory.child_id)
        name = store.get_name()
        store.close()
        if name and _looks_like_name(name):
            return name
    except Exception as exc:  # noqa: BLE001
        logger.debug("could not read child name: %s", exc)
    return None


def _name_ack_items(name: str) -> list:
    """(filename, text) for the personalised greetings for ``name``."""
    h = _short(name.lower())
    return [(f"name_{h}_{k}.mp3", tpl.format(name=name)) for k, tpl in enumerate(NAME_ACK_TEMPLATES)]


def ack_urls_ready() -> list:
    """All rendered ack clip URLs (generic + the current name's), for the tablet."""
    urls = ["/acks/" + fn for fn, _ in _base_ack_items() if _present(fn)]
    name = current_child_name()
    if name:
        urls += ["/acks/" + fn for fn, _ in _name_ack_items(name) if _present(fn)]
    return urls


def _ensure_async(items: list) -> None:
    """Render any missing (filename, text) clips in the background, once."""
    todo = [(fn, txt) for fn, txt in items if not _present(fn) and fn not in _inflight]
    if not todo:
        return
    with _ack_lock:
        for fn, _ in todo:
            _inflight.add(fn)

    def _worker() -> None:
        try:
            _render_clips(todo)
        finally:
            with _ack_lock:
                for fn, _ in todo:
                    _inflight.discard(fn)

    threading.Thread(target=_worker, name="wake-ack-render", daemon=True).start()


def _render_clips(items: list) -> None:
    try:
        from maxi.services.tts import SpeechService  # local import: avoids an import cycle
        svc = SpeechService()

        async def _go() -> None:
            for fn, text in items:
                path = os.path.join(ack_dir(), fn)
                if _present(fn):
                    continue
                audio = await svc.synthesize(text)
                if audio:
                    with open(path, "wb") as fh:
                        fh.write(audio)
                    logger.info("🔊 ack clip rendered (%d bytes): %r → %s", len(audio), text, fn)
                else:
                    logger.warning("ack clip came back empty: %r", text)

        asyncio.run(_go())
    except Exception as exc:  # noqa: BLE001
        logger.warning("ack render failed (%s); tablet uses a short silent settle", exc)


def ensure_ack_clips_async() -> None:
    """Render the generic wake-ack clips (Maxi's voice) to the volume, once."""
    _ensure_async(_base_ack_items())


def ensure_name_acks_async(name: Optional[str]) -> None:
    """Render the personalised 'Hi {name}!' clips for the remembered child, once."""
    if name:
        _ensure_async(_name_ack_items(name))


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
