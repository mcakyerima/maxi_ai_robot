# Maxi v2 — Session Handoff

This is the bridge document for continuing work in a new session. Read this first,
then `ARCHITECTURE.md` and `docs/BARGE_IN.md`. Memory files under the Claude memory
dir also carry the key facts.

---

## 0. Latest session (2026-07-28) — what changed since §9
All pushed to `main` and deployed on Railway (verified) UNLESS noted. Details live in
the Claude memory files (read those + this):
- **Long-term memory (SHIPPED, live):** `PersistentMemory` (SQLite facts/topics + rolling
  summary, no heavy deps). On Railway it needs a **Volume** at `/data` + `MAXI_MEMORY_DB=
  /data/maxi_memory.db` (else the ephemeral disk wipes it). See §9b + [[maxi-longterm-memory]].
- **Hands-free "Hey Maxi" (SHIPPED):** pluggable `wakeProvider` in `maxi_voice_engine.js`.
  Picovoice/Porcupine went sales-gated → default is **Vosk** (no account), model + **Maxi-voice
  wake-ack clips** hosted on the Railway volume (`maxi/services/models.py`), served `/models`,
  `/acks`. Wake is beepless; CAPTURE uses webkitSpeechRecognition (one beep). `MAXI_WAKE_ENGINE=
  auto`. See [[maxi-hands-free-wakeword]].
- **Mic/UX fixes (SHIPPED):** cross-turn mic-contention fix (serialized Vosk mic), name-bug fix
  ("Coming"), spelling via say_as + the `B! A! N!` hack, robot-face **emotions** (chat face +
  math emoji badge), **Maxi's head** = tap→random animation / hold-3s→refresh-reset, **/settings
  + in-page Wake-Word toggle** (buttons-only fallback for the demo). See [[maxi-skills-extras]],
  [[maxi-head-reset]].
- **New skills (SHIPPED):** time/date, storytelling, spelling, quizzes (intent-based in ChatSkill).
- **Presentation (NOT committed):** `build_presentation.py` → `Maxi_Robot_Presentation.pptx` in
  root, 16 slides, sibling design system, verified via PNG export. Has a fill-in HARDWARE BOM +
  placeholder names. See [[maxi-presentation]].
- **Hands bring-up tooling (SHIPPED, awaiting the live hardware pass):** everything needed to
  connect the physical hands — see **`docs/HANDS_BRINGUP.md`**, a numbered STEP 1–20 runbook
  the user + children follow on the day (wiring → copy files to the Pi → one-command install →
  calibrate → tunnel → Railway → live test), plus a troubleshooting table and a printable
  tear-off checklist. Details in §9d.
- **PENDING / NEXT:** the actual **live hardware pass** — run `hardware/start_hands.sh` on the Pi,
  `tools/check_hands.py` from the laptop, set Railway `RASPBERRY_PI_URL` + `MAXI_HAND_API_KEY`,
  confirm `/hands/status` says `"mode":"hardware"`, then "Hey Maxi, what is 3 plus 2" → fingers
  move. Aug-4-2026 demo → favor reliability ([[maxi-presentation-deadline]]).

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
- **Hands-free wake word (two engines, `MAXI_WAKE_ENGINE=auto`):** **Vosk** (no account,
  real "Hey Maxi") or **Porcupine** (needs a Picovoice key — now sales-gated). `auto` =
  Porcupine if `PICOVOICE_ACCESS_KEY` set, else **Vosk**. Vosk's ~40 MB model is served
  from the Railway volume (`/data/models`, auto-downloaded once on boot). No engine
  ready → push-to-talk. **Full guide: `docs/WAKEWORD.md`.**
- **Long-term memory (optional, sensible defaults):** `MAXI_MEMORY_ENABLED` (default on),
  `MAXI_MEMORY_DB` (default `<repo>/data/maxi_memory.db`), `MAXI_CHILD_ID` (default
  `default`), `MAXI_MEMORY_SUMMARIZE_EVERY` (default 6). ⚠️ **Railway's default
  filesystem is EPHEMERAL** — the memory DB resets on every redeploy. For memory that
  survives deploys, attach a Railway **Volume** and set `MAXI_MEMORY_DB` to a path on it.

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
  memory.py      WindowMemory (ephemeral) + PersistentMemory (long-term: SQLite
                 facts/topics + rolling summary; no heavy deps). Factory uses the
                 latter. Embedding context_manager still NOT wired (kept off Railway).
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
`ui/static/js/maxi_voice_engine.js` (wake-word/barge-in engine; pluggable `wakeProvider`),
`ui/static/js/porcupine_wake.js` (beepless on-device wake word — Porcupine Web),
`ui/static/js/audio_player.js`, `ui/sw.js` (network-first service worker).
Wake-word config served at runtime by `/voice_config.js` (from `settings.voice`).

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

