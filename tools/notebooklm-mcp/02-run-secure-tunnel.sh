#!/usr/bin/env bash
set -euo pipefail

BASE="$HOME/.nd-notebooklm-mcp"
VENV="$BASE/venv"
TC="$BASE/tunnel-client"
KEY_FILE="$BASE/openai-runtime-key"
PROFILE="nd-notebooklm"
TUNNEL_ID="tunnel_6aa11901abe48191adbc946db4ede98b"
mkdir -p "$BASE"
chmod 700 "$BASE"

say() { echo; echo "==> $*"; }
fail() { echo; echo "ERROR: $*" >&2; exit 1; }

[[ -x "$VENV/bin/notebooklm-mcp" ]] || fail "NotebookLM is not prepared. Run 01-notebooklm-login.sh first."
"$VENV/bin/notebooklm" auth check --test --json >/dev/null || fail "NotebookLM authentication is not valid."

if [[ ! -x "$TC" ]]; then
  say "Installing OpenAI Secure MCP Tunnel client v0.0.14"
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT
  curl -fsSL \
    https://github.com/openai/tunnel-client/releases/download/v0.0.14/tunnel-client-v0.0.14-linux-amd64.zip \
    -o "$TMP/tunnel.zip"
  unzip -q "$TMP/tunnel.zip" -d "$TMP/unpacked"
  FOUND="$(find "$TMP/unpacked" -type f -name tunnel-client | head -n 1 || true)"
  [[ -n "$FOUND" ]] || fail "Could not find tunnel-client in the downloaded release."
  install -m 700 "$FOUND" "$TC"
  rm -rf "$TMP"
  trap - EXIT
fi

if [[ ! -s "$KEY_FILE" ]]; then
  echo
  echo "Paste the OpenAI Runtime API key for this tunnel (input is hidden), then press Enter:"
  read -r -s RUNTIME_KEY
  echo
  [[ -n "$RUNTIME_KEY" ]] || fail "Runtime API key is required."
  umask 077
  cat > "$KEY_FILE" <<< "$RUNTIME_KEY"
  unset RUNTIME_KEY
  chmod 600 "$KEY_FILE"
fi

say "Creating the local tunnel profile"
"$TC" init \
  --sample sample_mcp_stdio_local \
  --profile "$PROFILE" \
  --force \
  --tunnel-id "$TUNNEL_ID" \
  --control-plane-api-key-ref "file:$KEY_FILE" \
  --mcp-command "$VENV/bin/notebooklm-mcp"

say "Checking NotebookLM MCP and Secure Tunnel readiness"
"$TC" doctor --profile "$PROFILE" --explain

say "Secure MCP Tunnel is starting"
echo "Tunnel: $TUNNEL_ID"
echo "Keep this Cloud Shell session open for the initial connectivity test."
echo "When the tunnel reports ready, return to ChatGPT and refresh the Tunnel list."
echo
exec "$TC" run --profile "$PROFILE"
