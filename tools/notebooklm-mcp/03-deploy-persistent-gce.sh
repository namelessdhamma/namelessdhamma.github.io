#!/usr/bin/env bash
set -euo pipefail

# ND NotebookLM MCP — persistent, zero-recurring-cost-by-design deployment.
# Uses only Google Cloud Always Free eligible resources/configuration:
#   * one e2-micro in us-central1
#   * 10 GB pd-standard boot disk
#   * external IPv6 only (NO external IPv4 hourly charge)
#   * tiny Cloud Storage bootstrap object (well inside Always Free quota)
#   * two Secret Manager secrets (well inside Always Free quota)
# The script intentionally refuses to create paid-only network components such as
# external IPv4, Cloud NAT, load balancers, or minimum-instance serverless runtimes.

TUNNEL_ID="tunnel_6aa11901abe48191adbc946db4ede98b"
ZONE="us-central1-a"
REGION="us-central1"
INSTANCE="nd-notebooklm-mcp"
NETWORK="nd-mcp-net"
SUBNET="nd-mcp-subnet-v6"
SA_NAME="nd-notebooklm-mcp"
SECRET_MASTER="nd-notebooklm-master-token"
SECRET_RUNTIME="nd-openai-tunnel-runtime-key"
MASTER_FILE="$HOME/.notebooklm/profiles/default/master_token.json"
RUNTIME_FILE="$HOME/.nd-notebooklm-mcp/openai-runtime-key"
LOCAL_TUNNEL="$HOME/.nd-notebooklm-mcp/tunnel-client"
TUNNEL_VERSION="0.0.14"
NLM_VERSION="0.8.2"

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

