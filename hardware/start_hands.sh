#!/usr/bin/env bash
# start_hands.sh — install, start and publish Maxi's hands on the Raspberry Pi.
#
# Put this file in the SAME folder as finger_controller_api.py (they share
# hand_calibration.json via the current directory).
#
# Step-by-step guide: docs/HANDS_BRINGUP.md
#
#   ./start_hands.sh --setup     ONE-TIME: install everything, move nothing.
#   ./start_hands.sh             start the API on :5001 + a tunnel, print the URL.
#
# Options (environment variables):
#   TUNNEL=cloudflared|ngrok|none   default cloudflared (no account needed)
#   SIMULATION_MODE=true            dry run, servos never move
#   PORT=5001                       the API port
#
# Ctrl-C stops BOTH the API and the tunnel.

set -uo pipefail
# Resolve our own path BEFORE cd'ing (--help reads this file).
SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
cd "$(dirname "$0")"

PORT="${PORT:-5001}"
TUNNEL="${TUNNEL:-cloudflared}"
LOG_DIR="${LOG_DIR:-$PWD/logs}"
VENV="$PWD/venv"
SETUP_MARKER="$PWD/.hands_setup_done"
mkdir -p "$LOG_DIR"
API_LOG="$LOG_DIR/hands_api.log"
TUNNEL_LOG="$LOG_DIR/tunnel.log"

SETUP_ONLY=0
case "${1:-}" in
  --setup|--setup-only|setup) SETUP_ONLY=1 ;;
  --help|-h) sed -n '2,19p' "$SELF"; exit 0 ;;
esac

SUDO="sudo"
[ "$(id -u)" = "0" ] && SUDO=""

say()  { echo "$@"; }
line() { echo "────────────────────────────────────────────────────────────"; }
# The Pi's LAN address (only used in printed hints; never fatal).
lan_ip() { hostname -I 2>/dev/null | awk '{print $1}'; }

# Look for the servo board at 0x40. Checks bus 1 then bus 0, and accepts "UU"
# (address claimed by a kernel driver) as present. Sets I2C_BUS on success.
# Advisory only — a working calibrator is the real proof the wiring is good.
I2C_BUS=""
find_pca9685() {
  command -v i2cdetect >/dev/null 2>&1 || return 1
  local bus out
  for bus in 1 0; do
    out=$(i2cdetect -y "$bus" 2>/dev/null) || continue
    if printf '%s\n' "$out" | awk '/^40:/ {print $2}' | grep -qiE '^(40|UU)$'; then
      I2C_BUS="$bus"
      return 0
    fi
  done
  return 1
}

# ═══════════════════════════════════════════════════════════════════
# SETUP — runs on the first ever launch, or on demand with --setup
# ═══════════════════════════════════════════════════════════════════
run_setup() {
  line; say "🔧 ONE-TIME SETUP — installing what the hands need"; line

  say "1/5  system packages (needs your password for sudo)…"
  $SUDO apt-get update -qq
  $SUDO apt-get install -y -qq python3-venv python3-pip python3-dev i2c-tools curl \
    || { say "❌ apt-get install failed. Are you online?"; return 1; }
  say "     ✅ python3-venv, i2c-tools, curl"

  say "2/5  enabling the I2C bus…"
  if command -v raspi-config >/dev/null 2>&1; then
    $SUDO raspi-config nonint do_i2c 0 && say "     ✅ I2C enabled"
  else
    say "     ⚠️  raspi-config not found — enable I2C by hand if 0x40 doesn't show up."
  fi

  say "3/5  python packages (into ./venv, takes a few minutes)…"
  [ -d "$VENV" ] || python3 -m venv --system-site-packages "$VENV" \
    || { say "❌ could not create the venv"; return 1; }
  "$VENV/bin/pip" install -q --upgrade pip
  "$VENV/bin/pip" install -q -r requirements_pi.txt \
    || { say "❌ pip install failed — see the message above."; return 1; }
  say "     ✅ Flask + adafruit PCA9685 libraries"

  say "4/5  the tunnel program…"
  install_cloudflared

  say "5/5  checking the servo board…"
  if [ -e /dev/i2c-1 ] || [ -e /dev/i2c-0 ]; then
    if find_pca9685; then
      say "     ✅ PCA9685 found at 0x40 on bus $I2C_BUS"
    else
      say "     ⚠️  the I2C bus exists but nothing answered at 0x40:"
      i2cdetect -y 1 2>&1 | sed 's/^/        /' | head -12
      say "        Check SDA→GPIO2, SCL→GPIO3, VCC→3V3, and the COMMON GROUND."
      say "        (If the calibrator can move fingers, ignore this — it's only a hint.)"
    fi
  else
    say "     ⚠️  /dev/i2c-1 does not exist yet — I2C needs a REBOOT to switch on."
    say "        Run:  sudo reboot     then run this script again."
  fi

  touch "$SETUP_MARKER"
  line
  say "✅ SETUP DONE."
  say ""
  say "   NEXT: calibrate the fingers before anything moves on its own —"
  say "     $VENV/bin/python finger_callibrator.py     → http://$(lan_ip):5000"
  say "   Then come back and run:  ./start_hands.sh"
  line
}

