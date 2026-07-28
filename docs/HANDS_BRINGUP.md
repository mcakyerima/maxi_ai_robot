# Maxi's Hands — Setup Runbook

**Do these steps in order. Don't skip ahead.** Each step ends with *"you should see…"* —
if you don't see it, fix that step before moving on. The whole thing takes about
**60–90 minutes** the first time, and about **3 minutes** every day after that.

The chain you are building:
**tablet → Railway (Maxi's brain) → tunnel → Raspberry Pi → PCA9685 board → 12 servos.**

**Grown-up does:** everything with power and wiring (Steps 1–4), and the Railway steps.
**Children can do:** the calibration sliders (Step 9), the checks (Steps 11–13), and of
course the live test (Step 14).

### What you need on the table
- The robot hands, the Raspberry Pi, the PCA9685 board
- **External 5–6 V power supply, 10 A or more** (not a phone charger)
- A 1000 µF capacitor (optional but recommended), jumper wires
- A laptop on the same Wi-Fi as the Pi, and the tablet
- The Railway login, and the Pi's password

---

# PART A — POWER & WIRING (nothing plugged in yet)

> ⚠️ **This is the part that can destroy hardware.** MG996R servos pull about 2.5 A each
> when they push hard. Twelve of them is far more than the Raspberry Pi can give. If you
> power the servos from the Pi, the Pi will brown out and can corrupt its SD card.

### STEP 1 — Power the servo board (NOT from the Pi)
Connect the **external 5–6 V ≥10 A supply** to the PCA9685's **V+** and **GND** screw
terminals. Never take servo power from the Pi's 5 V pin.

### STEP 2 — Common ground
Run a wire from the **power supply's GND** to any **GND pin on the Pi**.

> Skipping this is the most common mistake. Without a shared ground the servos twitch
> randomly or ignore commands completely, and everything else looks fine.

### STEP 3 — Signal wires
| PCA9685 | Raspberry Pi |
|---|---|
| VCC (logic power) | 3V3 |
| GND | GND |
| SDA | GPIO2 |
| SCL | GPIO3 |

Optional: a **1000 µF capacitor** across V+/GND soaks up the current spike when several
fingers move at once.

### STEP 4 — Plug the servos in
Left hand = channels **0–5**, right hand = channels **6–11**, in this order each:
`thumb, index, majeure(middle), ringfinger, pinky, wrist`.

Check nothing is resting against a finger's path. Then power on: **servo supply first,
then the Pi.**

✅ *You should see:* the Pi boots normally. Servos may twitch once — that's fine.
❌ *If the Pi keeps rebooting:* the servos are drawing from the Pi. Go back to Step 1.

---

# PART B — PUT THE FILES ON THE PI

### STEP 5 — Get to the Pi's terminal
Either plug in a screen and keyboard, or from the laptop:

```bash
ssh pi@raspberrypi.local          # or:  ssh pi@<the Pi's IP address>
```

### STEP 6 — Copy the newest hand files onto the Pi

> ⚠️ **`finger_controller_api.py` MUST be replaced.** The old copy on your Pi has a bug:
> every `/gesture` call crashes with a 500 error. The new one also comes with
> `start_hands.sh` and `requirements_pi.txt`, which the next steps need.

**If the Pi has internet (easiest):**

```bash
cd ~
git clone https://github.com/mcakyerima/maxi_ai_robot.git   # first time only
cd maxi_ai_robot && git pull                                # every other time
cd hardware
```

**If not — copy from the laptop** (run this *on the laptop*, in the project folder):

```bash
scp hardware/finger_controller_api.py hardware/start_hands.sh \
    hardware/requirements_pi.txt hardware/finger_callibrator.py pi@raspberrypi.local:~/maxi/hardware/
```

**Either way, all the hand files must end up in ONE folder together.** The programs read
and write `hand_calibration.json` from whatever folder you're standing in, so they must
share one. Confirm:

```bash
ls
```

✅ *You should see:* `finger_controller_api.py`, `finger_callibrator.py`,
`start_hands.sh`, `requirements_pi.txt` (and `hand_calibration.json` if you calibrated before).

---

# PART C — ONE-TIME INSTALL

### STEP 7 — Run the setup

```bash
chmod +x start_hands.sh        # first time only — makes the script runnable
./start_hands.sh --setup
```

It installs everything for you: system packages, the I2C bus, the Python libraries (into
a `venv` folder here), and `cloudflared` for the tunnel. It asks for your password once
for `sudo`. **Nothing moves during setup.** It takes a few minutes.

✅ *You should see:* `✅ SETUP DONE.` and, near the top, `✅ PCA9685 found at 0x40`.

❌ *If it says `/dev/i2c-1 does not exist yet`:* I2C was just switched on and needs a restart.

```bash
sudo reboot
# wait, log back in, then:
cd ~/maxi_ai_robot/hardware && ./start_hands.sh --setup
```

❌ *If it says `NOTHING answers at 0x40`:* the board isn't wired right. Recheck Steps 2–3
(especially the **common ground**), then run `i2cdetect -y 1` — you need to see `40` in the grid.

---

# PART D — CALIBRATE THE FINGERS

> Do this **before** anything else runs, because the controller in Part E moves the servos
> the moment it starts. Wrong ranges make a finger push into its own mechanical stop — the
> servo buzzes, gets hot, and eventually burns out.
>
> **Already calibrated on this exact hand and nothing was rebuilt?** You can skip to Step 10 —
> just check `ls hand_calibration.json` shows the file.

### STEP 8 — Start the calibrator

```bash
venv/bin/python finger_callibrator.py
hostname -I                      # note the Pi's IP address
```

On the laptop, open **`http://<the Pi's IP>:5000`**.

### STEP 9 — Set each finger's two limits, then SAVE
This part the children can do. For **each** finger:

1. Drag the slider to find **open** — the finger fully extended. Write that as **min**.
2. Drag to find **closed** — curled in. Write that as **max**.
3. Stop as soon as the finger reaches its limit. **If it buzzes, back off immediately** —
   that means it's pushing against something and the motor is straining.

Then press **SAVE**.

✅ *You should see:* a new `hand_calibration.json` file:

```bash
ls -l hand_calibration.json
```

### STEP 10 — Stop the calibrator
Press **Ctrl-C** in the Pi terminal.

> Both programs drive the same servos. If the calibrator keeps running, the next step will
> fight it and the fingers will jerk.

---

# PART E — START THE HANDS

### STEP 11 — Set the secret key (once)
Pick a long random password-like string. It must be **identical** on the Pi and on Railway.

```bash
echo 'export MAXI_HAND_API_KEY="choose-a-long-random-string-here"' >> ~/.maxi_hands.env
```

Write it down — you'll paste the same one into Railway in Step 14.

### STEP 12 — Start everything

```bash
./start_hands.sh
```

This starts the finger API and opens a tunnel so the cloud brain can reach your Pi.

⚠️ **The servos WILL move now** — all fingers close, then the right hand shows a "2".
That's the self-test, and it means it's working.

✅ *You should see* a box like this:

```
════════════════════════════════════════════
 🖐  MAXI'S HANDS ARE ONLINE
════════════════════════════════════════════
 Public URL : https://something-random.trycloudflare.com

   RASPBERRY_PI_URL=https://something-random.trycloudflare.com
   MAXI_HAND_API_KEY=choose-a-long-random-string-here
```

📌 **Leave this terminal window open all day.** Closing it takes the hands offline, and the
web address changes every time you restart it.

❌ *If a finger buzzes and stays tense:* press Ctrl-C and redo Part D for that finger.

---

# PART F — CHECK THE CONNECTION FROM THE LAPTOP

### STEP 13 — Pre-flight the link
On the **laptop**, in the project folder — use the URL and key the Pi just printed:

```bash
python tools/check_hands.py https://something-random.trycloudflare.com --key YOURKEY --move
```

This talks to the Pi exactly the way Maxi's brain will, so it catches problems before
Railway is involved. With `--move` the right hand counts **3 → 5 → then closes**.

✅ *You should see:* `✅ ALL GOOD.` and fingers moving.

❌ *`/health unreachable`* → the tunnel or the Pi isn't running. Check the Pi terminal.
❌ *`401`* → the key doesn't match. Compare it character by character.
❌ *`status=degraded`* → the servo board isn't talking. Back to Step 7.
❌ *`calibration not saved`* → redo Part D and press SAVE.

---

# PART G — CONNECT THE CLOUD BRAIN

### STEP 14 — Paste the two variables into Railway
Railway → your service → **Variables**:

```
RASPBERRY_PI_URL=https://something-random.trycloudflare.com
MAXI_HAND_API_KEY=choose-a-long-random-string-here
```

The URL must have **no trailing slash**. The key must match the Pi **exactly** — one wrong
character and Maxi quietly pretends to move (simulation) with no error on screen.

While you're there, confirm these are still set:
`GROQ_MODEL=llama-3.1-8b-instant` and `MAXI_MEMORY_DB=/data/maxi_memory.db`.

Save. Railway restarts by itself (about a minute).

### STEP 15 — Ask Maxi's brain if it can see the hands
Open this in any browser, even a phone:

```
https://<your-railway-app>/hands/status?probe=1
```

✅ *You should see:* `"mode": "hardware"` and `"available": true`.

❌ *`"mode": "simulation (Pi unreachable)"`* → read the `last_error` field:
- mentions *connect* or *timeout* → the tunnel died. Restart Step 12 and re-paste the new URL.
- mentions *401* → the key doesn't match. Fix Step 14.

### STEP 16 — Move a finger from the internet
```
https://<your-railway-app>/hands/test?pin=1234&n=3
```
(`pin` is your `PARENT_DASHBOARD_PIN`, `1234` unless you changed it.)

✅ *You should see:* three fingers open on the robot, and `"moved": true` in the browser.

**This is the moment it's all connected.** 🎉

---

# PART H — THE LIVE TEST WITH THE CHILDREN

### STEP 17 — Open Maxi on the tablet
Go to `https://<your-railway-app>/math`. Volume up. Allow the microphone if asked.

> Only **one** tablet at a time — two open browsers scramble Maxi's state.

### STEP 18 — Talk to Maxi
Say **"Hey Maxi"** → wait for the reply sound → then **"what is 3 plus 2"**.

✅ *You should see and hear:*
1. The screen shows `3 + 2 = 5`
2. Maxi says *"We start with 3…"* — and the right hand opens **3 fingers**
3. Maxi says *"The answer is 5!"* — the hand opens **5 fingers**
4. The hand closes, and Maxi goes quiet, ready for the next question

### STEP 19 — Try a few more
- "what is 4 plus 4" → 8 fingers (both hands)
- "what is 8 plus 7" → 15, shown on the screen only (we only have 10 fingers!)
- "if I have 3 mangoes and buy 4 more, how many do I have?" → step-by-step

❌ *If Maxi doesn't hear you:* the microphone isn't the hands' fault. Turn the Wake-Word
toggle **off** in Settings and use the buttons instead — the hands work exactly the same way.

---

# PART I — SHUTTING DOWN

### STEP 20 — Stop safely
1. Press **Ctrl-C** in the Pi terminal (stops the API and the tunnel).
2. `sudo shutdown -h now`, wait for the green light to stop blinking.
3. **Then** switch off the servo power supply.

---

# 🚨 IF SOMETHING GOES WRONG

### Panic button — makes the hands go limp immediately
On the Pi, in a **second** terminal:

```bash
curl -X POST -H "X-API-Key: $MAXI_HAND_API_KEY" http://localhost:5001/emergency_stop
```

Or just pull the servo power. To recover afterwards, restart `./start_hands.sh`.

### Common problems

| What you see | What it means | What to do |
|---|---|---|
| Pi reboots when fingers move | servos drawing from the Pi | Step 1 — external supply, common ground |
| Servos twitch randomly | no common ground | Step 2 |
| `i2cdetect` shows nothing at 40 | I2C off or wiring wrong | Step 7, then reboot; recheck Step 3 |
| A finger buzzes and gets hot | calibration pushes into a stop | Ctrl-C now; redo Part D for that finger |
| One finger never moves | wrong channel or dead servo | Step 4 — left 0–5, right 6–11 |
| All fingers limp, nothing responds | emergency stop is latched | restart `./start_hands.sh` |
| `/hands/status` says simulation | tunnel down, wrong URL, or wrong key | Step 15, read `last_error` |
| Worked, then stopped mid-demo | the tunnel restarted → new URL | redo Steps 12 and 14 |
| Commands time out | moves take longer than 8 s | set `HANDS_TIMEOUT=15` on Railway |
| `Port 5001 already in use` | it's already running | `pkill -f finger_controller_api.py` |

### Every day after the first time
Steps 12 → 14 → 15 only. About 3 minutes:

```bash
cd ~/maxi_ai_robot/hardware && ./start_hands.sh
```
…then paste the new `RASPBERRY_PI_URL` into Railway and check `/hands/status?probe=1`.

> **For the 4 Aug demo:** a cloudflared **named** tunnel (free, needs a domain) keeps the
> same web address forever, so you never re-paste anything under pressure. Worth setting up
> in advance.

---

# ✅ PRINTABLE CHECKLIST — tear this off for demo day

```
MAXI — HANDS PRE-FLIGHT                              date: ____________

POWER & WIRING
[ ] External 5-6V >=10A supply -> PCA9685 V+ / GND   (NOT the Pi)
[ ] Common ground: supply GND -> Pi GND
[ ] PCA9685 VCC -> 3V3,  SDA -> GPIO2,  SCL -> GPIO3
[ ] Capacitor across V+/GND
[ ] Nothing pressing against a finger's path
[ ] Power on order: servo supply first, then the Pi

ON THE PI                            (cd ~/maxi_ai_robot/hardware)
[ ] hand_calibration.json is present
[ ] i2cdetect -y 1   shows 40
[ ] Calibrator (:5000) is NOT running
[ ] ./start_hands.sh   -> "API healthy" + a public URL printed
[ ] Boot self-test moved the right hand (a "2"), no buzzing
[ ] Public URL written down: ______________________________

FROM THE LAPTOP
[ ] python tools/check_hands.py <url> --key <key> --move   -> ALL GOOD

RAILWAY VARIABLES
[ ] RASPBERRY_PI_URL   = the printed URL (no trailing slash)
[ ] MAXI_HAND_API_KEY  = the Pi's key (character for character)
[ ] GROQ_MODEL=llama-3.1-8b-instant
[ ] MAXI_MEMORY_DB=/data/maxi_memory.db   (+ volume mounted)

CLOUD CHECK
[ ] /hands/status?probe=1      -> "mode":"hardware"
[ ] /hands/test?pin=____&n=3   -> 3 fingers move

TABLET
[ ] ONE tablet only, opened over https, volume up, mic allowed
[ ] "Hey Maxi" -> reply sound heard
[ ] "what is 3 plus 2" -> screen shows 5, hand shows 3 then 5
[ ] Fallback rehearsed: Wake-Word toggle OFF -> buttons only

ON THE TABLE, READY
[ ] Laptop or phone open on /hands/status
[ ] Emergency stop command ready to paste
[ ] Spare power supply and cables
[ ] Pi terminal window still open (do not close it!)
```

---

## Appendix — reference

**The three programs on the Pi**

| file | port | key needed | notes |
|---|---|---|---|
| `finger_callibrator.py` | 5000 | no | sets each finger's min/max. Doesn't move on startup. |
| `finger_controller_api.py` | 5001 | yes (`X-API-Key`) | what the brain calls. **Moves servos on startup.** |
| `start_hands.sh` | — | — | `--setup` installs; no argument starts API + tunnel. |

**Useful options**

```bash
SIMULATION_MODE=true ./start_hands.sh   # rehearse — nothing physically moves
TUNNEL=ngrok ./start_hands.sh           # ngrok instead of cloudflared
TUNNEL=none ./start_hands.sh            # LAN only (Railway CANNOT reach this)
```

**Optional — start the hands automatically at boot.** Only do this once everything works
manually, and note you'll still need to copy the new tunnel URL into Railway each time:

```bash
sudo tee /etc/systemd/system/maxi-hands.service >/dev/null <<'EOF'
[Unit]
Description=Maxi hands (finger API + tunnel)
After=network-online.target

[Service]
User=pi
WorkingDirectory=/home/pi/maxi_ai_robot/hardware
ExecStart=/home/pi/maxi_ai_robot/hardware/start_hands.sh
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl enable --now maxi-hands
journalctl -u maxi-hands -f      # watch it, and read the tunnel URL from here
```
