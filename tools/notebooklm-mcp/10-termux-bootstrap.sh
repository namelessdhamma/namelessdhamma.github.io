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
UPDATE_SERVICE="nd-notebooklm-updater"
PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
UPDATE_URL="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/notebooklm-mcp-bootstrap/tools/notebooklm-mcp/12-termux-self-update.sh"

say(){ printf '\n==> %s\n' "$*"; }
fail(){ printf '\nERROR: %s\n' "$*" >&2; exit 1; }

retry() {
  local attempts="$1" delay="$2"; shift 2
  local n=1
  until "$@"; do
    if (( n >= attempts )); then return 1; fi
    printf 'Transient failure; retry %d/%d in %ss...\n' "$n" "$attempts" "$delay" >&2
    sleep "$delay"
    n=$((n+1))
  done
}

[[ -d /data/data/com.termux/files/usr ]] || fail "Run this inside the Termux app."
ARCH="$(uname -m)"
case "$ARCH" in aarch64|arm64) ;; *) fail "This bootstrap currently expects ARM64/aarch64; detected: $ARCH";; esac

mkdir -p "$BASE" "$HOME/.notebooklm/profiles/default"
chmod 700 "$BASE" "$HOME/.notebooklm" "$HOME/.notebooklm/profiles" "$HOME/.notebooklm/profiles/default" 2>/dev/null || true

export DEBIAN_FRONTEND=noninteractive
export PIP_DEFAULT_TIMEOUT=120
export PIP_RETRIES=15
export PIP_DISABLE_PIP_VERSION_CHECK=1

say "Updating Termux packages"
retry 5 10 pkg update -y
apt-get -o Dpkg::Options::=--force-confold -y upgrade

say "Installing free local runtime dependencies"
retry 5 10 apt-get -o Dpkg::Options::=--force-confold -y install \
  python git golang rust clang make pkg-config libffi openssl \
  cloudflared termux-services curl coreutils

say "Verifying native build toolchain"
command -v rustc >/dev/null || fail "rustc is unavailable after installing the Termux rust package."
command -v cargo >/dev/null || fail "cargo is unavailable after installing the Termux rust package."
rustc --version
cargo --version

say "Installing NotebookLM MCP $NLM_VERSION"
if [[ ! -x "$VENV/bin/python" ]]; then
  python -m venv "$VENV"
fi
retry 5 15 "$VENV/bin/python" -m pip install -q --retries 15 --timeout 120 --upgrade pip setuptools wheel
retry 5 15 env PATH="$PREFIX/bin:$PATH" CARGO="$PREFIX/bin/cargo" RUSTC="$PREFIX/bin/rustc" \
  "$VENV/bin/python" -m pip install -q --retries 15 --timeout 120 --prefer-binary --upgrade "notebooklm-py[headless,mcp]==$NLM_VERSION"

say "Building OpenAI tunnel-client $TUNNEL_VERSION natively for Android/Termux"
if [[ ! -x "$TC" ]]; then
  rm -rf "$SRC"
  retry 5 15 git clone -q --depth 1 --branch "$TUNNEL_VERSION" https://github.com/openai/tunnel-client.git "$SRC"
  (
    cd "$SRC"
    export CGO_ENABLED=0
    go build -trimpath -ldflags="-s -w" -o "$TC" ./cmd/client
  )
  chmod 700 "$TC"
fi
"$TC" --version || fail "tunnel-client build is not runnable on this Android device."
cloudflared --version || fail "Termux cloudflared is not runnable."

say "Installing qualified self-update helper"
retry 5 10 curl --retry 10 --retry-all-errors --connect-timeout 20 -fsSL "$UPDATE_URL" -o "$BASE/self-update.sh"
chmod 700 "$BASE/self-update.sh"

say "Preparing supervised Termux services"
SVD="$PREFIX/var/service/$SERVICE"
UPD="$PREFIX/var/service/$UPDATE_SERVICE"
mkdir -p "$SVD/log" "$UPD/log" "$HOME/.termux/boot" "$BASE/logs"
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

cat >"$UPD/run" <<UPDATE_EOF
#!/data/data/com.termux/files/usr/bin/sh
exec 2>&1
export HOME="$HOME"
export PATH="$PREFIX/bin:$VENV/bin:/system/bin"
while true; do
  "$BASE/self-update.sh" || echo "ND-MCP updater: check failed; keeping current qualified runtime"
  sleep 21600
done
UPDATE_EOF
chmod 700 "$UPD/run"

cat >"$UPD/log/run" <<UPDATE_LOG_EOF
#!/data/data/com.termux/files/usr/bin/sh
mkdir -p "$BASE/logs/updater"
exec svlogd -tt "$BASE/logs/updater"
UPDATE_LOG_EOF
chmod 700 "$UPD/log/run"

cat >"$HOME/.termux/boot/00-nd-notebooklm-mcp" <<BOOT_EOF
#!/data/data/com.termux/files/usr/bin/sh
termux-wake-lock
source "$PREFIX/etc/profile.d/start-services.sh"
BOOT_EOF
chmod 700 "$HOME/.termux/boot/00-nd-notebooklm-mcp"

# Do not enable until credentials are imported and profile initialized.
sv-disable "$SERVICE" >/dev/null 2>&1 || true
sv-disable "$UPDATE_SERVICE" >/dev/null 2>&1 || true

cat <<EOF

============================================================
TERMUX RUNTIME PREPARED
Android architecture: $ARCH
NotebookLM MCP: $NLM_VERSION
OpenAI tunnel-client: $TUNNEL_VERSION
Tunnel: $TUNNEL_ID
Updater: GitHub qualified manifest + local check every 6 hours

No Google/OpenAI secret has been imported yet.
Next step: secure credential migration from the existing Cloud Shell session.
============================================================
EOF
