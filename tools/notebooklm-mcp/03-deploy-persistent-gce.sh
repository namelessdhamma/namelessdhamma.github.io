#!/usr/bin/env bash
set -euo pipefail

TUNNEL_ID="tunnel_6aa11901abe48191adbc946db4ede98b"
ZONE="us-central1-a"
REGION="us-central1"
INSTANCE="nd-notebooklm-mcp"
NETWORK="nd-mcp-net"
SUBNET="nd-mcp-subnet"
SA_NAME="nd-notebooklm-mcp"
SECRET_MASTER="nd-notebooklm-master-token"
SECRET_RUNTIME="nd-openai-tunnel-runtime-key"
MASTER_FILE="$HOME/.notebooklm/profiles/default/master_token.json"
RUNTIME_FILE="$HOME/.nd-notebooklm-mcp/openai-runtime-key"

say() { printf '\n==> %s\n' "$*"; }
fail() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

[[ -s "$MASTER_FILE" ]] || fail "NotebookLM master token is missing: $MASTER_FILE"
[[ -s "$RUNTIME_FILE" ]] || fail "OpenAI tunnel runtime key is missing: $RUNTIME_FILE"
command -v gcloud >/dev/null || fail "gcloud is not available. Run this in Google Cloud Shell."

ACCOUNT="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | head -n1 || true)"
[[ -n "$ACCOUNT" ]] || fail "No active Google Cloud account."
say "Using Google account: $ACCOUNT"

PROJECT="$(gcloud config get-value project 2>/dev/null || true)"
if [[ -z "$PROJECT" || "$PROJECT" == "(unset)" ]]; then
  SUFFIX="$(date +%y%m%d)-$(python3 - <<'PY'
import secrets
print(secrets.token_hex(2))
PY
)"
  PROJECT="nd-nlm-mcp-$SUFFIX"
  say "Creating dedicated Google Cloud project: $PROJECT"
  gcloud projects create "$PROJECT" --name="ND NotebookLM MCP" --quiet
  gcloud config set project "$PROJECT" >/dev/null
fi
say "Google Cloud project: $PROJECT"