install_cloudflared() {
  if command -v cloudflared >/dev/null 2>&1; then
    say "     ✅ cloudflared already installed"
    return 0
  fi
  if [ "$TUNNEL" = "ngrok" ] || [ "$TUNNEL" = "none" ]; then
    say "     ⏭  skipped (TUNNEL=$TUNNEL)"
    return 0
  fi
  local arch deb
  case "$(uname -m)" in
    aarch64|arm64)   arch="arm64" ;;
    armv7l|armv6l)   arch="arm"   ;;
    x86_64)          arch="amd64" ;;
    *) say "     ⚠️  unknown CPU $(uname -m) — install cloudflared by hand."; return 0 ;;
  esac
  deb="/tmp/cloudflared.deb"
  say "     downloading cloudflared ($arch)…"
  if curl -fsSL -o "$deb" \
      "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${arch}.deb"; then
    $SUDO dpkg -i "$deb" >/dev/null 2>&1 && say "     ✅ cloudflared installed" \
      || say "     ⚠️  dpkg failed — try: sudo dpkg -i $deb"
  else
    say "     ⚠️  download failed (no internet?). Install it later, or use TUNNEL=ngrok."
  fi
}

if [ "$SETUP_ONLY" = "1" ]; then
  run_setup
  exit $?
fi
if [ ! -f "$SETUP_MARKER" ]; then
  say "ℹ️  First run detected — doing the one-time setup first."
  run_setup || exit 1
  say ""
  say "⏸  Setup finished. Calibrate first (see above), then run ./start_hands.sh again."
  exit 0
fi

# Prefer the venv we built; fall back to system python.
PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
  if [ -x "$VENV/bin/python" ]; then PYTHON="$VENV/bin/python"; else PYTHON="python3"; fi
fi

# ═══════════════════════════════════════════════════════════════════
# RUN
# ═══════════════════════════════════════════════════════════════════

# --- API key -----------------------------------------------------------------
# Must match Railway's MAXI_HAND_API_KEY EXACTLY or the brain gets a 401 and
# silently falls back to simulation. Persist it in ~/.maxi_hands.env:
#   echo 'export MAXI_HAND_API_KEY="....."' >> ~/.maxi_hands.env
[ -f "$HOME/.maxi_hands.env" ] && . "$HOME/.maxi_hands.env"
if [ -z "${MAXI_HAND_API_KEY:-}" ]; then
  say "⚠️  MAXI_HAND_API_KEY is not set — the API will use its built-in default key."
  say "    That still works, but set a real one on BOTH the Pi and Railway."
fi
export MAXI_HAND_API_KEY

