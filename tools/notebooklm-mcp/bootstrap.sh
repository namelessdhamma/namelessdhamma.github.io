#!/usr/bin/env bash
set -euo pipefail
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
BASE_URL="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/notebooklm-mcp-bootstrap/tools/notebooklm-mcp"
curl -fsSL "$BASE_URL/01-notebooklm-login.sh" -o "$TMP/01-notebooklm-login.sh"
curl -fsSL "$BASE_URL/02-run-secure-tunnel.sh" -o "$TMP/02-run-secure-tunnel.sh"
chmod 700 "$TMP/01-notebooklm-login.sh" "$TMP/02-run-secure-tunnel.sh"
bash "$TMP/01-notebooklm-login.sh"
bash "$TMP/02-run-secure-tunnel.sh"