## 9. Just built (this session): step-by-step math — WORKING & verified on Railway
- **Simple arithmetic** (`A op B`): fingers if answer 0–10, UI equation if >10.
- **Multi-operand** ("5 + 3 + 2"): solved locally into left-to-right steps.
- **Word problems / complex:** Groq JSON (`intro`, `steps[{operation,result,description}]`,
  `final_answer`, `breakdown`) → renders the step list in the UI (`math_result` advanced) then
  speaks each step while emitting `highlight_step` so the UI highlights in sync (paced per step).
- **Explanations are story-contextual & kid-friendly** (uses the real objects/actions, e.g.
  "You give 2 mangoes to Fatima… you eat 3… so you have 5 mangoes left!" — not "the answer is 5").
- **Routing gate `_is_bare_arithmetic`**: local solvers ONLY handle a plain sum; word problems
  go to the LLM. (Bug fixed: "and" was read as "+", so "10 mangoes and give 2 and eat 3"
  wrongly computed 15 via the local solver — now it correctly routes to the LLM → 5.)
- **Word problems REQUIRE Groq working** → `GROQ_MODEL=llama-3.1-8b-instant` must be set on Railway.
- Diagnostic logs still in: startup "MAXI BUILD MARKER…" + per-question "🧮 MATH-V2… path=…".
  Handy for verifying deploys; can be stripped when no longer needed.
- UI machinery already existed in `math.html` (`displayAdvancedMath`, `highlightStep`).

**TEST THIS FIRST in the new session (after `GROQ_MODEL=llama-3.1-8b-instant` on Railway):**
1. "what is 2 plus 2" → `2 + 2 = 4`, counted on fingers, then idle (mic resets).
2. "what is 8 plus 7" → `15` in the UI (no fingers).
3. "what is 5 plus 3 plus 2" → step list, highlights each step as it explains, answer 10.
4. A word problem, e.g. "if I have 3 mangoes and buy 4 more, how many do I have?" →
   step-by-step in the UI + voice. Watch the highlight sync; tune the per-step `asyncio.sleep`
   in `math.py _walk_steps` if it drifts.

---

## 9b. Just built (this session): long-term memory — "Maxi remembers the child"
Lightweight, deployable, no heavy deps (stdlib `sqlite3` only — the embedding
`brain/context_manager` stays OFF the Railway image on purpose).
- **`maxi/services/memory.py` → `PersistentMemory`** (same `Memory` interface, so BOTH
  chat and math skills gained memory with zero call-site changes). Keeps the fast
  sliding window AND a durable per-child SQLite store (`MemoryStore`).
- **Learns deterministically (no network, fully unit-tested):** name (`my name is…`,
  `call me…`, gated `i am…` so "i am happy/five" is never a name), likes/dislikes
  (`i like/love…`, `favorite X is…`, `i don't like/hate…`), and **topics** (content
  words, stopword-filtered, recency+count ranked).
- **Rolling summary** = the ONLY LLM-backed piece: fire-and-forget every
  `SUMMARIZE_EVERY` (6) assistant turns, 10s timeout, degrades to a no-op when Groq is off.
- **Recall** is injected as ONE extra `system` message ("child you've met before: name…,
  likes…, recently asked about…, what you remember…"). **A brand-new child gets NO block**,
  so behavior is byte-identical to the old `WindowMemory` until Maxi has actually learned
  something — no regression risk to chat/math.
- **Persistence is across sessions**, not just in-process: a fresh `Session` (new
  `session_id` each connect) reads the same DB, so Maxi greets a returning child by name.
- Config: `MemorySettings` in `config.py` (`MAXI_MEMORY_*` env, see §3). DB is `.gitignore`d.
- **Verified:** `venv/Scripts/python.exe tests/test_memory.py` → 24/24 (extraction,
  cross-session persistence, recall injection, summary via a fake LLM, robustness). Existing
  barge-in + playback tests still pass; factory boots with `PersistentMemory`.
- **Try it on device:** tell Maxi "my name is Amina and I love football", ask a couple
  things, reconnect/restart, then just say "hi" — the answer should use the name/interests.

---

## 9c. Just built (this session): hands-free "Hey Maxi" — beepless wake word
Full guide: **`docs/WAKEWORD.md`**. Buildable + unit-tested with no hardware/account;
live-testable once a (free) Picovoice AccessKey is set.
- **Key insight:** the Android beep storm is ONLY the idle WAKE stage. So an on-device
  wake model (Porcupine Web / WASM over `getUserMedia`, no `webkitSpeechRecognition`)
  owns WAKE + speaking BARGE_IN (beepless); `webkitSpeechRecognition` is used ONLY to
  capture the one question (one acceptable beep, like Google Assistant).
- **`maxi_voice_engine.js`** gained a pluggable **`wakeProvider`**. Ready provider →
  beepless WAKE/BARGE_IN; CAPTURE pauses the provider's mic (so the two don't fight
  over the microphone) then resumes. Barge-in via the wake word is echo-safe (Maxi
  never says its own wake word). NON-provider behavior is byte-identical to before.
