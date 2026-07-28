"""
maxi.skills.play_intents — fun learning intents inside general chat:
storytelling, spelling, and quizzes. No new UI modes: the child just asks
("tell me a story", "how do you spell cat", "quiz me") and ChatSkill routes here.

Split of work:
  * spelling of a specific word → answered LOCALLY (instant, always correct),
  * a spelling challenge / story / quiz → a specialised system prompt handed to the
    LLM so the answer is on-brand and personalised (child's name/interests).

Everything here is pure/deterministic (no I/O) so it's easy to unit-test.
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

# --- intent detection --------------------------------------------------------
_STORY_RE = re.compile(
    r"\b(tell|read|say|give)\s+(me\s+)?(a\s+|another\s+|one\s+)?(story|tale|bedtime\s+story)"
    r"|\bstory\s+time\b|\btell\s+me\s+a\s+story\b",
    re.I,
)
_QUIZ_RE = re.compile(
    r"\b(quiz\s+me|quiz\s+time|ask\s+me\s+a\s+question|ask\s+me\s+something"
    r"|play\s+a\s+quiz|give\s+me\s+a\s+quiz|test\s+me|riddle)\b",
    re.I,
)
# "how do you spell cat" / "spell mango" / "spelling of dog"
_SPELL_WORD_RE = re.compile(
    r"\b(?:how\s+(?:do|would)\s+you\s+spell|how\s+is\s+.*\s+spelled|spell\s+the\s+word|spell|spelling\s+of)\s+([a-z][a-z'\-]{1,20})\b",
    re.I,
)
# "let's do spelling" / "spelling game" / "teach me spelling" / "give me a word to spell"
_SPELL_GAME_RE = re.compile(
    r"\b(spelling\s+(game|practice|time)|teach\s+me\s+(to\s+)?spell(ing)?|let'?s\s+spell"
    r"|word\s+to\s+spell|a\s+spelling|do\s+spelling)\b",
    re.I,
)

# Simple, familiar words for the spelling game (Nigerian-child friendly).
SPELL_WORDS = [
    "cat", "dog", "sun", "book", "tree", "fish", "rice", "milk", "ball", "bird",
    "mango", "water", "house", "school", "friend", "yellow", "orange", "banana",
]

# Our voice agent (edge-tts) can't take SSML. The reliable hack (found in the MS
# voice sandbox): SPELL with the CAPITAL letters and a "!" after each one EXCEPT the
# last, space-separated — e.g. "B! A! N! A! N! A". The "!" forces the TTS to say each
# letter as its own natural, well-paced letter name instead of running them together.
def spell_spoken(word: str) -> str:
    letters = [ch.upper() for ch in word if ch.isalpha()]
    if not letters:
        return ""
    return " ".join([c + "!" for c in letters[:-1]] + [letters[-1]])


def spell_letters(word: str) -> str:
    """Real letters for the UI / transcript (the child SEES B - A - N - A - N - A)."""
    return " - ".join(ch.upper() for ch in word if ch.isalpha())


def spell_word_reply(word: str):
    """Return (spoken, display): SPEAK the letter hack, SHOW the clean letters."""
    w = word.strip().lower()
    spoken = f"{w.capitalize()} is spelled. {spell_spoken(w)}. {w.capitalize()}!"
    display = f"{w.capitalize()} is spelled {spell_letters(w)}. {w.capitalize()}!"
    return spoken, display


def spell_game_reply(index: int):
    """A teaching-style spelling prompt. Returns (spoken, display)."""
    word = SPELL_WORDS[index % len(SPELL_WORDS)]
    spoken = (f"Let's spell {word.capitalize()}. {spell_spoken(word)}. "
              f"{word.capitalize()}! Now you try it!")
    display = (f"Let's spell {word.capitalize()}! It goes {spell_letters(word)}. "
               f"{word.capitalize()}! Now you try it!")
    return spoken, display


def detect_play_intent(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Return (intent, arg). intent ∈ {story, quiz, spell_word, spell_game} or (None, None).
    For spell_word, arg is the word to spell."""
    if not text:
        return (None, None)
    m = _SPELL_WORD_RE.search(text)
    if m:
        return ("spell_word", m.group(1))
    if _SPELL_GAME_RE.search(text):
        return ("spell_game", None)
    if _STORY_RE.search(text):
        return ("story", None)
    if _QUIZ_RE.search(text):
        return ("quiz", None)
    return (None, None)


# --- LLM guidance for story / quiz (added as an extra system message) ---------
def play_system_prompt(intent: str, child_name: Optional[str] = None) -> str:
    who = f" The child's name is {child_name}; use it warmly." if child_name else ""
    if intent == "story":
        return (
            "The child asked for a STORY. Tell ONE short, gentle, imaginative story "
            "(about 5 to 8 short sentences) for a young Nigerian child. Use simple "
            "words and everyday things they'd know (mango trees, markets, animals, "
            "friends). Give it a tiny lesson or a happy ending. If you know the "
            "child's interests, weave them in. No scary or sad content." + who
        )
    if intent == "quiz":
        return (
            "The child wants a QUIZ. Ask exactly ONE fun, easy question a young child "
            "can answer (animals, colours, counting, nature, their body). Ask just the "
            "question in one short sentence, and stop — do NOT reveal the answer yet; "
            "you'll check their reply next." + who
        )
    return ""
