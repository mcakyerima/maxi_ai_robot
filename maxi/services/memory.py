"""
maxi.services.memory — conversation memory behind a small, swappable interface.

Two implementations share one ``Memory`` interface, so the orchestrator and every
skill are agnostic to which is in use:

* ``WindowMemory`` — the original: a fast in-process sliding window + the persona
  system prompt. Zero persistence. Kept for tests and as a fallback.
* ``PersistentMemory`` — lightweight LONG-TERM memory. It keeps the same sliding
  window AND remembers the child across sessions in a tiny SQLite file:
  their name, things they like/dislike, topics they've asked about, and a rolling
  one-paragraph summary of the relationship. On every ``context()`` those memories
  are injected as one extra ``system`` message so Maxi can greet the child by name
  and build on what they've done before.

Design constraints (deliberate):
  * NO heavy dependencies. Fact/topic learning is pure-Python regex + a stopword
    list, so it works — and is fully testable — with no network and no models.
    The embedding-based ``brain/context_manager`` is intentionally NOT wired; it
    needs torch/sentence-transformers, which we keep off the Railway image.
  * The ONLY part that uses the LLM is the rolling summary, and it runs
    fire-and-forget every N turns and degrades to a no-op when the LLM is off.
  * Recall is additive: a brand-new child produces NO extra system message, so
    behavior is identical to ``WindowMemory`` until Maxi has actually learned
    something.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import sqlite3
import threading
import time
from collections import deque
from pathlib import Path
from typing import Deque, Dict, List, Optional, Protocol, Set

from maxi import persona
from maxi.config import settings

logger = logging.getLogger("maxi.memory")

Message = Dict[str, str]


class Memory(Protocol):
    async def add_user(self, text: str) -> None: ...
    async def add_assistant(self, text: str) -> None: ...
    async def context(self, query: str = "") -> List[Message]: ...


# ---------------------------------------------------------------------------
# WindowMemory — the original fast, ephemeral implementation.
# ---------------------------------------------------------------------------
class WindowMemory:
    """Keeps the last N turns and prepends the persona system prompt."""

    def __init__(self, turns: int = 12) -> None:
        self._buf: Deque[Message] = deque(maxlen=turns * 2)

    async def add_user(self, text: str) -> None:
        self._buf.append({"role": "user", "content": text})

    async def add_assistant(self, text: str) -> None:
        self._buf.append({"role": "assistant", "content": text})

    async def context(self, query: str = "") -> List[Message]:
        return [{"role": "system", "content": persona.system_prompt()}, *self._buf]

    def reset(self) -> None:
        self._buf.clear()


# ---------------------------------------------------------------------------
# Deterministic fact / topic extraction (no ML, no network).
# ---------------------------------------------------------------------------
# Words we never want to mistake for a child's NAME after "I am ...".
_NAME_BLOCKLIST: Set[str] = {
    "a", "an", "the", "not", "so", "very", "really", "just", "from", "in", "here",
    "going", "learning", "playing", "trying", "done", "ready", "sorry", "sure",
    "happy", "sad", "fine", "good", "great", "okay", "ok", "tired", "hungry",
    "thirsty", "sleepy", "bored", "scared", "excited", "cold", "hot", "big",
    "small", "your", "boy", "girl", "kid", "child", "student", "one", "two",
    "three", "four", "five", "six", "seven", "eight", "nine", "ten", "years",
    "year", "old",
}

# Common words that are not useful "topics".
_STOPWORDS: Set[str] = {
    "what", "when", "where", "which", "whom", "whose", "that", "this", "these",
    "those", "have", "with", "your", "yours", "from", "they", "them", "then",
    "than", "about", "would", "could", "should", "tell", "know", "want", "does",
    "done", "much", "many", "very", "just", "some", "more", "most", "into",
    "over", "because", "please", "maxi", "hello", "okay", "yeah", "right", "like",
    "love", "there", "here", "them", "will", "were", "been", "being", "make",
    "made", "come", "goes", "going", "said", "says", "thing", "things", "stuff",
    "plus", "minus", "times", "equals", "divided", "answer", "question",
}

_NAME_PATTERNS = [
    re.compile(r"\bmy name(?:'s| is)\s+([a-z][a-z'\-]{1,20})", re.I),
    re.compile(
        r"\b(?:you can call me|they call me|please call me|call me|i am called|i'm called)\s+([a-z][a-z'\-]{1,20})",
        re.I,
    ),
    # "i am amina" / "i'm amina" — gated hard by the blocklist so "i am happy"
    # or "i am five" is never taken as a name.
    re.compile(r"\bi(?:'m| am)\s+([a-z][a-z'\-]{1,20})\b", re.I),
]

_LIKE_PATTERNS = [
    re.compile(r"\bi (?:really |so |also )?(?:like|love|enjoy)d?\s+(.+)", re.I),
    re.compile(r"\bmy favou?rite [a-z]+ (?:is|are)\s+(.+)", re.I),
]
_DISLIKE_PATTERNS = [
    re.compile(r"\bi (?:really )?(?:hate|dislike)\s+(.+)", re.I),
    re.compile(r"\bi (?:do not|don'?t|dont)\s+(?:like|enjoy)\s+(.+)", re.I),
]

# Where a captured "like/dislike" phrase should be cut short.
_PHRASE_SPLIT = re.compile(r"\s+(?:and|but|because|so|when|then|,|\.|!|\?)\b|[,.!?]")
_LEADING_FILLER = re.compile(r"^(?:to|the|a|an|playing|eating|watching|reading|doing)\s+", re.I)
_GENERIC_OBJECTS: Set[str] = {"it", "that", "this", "them", "you", "him", "her", "us", "stuff", "things", "thing"}


def _clean_phrase(raw: str) -> str:
    """Trim a captured like/dislike phrase to a short, storable noun phrase."""
    text = _PHRASE_SPLIT.split(raw.strip(), maxsplit=1)[0].strip()
    text = _LEADING_FILLER.sub("", text).strip()
    text = re.sub(r"\s+", " ", text).lower()
    return text[:40].strip()


def _extract_name(text: str) -> Optional[str]:
    for pat in _NAME_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        candidate = m.group(1).strip("-'").lower()
        if not candidate or candidate in _NAME_BLOCKLIST:
            continue
        return candidate.capitalize()
    return None


def _extract_likes(text: str) -> List[str]:
    out: List[str] = []
    for pat in _LIKE_PATTERNS:
        for m in pat.finditer(text):
            phrase = _clean_phrase(m.group(1))
            if phrase and phrase not in _GENERIC_OBJECTS and phrase not in out:
                out.append(phrase)
    return out


def _extract_dislikes(text: str) -> List[str]:
    out: List[str] = []
    for pat in _DISLIKE_PATTERNS:
        for m in pat.finditer(text):
            phrase = _clean_phrase(m.group(1))
            if phrase and phrase not in _GENERIC_OBJECTS and phrase not in out:
                out.append(phrase)
    return out


def _extract_topics(text: str) -> List[str]:
    seen: List[str] = []
    for word in re.findall(r"[a-z]{4,}", text.lower()):
        if word in _STOPWORDS or word in seen:
            continue
        seen.append(word)
    return seen[:6]


# ---------------------------------------------------------------------------
# The SQLite store — durable, tiny, thread-safe.
# ---------------------------------------------------------------------------
def _default_db_path(configured: str) -> str:
    if configured:
        return configured
    repo_root = Path(__file__).resolve().parents[2]
    return str(repo_root / "data" / "maxi_memory.db")


def describe_config() -> str:
    """One-line, log-friendly summary of where long-term memory lives and whether
    it survives a redeploy. Called at startup so a Railway deploy check is
    unambiguous (see docs/HANDOFF.md §3/§9b)."""
    cfg = settings.memory
    if not cfg.enabled:
        return "long-term memory DISABLED (MAXI_MEMORY_ENABLED=0) → using ephemeral window only"
    path = os.path.abspath(_default_db_path(cfg.db_path))
    explicit = bool(cfg.db_path)
    # Railway exposes the volume's mount path here when a volume is attached.
    volume = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "")
    on_volume = bool(volume) and path.replace("\\", "/").startswith(volume.replace("\\", "/").rstrip("/") + "/")
    if on_volume:
        durability = f"PERSISTENT across redeploys (on Railway volume {volume})"
    elif volume:
        durability = (f"EPHEMERAL — a volume is mounted at {volume} but the DB is NOT on it; "
                      f"set MAXI_MEMORY_DB={volume.rstrip('/')}/maxi_memory.db")
    else:
        durability = "EPHEMERAL — no Railway volume; DB resets on each redeploy (fine for local/testing)"
    src = "MAXI_MEMORY_DB" if explicit else "default"
    return f"long-term memory ON · db={path} ({src}) · child_id={cfg.child_id} · {durability}"


class MemoryStore:
    """A thread-safe SQLite wrapper. One row-set per ``child_id``."""

    def __init__(self, db_path: str, child_id: str) -> None:
        self.child_id = child_id
        self._lock = threading.Lock()
        if db_path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS facts(
                    child_id   TEXT NOT NULL,
                    kind       TEXT NOT NULL,     -- 'like' | 'dislike'
                    value      TEXT NOT NULL,
                    created_at REAL,
                    updated_at REAL,
                    UNIQUE(child_id, kind, value)
                );
                CREATE TABLE IF NOT EXISTS topics(
                    child_id  TEXT NOT NULL,
                    topic     TEXT NOT NULL,
                    count     INTEGER NOT NULL DEFAULT 1,
                    last_seen REAL,
                    PRIMARY KEY(child_id, topic)
                );
                CREATE TABLE IF NOT EXISTS profile(
                    child_id   TEXT PRIMARY KEY,
                    name       TEXT,
                    summary    TEXT,
                    turn_count INTEGER NOT NULL DEFAULT 0,
                    updated_at REAL
                );
                """
            )

    @staticmethod
    def _now() -> float:
        return time.time()

    def _ensure_profile(self) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO profile(child_id, turn_count, updated_at) VALUES(?, 0, ?)",
            (self.child_id, self._now()),
        )

    # -- writes --------------------------------------------------------------
    def set_name(self, name: str) -> None:
        with self._lock, self._conn:
            self._ensure_profile()
            self._conn.execute(
                "UPDATE profile SET name=?, updated_at=? WHERE child_id=?",
                (name, self._now(), self.child_id),
            )

    def add_fact(self, kind: str, value: str) -> None:
        value = (value or "").strip()
        if not value:
            return
        now = self._now()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO facts(child_id, kind, value, created_at, updated_at) "
                "VALUES(?, ?, ?, ?, ?) "
                "ON CONFLICT(child_id, kind, value) DO UPDATE SET updated_at=excluded.updated_at",
                (self.child_id, kind, value, now, now),
            )

    def bump_topic(self, topic: str) -> None:
        topic = (topic or "").strip()
        if not topic:
            return
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO topics(child_id, topic, count, last_seen) VALUES(?, ?, 1, ?) "
                "ON CONFLICT(child_id, topic) DO UPDATE SET "
                "count=count+1, last_seen=excluded.last_seen",
                (self.child_id, topic, self._now()),
            )

    def bump_turn(self) -> int:
        with self._lock, self._conn:
            self._ensure_profile()
            self._conn.execute(
                "UPDATE profile SET turn_count=turn_count+1 WHERE child_id=?", (self.child_id,)
            )
            row = self._conn.execute(
                "SELECT turn_count FROM profile WHERE child_id=?", (self.child_id,)
            ).fetchone()
        return int(row["turn_count"]) if row else 0

    def set_summary(self, text: str) -> None:
        with self._lock, self._conn:
            self._ensure_profile()
            self._conn.execute(
                "UPDATE profile SET summary=?, updated_at=? WHERE child_id=?",
                (text, self._now(), self.child_id),
            )

    # -- reads ---------------------------------------------------------------
    def get_name(self) -> Optional[str]:
        with self._lock:
            row = self._conn.execute(
                "SELECT name FROM profile WHERE child_id=?", (self.child_id,)
            ).fetchone()
        return row["name"] if row and row["name"] else None

    def get_facts(self, kind: str, limit: int) -> List[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT value FROM facts WHERE child_id=? AND kind=? "
                "ORDER BY updated_at DESC LIMIT ?",
                (self.child_id, kind, limit),
            ).fetchall()
        return [r["value"] for r in rows]

    def get_topics(self, limit: int) -> List[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT topic FROM topics WHERE child_id=? "
                "ORDER BY last_seen DESC, count DESC LIMIT ?",
                (self.child_id, limit),
            ).fetchall()
        return [r["topic"] for r in rows]

    def get_summary(self) -> str:
        with self._lock:
            row = self._conn.execute(
                "SELECT summary FROM profile WHERE child_id=?", (self.child_id,)
            ).fetchone()
        return row["summary"] if row and row["summary"] else ""

    def close(self) -> None:
        with self._lock:
            self._conn.close()


