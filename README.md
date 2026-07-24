# Maxi AI — Educational Robot (v2)

Maxi is an AI robot that tutors children (ages 6–12). It talks, listens, can be
**interrupted mid-sentence like Siri/Alexa**, and moves physical hands to count and
gesture. Built at Maxeeton Technology by Mohammed Kaka.

## How it's put together

Three tiers (full detail in [ARCHITECTURE.md](ARCHITECTURE.md)):

- **Tablet (Maxi's chest)** — a PWA. Does speech-to-text, plays Maxi's voice, shows the
  robot face, and runs the **voice engine**: continuous "Hey Maxi" wake word + self-echo-safe
  barge-in ([docs/BARGE_IN.md](docs/BARGE_IN.md)).
- **Backend (cloud / Railway)** — the brain. Flask + Socket.IO gateway around an async
  orchestrator that streams Groq answers into Edge-TTS speech and commands the hands.
- **Raspberry Pi (on the robot)** — a small REST API driving the finger/wrist servos.

The free stack: **Groq** (LLM) · **Edge-TTS** (voice) · **browser Web Speech** (STT).

## The backend (`maxi/`)

```
maxi/
  config.py        one typed settings source (reads .env)
  persona.py       Maxi's voice + kid-safety rules
  server.py        Flask + Socket.IO entry point  (python -m maxi.server)
  factory.py       assembles the brain
  core/            events · session · transport · speaker · orchestrator (state machine)
  services/        llm (Groq) · tts (Edge) · memory · safety
  skills/          chat · math   (add a skill → it's live)
  actuators/       hands (Raspberry Pi client)
```

## Run it

```bash
# 1. install deps (into the project venv)
pip install -r requirements.txt

# 2. set secrets
cp .env.example .env      # add GROQ_API_KEY, RASPBERRY_PI_IP/URL, etc.

# 3. start Maxi
python start.py           # serves http://localhost:5002
```

Open the tablet browser at `http://<server-ip>:5002` → tap **Chat** or **Math**.
Say **"Hey Maxi"** to wake it, and **"stop Maxi"** to interrupt.

## Tests

```bash
python tests/test_orchestrator_bargein.py   # backend barge-in state machine
node   tests/test_voice_engine.mjs          # tablet wake word + self-echo rejection
```

## The Raspberry Pi

Pi-side code lives in [hardware/](hardware/) (`finger_controller_api.py`) and runs on the
robot, not in the cloud app. The backend talks to it over HTTP via
[maxi/actuators/hands.py](maxi/actuators/hands.py).
