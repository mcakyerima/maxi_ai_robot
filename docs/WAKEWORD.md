# Hands-free "Hey Maxi" — beepless wake word

Maxi's tablet can listen hands-free with **no beeps** using an on-device wake-word
model (Picovoice **Porcupine Web**, WebAssembly) running over `getUserMedia`. This
replaces the beepy `webkitSpeechRecognition` **only for the wake stage** — the actual
question is still captured by `webkitSpeechRecognition` (one acceptable beep per
question, like Google Assistant). It's a **progressive enhancement**: with no
AccessKey configured, the tablet silently falls back to the existing push-to-talk.

## Why this design
Android Chrome's `webkitSpeechRecognition` beeps on every start/stop and auto-stops
on silence, so *continuous* listening = a constant beep storm. The beep storm lives
**only** in the idle WAKE stage. So we let a beepless on-device model own WAKE (and
speaking barge-in), and keep `webkitSpeechRecognition` for just the one-shot question.
Barge-in via the wake word is naturally **echo-safe** — Maxi never says its own wake
word, so it can't interrupt itself.

## Architecture
- `ui/static/js/maxi_voice_engine.js` — gained a pluggable `wakeProvider`. When a
  ready provider is present: WAKE + BARGE_IN run through it (beepless); CAPTURE pauses
  the provider's mic and uses `webkitSpeechRecognition`, then resumes. Provider hits
  are routed by mode → `onWake` (idle) or `onInterrupt` (speaking).
- `ui/static/js/porcupine_wake.js` — `PorcupineWakeProvider`: loads the Porcupine Web
  SDK from a CDN, runs it over `getUserMedia` via WebVoiceProcessor. Fully defensive:
  any failure (no key, CDN down, insecure context) → `isReady()` stays false → engine
  falls back to push-to-talk. Never a hard dependency.
- `/voice_config.js` (backend route in `maxi/server.py`) — serves
  `window.MAXI_VOICE_CONFIG` from env at runtime, so the **AccessKey is never committed**.
- Config lives in `maxi/config.py` → `VoiceSettings` (`settings.voice`).

## Setup (one-time, free)

### 1. Get a Picovoice AccessKey (~2 min, free)
1. Sign up at **https://console.picovoice.ai/**.
2. Copy your **AccessKey** from the console home.
3. On Railway → service → **Variables**, add:
   ```
   PICOVOICE_ACCESS_KEY = <your access key>
   ```
   Optionally pick a built-in keyword (default is `Computer`):
   ```
   PICOVOICE_KEYWORD = Computer      # or Jarvis, Bumblebee, Hey Google, Grasshopper, …
   ```
   Redeploy. Startup log should show:
   `🎙️ hands-free wake word ON (say 'Computer') …`

### 2. Test on the tablet
Open `/chat` (or `/math`) over **https** (Railway or a tunnel — mic needs https).
- Say the keyword (**"Computer"**) → Maxi wakes with **no beep**, then beeps once as it
  starts listening for your question. Ask it. Answer plays. Say the keyword again to ask
  again — all hands-free.
- While Maxi is talking, say the keyword to **interrupt** (beepless barge-in).
- Add `?maxidebug=1` to the URL for a live HUD (mode / heard / decision). It shows
  `hands-free (wake-model)` when the beepless path is active.

### 3. (Later) Custom "Hey Maxi" keyword
Built-in keywords don't include "Hey Maxi". To use the real phrase:
1. In the Picovoice console → **Porcupine** → create a custom wake word "Hey Maxi",
   train it, and download the **WebAssembly (WASM)** `.ppn` (free tier allows this).
2. Put the file under `ui/static/wake/hey-maxi_wasm.ppn` (create the folder), or host it.
   Note: `.ppn` is currently in `.gitignore` — either commit it explicitly
   (`git add -f`) or serve it from a volume/URL.
3. Set on Railway:
   ```
   PICOVOICE_KEYWORD_URL   = /static/wake/hey-maxi_wasm.ppn
   PICOVOICE_KEYWORD_LABEL = Hey Maxi
   ```
   Redeploy. Now the wake phrase is "Hey Maxi".

## Env vars (all optional; absent key → push-to-talk)
| Var | Default | Meaning |
|-----|---------|---------|
| `PICOVOICE_ACCESS_KEY` | — | **Enables** hands-free. From console.picovoice.ai. |
| `PICOVOICE_KEYWORD` | `Computer` | Built-in keyword (ignored if a custom URL is set). |
| `PICOVOICE_SENSITIVITY` | `0.6` | 0–1; higher = more sensitive (more false wakes). |
| `PICOVOICE_KEYWORD_URL` | — | Custom WASM `.ppn` (e.g. trained "Hey Maxi"). |
| `PICOVOICE_KEYWORD_LABEL` | `Hey Maxi` | Label for the custom keyword. |
| `PICOVOICE_MODEL_URL` | jsDelivr CDN | Override `porcupine_params.pv` (vendor for robustness). |
| `PICOVOICE_SDK_PORCUPINE_URL` / `PICOVOICE_SDK_VP_URL` | jsDelivr `/+esm` | Override the SDK module URLs. |

## Robustness notes
- **CDN dependency:** the SDK + acoustic model load from jsDelivr by default. The robot
  needs internet anyway (Groq), and the service worker never touches cross-origin, so
  this is fine — but for production hardening you can **vendor** the SDK + `.pv` into
  `ui/static/` and point the `*_URL` vars at same-origin paths.
- **Verified:** `node tests/test_voice_engine.mjs` (15/15) covers the provider swap:
  beepless WAKE, CAPTURE mic hand-off, barge-in, onset-deafness, and graceful fallback
  when the provider isn't ready.
