#!/usr/bin/env bash
# start_hands.sh — bring Maxi's hands online on the Raspberry Pi.
#
#   1. starts finger_controller_api.py on :5001 (the API the cloud brain calls)
#   2. opens an outbound tunnel so Railway can reach it (no port-forwarding)
#   3. prints the public URL + the exact Railway variables to paste
#
# Usage:
#   chmod +x start_hands.sh
#   ./start_hands.sh                 # cloudflared quick tunnel (no account)
#   TUNNEL=ngrok ./start_hands.sh    # ngrok instead
#   TUNNEL=none  ./start_hands.sh    # API only (LAN testing)
#   SIMULATION_MODE=true ./start_hands.sh   # dry-run, no servos move
#
# Ctrl-C stops BOTH the API and the tunnel.

set -uo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-5001}"
TUNNEL="${TUNNEL:-cloudflared}"
PYTHON="${PYTHON:-python3}"
LOG_DIR="${LOG_DIR:-$PWD/logs}"
mkdir -p "$LOG_DIR"
API_LOG="$LOG_DIR/hands_api.log"
TUNNEL_LOG="$LOG_DIR/tunnel.log"

# --- API key -----------------------------------------------------------------
# Must match Railway's MAXI_HAND_API_KEY EXACTLY or the brain gets a 401 and
# silently falls back to simulation. Put it in ~/.maxi_hands.env to persist:
#   echo 'export MAXI_HAND_API_KEY="....."' >> ~/.maxi_hands.env
[ -f "$HOME/.maxi_hands.env" ] && . "$HOME/.maxi_hands.env"
if [ -z "${MAXI_HAND_API_KEY:-}" ]; then
  echo "⚠️  MAXI_HAND_API_KEY is not set — the API will use its built-in default key."
  echo "    That still works, but set a real one on BOTH the Pi and Railway."
fi
export MAXI_HAND_API_KEY

API_PID=""; TUNNEL_PID=""
cleanup() {
  echo ""
  echo "🛑 stopping…"
  [ -n "$TUNNEL_PID" ] && kill "$TUNNEL_PID" 2>/dev/null
  [ -n "$API_PID" ] && kill "$API_PID" 2>/dev/null
  wait 2>/dev/null
  echo "👋 hands offline."
}
trap cleanup EXIT INT TERM

# --- 0. sanity: I2C + the PCA9685 -------------------------------------------
if [ "${SIMULATION_MODE:-false}" != "true" ]; then
  if command -v i2cdetect >/dev/null 2>&1; then
    if i2cdetect -y 1 2>/dev/null | grep -qi " 40"; then
      echo "✅ PCA9685 found on I2C bus 1 at 0x40"
    else
      echo "❌ PCA9685 NOT found at 0x40 on i2c-1."
      echo "   Check: SDA/SCL wiring, common ground, and 'sudo raspi-config' → Interface → I2C."
      echo "   Continuing anyway — the API will report degraded health."
    fi
  else
    echo "ℹ️  i2cdetect not installed (sudo apt install -y i2c-tools) — skipping I2C check."
  fi
fi

# --- 1. the finger API -------------------------------------------------------
if lsof -ti :"$PORT" >/dev/null 2>&1 || (command -v ss >/dev/null && ss -ltn "sport = :$PORT" | grep -q LISTEN); then
  echo "❌ Port $PORT is already in use — another controller is running."
  echo "   Stop it first:  pkill -f finger_controller_api.py"
  exit 1
fi

echo "🤖 starting finger_controller_api.py on :$PORT …"
echo "   ⚠️  SERVOS WILL MOVE ON BOOT (closes all fingers, then a '2' self-test)."
"$PYTHON" finger_controller_api.py >"$API_LOG" 2>&1 &
API_PID=$!

# Wait for /health to answer (boot does a servo self-test, so give it time).
for i in $(seq 1 30); do
  if curl -sf "http://localhost:$PORT/health" >/dev/null 2>&1; then break; fi
  if ! kill -0 "$API_PID" 2>/dev/null; then
    echo "❌ the API died on startup. Last lines of $API_LOG:"
    tail -20 "$API_LOG"
    exit 1
  fi
  sleep 1
