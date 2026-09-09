#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$HERE/01-notebooklm-login.sh"
bash "$HERE/02-run-secure-tunnel.sh"
