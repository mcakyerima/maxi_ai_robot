# Maxi's Hands — bring-up & live test

How to get from "servos in a box" to **"Hey Maxi, what is 3 plus 2" → fingers move**,
driven by the cloud brain on Railway.

The chain is: **tablet → Railway (brain) → tunnel → Pi (:5001) → PCA9685 → 12 servos.**
Every step below verifies one link, so when something fails you know exactly which one.

---

## 0. What's on the Pi

| file | port | auth | notes |
|---|---|---|---|
| `finger_callibrator.py` | 5000 | none | web UI to set each finger's min/max. **Run FIRST.** Does *not* move on startup. |
| `finger_controller_api.py` | 5001 | `X-API-Key` | the production API the brain calls. **MOVES SERVOS ON BOOT.** |
| `start_hands.sh` | — | — | starts the API + a tunnel and prints the public URL. |

Both read/write `hand_calibration.json` **in the current working directory** — so always
`cd` into the same folder before running either, or they'll disagree about calibration.

---

## 1. Power & wiring (do this before any software)

⚠️ **MG996R servos are the #1 risk.** Each stalls at ~2.5 A; twelve of them can pull
well over 10 A. The Pi's 5 V rail cannot do this — trying will brown out the Pi
mid-demo (SD-card corruption, random reboots).

- External **5–6 V, ≥10 A** supply → PCA9685 **V+ / GND** screw terminals. **Never** the Pi's 5 V.
- **Common ground:** the supply's GND *must* also connect to a Pi GND pin. Without this,
  the PWM signal has no reference and servos twitch or ignore commands.
- PCA9685 **VCC** (logic) → Pi 3.3 V, **SDA**→GPIO2, **SCL**→GPIO3.
- A 1000 µF capacitor across V+/GND absorbs the current spike when fingers move together.
- Enable I²C once: `sudo raspi-config` → Interface Options → I2C → Yes → reboot.
- Verify: `i2cdetect -y 1` shows **40**. If not, nothing else will work.

---

## 2. Calibrate (once per physical build)

```bash
cd ~/maxi/hardware          # wherever the Pi files live
python3 finger_callibrator.py          # → http://<pi-ip>:5000
```

Open it from a laptop on the same Wi-Fi. For each finger set **min** (open) and **max**
(closed) so the finger reaches its travel limits **without pushing into a mechanical stop** —
a stalled MG996R gets hot and burns out. Then **SAVE** → writes `hand_calibration.json`.

Stop the calibrator (Ctrl-C) before starting the API — they both drive the same servos.

---

## 3. Start the hands + tunnel

```bash
chmod +x start_hands.sh
export MAXI_HAND_API_KEY="<a long random string>"     # or put it in ~/.maxi_hands.env
./start_hands.sh
```

It checks I²C, starts the API on :5001, waits for `/health`, opens a **cloudflared quick
tunnel** (no account needed), verifies the public URL, and prints the two Railway
variables to paste. `TUNNEL=ngrok ./start_hands.sh` uses ngrok instead;
`TUNNEL=none` is LAN-only (Railway cannot reach a LAN address).

Dry run with no servo movement: `SIMULATION_MODE=true ./start_hands.sh`.

> **Quick-tunnel URLs change on every restart.** Leave that terminal open for the whole
> demo. For 4 Aug, consider a cloudflared **named** tunnel (free, needs a domain) so the
> URL is stable and you never re-paste under pressure.

---

## 4. Pre-flight from the laptop (before touching Railway)

```bash
python tools/check_hands.py https://xxxx.trycloudflare.com --key YOURKEY --move
```

This speaks the exact protocol the brain uses. It checks `/health`, proves the API key
with `/status`, warns if calibration wasn't saved or the emergency stop is latched, and
with `--move` counts 3 → 5 → 0 on the right hand. Green here = the Pi side is done.

---

## 5. Wire it to Railway

Railway → your service → **Variables**:

```
RASPBERRY_PI_URL=https://xxxx.trycloudflare.com     ← full https URL, no trailing slash
MAXI_HAND_API_KEY=<exactly the same string as the Pi>
```

