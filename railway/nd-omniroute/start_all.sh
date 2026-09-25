#!/usr/bin/env bash
set -euo pipefail

# Godot is deliberately a non-critical sidecar. Existing ND external routes
# remain served by drive_proxy.mjs even if Godot setup/tunnel is unavailable.
bash ./godot_sidecar.sh > /tmp/nd-godot-sidecar.log 2>&1 &
GODOT_SIDECAR_PID=$!

cleanup() {
  kill "$GODOT_SIDECAR_PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

exec node drive_proxy.mjs