# ---------------------------------------------------------------------------
# PersistentMemory — the long-term Memory implementation.
# ---------------------------------------------------------------------------
class PersistentMemory:
    """Sliding-window context + durable per-child memory (SQLite)."""

    def __init__(
        self,
        *,
        db_path: Optional[str] = None,
        child_id: Optional[str] = None,
        window_turns: Optional[int] = None,
        llm: Optional[object] = None,
        summarize_every: Optional[int] = None,
        max_facts: Optional[int] = None,
        max_topics: Optional[int] = None,
    ) -> None:
        cfg = settings.memory
        self.child_id = child_id or cfg.child_id
        turns = window_turns or cfg.window_turns
        self._buf: Deque[Message] = deque(maxlen=turns * 2)
        self.store = MemoryStore(_default_db_path(db_path if db_path is not None else cfg.db_path), self.child_id)
        self._llm = llm
        self.summarize_every = summarize_every or cfg.summarize_every
        self.max_facts = max_facts or cfg.max_facts_recall
        self.max_topics = max_topics or cfg.max_topics_recall
        self._turns_since_summary = 0
        self._bg_tasks: Set[asyncio.Task] = set()

    # -- Memory interface ----------------------------------------------------
    async def add_user(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        self._buf.append({"role": "user", "content": text})
        try:
            self._learn(text)
        except Exception as exc:  # noqa: BLE001 — learning must never break a turn
            logger.warning("memory learn failed: %s", exc)

    async def add_assistant(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        self._buf.append({"role": "assistant", "content": text})
        try:
            self.store.bump_turn()
        except Exception as exc:  # noqa: BLE001
            logger.warning("memory turn bump failed: %s", exc)
        self._turns_since_summary += 1
        if self._llm is not None and self._turns_since_summary >= self.summarize_every:
            self._turns_since_summary = 0
            self._spawn_summary()

    async def context(self, query: str = "") -> List[Message]:
        msgs: List[Message] = [{"role": "system", "content": persona.system_prompt()}]
        recall = self._recall_block()
        if recall:
            msgs.append({"role": "system", "content": recall})
        msgs.extend(self._buf)
        return msgs

    def reset(self) -> None:
        """Clear the live window only — durable memory persists on purpose."""
        self._buf.clear()

    # -- learning ------------------------------------------------------------
    def _learn(self, text: str) -> None:
        name = _extract_name(text)
        if name:
            self.store.set_name(name)
        for value in _extract_likes(text):
            self.store.add_fact("like", value)
        for value in _extract_dislikes(text):
            self.store.add_fact("dislike", value)
        for topic in _extract_topics(text):
            self.store.bump_topic(topic)

    # -- recall --------------------------------------------------------------
    def _recall_block(self) -> Optional[str]:
        name = self.store.get_name()
        likes = self.store.get_facts("like", self.max_facts)
        dislikes = self.store.get_facts("dislike", self.max_facts)
        topics = self.store.get_topics(self.max_topics)
        summary = self.store.get_summary()

        lines: List[str] = []
        if name:
            lines.append(f"The child's name is {name}. Greet them by name now and then.")
        if likes:
            lines.append("Things they like: " + ", ".join(likes) + ".")
        if dislikes:
            lines.append("Things they don't enjoy: " + ", ".join(dislikes) + ".")
        if topics:
            lines.append("Recently they asked about: " + ", ".join(topics) + ".")
        if summary:
            lines.append("What you remember about them from before: " + summary)
        if not lines:
            return None
        return (
            "You are talking to a child you have met before. Use these memories "
            "naturally to make them feel known — do NOT read this list aloud:\n- "
            + "\n- ".join(lines)
        )

    # -- rolling summary (the only LLM-backed piece) -------------------------
    def _spawn_summary(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # no loop (e.g. a sync test) — skip; facts/topics still work
        task = loop.create_task(self._summarize_guarded())
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    async def _summarize_guarded(self) -> None:
        try:
            await asyncio.wait_for(self.summarize_now(), timeout=10.0)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("rolling summary failed: %s", exc)

    async def summarize_now(self) -> Optional[str]:
        """Regenerate the rolling summary from the recent window. Returns the new
        summary (or None if the LLM is unavailable / there's nothing to summarize)."""
        llm = self._llm
        if llm is None or not getattr(llm, "enabled", False):
            return None
        convo = "\n".join(f"{m['role']}: {m['content']}" for m in self._buf).strip()
        if not convo:
            return None
        previous = self.store.get_summary()
        prompt = [
            {
                "role": "system",
                "content": (
                    "You keep a short private memory of a child you tutor. In ONE or "
                    "TWO short sentences, update your notes on who this child is and "
                    "what they enjoy or have been learning. Write plain notes to "
                    "yourself, no emojis, no greeting."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Previous notes: {previous or '(none yet)'}\n\n"
                    f"Recent conversation:\n{convo}\n\nUpdated notes:"
                ),
            },
        ]
        text = (await llm.complete(prompt, max_tokens=90, temperature=0.3)).strip()
        if text:
            self.store.set_summary(text)
            return text
        return None
