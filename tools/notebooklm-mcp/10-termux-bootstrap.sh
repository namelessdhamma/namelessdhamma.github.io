#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

TUNNEL_ID="tunnel_6aa11901abe48191adbc946db4ede98b"
NLM_VERSION="0.8.2"
TUNNEL_VERSION="v0.0.14"
BASE="$HOME/.nd-notebooklm-mcp"
VENV="$BASE/venv"
TC="$BASE/tunnel-client"
SRC="$BASE/tunnel-client-src"
SERVICE="nd-notebooklm-mcp"
PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"

say(){ printf '\n==> %s\n' "$*"; }
fail(){ printf '\nERROR: %s\n' "$*" >&2; exit 1; }

[[ -d /data/data/com.termux/files/usr ]] || fail "Run this inside the Termux app."
ARCH="$(uname -m)"
case "$ARCH" in aarch64|arm64) ;; *) fail "This bootstrap currently expects ARM64/aarch64; detected: $ARCH";; esac

mkdir -p "$BASE" "$HOME/.notebooklm/profiles/default"
chmod 700 "$BASE" "$HOME/.notebooklm" "$HOME/.notebooklm/profiles" "$HOME/.notebooklm/profiles/default" 2>/dev/null || true

say "Updating Termux packages"
pkg update -y
pkg upgrade -y

say "Installing free local runtime dependencies"
pkg install -y python git golang cloudflared termux-services curl coreutils openssl

say "Installing NotebookLM MCP $NLM_VERSION"
if [[ ! -x "$VENV/bin/python" ]]; then
  python -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install -q --upgrade pip
"$VENV/bin/python" -m pip install -q --upgrade "notebooklm-py[headless,mcp]==$NLM_VERSION"

say "Building OpenAI tunnel-client $TUNNEL_VERSION natively for Android/Termux"
if [[ ! -x "$TC" ]]; then
  rm -rf "$SRC"
  git clone -q --depth 1 --branch "$TUNNEL_VERSION" https://github.com/openai/tunnel-client.git "$SRC"
  (
    cd "$SRC"
    export CGO_ENABLED=0
    go build -trimpath -ldflags="-s -w" -o "$TC" ./cmd/client
  )
  chmod 700 "$TC"
fi
"$TC" --version || fail "tunnel-client build is not runnable on this Android device."
cloudflared --version || fail "Termux cloudflared is not runnable."

say "Preparing supervised Termux service"
SVD="$PREFIX/var/service/$SERVICE"
mkdir -p "$SVD/log" "$HOME/.termux/boot" "$BASE/logs"
cat >"$SVD/run" <<RUN_EOF
#!/data/data/com.termux/files/usr/bin/sh
exec 2>&1
export HOME="$HOME"
export PATH="$PREFIX/bin:$VENV/bin:/system/bin"
export NOTEBOOKLM_PROFILE=default
export NOTEBOOKLM_HEADLESS_REAUTH=1
export CLOUDFLARED_PATH="$PREFIX/bin/cloudflared"

MASTER="$HOME/.notebooklm/profiles/default/master_token.json"
RUNTIME="$BASE/openai-runtime-key"
PROFILE_DIR="$HOME/.config/openai/tunnel-client/profiles/nd-notebooklm"

[ -s "\$MASTER" ] || { echo "ND-MCP: waiting for NotebookLM master token"; sleep 30; exit 1; }
[ -s "\$RUNTIME" ] || { echo "ND-MCP: waiting for OpenAI runtime key"; sleep 30; exit 1; }

"$VENV/bin/notebooklm" auth refresh --verify >/dev/null 2>&1 || {
  echo "ND-MCP: NotebookLM auth refresh failed"; sleep 15; exit 1;
}

exec "$TC" run --profile nd-notebooklm
RUN_EOF
chmod 700 "$SVD/run"

cat >"$SVD/log/run" <<LOG_EOF
#!/data/data/com.termux/files/usr/bin/sh
mkdir -p "$BASE/logs/service"
exec svlogd -tt "$BASE/logs/service"
LOG_EOF
chmod 700 "$SVD/log/run"

cat >"$HOME/.termux/boot/00-nd-notebooklm-mcp" <<BOOT_EOF
#!/data/data/com.termux/files/usr/bin/sh
termux-wake-lock
source "$PREFIX/etc/profile.d/start-services.sh"
BOOT_EOF
chmod 700 "$HOME/.termux/boot/00-nd-notebooklm-mcp"

# Do not enable until credentials are imported and profile initialized.
sv-disable "$SERVICE" >/dev/null 2>&1 || true

cat <<EOF

============================================================
TERMUX RUNTIME PREPARED
Android architecture: $ARCH
NotebookLM MCP: $NLM_VERSION
OpenAI tunnel-client: $TUNNEL_VERSION
Tunnel: $TUNNEL_ID

No Google/OpenAI secret has been imported yet.
Next step: secure credential migration from the existing Cloud Shell session.
============================================================
EOF
