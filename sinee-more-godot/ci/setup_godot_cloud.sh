#!/usr/bin/env bash
set -euo pipefail

GODOT_VERSION=4.7.2
GODOT_SHA256=129f82db7bafd54ae14bb5bb284041c73860e8c7a009a3a026ca5e946cbff247
GODOT_MCP_COMMIT=735bdc9c98806e5ecdd05b819bc4ac461d9af935

sudo apt-get update -y
sudo apt-get install -y --no-install-recommends \
  ca-certificates curl git unzip xvfb ffmpeg \
  libx11-6 libxcursor1 libxinerama1 libxrandr2 libxi6 libxkbcommon0 \
  libgl1 libegl1 libvulkan1 libasound2t64 libpulse0 libfontconfig1 libudev1 libdbus-1-3

rm -rf /tmp/nd-godot-dist /tmp/godot-mcp /tmp/godot.zip
curl -fL "https://github.com/godotengine/godot-builds/releases/download/${GODOT_VERSION}-stable/Godot_v${GODOT_VERSION}-stable_mono_linux_x86_64.zip" -o /tmp/godot.zip
echo "${GODOT_SHA256}  /tmp/godot.zip" | sha256sum -c -
mkdir -p /tmp/nd-godot-dist
unzip -q /tmp/godot.zip -d /tmp/nd-godot-dist
GODOT_BIN="$(find /tmp/nd-godot-dist -type f -name 'Godot_v*-stable_mono_linux.x86_64' -print -quit)"
test -n "$GODOT_BIN"
chmod +x "$GODOT_BIN"
sudo ln -sf "$GODOT_BIN" /usr/local/bin/godot

git clone --quiet https://github.com/blentz/godot-mcp.git /tmp/godot-mcp
git -C /tmp/godot-mcp checkout --quiet "$GODOT_MCP_COMMIT"
npm --prefix /tmp/godot-mcp ci
npm --prefix /tmp/godot-mcp run build

godot --version
dotnet --version
node --version
test -f /tmp/godot-mcp/dist/server.js