API_PID=""; TUNNEL_PID=""; CLEANED=0
cleanup() {
  [ "$CLEANED" = "1" ] && return          # TERM then EXIT would fire this twice
  CLEANED=1
  trap - EXIT INT TERM
  # Say nothing if we never actually started anything — otherwise an early exit
  # (e.g. "port in use") looks like the hands themselves failed.
  if [ -z "$API_PID" ] && [ -z "$TUNNEL_PID" ]; then
    return
  fi
  echo ""
  say "🛑 stopping…"
  [ -n "$TUNNEL_PID" ] && kill "$TUNNEL_PID" 2>/dev/null
  [ -n "$API_PID" ] && kill "$API_PID" 2>/dev/null
  wait 2>/dev/null
  say "👋 hands offline."
}
trap cleanup EXIT INT TERM

# --- 0. sanity checks --------------------------------------------------------
if [ ! -f hand_calibration.json ]; then
  say "⚠️  No hand_calibration.json in $PWD — the API will use DEFAULT finger ranges."
  say "    Fingers may push into their stops (servos get hot). Calibrate first:"
  say "      $PYTHON finger_callibrator.py    → http://$(lan_ip):5000"
  if [ -t 0 ]; then
    printf "    Continue anyway? [y/N] "
    read -r reply
    case "$reply" in y|Y) ;; *) exit 1 ;; esac
  else
    say "    (no terminal to ask — continuing with defaults)"
  fi
fi

if [ "${SIMULATION_MODE:-false}" != "true" ]; then
  if find_pca9685; then
    say "✅ PCA9685 found at 0x40 on I2C bus $I2C_BUS"
  elif ! command -v i2cdetect >/dev/null 2>&1; then
    say "ℹ️  i2cdetect not installed, skipping the board check (sudo apt install i2c-tools)."
  else
    say "ℹ️  Could not see the PCA9685 at 0x40 with i2cdetect. This check is only a"
    say "    hint — if the calibrator moves the fingers, your wiring IS fine."
    say "    What i2cdetect reported:"
    i2cdetect -y 1 2>&1 | sed 's/^/      /' | head -12
    say "    (an address shown as UU means a kernel driver claimed it — also OK)"
    say "    Continuing — the real answer comes from /health below."
  fi
fi

# --- is something already on the port? ---------------------------------------
port_holder() { ss -ltnp 2>/dev/null | grep ":$PORT " | head -1; }
if command -v ss >/dev/null 2>&1 && [ -n "$(port_holder)" ]; then
  say "❌ Port $PORT is already in use — another controller is running."
  say "   That is what is holding it:"
  say "      $(port_holder)"
  case "$(port_holder)" in
    *users:*) ;;
    *) say "      (to see WHICH program:  sudo ss -ltnp | grep :$PORT)" ;;
  esac
  say ""
  say "   Old versions of this project also serve this port. To stop them all:"
  say "      pkill -f finger_controller_api.py; pkill -f hand_api.py; pkill -f app.py"
  say "   If it comes back after a reboot, something auto-starts it:"
  say "      systemctl list-units --type=service --all | grep -iE 'hand|servo|maxi|finger'"
  if [ -t 0 ]; then
    printf "   Kill whatever is on port %s now and continue? [y/N] " "$PORT"
    read -r reply
    case "$reply" in
      y|Y)
        pkill -f finger_controller_api.py 2>/dev/null
        pkill -f hand_api.py 2>/dev/null
        pkill -f old_finger_controller_api.py 2>/dev/null
        sleep 2
        if [ -n "$(port_holder)" ]; then
          say "   ❌ still in use. Find it with:  sudo ss -ltnp | grep :$PORT"
          exit 1
        fi
        say "   ✅ port $PORT is free now."
        ;;
      *) exit 1 ;;
    esac
  else
    exit 1
  fi
fi

# --- 1. the finger API -------------------------------------------------------
say "🤖 starting finger_controller_api.py on :$PORT …"
say "   ⚠️  SERVOS WILL MOVE NOW (closes all fingers, then a '2' self-test)."
"$PYTHON" finger_controller_api.py >"$API_LOG" 2>&1 &
API_PID=$!

# Wait for /health (boot includes a servo self-test, so give it time).
for i in $(seq 1 30); do
  curl -sf "http://localhost:$PORT/health" >/dev/null 2>&1 && break
  if ! kill -0 "$API_PID" 2>/dev/null; then
    say "❌ the API died on startup. Last lines of $API_LOG:"
    tail -20 "$API_LOG"
    exit 1
  fi
  sleep 1