- **`porcupine_wake.js`** = `PorcupineWakeProvider`: CDN-loads the Porcupine Web SDK,
  runs it via WebVoiceProcessor. **Fully defensive** — no key / CDN fail / insecure
  context → `isReady()` false → engine falls back to push-to-talk. Progressive
  enhancement, never a hard dep.
- **Config** `settings.voice` (`VoiceSettings`) served at runtime via `/voice_config.js`
  so the **AccessKey is never committed**. Startup log: `🎙️ hands-free wake word ON/OFF`.
- Default keyword is a **built-in "Computer"** (works with just an AccessKey, no
  training). Custom "Hey Maxi" = train a WASM `.ppn` on the Picovoice console, set
  `PICOVOICE_KEYWORD_URL` (see WAKEWORD.md §3).
- **Update (Picovoice went sales-gated):** added a second engine **Vosk** (`vosk_wake.js`,
  no account, real "Hey Maxi", ~40 MB model served from the Railway volume via a boot-time
  one-time download + `/models/` route). `MAXI_WAKE_ENGINE=auto` picks Porcupine if a key
  exists, else Vosk. Both share the SAME `wakeProvider` slot — flip with one env var.
  This is the path to use NOW (no signup). See `docs/WAKEWORD.md`.
- **Verified:** `node tests/test_voice_engine.mjs` → **15/15** (7 original + 8 new:
  beepless WAKE, CAPTURE mic hand-off, provider barge-in, onset-deafness, not-ready
  fallback, reapplyMode, no-provider unchanged). Page JS syntax-checked; `/voice_config.js`
  renders; existing python tests still pass.
- **To go live:** set `PICOVOICE_ACCESS_KEY` on Railway → open `/chat` over https → say
  "Computer" (no beep) → ask → answer. `?maxidebug=1` HUD shows `hands-free (wake-model)`.

---

## 9d. Just built (this session): hands bring-up — self-healing link to the Pi
Full guide: **`docs/HANDS_BRINGUP.md`**. The goal was to make the cloud→Pi link survive
demo-day conditions and be verifiable without reading Railway logs.
- **The bug this fixes:** `HandsActuator.initialize()` probed the Pi exactly ONCE at brain
  boot. Railway almost always boots before the Pi's tunnel exists → `available=False`
  forever → silent simulation until someone redeployed. Free quick-tunnels also restart.
