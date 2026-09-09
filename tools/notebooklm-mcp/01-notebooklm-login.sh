#!/usr/bin/env bash
set -euo pipefail

BASE="$HOME/.nd-notebooklm-mcp"
VENV="$BASE/venv"
BROWSER_DIR="$BASE/browser-tmp"
LOG_DIR="$BASE/logs"
mkdir -p "$BASE" "$LOG_DIR"
chmod 700 "$BASE"

say() { printf '\n==> %s\n' "$*"; }
fail() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

if [[ -z "${WEB_HOST:-}" ]]; then
  fail "Run this inside Google Cloud Shell (WEB_HOST is missing)."
fi

say "Preparing Google Cloud Shell packages"
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  xvfb x11vnc novnc websockify chromium python3-venv curl unzip >/dev/null

say "Installing NotebookLM MCP in a private virtual environment"
if [[ ! -x "$VENV/bin/python" ]]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install -q --upgrade pip
"$VENV/bin/python" -m pip install -q --upgrade 'notebooklm-py[headless,browser,mcp]'

printf '\nGoogle account email: '
read -r GOOGLE_EMAIL
[[ -n "$GOOGLE_EMAIL" ]] || fail "Google account email is required."

rm -rf "$BROWSER_DIR"
mkdir -p "$BROWSER_DIR"
chmod 700 "$BROWSER_DIR"

XVFB_PID=""; VNC_PID=""; NOVNC_PID=""; CHROME_PID=""
cleanup() {
  set +e
  for p in "$CHROME_PID" "$NOVNC_PID" "$VNC_PID" "$XVFB_PID"; do
    [[ -n "$p" ]] && kill "$p" 2>/dev/null || true
  done
  rm -rf "$BROWSER_DIR"
}
trap cleanup EXIT INT TERM

say "Starting a temporary private browser inside Google Cloud Shell"
Xvfb :99 -screen 0 1280x800x24 -nolisten tcp >"$LOG_DIR/xvfb.log" 2>&1 & XVFB_PID=$!
export DISPLAY=:99
sleep 1

x11vnc -display :99 -forever -shared -nopw -rfbport 5900 -localhost \
  >"$LOG_DIR/x11vnc.log" 2>&1 & VNC_PID=$!

websockify --web=/usr/share/novnc 6080 localhost:5900 \
  >"$LOG_DIR/novnc.log" 2>&1 & NOVNC_PID=$!

chromium \
  --no-sandbox \
  --disable-dev-shm-usage \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port=9222 \
  --user-data-dir="$BROWSER_DIR" \
  --window-size=1280,800 \
  about:blank >"$LOG_DIR/chromium.log" 2>&1 & CHROME_PID=$!

sleep 3
if ! curl -fsS http://127.0.0.1:9222/json/version >/dev/null; then
  fail "Chromium did not start correctly. See $LOG_DIR/chromium.log"
fi

PREVIEW="https://6080-${WEB_HOST}/vnc.html?autoconnect=true&resize=scale"
printf '\n============================================================\n'
printf 'OPEN THIS LINK ON YOUR PHONE:\n%s\n' "$PREVIEW"
printf 'Sign in to Google in the browser window that appears.\n'
printf 'Do not close this terminal until it says LOGIN COMPLETE.\n'
printf '============================================================\n\n'

say "Waiting for the one-time Google sign-in"
"$VENV/bin/notebooklm" login \
  --master-token \
  --account "$GOOGLE_EMAIL" \
  --cdp-url http://127.0.0.1:9222 \
  --browser-timeout 1800

say "Validating NotebookLM authentication"
"$VENV/bin/notebooklm" auth check --test --json

TOKEN_FILE="$HOME/.notebooklm/profiles/default/master_token.json"
if [[ -f "$TOKEN_FILE" ]]; then
  chmod 600 "$TOKEN_FILE"
fi

say "LOGIN COMPLETE"
printf 'NotebookLM credential is stored only in your Google Cloud Shell home directory.\n'
printf 'Temporary browser profile is now being destroyed.\n'
printf 'Next step: return to ChatGPT.\n'
