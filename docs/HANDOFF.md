# Maxi v2 — Session Handoff

This is the bridge document for continuing work in a new session. Read this first,
then `ARCHITECTURE.md` and `docs/BARGE_IN.md`. Memory files under the Claude memory
dir also carry the key facts.

---

## 1. What Maxi is
An AI educational robot that tutors Nigerian children (ages 6–12), built at Maxeeton
Technology by Mohammed Kaka. It talks, listens, can be interrupted, and moves 10
physical fingers + wrists. Two modes: **General Chat** and **Math (with fingers)**.

**3 tiers:** Android tablet (mic/STT + speaker + robot face UI) ⇄ cloud backend
(the brain, on Railway) ⇄ Raspberry Pi (finger servos over HTTP).
**Free stack:** Groq (LLM) · Edge-TTS (voice) · browser Web Speech (STT).

---

## 2. How to run / test / deploy

```bash
# Run locally (Windows). ALWAYS use the repo venv, not system python.
venv/Scripts/python.exe start.py          # serves http://localhost:5002
# or:  venv/Scripts/python.exe -m maxi.server

# Tests (all pass today):
venv/Scripts/python.exe tests/test_orchestrator_bargein.py   # barge-in state machine
venv/Scripts/python.exe tests/test_playback_gating.py        # SPEAKING until audio done
node tests/test_voice_engine.mjs                             # wake word + self-echo

# Validate tablet JS after editing chat.html/math.html (extract the big <script> and node --check it):
#   python: big=max(re.findall(r'<script>(.*?)</script>', html, re.S), key=len); write to a .js; node --check it

# Deploy: git push origin main  → Railway auto-deploys (Procfile/railway.json run `python start.py`).
```

**Windows console gotcha:** emoji prints crash cp1252 consoles. `start.py`/`server.py`
reconfigure stdout to UTF-8; for ad-hoc scripts prefix `PYTHONIOENCODING=utf-8`.

---

