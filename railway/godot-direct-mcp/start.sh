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

# Railway Free cannot keep a full Godot editor resident without OOM-kill.
# Keep the lightweight X display available for Tier D on-demand processes,
# but make Tier C editor bridge explicitly optional instead of gating health.
rm -f "$GODOT_PROJECT/.godot/mcp_bridge.json"
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 2>/dev/null || true

echo "ND_GODOT_XVFB_START"
Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp   >"$GODOT_PROJECT/ci-out/xvfb.log" 2>&1 &
XVFB_PID=$!
sleep 0.5
if ! kill -0 "$XVFB_PID" >/dev/null 2>&1; then
  echo "ND_GODOT_XVFB_FAILED"
  cat "$GODOT_PROJECT/ci-out/xvfb.log" >&2 || true
  exit 1
fi
echo "ND_GODOT_XVFB_READY"

EDITOR_PID=""
if [[ "${ND_GODOT_PERSISTENT_EDITOR:-false}" == "true" ]]; then
  echo "ND_GODOT_EDITOR_OPTIONAL_START"
  godot --headless --editor --path "$GODOT_PROJECT"     >"$GODOT_PROJECT/ci-out/editor.log" 2>&1 &
  EDITOR_PID=$!
  for _ in $(seq 1 40); do
    if ! kill -0 "$EDITOR_PID" >/dev/null 2>&1; then
      echo "ND_GODOT_EDITOR_OPTIONAL_UNAVAILABLE"
      EDITOR_PID=""
      break
    fi
    if test -s "$GODOT_PROJECT/.godot/mcp_bridge.json"; then
      echo "ND_GODOT_EDITOR_BRIDGE_READY"
      break
    fi
    sleep 0.5
  done
else
  echo "ND_GODOT_EDITOR_BRIDGE_DISABLED_FREE_MODE"
fi

cd "$GODOT_PROJECT"
INTERNAL_MCP_PORT="${ND_GODOT_INTERNAL_MCP_PORT:-8001}"

echo "ND_GODOT_GATEWAY_START internal_port=$INTERNAL_MCP_PORT"
supergateway   --stdio "node /opt/godot-mcp/dist/server.js"   --outputTransport streamableHttp   --port "$INTERNAL_MCP_PORT"   --streamableHttpPath /mcp   --healthEndpoint /healthz   --logLevel none &
GATEWAY_PID=$!

for _ in $(seq 1 60); do
  if ! kill -0 "$GATEWAY_PID" >/dev/null 2>&1; then
    echo "ND_GODOT_GATEWAY_FAILED"
    exit 1
  fi
  if curl -fsS "http://127.0.0.1:$INTERNAL_MCP_PORT/healthz" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done

curl -fsS "http://127.0.0.1:$INTERNAL_MCP_PORT/healthz" >/dev/null
echo "ND_GODOT_GATEWAY_READY"

node /opt/nd-godot/proxy.mjs &
PROXY_PID=$!

cleanup() {
  kill "$PROXY_PID" >/dev/null 2>&1 || true
  kill "$GATEWAY_PID" >/dev/null 2>&1 || true
  if [[ -n "$EDITOR_PID" ]]; then
    kill "$EDITOR_PID" >/dev/null 2>&1 || true
  fi
  kill "$XVFB_PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

echo "ND_GODOT_FREE_MODE_READY tiers=A,B,D tier_C=optional"
set +e
wait -n "$GATEWAY_PID" "$PROXY_PID"
RC=$?
set -e
echo "ND_GODOT_PUBLIC_STACK_EXIT rc=$RC"
exit "$RC"
