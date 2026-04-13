#!/usr/bin/env bash
# ── One-command demo launcher ────────────────────────────────────────────────
# Usage (from d:/failed payment):
#   bash demo.sh
#
# What it does:
#   1. Kills anything already on port 8000 (so there's no "port in use" error)
#   2. Activates the Python venv
#   3. Starts the FastAPI server in the background
#   4. Waits until the server is actually responding (no manual timing needed)
#   5. Opens http://localhost:8000/demo in Chrome
# ─────────────────────────────────────────────────────────────────────────────

set -e  # stop on any error

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$SCRIPT_DIR/payment-recovery"
PORT=8000
URL="http://localhost:$PORT/demo"

echo ""
echo "▶  Starting Failed Payment Recovery demo..."
echo ""

# ── Step 1: Free up port 8000 if something is already using it ────────────────
# PowerShell finds the owning PID cleanly, without any cmd.exe banner noise
powershell.exe -NoProfile -Command "
  \$conn = Get-NetTCPConnection -LocalPort $PORT -ErrorAction SilentlyContinue
  if (\$conn) { Stop-Process -Id \$conn.OwningProcess -Force -ErrorAction SilentlyContinue; Start-Sleep -Milliseconds 500 }
" 2>/dev/null || true

# ── Step 2: Activate venv ─────────────────────────────────────────────────────
source "$APP_DIR/venv/Scripts/activate"

# ── Step 3: Start server in background ───────────────────────────────────────
cd "$APP_DIR"
uvicorn main:app --port $PORT --log-level info > server.log 2>&1 &
SERVER_PID=$!
echo "   Server starting (PID $SERVER_PID)..."

# ── Step 4: Wait until the health endpoint responds (max 15 seconds) ─────────
echo -n "   Waiting for server"
for i in $(seq 1 30); do
  if curl -s "http://localhost:$PORT/health" > /dev/null 2>&1; then
    echo " ready!"
    break
  fi
  echo -n "."
  sleep 0.5
done

# ── Step 5: Open Chrome ───────────────────────────────────────────────────────
echo "   Opening $URL in Chrome..."
powershell.exe -NoProfile -Command "Start-Process chrome '$URL'" 2>/dev/null || \
  powershell.exe -NoProfile -Command "Start-Process '$URL'"

echo ""
echo "✓  Demo is live at $URL"
echo "   Press Ctrl+C to stop the server."
echo ""
echo "── SMS delivery monitor ─────────────────────────────────────────────────────"
echo "   Watching for SMS events... (trigger a webhook to see status)"
echo "   Note: Indian numbers may not receive SMS due to DND registry or Twilio"
echo "         trial account restrictions (error 21608 = number not verified)."
echo "─────────────────────────────────────────────────────────────────────────────"
echo ""

# Tail server.log and surface only SMS/webhook-relevant lines so the terminal
# shows a clear sent/failed status after each demo trigger.
tail -f server.log | grep --line-buffered -E "SMS|Twilio|twilio|sms|webhook|payment_link|ERROR|WARNING|status"
