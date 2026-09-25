#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${BLUE_SEA_REPO_URL:-https://github.com/namelessdhamma/namelessdhamma.github.io.git}"
BRANCH="${BLUE_SEA_BRANCH:-main}"
PROJECT_REL="${BLUE_SEA_PROJECT_REL:-sinee-more-godot}"
SOURCE_ROOT="/tmp/nd-godot-source"
CACHE_ROOT="/tmp/nd-godot-cache"

echo "[nd-godot] engine=$(godot --version)"
echo "[nd-godot] dotnet=$(dotnet --version)"
echo "[nd-godot] tunnel=$(tunnel-client --version)"

rm -rf "$SOURCE_ROOT"
mkdir -p "$CACHE_ROOT"
git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$SOURCE_ROOT"

export GODOT_PROJECT="$SOURCE_ROOT/$PROJECT_REL"
export GODOT_PATH="/usr/local/bin/godot"
export GODOT_MCP_DOCS_CACHE="$CACHE_ROOT/docs"
export DISPLAY="${DISPLAY:-:99}"

test -f "$GODOT_PROJECT/project.godot"

# Tier C bridge is injected only into the disposable cloud checkout.
mkdir -p "$GODOT_PROJECT/addons"
rm -rf "$GODOT_PROJECT/addons/godot_mcp"
cp -R /opt/godot-mcp/addon/godot_mcp "$GODOT_PROJECT/addons/godot_mcp"

if ! grep -Fq 'res://addons/godot_mcp/plugin.cfg' "$GODOT_PROJECT/project.godot"; then
  cat >> "$GODOT_PROJECT/project.godot" <<'EOF'

[editor_plugins]

enabled=PackedStringArray("res://addons/godot_mcp/plugin.cfg")
EOF
fi

# Tier D virtual display.
Xvfb "$DISPLAY" -screen 0 1920x1080x24 -nolisten tcp >/tmp/nd-godot-xvfb.log 2>&1 &
XVFB_PID=$!

cleanup() {
  kill "$XVFB_PID" >/dev/null 2>&1 || true
  if [[ -n "${EDITOR_PID:-}" ]]; then
    kill "$EDITOR_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

# Engine-native import + smoke qualification runs even before tunnel provisioning.
godot --headless --path "$GODOT_PROJECT" --editor --quit >/tmp/nd-godot-import.log 2>&1
godot --headless --path "$GODOT_PROJECT" --quit-after 2 >/tmp/nd-godot-smoke.log 2>&1 || {
  cat /tmp/nd-godot-smoke.log >&2
  exit 1
}
grep -Fq "BLUE_SEA_GODOT_READY" /tmp/nd-godot-smoke.log
echo "[nd-godot] ENGINE_SMOKE_PASS"

# Do not consume a persistent editor process until Secure MCP Tunnel exists.
if [[ -z "${CONTROL_PLANE_TUNNEL_ID:-}" || -z "${CONTROL_PLANE_API_KEY:-}" ]]; then
  echo "[nd-godot] WAITING_FOR_TUNNEL_CONFIG"
  while true; do sleep 3600; done
fi

godot --headless --editor --path "$GODOT_PROJECT" >/tmp/nd-godot-editor.log 2>&1 &
EDITOR_PID=$!
for _ in $(seq 1 60); do
  [[ -f "$GODOT_PROJECT/.godot/mcp_bridge.json" ]] && break
  sleep 0.5
done
if [[ ! -f "$GODOT_PROJECT/.godot/mcp_bridge.json" ]]; then
  echo "[nd-godot] editor bridge failed" >&2
  cat /tmp/nd-godot-editor.log >&2 || true
  exit 1
fi

rm -rf /root/.config/tunnel-client /root/.local/share/tunnel-client || true

tunnel-client init \
  --sample sample_mcp_stdio_local \
  --profile nd-godot \
  --tunnel-id "$CONTROL_PLANE_TUNNEL_ID" \
  --mcp-command "node /opt/godot-mcp/dist/server.js"

tunnel-client doctor --profile nd-godot --explain
echo "[nd-godot] SECURE_TUNNEL_PASS"

exec tunnel-client run --profile nd-godot
