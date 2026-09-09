#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

BASE="$HOME/.nd-notebooklm-mcp"
VENV="$BASE/venv"
TC="$BASE/tunnel-client"
SRC="$BASE/tunnel-client-src"
SERVICE="nd-notebooklm-mcp"
MANIFEST_URL="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/notebooklm-mcp-bootstrap/tools/notebooklm-mcp/update-manifest.json"

mkdir -p "$BASE"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
curl -fsSL "$MANIFEST_URL" -o "$TMP/manifest.json"
read -r NLM TUNNEL < <(python - "$TMP/manifest.json" <<'PY'
import json,sys
m=json.load(open(sys.argv[1]))
assert m.get('channel')=='qualified'
print(m['notebooklm_py'], m['tunnel_client'])
PY
)

CURRENT_NLM="$($VENV/bin/python -c 'import importlib.metadata as m; print(m.version("notebooklm-py"))' 2>/dev/null || true)"
CURRENT_TUNNEL="$($TC --version 2>/dev/null | grep -oE 'v?[0-9]+\.[0-9]+\.[0-9]+' | head -n1 || true)"

changed=0
if [[ "$CURRENT_NLM" != "$NLM" ]]; then
  "$VENV/bin/python" -m pip install -q --upgrade "notebooklm-py[headless,mcp]==$NLM"
  "$VENV/bin/notebooklm" auth refresh --verify >/dev/null
  changed=1
fi

norm_current="${CURRENT_TUNNEL#v}"
norm_target="${TUNNEL#v}"
if [[ "$norm_current" != "$norm_target" ]]; then
  rm -rf "$SRC"
  git clone -q --depth 1 --branch "$TUNNEL" https://github.com/openai/tunnel-client.git "$SRC"
  (cd "$SRC" && CGO_ENABLED=0 go build -trimpath -ldflags='-s -w' -o "$TMP/tunnel-client" ./cmd/client)
  "$TMP/tunnel-client" --version >/dev/null
  install -m 700 "$TMP/tunnel-client" "$TC"
  changed=1
fi

if [[ "$changed" -eq 1 ]]; then
  sv restart "$SERVICE" >/dev/null 2>&1 || true
  sleep 5
  sv status "$SERVICE"
else
  echo "ND-MCP already matches qualified manifest: notebooklm-py=$NLM tunnel-client=$TUNNEL"
fi