done

if ! curl -sf "http://localhost:$PORT/health" >/dev/null 2>&1; then
  say "❌ /health never came up. See $API_LOG"
  exit 1
fi
say "✅ API healthy:  $(curl -s "http://localhost:$PORT/health")"

if [ "$TUNNEL" = "none" ]; then
  IP=$(lan_ip)
  say ""
  say "🔌 LAN only (TUNNEL=none).  http://$IP:$PORT"
  say "   NOTE: Railway CANNOT reach a LAN address — use a tunnel for the cloud brain."
  say "   Ctrl-C to stop."
  wait "$API_PID"
  exit 0
fi

# --- 2. the tunnel -----------------------------------------------------------
PUBLIC_URL=""
if [ "$TUNNEL" = "cloudflared" ]; then
  if ! command -v cloudflared >/dev/null 2>&1; then
    say "❌ cloudflared not installed. Run:  ./start_hands.sh --setup"
    say "   (or use the alternative:  TUNNEL=ngrok ./start_hands.sh)"
    exit 1
  fi
  say "🌍 opening cloudflared quick tunnel → localhost:$PORT …"
  cloudflared tunnel --url "http://localhost:$PORT" >"$TUNNEL_LOG" 2>&1 &
  TUNNEL_PID=$!
  for i in $(seq 1 30); do
    PUBLIC_URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG" | head -1)
    [ -n "$PUBLIC_URL" ] && break
    sleep 1
  done
elif [ "$TUNNEL" = "ngrok" ]; then
  if ! command -v ngrok >/dev/null 2>&1; then
    say "❌ ngrok not installed.  https://ngrok.com/download   (needs a free authtoken)"
    exit 1
  fi
  say "🌍 opening ngrok tunnel → localhost:$PORT …"
  ngrok http "$PORT" --log=stdout >"$TUNNEL_LOG" 2>&1 &
  TUNNEL_PID=$!
  for i in $(seq 1 30); do
    PUBLIC_URL=$(curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null \
      | grep -oE 'https://[a-zA-Z0-9.-]+\.ngrok[a-z.-]*\.(app|io)' | head -1)
    [ -n "$PUBLIC_URL" ] && break
    sleep 1
  done
else
  say "❌ unknown TUNNEL='$TUNNEL' (use cloudflared | ngrok | none)"
  exit 1
fi

if [ -z "$PUBLIC_URL" ]; then
  say "❌ the tunnel did not report a public URL. See $TUNNEL_LOG"
  exit 1
fi

# --- 3. verify end-to-end through the tunnel ---------------------------------
say ""
say "🔎 checking the public URL…"
if curl -sf --max-time 15 "$PUBLIC_URL/health" >/dev/null 2>&1; then
  say "✅ $PUBLIC_URL/health  →  $(curl -s --max-time 15 "$PUBLIC_URL/health")"
else
  say "⚠️  $PUBLIC_URL/health did not answer yet (tunnels take a few seconds)."
fi

cat <<EOF

════════════════════════════════════════════════════════════════════
 🖐  MAXI'S HANDS ARE ONLINE
════════════════════════════════════════════════════════════════════
 Public URL : $PUBLIC_URL

 Paste these into Railway → service → Variables, then Redeploy:

   RASPBERRY_PI_URL=$PUBLIC_URL
   MAXI_HAND_API_KEY=${MAXI_HAND_API_KEY:-<the key this Pi is using>}

 Then confirm from any browser:
   https://<your-railway-app>/hands/status?probe=1     → "mode":"hardware"
   https://<your-railway-app>/hands/test?pin=1234&n=3  → 3 fingers move

 Logs:  $API_LOG
        $TUNNEL_LOG
 Panic: curl -X POST -H "X-API-Key: \$MAXI_HAND_API_KEY" http://localhost:$PORT/emergency_stop
 Ctrl-C stops the API and the tunnel.
════════════════════════════════════════════════════════════════════
EOF

# A quick-tunnel URL changes on every restart — keep this window open for the demo.
wait "$API_PID"
