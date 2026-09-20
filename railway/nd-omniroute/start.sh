#!/bin/sh
set -eu
DATA_DIR="${DATA_DIR:-/tmp/omniroute-data}"
export DATA_DIR
mkdir -p "$DATA_DIR"
if [ ! -f "$DATA_DIR/.nd_bootstrap_v1" ]; then
  ./node_modules/.bin/omniroute setup --non-interactive \
    --password "$OMNIROUTE_SETUP_PASSWORD" \
    --add-provider \
    --provider glm \
    --provider-name nd-zai \
    --default-model glm/glm-4.7-flash
  touch "$DATA_DIR/.nd_bootstrap_v1"
fi
exec ./node_modules/.bin/omniroute --no-open --port "${PORT:-20128}"
