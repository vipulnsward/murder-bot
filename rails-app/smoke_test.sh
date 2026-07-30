#!/bin/sh
set -eu

cd "$(dirname "$0")"
export BUILDX_CONFIG=/tmp/murderbot-rails-buildx
mkdir -p "$BUILDX_CONFIG"
compose="docker compose -p murderbot-rails-smoke -f docker-compose.smoke.yml"

cleanup() {
  $compose down --volumes --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT
cleanup

check() {
  name=$1
  expected=$2
  response=$3
  body=$(printf '%s\n' "$response" | sed '$d')
  status=$(printf '%s\n' "$response" | tail -n 1)
  printf '%s response: %s\n' "$name" "$body"
  if [ "$status" = "$expected" ]; then
    printf 'PASS %s status=%s\n' "$name" "$status"
  else
    printf 'FAIL %s expected=%s actual=%s\n' "$name" "$expected" "$status"
    exit 1
  fi
}

printf 'Building Rails image...\n'
$compose build --quiet
printf 'Starting PostgreSQL...\n'
$compose up -d --wait postgres >/dev/null
printf 'Running db:create db:migrate...\n'
$compose run --rm web ./bin/rails db:create db:migrate
$compose run --rm web ./bin/rails --version
printf 'Starting Rails services...\n'
$compose up -d --wait web live_guard >/dev/null

health=$(curl -sS -w '\n%{http_code}' http://localhost:3100/up)
check health 200 "$health"

signup=$(curl -sS -w '\n%{http_code}' -H 'Content-Type: application/json' \
  -d '{"email":"smoke@example.com","password":"password123"}' \
  http://localhost:3100/api/signup)
check signup 201 "$signup"
signup_body=$(printf '%s\n' "$signup" | sed '$d')
token=$(printf '%s\n' "$signup_body" | sed -n 's/.*"token":"\([^"]*\)".*/\1/p')
[ -n "$token" ] || { printf 'FAIL signup token missing\n'; exit 1; }

unauthorized_me=$(curl -sS -w '\n%{http_code}' http://localhost:3100/api/me)
check unauthorized-me 401 "$unauthorized_me"

me=$(curl -sS -w '\n%{http_code}' -H "Authorization: Bearer $token" \
  http://localhost:3100/api/me)
check me 200 "$me"
me_body=$(printf '%s\n' "$me" | sed '$d')
printf '%s' "$me_body" | grep -q '"email":"smoke@example.com"' || { printf 'FAIL me email\n'; exit 1; }
printf 'PASS me email=smoke@example.com\n'

counter_generals=$(curl -sS -w '\n%{http_code}' \
  'http://localhost:3100/api/counter-generals?enemy=stub-enemy&role=attack&top=5')
check counter-generals 200 "$counter_generals"
counter_generals_body=$(printf '%s\n' "$counter_generals" | sed '$d')
printf '%s' "$counter_generals_body" | grep -q '"recommendations":' || { printf 'FAIL counter-generals recommendations missing\n'; exit 1; }
printf '%s' "$counter_generals_body" | grep -q '"general":"stub-counter"' || { printf 'FAIL counter-generals stub response missing\n'; exit 1; }
printf 'PASS counter-generals proxied local stub response\n'

counter_generals_unavailable=$(curl -sS -w '\n%{http_code}' \
  'http://localhost:3100/api/counter-generals?enemy=unavailable')
check counter-generals-unavailable 200 "$counter_generals_unavailable"
counter_generals_unavailable_body=$(printf '%s\n' "$counter_generals_unavailable" | sed '$d')
printf '%s' "$counter_generals_unavailable_body" | grep -q '"error":"brain unavailable"' || { printf 'FAIL counter-generals fallback\n'; exit 1; }
printf 'PASS counter-generals upstream error fallback\n'

dashboard=$(curl -sS -w '\n%{http_code}' -H "Authorization: Bearer $token" \
  http://localhost:3100/api/dashboard/status)
check dashboard 200 "$dashboard"
dashboard_body=$(printf '%s\n' "$dashboard" | sed '$d')
printf '%s' "$dashboard_body" | grep -q '"reachable":true' || { printf 'FAIL dashboard brain unreachable\n'; exit 1; }
printf 'PASS dashboard brain reachable=true\n'

login=$(curl -sS -w '\n%{http_code}' -H 'Content-Type: application/json' \
  -d '{"email":"SMOKE@example.com","password":"password123"}' \
  http://localhost:3100/api/login)
check login 200 "$login"

bad_login=$(curl -sS -w '\n%{http_code}' -H 'Content-Type: application/json' \
  -d '{"email":"smoke@example.com","password":"wrong-password"}' \
  http://localhost:3100/api/login)
check bad-login 401 "$bad_login"

duplicate=$(curl -sS -w '\n%{http_code}' -H 'Content-Type: application/json' \
  -d '{"email":"SMOKE@example.com","password":"password123"}' \
  http://localhost:3100/api/signup)
check duplicate-signup 409 "$duplicate"

plans=$(curl -sS -w '\n%{http_code}' http://localhost:3100/api/billing/plans)
check plans 200 "$plans"
plans_body=$(printf '%s\n' "$plans" | sed '$d')
for plan in brain auto alliance; do
  printf '%s' "$plans_body" | grep -q "\"$plan\"" || { printf 'FAIL plans missing=%s\n' "$plan"; exit 1; }
done
printf 'PASS plans include=brain,auto,alliance\n'

unauthorized=$(curl -sS -w '\n%{http_code}' -H 'Content-Type: application/json' \
  -d '{"plan":"brain"}' http://localhost:3100/api/billing/checkout)
check unauthorized-checkout 401 "$unauthorized"

checkout=$(curl -sS -w '\n%{http_code}' -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $token" -d '{"plan":"brain"}' \
  http://localhost:3100/api/billing/checkout)
check checkout 200 "$checkout"
checkout_body=$(printf '%s\n' "$checkout" | sed '$d')
printf '%s' "$checkout_body" | grep -q '"configured":false' || { printf 'FAIL checkout configured flag\n'; exit 1; }
printf 'PASS checkout configured=false\n'

live_guard=$(curl -sS -w '\n%{http_code}' -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $token" -d '{"plan":"brain"}' \
  http://localhost:3101/api/billing/checkout)
check live-key-guard 403 "$live_guard"

timestamp=$(date +%s)
webhook_body='{"type":"checkout.session.completed","data":{"object":{"client_reference_id":"1","customer":"cus_smoke","subscription":"sub_smoke","metadata":{"plan":"auto","user_id":"1"}}}}'
signature=$(printf '%s' "$webhook_body" | $compose exec -T -e TIMESTAMP="$timestamp" web \
  ruby -ropenssl -e 'print OpenSSL::HMAC.hexdigest("SHA256", "smoke-webhook-secret", "#{ENV.fetch("TIMESTAMP")}.#{STDIN.read}")')
bad_webhook=$(curl -sS -w '\n%{http_code}' -H 'Content-Type: application/json' \
  -H "Stripe-Signature: t=$timestamp,v1=bad" -d "$webhook_body" \
  http://localhost:3100/api/billing/stripe/webhook)
check bad-webhook-signature 400 "$bad_webhook"

webhook=$(curl -sS -w '\n%{http_code}' -H 'Content-Type: application/json' \
  -H "Stripe-Signature: t=$timestamp,v1=$signature" -d "$webhook_body" \
  http://localhost:3100/api/billing/stripe/webhook)
check webhook 200 "$webhook"

activated=$(curl -sS -w '\n%{http_code}' -H 'Content-Type: application/json' \
  -d '{"email":"smoke@example.com","password":"password123"}' \
  http://localhost:3100/api/login)
check activated-plan 200 "$activated"
activated_body=$(printf '%s\n' "$activated" | sed '$d')
printf '%s' "$activated_body" | grep -q '"plan":"auto"' || { printf 'FAIL activated plan\n'; exit 1; }
printf 'PASS activated plan=auto\n'

printf 'ALL SMOKE TESTS PASSED\n'
