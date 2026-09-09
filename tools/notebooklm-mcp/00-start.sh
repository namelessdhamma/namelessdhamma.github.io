#!/usr/bin/env bash
set -euo pipefail

RAW_BASE="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/notebooklm-mcp-bootstrap/tools/notebooklm-mcp"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

printf '\n==> Downloading ND NotebookLM MCP bootstrap\n'
curl -fsSL "$RAW_BASE/01-notebooklm-login.sh" -o "$TMP/01-notebooklm-login.sh"
curl -fsSL "$RAW_BASE/02-run-secure-tunnel.sh" -o "$TMP/02-run-secure-tunnel.sh"
chmod 700 "$TMP/01-notebooklm-login.sh" "$TMP/02-run-secure-tunnel.sh"

printf '\n==> Step 1/2: one-time Google / NotebookLM authorization\n'
bash "$TMP/01-notebooklm-login.sh"

printf '\n==> Step 2/2: starting OpenAI Secure MCP Tunnel\n'
printf 'When asked for the OpenAI Runtime API key, paste it and press Enter.\n'
printf 'The terminal will not display the key while you paste it.\n'
bash "$TMP/02-run-secure-tunnel.sh"
