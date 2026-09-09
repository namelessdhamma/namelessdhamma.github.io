#!/usr/bin/env bash
set -euo pipefail

BASE="$HOME/.nd-notebooklm-mcp"
VENV="$BASE/venv"
LOG_DIR="$BASE/logs"
mkdir -p "$BASE" "$LOG_DIR"
chmod 700 "$BASE"

say() { printf '\n==> %s\n' "$*"; }
fail() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

if [[ -z "${WEB_HOST:-}" ]]; then
  fail "Run this inside Google Cloud Shell (WEB_HOST is missing)."
fi

say "Preparing Google Cloud Shell packages"
sudo apt-get update -qq || true
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  xvfb x11vnc novnc websockify python3-venv curl unzip >/dev/null

say "Installing NotebookLM MCP in a private virtual environment"
if [[ ! -x "$VENV/bin/python" ]]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install -q --upgrade pip
"$VENV/bin/python" -m pip install -q --upgrade 'notebooklm-py[headless,browser,mcp]'

say "Installing Playwright Chromium"
"$VENV/bin/python" -m playwright install chromium >/dev/null

GOOGLE_EMAIL="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | head -n 1 || true)"
if [[ -z "$GOOGLE_EMAIL" ]]; then
  printf '\nGoogle account email: '
  read -r GOOGLE_EMAIL
fi
[[ -n "$GOOGLE_EMAIL" ]] || fail "Google account email is required."
printf '\nUsing Google account: %s\n' "$GOOGLE_EMAIL"

XVFB_PID=""; VNC_PID=""; NOVNC_PID=""
cleanup() {
  set +e
  for p in "$NOVNC_PID" "$VNC_PID" "$XVFB_PID"; do
    [[ -n "$p" ]] && kill "$p" 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM

say "Starting a temporary private browser display inside Google Cloud Shell"
Xvfb :99 -screen 0 1280x800x24 -nolisten tcp >"$LOG_DIR/xvfb.log" 2>&1 & XVFB_PID=$!
export DISPLAY=:99
sleep 1

x11vnc -display :99 -forever -shared -nopw -rfbport 5900 -localhost \
  >"$LOG_DIR/x11vnc.log" 2>&1 & VNC_PID=$!

websockify --web=/usr/share/novnc 6080 localhost:5900 \
  >"$LOG_DIR/novnc.log" 2>&1 & NOVNC_PID=$!

sleep 2
PREVIEW="https://6080-${WEB_HOST}/vnc.html?autoconnect=true&resize=scale"
printf '\n============================================================\n'
printf 'OPEN THIS LINK ON YOUR PHONE:\n%s\n' "$PREVIEW"
printf 'A Google sign-in browser will appear there automatically.\n'
printf 'Complete the sign-in and do not close this terminal.\n'
printf '============================================================\n\n'

say "Waiting for the one-time Google sign-in"
"$VENV/bin/notebooklm" login \
  --master-token \
  --account "$GOOGLE_EMAIL" \
  --browser chromium \
  --browser-timeout 1800

say "Validating NotebookLM authentication"
"$VENV/bin/notebooklm" auth check --test --json

TOKEN_FILE="$HOME/.notebooklm/profiles/default/master_token.json"
if [[ -f "$TOKEN_FILE" ]]; then
  chmod 600 "$TOKEN_FILE"
fi

say "LOGIN COMPLETE"
printf 'NotebookLM credential is stored only in your Google Cloud Shell home directory.\n'
printf 'Next step will start the OpenAI Secure MCP Tunnel.\n'