- **`maxi/actuators/hands.py` now re-probes lazily** (`_ensure_available`, 20 s cooldown;
  120 s after a 401). A dead tunnel's own **HTTP 5xx error page** now counts as "Pi gone"
  too (it isn't a connection error, so it used to look like a valid reply). Recovery needs
  no redeploy. Adds `probe()`, `status()`, and `last_error`.
- **Two diagnostic routes** (`maxi/server.py`), usable from any phone browser:
  `/hands/status[?probe=1]` → `{"mode":"hardware"|"simulation …","last_error":…}` (never
  leaks the API key) and `/hands/test?pin=<PARENT_DASHBOARD_PIN>&n=3` → moves real fingers
  without the tablet. Backed by a new `Transport.run_coro()` (Flask thread → brain loop).
- **`hardware/start_hands.sh`** (NEW, for the Pi) — two modes:
  `--setup` does the whole ONE-TIME install (apt packages, `raspi-config nonint do_i2c 0`,
  a `hardware/venv` from the new `requirements_pi.txt`, arch-correct `cloudflared` .deb) and
  moves nothing; with no argument it checks `i2cdetect` for 0x40, warns if
  `hand_calibration.json` is missing, starts the API on :5001, waits for `/health`, opens a
  **cloudflared quick tunnel** (`TUNNEL=ngrok|none` too), verifies the public URL, and
  prints the exact Railway vars. First run auto-runs setup then stops so you calibrate
  before anything moves. Ctrl-C stops both. Logs to `hardware/logs/`.
- **`tools/check_hands.py`** (NEW, stdlib only): pre-flights the tunnel from the laptop the
  same way the brain does — `/health`, key check via `/status`, warns on degraded hardware /
  unsaved calibration / latched e-stop, `--move` counts 3→5→0, and flags moves slower than
  `HANDS_TIMEOUT`.
- **Pi bug fixed** in `hardware/finger_controller_api.py`: `make_fist`/`make_peace`/`wave`/
  `count_to_ten` were defined INSIDE the `/gesture` route body (dead code after its
  `return`), so the lambda shim hit `AttributeError` → every `/gesture` call 500'd. They're
  real class methods now. ⚠️ **This file must be re-copied to the Pi.** (The math/finger
  path — `/show_number`, `/move_finger` — was never affected.)
- **Verified:** `tests/test_hands_reconnect.py` → **28/28** against a fake Pi on a real
  socket (boot-then-appear, mid-session tunnel drop + recovery, 401 handling, forced sim,
  no key leakage); the new routes exercised end-to-end on the real Flask app; full existing
  suite still passes. **NOT yet verified on real servos** — that's the live pass.

---

## 10. Roadmap (priority order) — pick up here
**Tier 1 — finish/validate**
1. ✅ Step-by-step math (just done — verify on device).
2. **Real hardware test pass** (Pi hands + tablet mic) and tune thresholds. BIGGEST gap.
   Tooling + guide are now ready (§9d, `docs/HANDS_BRINGUP.md`); only the live run remains.
3. ✅ **True hands-free "Hey Maxi" (beepless)** — DONE this session via a pluggable
   `wakeProvider` + Porcupine Web (`porcupine_wake.js`). See §9c + `docs/WAKEWORD.md`.
   Remaining polish: train the custom "Hey Maxi" WASM `.ppn` (built-in "Computer" for
   now); optionally vendor the SDK/model for CDN-independence.

**Tier 2 — robustness**
4. Proper realtime server (gunicorn + eventlet/gevent) → real WebSockets, lower latency.
5. Session scoping (rooms) so multiple devices don't share one brain.
6. Groq model fallback / quota-aware messaging (partly done).

**Tier 3 — advanced tutor**
7. ✅ **Long-term memory (lightweight):** DONE this session — `PersistentMemory`
   (SQLite facts/topics + rolling summary, no heavy deps). See §9b. Future option:
   upgrade to embedding recall via `brain/context_manager` IF semantic search is ever
   needed (adds torch/sentence-transformers — deliberately avoided for now).
8. ✅ More skills (DONE, intent-based in ChatSkill): **time/date**
   (`skills/datetime_intent.py`), **storytelling / spelling / quizzes**
   (`skills/play_intents.py`). Spelling is answered locally; story/quiz use a
   specialised LLM prompt + the child's name. Add more the same way.
9. ✅ Personality/expression (DONE, first pass): `emotion` event
   (`events.emotion`) → tablet robot-face expressions (happy/excited/curious/sad) in
   chat.html; skills emit per intent. Extend to math + more nuance later.
10. ~ Local language (started): persona may greet in Hausa ("Sannu"), a "Sannu!"
    wake ack, local greeting. Deepen (Hausa/Kanuri/pidgin) later.

**Tier 4 — body & pedagogy**
11. More limbs (arms/head/eyes) — actuator abstraction is ready.
12. Vision (camera input).
13. Curriculum + progress tracking + parent dashboard insights.

---

## 11. Recent commit trail (newest first)
- (this session) hands-free "Hey Maxi": beepless on-device wake word (Porcupine Web) + pluggable wakeProvider
- (this session) long-term memory: PersistentMemory (SQLite facts/topics + rolling summary)
- `230a415` fix word problems misrouted to local solver ("and"→"+"; now LLM path, answer correct)
- `b7d923a` build marker + math diagnostic logs
- `4250886` kid-friendly, story-contextual word-problem explanations (+ final_answer)
- `936f996` this handoff doc
- `2d08540` step-by-step math (multi-operand + word problems + highlight sync)
- `523b164` math: preserve spoken operators, drive equation+fingers, align states
- `958f1e5` barge-in actually stops playback (drop in-flight chunks)
- `d3a30f7` stay SPEAKING until tablet finishes playing
- `c272588` streaming smoothness + mic status/beep + natural interruption
- `17c7727` Groq quota handling + model + streaming UI ("Oops" fix)
- `fde13ee` push-to-talk default (Android beep storm)
- `e21f5dd` wake-gated turns + polling transport (runaway loop fix)
- earlier: full v2 rebuild + legacy cleanup (see maxi-refactor-plan memory)
