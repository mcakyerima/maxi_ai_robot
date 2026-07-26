# Hands-free "Hey Maxi" — beepless wake word

Maxi's tablet can listen hands-free with **no beeps** using an on-device wake-word
model running over `getUserMedia`. This replaces the beepy `webkitSpeechRecognition`
**only for the wake stage** — the actual question is still captured by
`webkitSpeechRecognition` (one acceptable beep per question, like Google Assistant).
It's a **progressive enhancement**: if nothing is configured/ready, the tablet
silently falls back to push-to-talk.

## Two engines, one switch (`MAXI_WAKE_ENGINE`)
Both plug into the same `wakeProvider` slot in `maxi_voice_engine.js`:

| Engine | Account? | Phrase | Notes |
|--------|----------|--------|-------|
| **Vosk** (`vosk_wake.js`) | **None** ✅ | real **"Hey Maxi"** | ~40 MB model served from Maxi's drive; more CPU |
| **Porcupine** (`porcupine_wake.js`) | Picovoice key (now sales-gated) | built-in "Computer" (custom "Hey Maxi" via train) | tiny model, lightest |

`MAXI_WAKE_ENGINE=auto` (default) → **Porcupine if a Picovoice key is set, else Vosk**.
Force with `vosk` / `porcupine`; disable with `off`. Startup log shows the resolved
engine. **Vosk needs no signup and gives the real "Hey Maxi" phrase — start here.**

### 🔴 Presentation safety switch — turn wake word OFF from /settings
Go to **/settings → Voice & Wake Word** and flip the toggle **OFF** to run **buttons
only** (tap the mic). This is a per-device client preference (localStorage
`maxi_wake_word`, read by /chat + /math) that needs no redeploy and doesn't depend on
the backend — the reliable mode to fall back to if the wake word misbehaves during a
demo. Default is ON. (Turning it OFF makes `pickWakeProvider()` return null → pure
push-to-talk.)

---

## Vosk (no account — recommended right now)
Vosk is a fully open, keyless offline speech model. `vosk-browser` runs it in the
tablet browser (WASM, in a worker) over `getUserMedia` — beepless like Porcupine — and
matches the real **"Hey Maxi"** phrase with no training. We restrict it to a tiny
grammar (`hey maxi`, `stop`) for speed + accuracy.

**Model hosting — on Maxi's own drive (the Railway volume):** the ~40 MB model lives
on the volume (same disk as the memory DB). On boot, if it's missing, Maxi downloads
it **once** in a background thread, then serves it same-origin from `/models/…` — no
runtime CDN, no CORS, persists across redeploys. The tablet caches it after first load.

### Setup (nothing to sign up for)
1. Keep `MAXI_WAKE_ENGINE=auto` (or set `=vosk`). With no Picovoice key, auto = Vosk.
2. Make sure a **Railway volume** is attached (you already have one at `/data` for
   memory). The model goes to `/data/models/` automatically.
3. Redeploy. First boot logs `⬇️ seeding Vosk model…` then `✅ Vosk model ready`.
   Until it's ready, `/voice_config.js` reports engine `none` (push-to-talk) — reload
   the tablet after the model finishes (a minute or two on first deploy).
4. Open `/chat` over **https**, say **"Hey Maxi"** → wakes with no beep → ask. Say
   "stop" while it talks to interrupt. `?maxidebug=1` HUD shows `hands-free (wake-model)`.

### Vosk env vars
| Var | Default | Meaning |
|-----|---------|---------|
| `MAXI_WAKE_ENGINE` | `auto` | `auto` \| `vosk` \| `porcupine` \| `off` |
| `MAXI_WAKE_PHRASE` | `hey maxi` | The wake phrase Vosk listens for. |
| `MAXI_MODEL_DIR` | volume `/models` | Where the model is stored/served. |
| `MAXI_VOSK_MODEL_FILE` | `vosk-model-small-en-us-0.15.tar.gz` | Filename on disk + at `/models/…`. |
| `MAXI_VOSK_MODEL_SOURCE` | ccoreilly gh tar.gz | One-time seed URL (verified reachable, ~41 MB). |
| `MAXI_VOSK_SDK_URL` | jsDelivr `vosk-browser@0.0.5` | The small SDK (`vosk.js`). |
| `MAXI_VOSK_MIN_CONFIDENCE` | `0.6` | Min avg word confidence to accept a wake (raise to `0.8` if noisy). |

**Tradeoffs vs Porcupine:** bigger one-time download (cached after), more tablet CPU
(mitigated by the tiny grammar), accuracy depends on the small model. No account,
though, and the real "Hey Maxi" phrase out of the box.

### Vosk is WAKE-ONLY (no hands-free barge-in) — by design
A small STT model mis-hears **Maxi's own voice** (and background chatter) as the wake
phrase. If Vosk listened while Maxi talked, it would falsely "interrupt" itself (you'd
hear an "I'm listening!" ack and get re-prompted — the double-mic bug). So the Vosk
provider sets `supportsBargeIn = false`: **the mic is OFF while Maxi speaks**, and Vosk
only listens for the wake phrase while idle. To interrupt mid-answer, **tap the mic
button**. (Porcupine, being a true wake-word DNN, is echo-safe and still does hands-free
barge-in.)

### Tuning false wakes
Detection uses FINAL results only, whole-phrase token matching, and a per-word
**confidence gate** (`MAXI_VOSK_MIN_CONFIDENCE`, default `0.6`). If background noise or
other people talking still wakes Maxi, **raise it toward `0.8`**; if it misses real
"Hey Maxi"s, lower it. The browser console logs `[vosk] ignored low-confidence wake …`
and `[vosk] WAKE …` so you can see what it's hearing and pick a threshold.

---

## Porcupine (best quality — when your Picovoice account is verified)
Picovoice now gates AccessKeys behind company-account/sales verification. Once you get
a key, Porcupine is the lightest, highest-accuracy option.

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
