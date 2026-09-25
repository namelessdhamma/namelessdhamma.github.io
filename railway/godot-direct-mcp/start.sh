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

# Bound the optional warm import. It improves first-call latency but must never
# prevent the MCP gateway from becoming available.
echo "ND_GODOT_IMPORT_START"
set +e
timeout 60s godot --headless --path "$GODOT_PROJECT" --editor --quit \
  2>&1 | tee "$GODOT_PROJECT/ci-out/boot-import.log"
IMPORT_RC=${PIPESTATUS[0]}
set -e
echo "ND_GODOT_IMPORT_DONE rc=$IMPORT_RC"

# Warm import may leave a dead bridge descriptor. Require the long-lived
# editor to create a fresh descriptor so readiness cannot be satisfied by stale state.
rm -f "$GODOT_PROJECT/.godot/mcp_bridge.json"

echo "ND_GODOT_XVFB_START"
Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp \
  >"$GODOT_PROJECT/ci-out/xvfb.log" 2>&1 &
XVFB_PID=$!
sleep 0.5
if ! kill -0 "$XVFB_PID" >/dev/null 2>&1; then
  echo "ND_GODOT_XVFB_FAILED"
  cat "$GODOT_PROJECT/ci-out/xvfb.log" >&2 || true
  exit 1
fi
echo "ND_GODOT_XVFB_READY"

echo "ND_GODOT_EDITOR_START"
godot --headless --editor --path "$GODOT_PROJECT" \
  >"$GODOT_PROJECT/ci-out/editor.log" 2>&1 &
EDITOR_PID=$!

cleanup() {
  kill "$EDITOR_PID" >/dev/null 2>&1 || true
  kill "$XVFB_PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

BRIDGE_READY=0
for _ in $(seq 1 80); do
  if ! kill -0 "$EDITOR_PID" >/dev/null 2>&1; then
    echo "ND_GODOT_EDITOR_FAILED"
    cat "$GODOT_PROJECT/ci-out/editor.log" >&2 || true
    exit 1
  fi
  if test -s "$GODOT_PROJECT/.godot/mcp_bridge.json"; then
    BRIDGE_READY=1
    break
  fi
  sleep 0.5
done

if test "$BRIDGE_READY" != "1"; then
  echo "ND_GODOT_BRIDGE_TIMEOUT"
  cat "$GODOT_PROJECT/ci-out/editor.log" >&2 || true
  exit 1
fi

echo "ND_GODOT_BRIDGE_READY"
cd "$GODOT_PROJECT"

echo "ND_GODOT_GATEWAY_START port=${PORT:-8080}"
exec supergateway \
  --stdio "node /opt/godot-mcp/dist/server.js" \
  --outputTransport streamableHttp \
  --port "${PORT:-8080}" \
  --streamableHttpPath "/mcp/${ND_GODOT_MCP_PATH_TOKEN}" \
  --healthEndpoint /healthz \
  --logLevel none