## 3. Railway env vars (CRITICAL — .env is NOT deployed)
Set these in Railway → service → Variables:
- `GROQ_API_KEY` — **required** (no answers without it).
- `GROQ_MODEL=llama-3.1-8b-instant` — **important**: the free-tier daily token limit
  on 70b/compound models (100k/day) runs out fast → "Oops" everywhere. 8b-instant has
  a much larger free budget. (Default in code is already 8b-instant; set/remove the var
  so it isn't pinned to compound-beta-mini.)
- `RASPBERRY_PI_URL=https://<pi-tunnel>` (+ `MAXI_HAND_API_KEY`) — only if you want the
  physical hands from the cloud (Railway can't reach a LAN IP). Else hands run in sim.
- `PORT` is set by Railway automatically.

---

## 4. Backend file map (`maxi/`)
```
config.py        typed settings from env (from maxi.config import settings)
persona.py       Maxi's voice + kid-safety rules + greetings + INTERRUPT_ACKS
server.py        Flask + Socket.IO entry; runs the brain on a bg thread; PWA routes
factory.py       assembles the Orchestrator (services + skills + hands)
core/
  events.py      the tablet⇄brain message contract (Incoming/Outgoing enums + builders)
  session.py     per-conversation state; speaking_task (cancel = barge-in); playback_done
  transport.py   sync Flask ⇄ async brain bridge (emit / submit / next_message)
  speaker.py     per-sentence interruptible speech out (no artificial pacing)
  orchestrator.py the async state machine (see §5)
services/
  llm.py         Groq streaming; NEVER throws (falls back to friendly msg); complete(json_mode)
  tts.py         Edge-TTS, one sentence at a time, retry + voice fallback
  memory.py      WindowMemory (fast, in-process). Advanced embedding memory NOT wired.
  safety.py      wraps brain.safety (content filter, rate limiter, usage tracker)
skills/
  base.py        Skill + SkillContext + SkillRouter (register a skill → it's live)
  chat.py        general tutoring
  math.py        arithmetic (fingers ≤10 / UI >10) + step-by-step (multi-operand + word problems)
actuators/
  hands.py       Raspberry Pi HTTP client; graceful sim fallback
```
Reused legacy kept: `brain/safety/`, `brain/context_manager/` (for future memory),
`integrations/{weather_api,humor_db}` (future skills), `ui/` (templates/static/routes),
`hardware/` (Pi code — UNCHANGED, runs on the Pi). All other legacy was deleted.

Tablet: `ui/templates/{chat,math,menu,settings}.html`,
`ui/static/js/maxi_voice_engine.js` (the wake-word/barge-in engine),
`ui/static/js/audio_player.js`, `ui/sw.js` (network-first service worker).

---

## 5. Conversation state machine (orchestrator)
`IDLE → (wake word / mic tap) → LISTENING → THINKING → SPEAKING → (audio_complete) → IDLE`

Key behaviors (hard-won, don't regress):
- **Wake-gated:** it does NOT auto-listen on connect or after answering — the child
  wakes it each turn (prevents the runaway listen→speak→listen loop).
- **Transcriptions only accepted in phase==LISTENING** (echo during other phases ignored).
- **SPEAKING holds until the tablet reports `audio_complete`** (playback_done), not just
  until sending finishes — so state is truthful and barge-in works to the last word.
  `_await_playback_done` MUST only run inside the speaking task, never inline in dispatch
  (would deadlock waiting for audio_complete the same loop must process).
- **Barge-in:** tablet drops incoming audio/text chunks after an interrupt (until the
  next `response_start`); backend cancels the task FIRST, then emits INTERRUPTED +
  response_start + a spoken ack. `audio_interrupted` does NOT end the turn; `audio_complete` does.

---

## 6. The voice engine (`maxi_voice_engine.js`) — read `docs/BARGE_IN.md`
- **PUSH-TO-TALK by default** because Android's webkitSpeechRecognition BEEPS on every
  start/stop; continuous listening = constant beeping. Mic is OFF when idle; tap to ask.
- Hands-free "Hey Maxi" + voice "stop" are OPT-IN via `?wake=1` (they beep on this platform).
- Self-echo rejection (Maxi ignoring its own voice) uses the `speaking_script` the backend
  publishes per sentence. Verified by `tests/test_voice_engine.mjs` (7/7).
- Debug HUD: open the page with `?maxidebug=1` → shows mode / heard / decision live.

---

## 7. Known constraints / gotchas
- **Transport is POLLING**, not WebSocket — the Flask dev server on Railway can't do raw
  WS (`write() before start_response`). Works, but higher latency. See roadmap 2.4.
- **Single client only:** `socketio.emit` broadcasts to ALL connected clients sharing ONE
  brain session. Two open browsers = scrambled state. Connect only the tablet.
- **Mic needs HTTPS:** browser speech is blocked on plain http LAN IPs; only localhost or
  https. Railway gives https. For local tablet testing use an ngrok/cloudflared tunnel.
- **Groq free quota:** 70b/compound share a small daily token limit; use 8b-instant.
- **⚠️ Dev machine disk was ~100% full** (C:, ~149 MB free after a temp cleanup). Writes/git
  will fail again until real space is freed. Flag this to the user.

---

## 8. What's verified vs NOT
- **Verified (unit/local):** barge-in state machine, playback gating, voice-engine
  self-echo logic, math parser (operators + multi-operand), server boots + serves 200s.
- **NOT tested on real hardware:** the actual Pi hands, the real tablet mic/echo, and
  timing/threshold tuning. This is the biggest gap — needs a live pass with the user.

---

## 9. Just built (this session's last task): step-by-step math
- **Simple arithmetic** (`A op B`): fingers if answer 0–10, UI equation if >10.
- **Multi-operand** ("5 + 3 + 2"): solved locally into left-to-right steps.
- **Word problems / complex:** Groq JSON (`intro`, `steps[{operation,result,description}]`,
  `breakdown`) → renders the step list in the UI (`math_result` advanced) then speaks each
  step while emitting `highlight_step` so the UI highlights in sync (paced per step).
- UI machinery already existed in `math.html` (`displayAdvancedMath`, `highlightStep`).

**TEST THIS FIRST in the new session (after `GROQ_MODEL=llama-3.1-8b-instant` on Railway):**
1. "what is 2 plus 2" → `2 + 2 = 4`, counted on fingers, then idle (mic resets).
2. "what is 8 plus 7" → `15` in the UI (no fingers).
3. "what is 5 plus 3 plus 2" → step list, highlights each step as it explains, answer 10.
4. A word problem, e.g. "if I have 3 mangoes and buy 4 more, how many do I have?" →
   step-by-step in the UI + voice. Watch the highlight sync; tune the per-step `asyncio.sleep`
   in `math.py _walk_steps` if it drifts.

---

## 10. Roadmap (priority order) — pick up here
**Tier 1 — finish/validate**
1. ✅ Step-by-step math (just done — verify on device).
2. **Real hardware test pass** (Pi hands + tablet mic) and tune thresholds. BIGGEST gap.
3. **True hands-free "Hey Maxi"** without beeps → integrate an on-device wake-word model
   (openWakeWord ONNX/WASM, or Porcupine Web) over getUserMedia. Slots into the voice
   engine's mode interface. Highest-impact UX upgrade.

**Tier 2 — robustness**
4. Proper realtime server (gunicorn + eventlet/gevent) → real WebSockets, lower latency.
5. Session scoping (rooms) so multiple devices don't share one brain.
6. Groq model fallback / quota-aware messaging (partly done).

**Tier 3 — advanced tutor**
7. **Long-term memory:** wire `brain/context_manager` (SQLite + embeddings) behind the
   `Memory` interface so Maxi remembers the child (name, interests, progress). Big win.
8. More skills: storytelling, spelling, science Q&A, quizzes, songs, games.
9. Personality/expression: richer robot-face emotions synced to content.
10. Local language (Hausa/Kanuri/pidgin).

**Tier 4 — body & pedagogy**
11. More limbs (arms/head/eyes) — actuator abstraction is ready.
12. Vision (camera input).
13. Curriculum + progress tracking + parent dashboard insights.

---

## 11. Recent commit trail (newest first)
- `2d08540` step-by-step math (multi-operand + word problems + highlight sync)
- `523b164` math: preserve spoken operators, drive equation+fingers, align states
- `958f1e5` barge-in actually stops playback (drop in-flight chunks)
- `d3a30f7` stay SPEAKING until tablet finishes playing
- `c272588` streaming smoothness + mic status/beep + natural interruption
- `17c7727` Groq quota handling + model + streaming UI ("Oops" fix)
- `fde13ee` push-to-talk default (Android beep storm)
- `e21f5dd` wake-gated turns + polling transport (runaway loop fix)
- earlier: full v2 rebuild + legacy cleanup (see maxi-refactor-plan memory)
