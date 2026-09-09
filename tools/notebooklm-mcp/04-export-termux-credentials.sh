#!/usr/bin/env bash
set -euo pipefail

MASTER="$HOME/.notebooklm/profiles/default/master_token.json"
RUNTIME="$HOME/.nd-notebooklm-mcp/openai-runtime-key"
[[ -s "$MASTER" ]] || { echo "ERROR: master token not found" >&2; exit 1; }
[[ -s "$RUNTIME" ]] || { echo "ERROR: runtime key not found" >&2; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
umask 077
cp "$MASTER" "$TMP/master_token.json"
cp "$RUNTIME" "$TMP/openai-runtime-key"

PASS="$(openssl rand -hex 16)"
PAYLOAD="$({ cd "$TMP"; tar -cf - master_token.json openai-runtime-key; } | \
  openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass "pass:$PASS" | base64 | tr -d '\n')"

cat <<EOF

============================================================
ND TERMUX SECURE MIGRATION PACKAGE

STEP A — copy this passphrase to Termux when asked:
$PASS

STEP B — after that, copy this encrypted payload to Termux when asked:
$PAYLOAD

The payload contains the NotebookLM master token and OpenAI tunnel runtime key,
but is AES-256 encrypted. Do not paste either value into ChatGPT.
After successful import, clear these values from clipboard history.
============================================================
EOF

unset PASS PAYLOAD
