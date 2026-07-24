# Maxi AI — Architecture (v2)

Maxi is an AI educational robot that tutors children (ages 6–12). It talks, listens,
can be interrupted mid-sentence, and actuates physical limbs (v1: 10 fingers + wrist).
This document describes the **v2 ground-up architecture** that replaces the tangled
`main.py` / `ui/app.py` design.

## 1. Physical / deployment topology

```
┌──────────────────────────────┐        ┌─────────────────────────────┐        ┌──────────────────────┐
│  ANDROID TABLET (Maxi chest)  │  WS    │   BACKEND  (Railway cloud)  │  HTTP  │  RASPBERRY PI (robot) │
│  ── the senses & face ──      │◄──────►│   ── the brain ──           │───────►│  ── the muscles ──    │
│                               │        │                             │        │                      │
│ • Web Speech STT (mic)        │        │ • Flask + Socket.IO gateway │        │ • Flask REST :5001   │
│ • "Hey Maxi" wake word (cont.)│        │ • Orchestrator state machine│        │ • PCA9685 servo ctrl │
│ • "Stop" voice barge-in       │        │ • Skills (chat/math/…)      │        │ • 10 fingers + wrist │
│ • Audio playback (Edge-TTS)   │        │ • Groq LLM (streaming)      │        │                      │
│ • Robot face + mode UI (PWA)  │        │ • Edge-TTS (streaming)      │        │                      │
└──────────────────────────────┘        │ • Memory + Safety           │        └──────────────────────┘
                                         └─────────────────────────────┘
```

**Why this split:** the tablet is the only device with a microphone and speaker near
the child, so *all audio in/out lives on the tablet*. The backend is pure logic and can
run anywhere with internet. The Pi is a dumb, reliable actuator behind an HTTP API.

> Root-cause note: v1 wake word / interruption never worked because they ran server-side
> `pyaudio` on a microphone that doesn't exist in the cloud. v2 moves both to the tablet.

## 2. The free stack

| Concern            | Tool                         | Where it runs |
|--------------------|------------------------------|---------------|
| Speech-to-text     | Browser Web Speech API       | Tablet        |
| Wake word          | Web Speech keyword spotting  | Tablet        |
| Interruption       | Web Speech barge-in listener | Tablet        |
| LLM                | Groq API (free tier)         | Backend       |
| Text-to-speech     | Microsoft Edge-TTS (free)    | Backend → tablet plays audio |
| Hand control       | Flask + adafruit PCA9685     | Raspberry Pi  |

## 3. Backend package layout (`maxi/`)

```
maxi/
  config.py              Typed, centralized settings from env (one source of truth)
  server.py              Flask app + PWA routes + Socket.IO transport (entry point)
  core/
    events.py            Typed event/message models (tablet ⇄ brain contract)
    session.py           Per-conversation state (mode, phase, interrupt flag)
    orchestrator.py      Async conversation engine + state machine
  services/
    llm.py               Groq streaming client (provider-agnostic interface)
    tts.py               Edge-TTS streaming → base64 audio chunks
    memory.py            Conversation context / long-term memory (SQLite + embeddings)
    safety.py            Content filter, rate limiter, usage tracker
  skills/
    base.py              Skill interface + registry
    chat.py              General tutoring chat
    math.py              Math with finger-counting gestures
    (time / weather / humor as needed)
  actuators/
    hands.py             Finger + wrist controller (HTTP client to the Pi)
    limbs.py             Limb abstraction (extensible for future arms/head/etc.)
```

Legacy `brain/`, `voice/`, `ui/` are ported into this layout and then removed.

## 4. Conversation state machine

```
        wake word / mic tap
IDLE ─────────────────────────► LISTENING
 ▲                                  │ transcription received
 │ timeout / "goodbye"              ▼
 │                               THINKING ──(Groq stream)──► SPEAKING
 │                                  ▲                          │
 │                                  │  barge-in ("stop")       │ audio done
 └──────────────────────────────────┴──────────────────────────┘
```

**Barge-in is a first-class transition.** SPEAKING runs a cancellable task
(Groq → sentence chunker → Edge-TTS → audio chunks). An `interrupt` event from the
tablet cancels the task immediately, flushes queued audio, and returns to LISTENING.

## 5. Streaming pipeline (low latency + interruptible)

```
Groq tokens ─► sentence buffer ─► Edge-TTS(sentence) ─► base64 mp3 ─► WS audio_chunk ─► tablet plays
     ▲                                                                                     │
     └───────────────────── cancel on interrupt (asyncio.Task.cancel) ◄────────────────────┘
```

Speaking one sentence at a time (not the whole answer) means the first words play in
~1s and any interrupt stops within one sentence.

## 6. Tablet ⇄ brain WebSocket contract (Socket.IO `message` channel)

**Tablet → brain:** `wake_word_detected`, `user_transcription {text, confidence}`,
`interrupted`, `audio_started` / `audio_complete` / `audio_interrupted`, `set_mode {mode}`,
`back_to_menu`, `ping`.

**Brain → tablet:** `state_change {state}`, `transcription {text}`,
`response` / `response_chunk` / `response_complete`, `audio_chunk {audio, format}`,
`finger_pose`, `error`, `pong`.

The v2 backend keeps this contract so the tablet keeps working during migration; the
tablet is then upgraded for continuous wake word + voice barge-in.

## 7. Extensibility (future limbs & skills)

- **New capability** → add a `Skill` subclass to `maxi/skills/` and register it.
- **New limb** (arm, head, eyes) → add an actuator to `maxi/actuators/` behind the same
  Pi HTTP pattern; skills call limbs through the `limbs` abstraction.
- The orchestrator and transport never change when capabilities or limbs are added.
```