The key must match **character for character** — a mismatch gives a 401 and the brain
silently falls back to simulation (you'd see fingers not moving with no obvious error).

A redeploy is no longer required just to pick up a live Pi — the brain re-probes every
20 s — but changing the *variables* does restart the service, which is fine.

---

## 6. Verify from a browser (no log-diving)

```
https://<your-railway-app>/hands/status?probe=1
```

```json
{"hands": {"mode": "hardware", "available": true, "base_url": "https://xxxx.trycloudflare.com", ...}}
```

- `"mode": "hardware"` → connected. 🎉
- `"mode": "simulation (Pi unreachable)"` → read `last_error`:
  - `ClientConnectorError` / timeout → the tunnel is down, or `RASPBERRY_PI_URL` is wrong.
  - `401` → key mismatch.
- Then move real fingers without the tablet:
  `https://<railway-app>/hands/test?pin=1234&n=3` (PIN = `PARENT_DASHBOARD_PIN`).

The Railway deploy log still prints the classic line at boot:
`Hands: hardware connected at https://…` (vs `simulation (Pi unreachable)`).

---

## 7. The live test

1. Open the tablet on `https://<railway-app>/math`.
2. Say **"Hey Maxi"** → wake ack → **"what is 3 plus 2"**.
3. Expected: the UI shows `3 + 2 = 5`, Maxi says *"We start with 3…"* while the right hand
   opens **3** fingers, then **5**, and closes at the end.

Add `?maxidebug=1` to the URL for the voice HUD. If the mic is the problem and not the
hands, use the buttons-only fallback (Wake-Word toggle in Settings) and type/tap instead —
the hands path is identical.

---

## 8. Troubleshooting

| symptom | cause | fix |
|---|---|---|
| `/health` says `"status": "degraded"` | PCA9685 not initialised | I²C off, bad wiring, or no logic power. `i2cdetect -y 1` must show `40`. |
| Servos jitter / Pi reboots | current brown-out | proper external 5–6 V ≥10 A supply, common ground, add the capacitor. |
| Fingers buzz and get hot | calibration drives into a stop | re-calibrate that finger with a safer min/max. |
| One finger doesn't move | wrong channel or dead servo | left = ch 0–5, right = ch 6–11 (thumb, index, majeure, ringfinger, pinky, wrist). |
| Everything limp, nothing responds | emergency stop latched | `POST /reset_emergency` (with the key), or restart the API. |
| Brain says simulation but curl works | `RASPBERRY_PI_URL` typo/trailing slash, or key mismatch | compare against `/hands/status`'s `base_url`. |
| Moves are slow / commands time out | show_number can take seconds | raise `HANDS_TIMEOUT` (default 8 s) on Railway. |
| Worked, then stopped mid-demo | quick tunnel restarted → new URL | restart `start_hands.sh`, paste the new `RASPBERRY_PI_URL`. |

**Panic button** (kills all servo power output, hands go limp):

```bash
curl -X POST -H "X-API-Key: $MAXI_HAND_API_KEY" http://localhost:5001/emergency_stop
```

---

## 9. Printable pre-flight checklist (demo day)

```
MAXI — HANDS PRE-FLIGHT                              date: ____________

POWER & WIRING
[ ] External 5-6V >=10A supply connected to PCA9685 V+ / GND
[ ] Common ground: supply GND -> Pi GND
[ ] PCA9685 VCC -> Pi 3V3,  SDA -> GPIO2,  SCL -> GPIO3
[ ] Capacitor (1000uF) across V+/GND
[ ] Nothing is pressing against a finger's travel path

PI
[ ] Pi booted, on Wi-Fi, correct folder (hand_calibration.json present)
[ ] i2cdetect -y 1   shows 40
[ ] Calibrator (:5000) NOT running
[ ] ./start_hands.sh   -> "API healthy" + a public URL printed
[ ] Boot self-test moved the right hand (a "2") without buzzing

LINK
[ ] python tools/check_hands.py <public-url> --key <key> --move   -> ALL GOOD
[ ] Railway RASPBERRY_PI_URL  = the printed URL (no trailing slash)
[ ] Railway MAXI_HAND_API_KEY = the Pi's key (character for character)
[ ] Railway GROQ_MODEL=llama-3.1-8b-instant
[ ] Railway MAXI_MEMORY_DB=/data/maxi_memory.db  (+ volume mounted)

CLOUD
[ ] /hands/status?probe=1   -> "mode":"hardware"
[ ] /hands/test?pin=____&n=3   -> 3 fingers move

TABLET
[ ] ONE tablet connected (only one at a time)
[ ] Opened over https, volume up, mic permission granted
[ ] "Hey Maxi" -> ack heard
[ ] "what is 3 plus 2" -> UI shows 5, hand shows 3 then 5
[ ] Fallback rehearsed: Wake-Word toggle OFF -> buttons only

ON THE TABLE
[ ] Laptop/phone open on /hands/status
[ ] Emergency stop command ready to paste
[ ] Spare power supply / cable
```
