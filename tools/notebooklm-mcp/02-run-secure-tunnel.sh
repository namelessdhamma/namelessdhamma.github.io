#!/usr/bin/env bash
set -euo pipefail

BASE="$HOME/.nd-notebooklm-mcp"
VENV="$BASE/venv"
TC="$BASE/tunnel-client"
KEY_FILE="$BASE/openai-runtime-key"
TUNNEL_FILE="$BASE/tunnel-id"
PROFILE="nd-notebooklm"
mkdir -p "$BASE"
chmod 700 "$BASE"

say() { printf '\n==> %s\n' "$*"; }
fail() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

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

TUNNEL_ID=""
if [[ -s "$TUNNEL_FILE" ]]; then
  TUNNEL_ID="$(cat "$TUNNEL_FILE")"
fi
if [[ -z "$TUNNEL_ID" ]]; then
  printf '\nOpenAI tunnel ID (starts with tunnel_): '
  read -r TUNNEL_ID
  [[ "$TUNNEL_ID" == tunnel_* ]] || fail "A valid tunnel ID is required."
  printf '%s' "$TUNNEL_ID" > "$TUNNEL_FILE"
  chmod 600 "$TUNNEL_FILE"
fi

if [[ ! -s "$KEY_FILE" ]]; then
  printf '\nOpenAI runtime API key (input is hidden): '
  read -r -s RUNTIME_KEY
  printf '\n'
  [[ -n "$RUNTIME_KEY" ]] || fail "Runtime API key is required."
  umask 077
  printf '%s' "$RUNTIME_KEY" > "$KEY_FILE"
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
printf 'Keep this Cloud Shell session running while using NotebookLM from ChatGPT.\n'
printf 'Return to ChatGPT and connect the custom plugin to tunnel: %s\n\n' "$TUNNEL_ID"
exec "$TC" run --profile "$PROFILE"
