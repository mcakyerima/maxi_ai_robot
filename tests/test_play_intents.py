"""
Self-audit: storytelling / spelling / quiz intent detection + local handlers.

Run:  venv/Scripts/python.exe tests/test_play_intents.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from maxi.skills.play_intents import (  # noqa: E402
    detect_play_intent,
    play_system_prompt,
    spell_game_reply,
    spell_word_reply,
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


print("intent detection:")
check("'tell me a story' → story", detect_play_intent("Maxi, tell me a story") == ("story", None))
check("'story time' → story", detect_play_intent("story time please") == ("story", None))
check("'quiz me' → quiz", detect_play_intent("quiz me!") == ("quiz", None))
check("'ask me a question' → quiz", detect_play_intent("can you ask me a question") == ("quiz", None))

i, arg = detect_play_intent("how do you spell cat")
check("'how do you spell cat' → spell_word cat", i == "spell_word" and arg == "cat")
i, arg = detect_play_intent("spell mango")
check("'spell mango' → spell_word mango", i == "spell_word" and arg == "mango")
check("'let's do spelling' → spell_game", detect_play_intent("let's do spelling") == ("spell_game", None))
check("'give me a word to spell' → spell_game", detect_play_intent("give me a word to spell") == ("spell_game", None))

check("plain question → no intent", detect_play_intent("why is the sky blue") == (None, None))
check("'what is 2 plus 2' → no intent", detect_play_intent("what is 2 plus 2") == (None, None))
check("empty → no intent", detect_play_intent("") == (None, None))

print("\nspelling (SPEAK letter sounds w/ pauses, SHOW real letters):")
spoken, display = spell_word_reply("cat")
check("spoken uses letter sounds + '!' pauses", "see! ay! tee!" in spoken)
check("display shows real letters", display == "Cat is spelled C - A - T. Cat!")
check("spoken != display", spoken != display)
sp_m, di_m = spell_word_reply("mango")
check("mango spoken sounds", "em! ay! en! gee! oh!" in sp_m)
check("mango display letters", "M - A - N - G - O" in di_m)
g_spoken, g_display = spell_game_reply(0)
check("game spoken has sounds + invite", "!" in g_spoken and "try" in g_spoken.lower())
check("game display has real letters + invite", " - " in g_display and "try" in g_display.lower())
check("game deterministic by index", spell_game_reply(0) == spell_game_reply(0))

print("\nllm guidance:")
story = play_system_prompt("story", "Fatima")
check("story prompt mentions story + name", "STORY" in story and "Fatima" in story)
check("quiz prompt asks ONE question, no answer yet",
      "ONE" in play_system_prompt("quiz") and "answer" in play_system_prompt("quiz").lower())
check("no name → no name clause", "name is" not in play_system_prompt("story"))

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
