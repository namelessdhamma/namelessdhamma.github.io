#!/usr/bin/env bash
set -euo pipefail

: "${ND_GODOT_MCP_PATH_TOKEN:?ND_GODOT_MCP_PATH_TOKEN is required}"

export GODOT_PROJECT="${GODOT_PROJECT:-/workspace/sinee-more-godot}"
export GODOT_PATH="${GODOT_PATH:-/usr/local/bin/godot}"
export GODOT_MCP_DOCS_CACHE="${GODOT_MCP_DOCS_CACHE:-/tmp/nd-godot-docs}"
export LIBGL_ALWAYS_SOFTWARE="${LIBGL_ALWAYS_SOFTWARE:-1}"
export DISPLAY=:99

mkdir -p "$GODOT_MCP_DOCS_CACHE" "$GODOT_PROJECT/ci-out"

if ! grep -Fq 'res://addons/godot_mcp/plugin.cfg' "$GODOT_PROJECT/project.godot"; then
  cat >> "$GODOT_PROJECT/project.godot" <<'EOF'

[editor_plugins]

enabled=PackedStringArray("res://addons/godot_mcp/plugin.cfg")
EOF
fi

# Import once before starting the long-lived editor so all project metadata exists.
godot --headless --path "$GODOT_PROJECT" --editor --quit \
  >"$GODOT_PROJECT/ci-out/boot-import.log" 2>&1

Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp \
  >"$GODOT_PROJECT/ci-out/xvfb.log" 2>&1 &
XVFB_PID=$!

godot --headless --editor --path "$GODOT_PROJECT" \
  >"$GODOT_PROJECT/ci-out/editor.log" 2>&1 &
EDITOR_PID=$!

cleanup() {
  kill "$EDITOR_PID" >/dev/null 2>&1 || true
  kill "$XVFB_PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

for _ in $(seq 1 80); do
  if test -f "$GODOT_PROJECT/.godot/mcp_bridge.json"; then
    break
  fi
  if ! kill -0 "$EDITOR_PID" >/dev/null 2>&1; then
    cat "$GODOT_PROJECT/ci-out/editor.log" >&2 || true
    exit 1
  fi
  sleep 0.5
done

test -f "$GODOT_PROJECT/.godot/mcp_bridge.json"

cd "$GODOT_PROJECT"

exec supergateway \
  --stdio "node /opt/godot-mcp/dist/server.js" \
  --outputTransport streamableHttp \
  --port "${PORT:-8080}" \
  --streamableHttpPath "/mcp/${ND_GODOT_MCP_PATH_TOKEN}" \
  --healthEndpoint /healthz \
  --logLevel none