# Google requires an active billing account even to activate Compute Engine Free Tier.
# Billing linkage itself is not a subscription and this script creates no resource
# that is expected to have a recurring charge while Always Free limits are respected.
BILLING_ENABLED="$(gcloud billing projects describe "$PROJECT" --format='value(billingEnabled)' 2>/dev/null || true)"
if [[ "$BILLING_ENABLED" != "True" && "$BILLING_ENABLED" != "true" ]]; then
  mapfile -t BILLING_ACCOUNTS < <(gcloud billing accounts list --filter='open=true' --format='value(name)' 2>/dev/null || true)
  if [[ ${#BILLING_ACCOUNTS[@]} -eq 0 ]]; then
    cat <<EOF

BILLING_ACCOUNT_REQUIRED_FOR_FREE_TIER
Google requires an active billing account to activate Compute Engine, including its Always Free e2-micro allowance.
This revised deployment creates NO external IPv4, Cloud NAT, load balancer, or other paid-only component.
Expected recurring infrastructure charge for the configured resources: $0 while Always Free quotas remain available and are not exceeded.
Open: https://console.cloud.google.com/billing
Create/activate one billing account, then rerun this same script.
EOF
    exit 42
  fi
  BILLING_ID="${BILLING_ACCOUNTS[0]#billingAccounts/}"
  say "Linking project to billing account for Free Tier activation: $BILLING_ID"
  gcloud billing projects link "$PROJECT" --billing-account="$BILLING_ID" --quiet >/dev/null
fi

say "Enabling minimum Google Cloud APIs"
gcloud services enable \
  compute.googleapis.com \
  secretmanager.googleapis.com \
  iam.googleapis.com \
  storage.googleapis.com \
  --project="$PROJECT" --quiet

SA_EMAIL="$SA_NAME@$PROJECT.iam.gserviceaccount.com"
if ! gcloud iam service-accounts describe "$SA_EMAIL" --project="$PROJECT" >/dev/null 2>&1; then
  say "Creating dedicated least-privilege service account"
  gcloud iam service-accounts create "$SA_NAME" \
    --display-name="ND NotebookLM MCP runtime" \
    --project="$PROJECT" --quiet
fi

say "Storing credentials in Google Secret Manager (Always Free quota)"
for spec in "$SECRET_MASTER:$MASTER_FILE" "$SECRET_RUNTIME:$RUNTIME_FILE"; do
  NAME="${spec%%:*}"
  FILE="${spec#*:}"
  if ! gcloud secrets describe "$NAME" --project="$PROJECT" >/dev/null 2>&1; then
    gcloud secrets create "$NAME" --replication-policy=automatic --project="$PROJECT" --quiet >/dev/null
    gcloud secrets versions add "$NAME" --data-file="$FILE" --project="$PROJECT" --quiet >/dev/null
  fi
  gcloud secrets add-iam-policy-binding "$NAME" \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/secretmanager.secretAccessor" \
    --project="$PROJECT" --quiet >/dev/null
  printf '  ready: %s\n' "$NAME"
done

# Stage only the tunnel-client binary in Cloud Storage so the IPv6-only VM never
# needs GitHub connectivity (github.com itself may not publish AAAA records).
BUCKET="${PROJECT}-nd-mcp-bootstrap"
if ! gcloud storage buckets describe "gs://$BUCKET" --project="$PROJECT" >/dev/null 2>&1; then
  say "Creating tiny us-central1 bootstrap bucket (Always Free quota)"
  gcloud storage buckets create "gs://$BUCKET" \
    --project="$PROJECT" \
    --location="$REGION" \
    --uniform-bucket-level-access >/dev/null
fi

if [[ ! -x "$LOCAL_TUNNEL" ]]; then
  say "Downloading tunnel-client in Cloud Shell for IPv6-only VM staging"
  TMPDL="$(mktemp -d)"
  trap 'rm -rf "$TMPDL"' EXIT
  curl -fsSL "https://github.com/openai/tunnel-client/releases/download/v${TUNNEL_VERSION}/tunnel-client-v${TUNNEL_VERSION}-linux-amd64.zip" -o "$TMPDL/tunnel.zip"
  unzip -q "$TMPDL/tunnel.zip" -d "$TMPDL/unpacked"
  FOUND="$(find "$TMPDL/unpacked" -type f -name tunnel-client | head -n1 || true)"
  [[ -n "$FOUND" ]] || fail "Could not locate tunnel-client binary after download."
  mkdir -p "$(dirname "$LOCAL_TUNNEL")"
  install -m 700 "$FOUND" "$LOCAL_TUNNEL"
  rm -rf "$TMPDL"
  trap - EXIT
fi

gcloud storage cp "$LOCAL_TUNNEL" "gs://$BUCKET/tunnel-client" --quiet >/dev/null
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/storage.objectViewer" \
  --quiet >/dev/null

if ! gcloud compute networks describe "$NETWORK" --project="$PROJECT" >/dev/null 2>&1; then
  say "Creating private-by-default VPC"
  gcloud compute networks create "$NETWORK" --subnet-mode=custom --project="$PROJECT" --quiet >/dev/null
fi
if ! gcloud compute networks subnets describe "$SUBNET" --region="$REGION" --project="$PROJECT" >/dev/null 2>&1; then
  say "Creating external-IPv6 subnet (no paid external IPv4)"
  gcloud compute networks subnets create "$SUBNET" \
    --network="$NETWORK" \
    --region="$REGION" \
    --range="10.42.0.0/24" \
    --stack-type=IPV4_IPV6 \
    --ipv6-access-type=EXTERNAL \
    --project="$PROJECT" --quiet >/dev/null
fi

STARTUP="$(mktemp)"
trap 'rm -f "$STARTUP"' EXIT
cat >"$STARTUP" <<STARTUP_EOF
#!/usr/bin/env bash
set -euo pipefail

TUNNEL_ID="$TUNNEL_ID"
SECRET_MASTER="$SECRET_MASTER"
SECRET_RUNTIME="$SECRET_RUNTIME"
BUCKET="$BUCKET"
NLM_VERSION="$NLM_VERSION"
BASE="/opt/nd-notebooklm-mcp"
STATE="/var/lib/nd-notebooklm-mcp"
USER_NAME="ndmcp"
METADATA="http://[fd20:ce::254]/computeMetadata/v1"

log() { echo "ND-MCP: \$*"; }

# IPv6 connectivity qualification before installing anything.
for host in api.openai.com accounts.google.com notebooklm.google.com pypi.org files.pythonhosted.org; do
  if ! getent ahostsv6 "\$host" >/dev/null 2>&1; then
    echo "IPv6 DNS preflight failed for \$host" >&2
    exit 61
  fi
done

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv curl ca-certificates >/dev/null

if ! id "\$USER_NAME" >/dev/null 2>&1; then
  useradd --system --create-home --home-dir "\$STATE" --shell /usr/sbin/nologin "\$USER_NAME"
fi
mkdir -p "\$BASE" "\$STATE/.notebooklm/profiles/default"
chown -R "\$USER_NAME:\$USER_NAME" "\$STATE"
chmod 700 "\$STATE" "\$STATE/.notebooklm" "\$STATE/.notebooklm/profiles" "\$STATE/.notebooklm/profiles/default"

if [[ ! -x "\$BASE/venv/bin/python" ]]; then
  python3 -m venv "\$BASE/venv"
fi
"\$BASE/venv/bin/python" -m pip install -q --upgrade pip
"\$BASE/venv/bin/python" -m pip install -q --upgrade "notebooklm-py[headless,mcp]==\$NLM_VERSION"

meta() { curl -g -fsS -H 'Metadata-Flavor: Google' "\$METADATA/\$1"; }
PROJECT_ID="\$(meta project/project-id)"
access_token() {
  meta instance/service-accounts/default/token | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])'
}

fetch_secret() {
  local secret="\$1" dest="\$2" attempt token response tmp
  tmp="\${dest}.tmp"
  for attempt in \$(seq 1 24); do
    token="\$(access_token 2>/dev/null || true)"
    if [[ -n "\$token" ]]; then
      response="\$(curl -6 -fsS -H "Authorization: Bearer \$token" "https://secretmanager.googleapis.com/v1/projects/\$PROJECT_ID/secrets/\$secret/versions/latest:access" 2>/dev/null || true)"
      if [[ -n "\$response" ]] && printf '%s' "\$response" | python3 -c 'import base64,json,sys; d=json.load(sys.stdin); sys.stdout.buffer.write(base64.b64decode(d["payload"]["data"]))' >"\$tmp" 2>/dev/null && [[ -s "\$tmp" ]]; then
        mv "\$tmp" "\$dest"
        chmod 600 "\$dest"
        chown "\$USER_NAME:\$USER_NAME" "\$dest"
        return 0
      fi
    fi
    sleep 5
  done
  echo "Failed to retrieve secret: \$secret" >&2
  exit 62
}

fetch_secret "\$SECRET_MASTER" "\$STATE/.notebooklm/profiles/default/master_token.json"
fetch_secret "\$SECRET_RUNTIME" "\$STATE/openai-runtime-key"

log "Downloading pre-staged tunnel-client from same-project Cloud Storage"
token="\$(access_token)"
curl -6 -fsS -H "Authorization: Bearer \$token" \
  "https://storage.googleapis.com/storage/v1/b/\$BUCKET/o/tunnel-client?alt=media" \
  -o "\$BASE/tunnel-client"
chmod 755 "\$BASE/tunnel-client"

log "Minting fresh NotebookLM session from durable master token"
runuser -u "\$USER_NAME" -- env HOME="\$STATE" NOTEBOOKLM_PROFILE=default \
  "\$BASE/venv/bin/notebooklm" login --master-token-refresh >/tmp/nd-nlm-refresh.log 2>&1
runuser -u "\$USER_NAME" -- env HOME="\$STATE" NOTEBOOKLM_PROFILE=default \
  "\$BASE/venv/bin/notebooklm" auth check --test --json >/tmp/nd-nlm-auth.json 2>&1

log "Creating tunnel-client profile"
runuser -u "\$USER_NAME" -- env HOME="\$STATE" \
  "\$BASE/tunnel-client" init \
    --sample sample_mcp_stdio_local \
    --profile nd-notebooklm \
    --force \
    --tunnel-id "\$TUNNEL_ID" \
    --control-plane-api-key-ref "file:\$STATE/openai-runtime-key" \
    --mcp-command "\$BASE/venv/bin/notebooklm-mcp" >/tmp/nd-tunnel-init.log 2>&1

log "Running IPv6 tunnel preflight"
runuser -u "\$USER_NAME" -- env HOME="\$STATE" NOTEBOOKLM_PROFILE=default NOTEBOOKLM_HEADLESS_REAUTH=1 \
  "\$BASE/tunnel-client" doctor --profile nd-notebooklm --explain >/tmp/nd-tunnel-doctor.log 2>&1

cat >/etc/systemd/system/nd-notebooklm-mcp.service <<EOF
[Unit]
Description=ND NotebookLM MCP via OpenAI Secure MCP Tunnel
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=\$USER_NAME
Group=\$USER_NAME
Environment=HOME=\$STATE
Environment=NOTEBOOKLM_PROFILE=default
Environment=NOTEBOOKLM_HEADLESS_REAUTH=1
ExecStart=\$BASE/tunnel-client run --profile nd-notebooklm
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=\$STATE

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now nd-notebooklm-mcp.service
sleep 12
if ! systemctl is-active --quiet nd-notebooklm-mcp.service; then
  journalctl -u nd-notebooklm-mcp.service --no-pager -n 100
  exit 63
fi

log "Persistent IPv6-only service is active"
echo "ND_MCP_FREE_PERSISTENT_READY"
STARTUP_EOF

# Stop temporary Cloud Shell tunnel only at the ownership hand-off point.
say "Stopping temporary Cloud Shell tunnel before persistent hand-off"
pkill -f 'tunnel-client.*run.*nd-notebooklm' 2>/dev/null || true
sleep 2

if gcloud compute instances describe "$INSTANCE" --zone="$ZONE" --project="$PROJECT" >/dev/null 2>&1; then
  say "Existing VM found; recreating it with zero-cost IPv6-only configuration"
  gcloud compute instances delete "$INSTANCE" --zone="$ZONE" --project="$PROJECT" --quiet
fi

say "Creating Free Tier e2-micro VM: IPv6-only, 10 GB pd-standard, no external IPv4"
gcloud compute instances create "$INSTANCE" \
  --zone="$ZONE" \
  --project="$PROJECT" \
  --machine-type=e2-micro \
  --network-interface="subnet=$SUBNET,stack-type=IPV6_ONLY,ipv6-network-tier=PREMIUM" \
  --service-account="$SA_EMAIL" \
  --scopes=https://www.googleapis.com/auth/cloud-platform \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --boot-disk-type=pd-standard \
  --boot-disk-size=10GB \
  --shielded-secure-boot \
  --labels=purpose=nd-notebooklm-mcp,cost-policy=always-free \
  --metadata-from-file=startup-script="$STARTUP" \
  --quiet >/dev/null

# Fail closed if Google somehow attached a paid external IPv4.
EXTERNAL_V4="$(gcloud compute instances describe "$INSTANCE" --zone="$ZONE" --project="$PROJECT" --format='value(networkInterfaces[0].accessConfigs[0].natIP)' 2>/dev/null || true)"
if [[ -n "$EXTERNAL_V4" ]]; then
  gcloud compute instances delete "$INSTANCE" --zone="$ZONE" --project="$PROJECT" --quiet || true
  fail "Cost guard triggered: an external IPv4 was attached unexpectedly. VM deleted."
fi

say "Waiting for zero-cost persistent runtime to finish bootstrapping"
READY=0
for _ in $(seq 1 90); do
  SERIAL="$(gcloud compute instances get-serial-port-output "$INSTANCE" --zone="$ZONE" --project="$PROJECT" 2>/dev/null || true)"
  if grep -q 'ND_MCP_FREE_PERSISTENT_READY' <<<"$SERIAL"; then
    READY=1
    break
  fi
  if grep -qE 'IPv6 DNS preflight failed|Failed to retrieve secret|Traceback|Startup script.*failed|nd-notebooklm-mcp.service.*failed' <<<"$SERIAL"; then
    break
  fi
  sleep 10
done

if [[ "$READY" -ne 1 ]]; then
  printf '\nZero-cost VM did not report readiness. Last serial output follows:\n\n'
  gcloud compute instances get-serial-port-output "$INSTANCE" --zone="$ZONE" --project="$PROJECT" 2>/dev/null | tail -n 140 || true
  printf '\nThe VM is Free Tier configured, but it has not taken ownership of the tunnel.\n'
  printf 'Restart the temporary Cloud Shell tunnel if you need immediate connectivity while we diagnose.\n'
  exit 1
fi

EXTERNAL_V6="$(gcloud compute instances describe "$INSTANCE" --zone="$ZONE" --project="$PROJECT" --format='value(networkInterfaces[0].ipv6AccessConfigs[0].externalIpv6)' 2>/dev/null || true)"
cat <<EOF

============================================================
PERSISTENT ND NOTEBOOKLM MCP: READY — ZERO-COST CONFIGURATION
Project: $PROJECT
Instance: $INSTANCE
Zone: $ZONE
External IPv4: NONE
External IPv6: ${EXTERNAL_V6:-assigned automatically}
Machine: e2-micro (Always Free eligible in us-central1)
Disk: 10 GB pd-standard (inside 30 GB Always Free allowance)
Tunnel: $TUNNEL_ID

The temporary Cloud Shell tunnel has been stopped.
The persistent VM now runs NotebookLM MCP + tunnel-client under systemd.
No browser or Cloud Shell session is required for normal operation.
============================================================
EOF
