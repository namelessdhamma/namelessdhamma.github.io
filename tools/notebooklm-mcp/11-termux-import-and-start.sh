#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

TUNNEL_ID="tunnel_6aa11901abe48191adbc946db4ede98b"
BASE="$HOME/.nd-notebooklm-mcp"
VENV="$BASE/venv"
TC="$BASE/tunnel-client"
MASTER="$HOME/.notebooklm/profiles/default/master_token.json"
RUNTIME="$BASE/openai-runtime-key"
PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
SERVICE="nd-notebooklm-mcp"

say(){ printf '\n==> %s\n' "$*"; }
fail(){ printf '\nERROR: %s\n' "$*" >&2; exit 1; }

[[ -x "$VENV/bin/notebooklm" ]] || fail "Run 10-termux-bootstrap.sh first."
[[ -x "$TC" ]] || fail "tunnel-client is missing. Run 10-termux-bootstrap.sh first."

printf '\nPaste the migration passphrase (input hidden), then press Enter: '
read -r -s PASS
printf '\nPaste the encrypted payload, then press Enter:\n'
read -r PAYLOAD
[[ -n "$PASS" && -n "$PAYLOAD" ]] || fail "Both migration values are required."

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
umask 077
printf '%s' "$PAYLOAD" | base64 -d >"$TMP/payload.enc" 2>/dev/null || fail "Encrypted payload is not valid base64."
printf '%s' "$PASS" | openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass stdin \
  -in "$TMP/payload.enc" -out "$TMP/payload.tar" 2>/dev/null || fail "Could not decrypt payload; check the passphrase."
unset PASS PAYLOAD
mkdir -p "$TMP/unpacked"
tar -xf "$TMP/payload.tar" -C "$TMP/unpacked"
[[ -s "$TMP/unpacked/master_token.json" ]] || fail "master_token.json missing from package."
[[ -s "$TMP/unpacked/openai-runtime-key" ]] || fail "OpenAI runtime key missing from package."
python - "$TMP/unpacked/master_token.json" <<'PY'
import json,sys
p=sys.argv[1]
d=json.load(open(p))
assert d.get("version") == 1
assert isinstance(d.get("email"), str) and "@" in d["email"]
assert isinstance(d.get("master_token"), str) and d["master_token"].startswith("aas_et/")
assert isinstance(d.get("android_id"), str) and d["android_id"]
PY

say "Installing credentials locally with mode 0600"
mkdir -p "$(dirname "$MASTER")" "$BASE"
install -m 600 "$TMP/unpacked/master_token.json" "$MASTER"
install -m 600 "$TMP/unpacked/openai-runtime-key" "$RUNTIME"

say "Validating NotebookLM headless authentication on Android"
export NOTEBOOKLM_PROFILE=default
export NOTEBOOKLM_HEADLESS_REAUTH=1
"$VENV/bin/notebooklm" auth refresh --verify >/dev/null
"$VENV/bin/notebooklm" auth check --test --json

say "Creating the OpenAI Secure MCP Tunnel profile on Android"
export CLOUDFLARED_PATH="$PREFIX/bin/cloudflared"
"$TC" init \
  --sample sample_mcp_stdio_local \
  --profile nd-notebooklm \
  --force \
  --tunnel-id "$TUNNEL_ID" \
  --control-plane-api-key-ref "file:$RUNTIME" \
  --mcp-command "$VENV/bin/notebooklm-mcp"

say "Running tunnel preflight"
"$TC" doctor --profile nd-notebooklm --explain

say "Starting Termux service manager and enabling ND NotebookLM MCP"
source "$PREFIX/etc/profile.d/start-services.sh"
sv-enable "$SERVICE" >/dev/null 2>&1 || true
sv up "$SERVICE"
sleep 8

if sv status "$SERVICE" | grep -q '^run:'; then
  STATUS="$(sv status "$SERVICE")"
else
  echo
  echo "Service did not stay up. Recent log:"
  tail -n 80 "$BASE/logs/service/current" 2>/dev/null || true
  exit 1
fi

cat <<EOF

============================================================
ANDROID ND NOTEBOOKLM MCP: RUNNING
$STATUS
Tunnel: $TUNNEL_ID

The Android/Termux runtime is now supervised by termux-services.
Termux:Boot will start the service after phone reboot once its app has been
opened once and Android battery/autostart restrictions are disabled.

Next qualification: verify the existing ChatGPT plugin works while Cloud Shell
is stopped, then reboot the phone and verify again.
============================================================
EOF
