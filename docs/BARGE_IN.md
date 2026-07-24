# Barge-In & Wake-Word Engine (the hard part)

This is the engineering that makes Maxi feel like Alexa/Siri: it wakes to its name,
and you can cut it off mid-sentence — **without it interrupting itself.**

## The core problem: self-triggering

The tablet's speaker and microphone are inches apart. When Maxi talks, its **own voice
is picked up by its own microphone** (acoustic echo). A naive "if we hear speech while
speaking, stop" design makes Maxi hear itself and stop instantly. That was the v1 failure:
*Maxi treated its own words as an interruption.*

Real assistants defeat this with a layered defense. We use the same layers, all free:

### Layer 1 — Keyword-gated interruption (the Alexa model)
Maxi does **not** stop for arbitrary sound. It only stops when it hears an explicit
**barge-in keyword**: `"maxi"`, `"stop"`, `"stop maxi"`, `"wait"`, `"hold on"`, `"pause"`,
`"be quiet"`, `"shush"`, `"okay maxi"`, `"hey maxi"`. A child murmuring, a sibling, the TV,
or Maxi's own storytelling never trips it — only the trigger words do. This single rule
removes ~90% of false interrupts.

### Layer 2 — Self-echo rejection via the known script (the key trick)
**We generated Maxi's speech, so we know every word it is currently saying.** The tablet
keeps a live `spokenScript` buffer of the sentence(s) currently playing. When speech
recognition returns a phrase, we reject it if it is a fuzzy substring of `spokenScript`.
So even if the mic clearly hears Maxi say the word "stop" inside a sentence
("don't stop learning!"), it is ignored because that word belongs to Maxi's own script.
A barge-in only counts when the trigger word is **spoken by the child and is NOT in
Maxi's current script.**

### Layer 3 — Device acoustic echo cancellation (AEC)
The listening mic is opened through `getUserMedia({ audio: { echoCancellation: true,
noiseSuppression: true, autoGainControl: true } })`. The browser uses the audio it is
rendering as the AEC reference signal and cancels most of the echo before recognition
even sees it. This shrinks how often Layer 2 has to fire.

### Layer 4 — Timing gates & debounce
- **Onset deafness:** ignore recognition for the first ~350 ms after audio starts (the
  loudest echo transient).
- **Cooldown:** after a valid barge-in, ignore new triggers for ~800 ms so one "stop"
  doesn't fire twice.
- **Confidence floor:** drop results below a confidence threshold.

## Wake word ("Hey Maxi") when idle

When idle (nothing playing → no echo), one continuous recognizer listens for the wake
phrases (`"hey maxi"`, `"hi maxi"`, `"maxi"`, `"okay maxi"`). On match it transitions to
active listening and captures the child's question. Because there is no playback during
idle, wake-word spotting is simply keyword matching on the recognizer stream.

## One recognizer, three modes (state machine)

`webkitSpeechRecognition` allows only one healthy instance and auto-stops on silence, so a
single **`MaxiVoiceEngine`** owns it and swaps *modes* (not instances), restarting it on
`onend` to stay alive:

| Mode            | When              | What it accepts                                        |
|-----------------|-------------------|--------------------------------------------------------|
| `WAKE`          | Maxi idle         | wake phrases → start interaction                       |
| `CAPTURE`       | Maxi listening    | full utterance → send as `user_transcription`          |
| `BARGE_IN`      | Maxi speaking     | barge-in keywords, after Layer 2/3/4 filtering → `interrupted` |

## Backend responsibilities (the other half)

1. **Publish the script:** on every sentence it sends to be spoken, the backend also sends
   `speaking_script { text }` so the tablet's Layer 2 knows Maxi's current words.
2. **Speak one sentence at a time:** the LLM stream is chunked into sentences; each sentence
   is a separately cancellable Edge-TTS unit. First audio plays within ~1 s and an interrupt
   stops within one sentence, not one paragraph.
3. **Cancel instantly:** the SPEAKING state runs as a single `asyncio.Task`. On `interrupted`
   the orchestrator cancels it, flushes the audio queue, and transitions to LISTENING — no
   "finish the current paragraph" lag.

## Future hardening (optional, still free)
Swap the Web Speech recognizer for a dedicated on-device keyword spotter
(**openWakeWord** via ONNX/WASM, or Porcupine Web free tier) trained on "Hey Maxi" / "Stop".
KWS models are far more robust to echo and noise than full ASR and run at low CPU during
playback. The engine's mode interface stays identical — only the detector changes.