done

if ! curl -sf "http://localhost:$PORT/health" >/dev/null 2>&1; then
  echo "❌ /health never came up. See $API_LOG"
  exit 1
fi
echo "✅ API healthy:  $(curl -s "http://localhost:$PORT/health")"

if [ "$TUNNEL" = "none" ]; then
  IP=$(hostname -I | awk '{print $1}')
  echo ""
  echo "🔌 LAN only (TUNNEL=none).  http://$IP:$PORT"
  echo "   NOTE: Railway CANNOT reach a LAN address — use a tunnel for the cloud brain."
  echo "   Ctrl-C to stop."
  wait "$API_PID"
  exit 0
fi

# --- 2. the tunnel -----------------------------------------------------------
PUBLIC_URL=""
if [ "$TUNNEL" = "cloudflared" ]; then
  if ! command -v cloudflared >/dev/null 2>&1; then
    echo "❌ cloudflared not installed. On Raspberry Pi OS (64-bit):"
    echo "   curl -L -o cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb"
    echo "   sudo dpkg -i cloudflared.deb"
    echo "   (32-bit OS: use cloudflared-linux-arm.deb)   Or run:  TUNNEL=ngrok ./start_hands.sh"
    exit 1
  fi
  echo "🌍 opening cloudflared quick tunnel → localhost:$PORT …"
  cloudflared tunnel --url "http://localhost:$PORT" >"$TUNNEL_LOG" 2>&1 &
  TUNNEL_PID=$!
  for i in $(seq 1 30); do
    PUBLIC_URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG" | head -1)
    [ -n "$PUBLIC_URL" ] && break
    sleep 1
  done
elif [ "$TUNNEL" = "ngrok" ]; then
  if ! command -v ngrok >/dev/null 2>&1; then
    echo "❌ ngrok not installed.  https://ngrok.com/download   (needs a free authtoken)"
    exit 1
  fi
  echo "🌍 opening ngrok tunnel → localhost:$PORT …"
  ngrok http "$PORT" --log=stdout >"$TUNNEL_LOG" 2>&1 &
  TUNNEL_PID=$!
  for i in $(seq 1 30); do
    PUBLIC_URL=$(curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null \
      | grep -oE 'https://[a-zA-Z0-9.-]+\.ngrok[a-z.-]*\.(app|io)' | head -1)
    [ -n "$PUBLIC_URL" ] && break
    sleep 1
  done
else
  echo "❌ unknown TUNNEL='$TUNNEL' (use cloudflared | ngrok | none)"
  exit 1
fi

if [ -z "$PUBLIC_URL" ]; then
  echo "❌ the tunnel did not report a public URL. See $TUNNEL_LOG"
  exit 1
fi

# --- 3. verify end-to-end through the tunnel ---------------------------------
echo ""
echo "🔎 checking the public URL…"
if curl -sf --max-time 15 "$PUBLIC_URL/health" >/dev/null 2>&1; then
  echo "✅ $PUBLIC_URL/health  →  $(curl -s --max-time 15 "$PUBLIC_URL/health")"
else
  echo "⚠️  $PUBLIC_URL/health did not answer yet (tunnels take a few seconds)."
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
   https://<your-railway-app>/hands/status?probe=1   → "mode":"hardware"
   https://<your-railway-app>/hands/test?pin=1234&n=3  → 3 fingers move

 Logs:  $API_LOG
        $TUNNEL_LOG
 Panic: curl -X POST -H "X-API-Key: \$MAXI_HAND_API_KEY" http://localhost:$PORT/emergency_stop
 Ctrl-C stops the API and the tunnel.
════════════════════════════════════════════════════════════════════
EOF

# A quick-tunnel URL changes on every restart — keep this shell open for the demo.
wait "$API_PID"
