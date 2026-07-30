#!/usr/bin/env bash
# launch.sh — TURNKEY go-live for Murder Bot / Easybot on Hetzner Cloud.
#
# One command puts the whole dockerized stack (Redroid + bot + manager + Postgres + Caddy)
# on a fresh Hetzner ARM VM (Linux, so Redroid's binder works — proven required on 2026-07-29).
#
# Usage:
#   HCLOUD_TOKEN=xxxxxxxx ./deploy/launch.sh [server-name] [server-type] [location]
# Defaults: name=murderbot, type=cax21 (4 vCPU Ampere ARM / 8 GB), location=fsn1.
#
# It ONLY spends money when YOU run it with YOUR token. It creates ONE VM and prints the IP
# and next steps (DNS + APK sideload + first email/password login). No charges, no accounts
# are created on your behalf otherwise.
set -euo pipefail

NAME="${1:-murderbot}"
TYPE="${2:-cax21}"
LOCATION="${3:-fsn1}"
SSH_KEY="${SSH_KEY:-vipul-hetzner}"   # name of an SSH key already uploaded to Hetzner
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="ubuntu-24.04"
API="https://api.hetzner.cloud/v1"
CLOUD_INIT="$(dirname "$0")/cloud-init.yaml"

if [ -z "${HCLOUD_TOKEN:-}" ]; then
  echo "ERROR: set HCLOUD_TOKEN (Hetzner Cloud API token: Console -> Security -> API Tokens, Read&Write)." >&2
  echo "Then: HCLOUD_TOKEN=xxxx ./deploy/launch.sh" >&2
  exit 1
fi
[ -f "$CLOUD_INIT" ] || { echo "ERROR: $CLOUD_INIT not found." >&2; exit 1; }

auth=(-H "Authorization: Bearer ${HCLOUD_TOKEN}" -H "Content-Type: application/json")

echo "[launch] verifying token + server type availability ($TYPE in $LOCATION)…"
# Hetzner's /server_types/{id} takes a NUMERIC id; look up by name via ?name= instead.
curl -fsS "${auth[@]}" "$API/server_types?name=$TYPE" | grep -q '"id"' \
  || { echo "ERROR: token invalid or server type '$TYPE' unavailable." >&2; exit 1; }
# Ensure the SSH key exists on the account (so you can log in).
curl -fsS "${auth[@]}" "$API/ssh_keys?name=$SSH_KEY" | grep -q '"id"' \
  || { echo "ERROR: SSH key '$SSH_KEY' not found on the account (upload it first, or set SSH_KEY=)." >&2; exit 1; }

# cloud-init as user_data (JSON-escaped)
USERDATA="$(python3 -c 'import json,sys;print(json.dumps(open(sys.argv[1]).read()))' "$CLOUD_INIT")"

echo "[launch] creating $TYPE VM '$NAME' ($IMAGE, $LOCATION) with cloud-init…"
resp="$(curl -fsS "${auth[@]}" -X POST "$API/servers" -d @- <<JSON
{
  "name": "${NAME}",
  "server_type": "${TYPE}",
  "image": "${IMAGE}",
  "location": "${LOCATION}",
  "start_after_create": true,
  "user_data": ${USERDATA},
  "ssh_keys": ["${SSH_KEY}"],
  "labels": {"app": "murderbot"},
  "public_net": {"enable_ipv4": true, "enable_ipv6": true}
}
JSON
)"

ip="$(printf '%s' "$resp" | python3 -c 'import json,sys;print(json.load(sys.stdin)["server"]["public_net"]["ipv4"]["ip"])')"
sid="$(printf '%s' "$resp" | python3 -c 'import json,sys;print(json.load(sys.stdin)["server"]["id"])')"
echo "[launch] ✅ VM created — id=$sid, public IP = $ip"

SSHOPTS=(-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=6)

echo "[launch] waiting for SSH on $ip (cloud-init installs Docker in parallel)…"
for _ in $(seq 1 90); do
  ssh "${SSHOPTS[@]}" -o BatchMode=yes root@"$ip" true 2>/dev/null && { echo "  ssh is up"; break; }
  sleep 4
done

echo "[launch] uploading code -> root@$ip:/opt/murderbot …"
ssh "${SSHOPTS[@]}" root@"$ip" 'mkdir -p /opt/murderbot' || { echo "ERROR: cannot SSH to $ip yet — rerun the upload block once it's reachable." >&2; exit 1; }
rsync -az --delete \
  --exclude '.git' --exclude '.venv' --exclude 'venv' --exclude '__pycache__' \
  --exclude '*.pyc' --exclude '*.mp4' --exclude '*.mov' --exclude '*.webm' \
  --exclude 'node_modules' --exclude 'deploy/.env' \
  -e "ssh ${SSHOPTS[*]}" \
  "$REPO_ROOT/" root@"$ip":/opt/murderbot/

# DOMAIN: caller's $DOMAIN if set, else the bare IP so Caddy serves immediately (before DNS).
DEPLOY_DOMAIN="${DOMAIN:-$ip}"
echo "[launch] writing deploy/.env (DOMAIN=$DEPLOY_DOMAIN) + bringing the stack up (build ~5-10 min)…"
ssh "${SSHOPTS[@]}" root@"$ip" DEPLOY_DOMAIN="$DEPLOY_DOMAIN" 'bash -s' <<'REMOTE'
set -e
cd /opt/murderbot/deploy
if [ ! -f .env ]; then
  PG_PW=$(python3 -c "import secrets;print(secrets.token_urlsafe(24))")
  NEO=$(python3 -c "import secrets;print(secrets.token_urlsafe(48))")
  ENC=$(python3 -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())")
  { echo "DOMAIN=${DEPLOY_DOMAIN}"; echo "ADB_TARGET=redroid:5555"; echo "POSTGRES_DB=murderbot";
    echo "POSTGRES_USER=murderbot"; echo "POSTGRES_PASSWORD=${PG_PW}";
    echo "NEO_SECRET=${NEO}"; echo "EVONY_ENC_KEY=${ENC}"; } > .env
  chmod 600 .env
fi
for _ in $(seq 1 75); do command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1 && break; sleep 4; done
modprobe binder_linux devices=binder,hwbinder,vndbinder 2>/dev/null || true
docker compose up -d --build
echo "---- docker compose ps ----"; docker compose ps
REMOTE

cat <<DONE

[launch] ✅ stack build kicked off on $ip.
         The manager is reachable by IP as soon as it's healthy (Redroid keeps building):
           curl -s http://$ip/healthz            # {"status":"ok",...}
           open  http://$ip/                      # login: vipul@saeloun.com

NEXT:
  1. Point a domain at it (for real HTTPS):  <domain>  A  $ip   then rerun with DOMAIN=<domain>
  2. Watch it come up:      ssh root@$ip 'cd /opt/murderbot/deploy && docker compose ps'
  3. Verify Redroid booted: ssh root@$ip 'ls -l /dev/binder* ; cd /opt/murderbot/deploy && docker compose exec redroid getprop sys.boot_completed'
  4. Sideload Evony:        ssh root@$ip 'cd /opt/murderbot/deploy && docker compose exec redroid ...'  (or adb over a tunnel)
  5. Billing when ready:    set BILLING_LIVE=1 + real RAZORPAY_* in /opt/murderbot/deploy/.env, then 'docker compose up -d'

To destroy it later:  curl -H "Authorization: Bearer \$HCLOUD_TOKEN" -X DELETE $API/servers/$sid
DONE