BILLING_ENABLED="$(gcloud billing projects describe "$PROJECT" --format='value(billingEnabled)' 2>/dev/null || true)"
if [[ "$BILLING_ENABLED" != "True" && "$BILLING_ENABLED" != "true" ]]; then
  mapfile -t BILLING_ACCOUNTS < <(gcloud billing accounts list --filter='open=true' --format='value(name)' 2>/dev/null || true)
  if [[ ${#BILLING_ACCOUNTS[@]} -eq 0 ]]; then
    cat <<EOF

BILLING_REQUIRED
Google Cloud requires a billing account before a persistent VM can be created.
Open: https://console.cloud.google.com/billing
Create/activate one billing account, then rerun this same script.
The e2-micro VM itself is eligible for the Compute Engine Free Tier in us-central1 when the account is eligible; an in-use external IPv4 can still incur a small hourly network charge.
EOF
    exit 42
  fi
  BILLING_ID="${BILLING_ACCOUNTS[0]#billingAccounts/}"
  say "Linking project to available billing account: $BILLING_ID"
  gcloud billing projects link "$PROJECT" --billing-account="$BILLING_ID" --quiet >/dev/null
fi

say "Enabling minimum Google Cloud APIs"
gcloud services enable \
  compute.googleapis.com \
  secretmanager.googleapis.com \
  iam.googleapis.com \
  --project="$PROJECT" --quiet

SA_EMAIL="$SA_NAME@$PROJECT.iam.gserviceaccount.com"
if ! gcloud iam service-accounts describe "$SA_EMAIL" --project="$PROJECT" >/dev/null 2>&1; then
  say "Creating dedicated least-privilege service account"
  gcloud iam service-accounts create "$SA_NAME" \
    --display-name="ND NotebookLM MCP runtime" \
    --project="$PROJECT" --quiet
fi

say "Storing credentials in Google Secret Manager"
for spec in "$SECRET_MASTER:$MASTER_FILE" "$SECRET_RUNTIME:$RUNTIME_FILE"; do
  NAME="${spec%%:*}"
  FILE="${spec#*:}"
  if ! gcloud secrets describe "$NAME" --project="$PROJECT" >/dev/null 2>&1; then
    gcloud secrets create "$NAME" --replication-policy=automatic --project="$PROJECT" --quiet >/dev/null
  fi
  gcloud secrets versions add "$NAME" --data-file="$FILE" --project="$PROJECT" --quiet >/dev/null
  gcloud secrets add-iam-policy-binding "$NAME" \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/secretmanager.secretAccessor" \
    --project="$PROJECT" --quiet >/dev/null
  printf '  stored: %s\n' "$NAME"
done

if ! gcloud compute networks describe "$NETWORK" --project="$PROJECT" >/dev/null 2>&1; then
  say "Creating private-by-default VPC"
  gcloud compute networks create "$NETWORK" --subnet-mode=custom --project="$PROJECT" --quiet >/dev/null
fi
if ! gcloud compute networks subnets describe "$SUBNET" --region="$REGION" --project="$PROJECT" >/dev/null 2>&1; then
  gcloud compute networks subnets create "$SUBNET" \
    --network="$NETWORK" \
    --region="$REGION" \
    --range="10.42.0.0/24" \
    --project="$PROJECT" --quiet >/dev/null
fi

STARTUP="$(mktemp)"
trap 'rm -f "$STARTUP"' EXIT
cat >"$STARTUP" <<'STARTUP_EOF'
#!/usr/bin/env bash
set -euo pipefail

TUNNEL_ID="tunnel_6aa11901abe48191adbc946db4ede98b"
SECRET_MASTER="nd-notebooklm-master-token"
SECRET_RUNTIME="nd-openai-tunnel-runtime-key"
BASE="/opt/nd-notebooklm-mcp"
STATE="/var/lib/nd-notebooklm-mcp"
USER_NAME="ndmcp"

log() { echo "ND-MCP: $*"; }

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv curl unzip ca-certificates >/dev/null

if ! id "$USER_NAME" >/dev/null 2>&1; then
  useradd --system --create-home --home-dir "$STATE" --shell /usr/sbin/nologin "$USER_NAME"
fi
mkdir -p "$BASE" "$STATE/.notebooklm/profiles/default"
chown -R "$USER_NAME:$USER_NAME" "$STATE"
chmod 700 "$STATE" "$STATE/.notebooklm" "$STATE/.notebooklm/profiles" "$STATE/.notebooklm/profiles/default"

if [[ ! -x "$BASE/venv/bin/python" ]]; then
  python3 -m venv "$BASE/venv"
fi
"$BASE/venv/bin/python" -m pip install -q --upgrade pip
"$BASE/venv/bin/python" -m pip install -q --upgrade 'notebooklm-py[headless,mcp]==0.8.2'

PROJECT_ID="$(curl -fsS -H 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/project/project-id)"
fetch_secret() {
  local secret="$1" dest="$2"
  local attempt token_json token response tmp
  tmp="${dest}.tmp"
  for attempt in $(seq 1 24); do
    token_json="$(curl -fsS -H 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token 2>/dev/null || true)"
    token="$(printf '%s' "$token_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("access_token", ""))' 2>/dev/null || true)"
    if [[ -n "$token" ]]; then
      response="$(curl -fsS -H "Authorization: Bearer $token" "https://secretmanager.googleapis.com/v1/projects/$PROJECT_ID/secrets/$secret/versions/latest:access" 2>/dev/null || true)"
      if [[ -n "$response" ]]; then
        if printf '%s' "$response" | python3 -c 'import base64,json,sys; d=json.load(sys.stdin); sys.stdout.buffer.write(base64.b64decode(d["payload"]["data"]))' >"$tmp" 2>/dev/null && [[ -s "$tmp" ]]; then
          mv "$tmp" "$dest"
          chmod 600 "$dest"
          chown "$USER_NAME:$USER_NAME" "$dest"
          return 0
        fi
      fi
    fi
    sleep 5
  done
  echo "Failed to retrieve secret: $secret" >&2
  exit 1
}

fetch_secret "$SECRET_MASTER" "$STATE/.notebooklm/profiles/default/master_token.json"
fetch_secret "$SECRET_RUNTIME" "$STATE/openai-runtime-key"

log "Minting fresh NotebookLM browser session from durable master token"
sudo -u "$USER_NAME" env HOME="$STATE" NOTEBOOKLM_PROFILE=default \
  "$BASE/venv/bin/notebooklm" login --master-token-refresh >/tmp/nd-nlm-refresh.log 2>&1
sudo -u "$USER_NAME" env HOME="$STATE" NOTEBOOKLM_PROFILE=default \
  "$BASE/venv/bin/notebooklm" auth check --test --json >/tmp/nd-nlm-auth.json 2>&1

if [[ ! -x "$BASE/tunnel-client" ]]; then
  TMPDIR="$(mktemp -d)"
  curl -fsSL https://github.com/openai/tunnel-client/releases/download/v0.0.14/tunnel-client-v0.0.14-linux-amd64.zip -o "$TMPDIR/tunnel.zip"
  unzip -q "$TMPDIR/tunnel.zip" -d "$TMPDIR/unpacked"
  FOUND="$(find "$TMPDIR/unpacked" -type f -name tunnel-client | head -n1)"
  install -m 755 "$FOUND" "$BASE/tunnel-client"
  rm -rf "$TMPDIR"
fi

log "Creating tunnel-client profile"
sudo -u "$USER_NAME" env HOME="$STATE" \
  "$BASE/tunnel-client" init \
    --sample sample_mcp_stdio_local \
    --profile nd-notebooklm \
    --force \
    --tunnel-id "$TUNNEL_ID" \
    --control-plane-api-key-ref "file:$STATE/openai-runtime-key" \
    --mcp-command "$BASE/venv/bin/notebooklm-mcp" >/tmp/nd-tunnel-init.log 2>&1

log "Running preflight doctor"
sudo -u "$USER_NAME" env HOME="$STATE" NOTEBOOKLM_PROFILE=default NOTEBOOKLM_HEADLESS_REAUTH=1 \
  "$BASE/tunnel-client" doctor --profile nd-notebooklm --explain >/tmp/nd-tunnel-doctor.log 2>&1

cat >/etc/systemd/system/nd-notebooklm-mcp.service <<EOF
[Unit]
Description=ND NotebookLM MCP via OpenAI Secure MCP Tunnel
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER_NAME
Group=$USER_NAME
Environment=HOME=$STATE
Environment=NOTEBOOKLM_PROFILE=default
Environment=NOTEBOOKLM_HEADLESS_REAUTH=1
ExecStart=$BASE/tunnel-client run --profile nd-notebooklm
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=$STATE

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now nd-notebooklm-mcp.service
sleep 12
if ! systemctl is-active --quiet nd-notebooklm-mcp.service; then
  journalctl -u nd-notebooklm-mcp.service --no-pager -n 100
  exit 1
fi

log "Persistent service is active"
echo "ND_MCP_PERSISTENT_READY"
STARTUP_EOF

# Stop the temporary Cloud Shell tunnel before the persistent runtime takes ownership.
say "Stopping temporary Cloud Shell tunnel"
pkill -f 'tunnel-client.*run.*nd-notebooklm' 2>/dev/null || true
sleep 2

if gcloud compute instances describe "$INSTANCE" --zone="$ZONE" --project="$PROJECT" >/dev/null 2>&1; then
  say "Existing persistent VM found; recreating it with the current qualified configuration"
  gcloud compute instances delete "$INSTANCE" --zone="$ZONE" --project="$PROJECT" --quiet
fi

say "Creating persistent e2-micro VM (no inbound firewall rules)"
gcloud compute instances create "$INSTANCE" \
  --zone="$ZONE" \
  --project="$PROJECT" \
  --machine-type=e2-micro \
  --network="$NETWORK" \
  --subnet="$SUBNET" \
  --service-account="$SA_EMAIL" \
  --scopes=https://www.googleapis.com/auth/cloud-platform \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --boot-disk-type=pd-standard \
  --boot-disk-size=10GB \
  --shielded-secure-boot \
  --labels=purpose=nd-notebooklm-mcp \
  --metadata-from-file=startup-script="$STARTUP" \
  --quiet >/dev/null

say "Waiting for persistent runtime to finish bootstrapping"
READY=0
for _ in $(seq 1 72); do
  SERIAL="$(gcloud compute instances get-serial-port-output "$INSTANCE" --zone="$ZONE" --project="$PROJECT" 2>/dev/null || true)"
  if grep -q 'ND_MCP_PERSISTENT_READY' <<<"$SERIAL"; then
    READY=1
    break
  fi
  if grep -qE 'Failed to retrieve secret|Traceback|Startup script.*failed|nd-notebooklm-mcp.service.*failed' <<<"$SERIAL"; then
    break
  fi
  sleep 10
done

if [[ "$READY" -ne 1 ]]; then
  printf '\nPersistent VM did not report readiness. Last serial output follows:\n\n'
  gcloud compute instances get-serial-port-output "$INSTANCE" --zone="$ZONE" --project="$PROJECT" 2>/dev/null | tail -n 120 || true
  exit 1
fi

EXTERNAL_IP="$(gcloud compute instances describe "$INSTANCE" --zone="$ZONE" --project="$PROJECT" --format='value(networkInterfaces[0].accessConfigs[0].natIP)')"
cat <<EOF

============================================================
PERSISTENT ND NOTEBOOKLM MCP: READY
Project: $PROJECT
Instance: $INSTANCE
Zone: $ZONE
External IP (outbound only; no ingress firewall rule): $EXTERNAL_IP
Tunnel: $TUNNEL_ID

The temporary Cloud Shell tunnel has been stopped.
The persistent VM now runs NotebookLM MCP + tunnel-client under systemd.
You may close Cloud Shell and your browser after the ChatGPT verification test.
============================================================
EOF
