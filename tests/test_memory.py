"""
Self-audit: prove the lightweight long-term memory works with NO network.

Covers:
  * deterministic fact extraction (name / likes / dislikes) and topic tracking,
  * persistence ACROSS sessions (a fresh PersistentMemory on the same DB file
    still knows the child),
  * recall injected as a system message in context(),
  * a brand-new child produces NO recall block (behavior == WindowMemory),
  * rolling summary generation via a fake LLM (still zero network),
  * learning never crashes a turn.

Run:  venv/Scripts/python.exe tests/test_memory.py
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from maxi.services.memory import (  # noqa: E402
    PersistentMemory,
    _extract_dislikes,
    _extract_likes,
    _extract_name,
    _extract_topics,
)

PASS = 0
FAIL = 0


def check(label, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label}")


class FakeLLM:
    """A stand-in Groq: records the prompt and returns a canned summary."""

    enabled = True

    def __init__(self, reply="Amina, loves football and dinosaurs; learning addition."):
        self.reply = reply
        self.calls = []

    async def complete(self, messages, *, max_tokens=None, temperature=None, json_mode=False):
        self.calls.append(messages)
        return self.reply


# ---------------------------------------------------------------------------
def test_extractors():
    print("extractors (pure functions, deterministic):")
    check("my name is Amina", _extract_name("my name is Amina") == "Amina")
    check("i'm Musa", _extract_name("hi, i'm musa") == "Musa")
    check("call me Zainab", _extract_name("you can call me zainab") == "Zainab")
    check("'i am happy' is NOT a name", _extract_name("i am happy today") is None)
    check("'i am five' is NOT a name", _extract_name("i am five years old") is None)

    likes = _extract_likes("i really like football and my sister")
    check("likes football (cut at 'and')", likes == ["football"])
    check("favorite color is blue", _extract_likes("my favorite color is blue") == ["blue"])
    check("love dinosaurs", "dinosaurs" in _extract_likes("i love dinosaurs so much"))

    dislikes = _extract_dislikes("i don't like spiders")
    check("dislikes spiders", dislikes == ["spiders"])
    check("hate broccoli", _extract_dislikes("i hate broccoli") == ["broccoli"])
    check("'don't like' not read as a like", _extract_likes("i don't like spiders") == [])

    topics = _extract_topics("why is the sky blue and what are planets")
    check("topics drop stopwords, keep content", "planets" in topics and "what" not in topics)


def newmem(db_path, llm=None):
    return PersistentMemory(
        db_path=db_path, child_id="test-child", window_turns=8, llm=llm,
        summarize_every=2,
    )


async def test_persistence_and_recall():
    print("\npersistence + recall (SQLite round-trip across sessions):")
    tmp = tempfile.mkdtemp(prefix="maxi_mem_")
    db = os.path.join(tmp, "mem.db")

    # --- Session 1: the child introduces themselves.
    mem1 = newmem(db)
    # A brand-new child = no recall block yet (identical to WindowMemory).
    fresh = await mem1.context()
    check("new child: no recall block (only persona)", len(fresh) == 1 and fresh[0]["role"] == "system")

    await mem1.add_user("Hi Maxi, my name is Amina and i love football")
    await mem1.add_assistant("Nice to meet you, Amina!")
    await mem1.add_user("can you teach me about planets? i don't like spiders")
    mem1.store.close()

    # --- Session 2: a FRESH object on the same DB must remember everything.
    mem2 = newmem(db)
    msgs = await mem2.context("hello again")
    recall = next((m["content"] for m in msgs if m["role"] == "system" and "met before" in m["content"]), "")
    check("session 2 recalls the name", "Amina" in recall)
    check("session 2 recalls a like (football)", "football" in recall)
    check("session 2 recalls a dislike (spiders)", "spiders" in recall)
    check("session 2 recalls a topic (planets)", "planets" in recall)
    check("recall is a separate system message", any(
        m["role"] == "system" and "met before" in m["content"] for m in msgs))
    mem2.store.close()


async def test_summary_with_fake_llm():
    print("\nrolling summary (fake LLM, no network):")
    tmp = tempfile.mkdtemp(prefix="maxi_mem_")
    db = os.path.join(tmp, "mem.db")
    llm = FakeLLM()
    mem = newmem(db, llm=llm)

    await mem.add_user("my name is Amina, i love football")
    await mem.add_assistant("Great, Amina!")
    summary = await mem.summarize_now()
    check("summarize_now returns text", bool(summary))
    check("summary persisted to store", "football" in mem.store.get_summary())
    check("fake LLM was actually called", len(llm.calls) == 1)

    # The stored summary shows up in the next context() recall block.
    msgs = await mem.context()
    recall = next((m["content"] for m in msgs if "met before" in m["content"]), "")
    check("summary appears in recall", "learning addition" in recall)

    # No-LLM memory: summarize_now is a safe no-op.
    mem_nollm = newmem(db + ".2")
    await mem_nollm.add_user("hello there friend")
    check("summarize_now with no LLM returns None", await mem_nollm.summarize_now() is None)
    mem.store.close()
    mem_nollm.store.close()


async def test_learning_never_crashes():
    print("\nrobustness:")
    tmp = tempfile.mkdtemp(prefix="maxi_mem_")
    mem = newmem(os.path.join(tmp, "mem.db"))
    for junk in ["", "   ", "???", "12345", "a", "!!!"]:
        await mem.add_user(junk)  # must not raise
    check("odd/empty inputs don't crash learning", True)
    mem.store.close()


async def main():
    test_extractors()
    await test_persistence_and_recall()
    await test_summary_with_fake_llm()
    await test_learning_never_crashes()
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
