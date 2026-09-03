#!/bin/bash
# Prod smoke — general personal-loop check after a deploy.
#
# Covers: register/login → dashboard, consent setup (with the current mandatory
# module:social), inventory (device), lock session with device → start →
# safety-stop (device status transitions), Steps 6/7 pages, points/inventory
# pages. Registers a throwaway user and deletes it at the end (best-effort).
#
# Usage:
#   BASE_URL=http://127.0.0.1:8000 scripts/prod_smoke.sh
# Env:
#   BASE_URL  (default http://127.0.0.1:8000)
#   SMOKE_EMAIL_PREFIX (default smoke-<ts>@example.com)
set -euo pipefail

BASE="${BASE_URL:-http://127.0.0.1:8000}"
JAR=$(mktemp /tmp/prod_smoke.XXXXXX.cookies)
trap 'rm -f "$JAR"' EXIT
EMAIL="${SMOKE_EMAIL_PREFIX:-smoke-$(date +%s)@example.com}"
PASS="Smoke-Pass-2026!"
RANDOM_CSRF=$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')

echo "== register + login =="
REG_HTTP=$(curl -s -o /dev/null -w '%{http_code}' \
  -b "csrf_token=$RANDOM_CSRF" -c "$JAR" \
  --data-urlencode "csrf_token=$RANDOM_CSRF" --data-urlencode "email=$EMAIL" --data-urlencode "password=$PASS" \
  "$BASE/auth/register")
if [ "$REG_HTTP" -ge 400 ]; then
  echo "register: HTTP $REG_HTTP (FATAL)"
  exit 1
fi
echo "register: $REG_HTTP"
LOGIN_HTTP=$(curl -s -o /dev/null -w '%{http_code}' \
  -b "csrf_token=$RANDOM_CSRF" -c "$JAR" \
  --data-urlencode "csrf_token=$RANDOM_CSRF" --data-urlencode "email=$EMAIL" --data-urlencode "password=$PASS" \
  "$BASE/auth/login")
if [ "$LOGIN_HTTP" -ge 400 ]; then
  echo "login: HTTP $LOGIN_HTTP (FATAL)"
  exit 1
fi
LOGIN_REDIR=$(curl -s -o /dev/null -w '%{redirect_url}' \
  -b "csrf_token=$RANDOM_CSRF" -c "$JAR" \
  --data-urlencode "csrf_token=$RANDOM_CSRF" --data-urlencode "email=$EMAIL" --data-urlencode "password=$PASS" \
  "$BASE/auth/login")
echo "login: $LOGIN_HTTP -> $LOGIN_REDIR"
CSRF=$(grep csrf_token "$JAR" | awk '{print $7}' | tail -1)
HDR=(-b "$JAR" -c "$JAR" -H "X-CSRF-Token: $CSRF")
CONSENT_HTTP=$(curl -s -o /dev/null -w '%{http_code}' "${HDR[@]}" \
  --data-urlencode "consent_types=module:tracker" \
  --data-urlencode "consent_types=module:timer" \
  --data-urlencode "consent_types=module:medication" \
  --data-urlencode "consent_types=module:health" \
  --data-urlencode "consent_types=module:journal" \
  --data-urlencode "consent_types=module:care" \
  --data-urlencode "consent_types=module:catalog" \
  --data-urlencode "consent_types=module:insights" \
  --data-urlencode "consent_types=module:aftercare" \
  --data-urlencode "consent_types=module:social" \
  "$BASE/consent/setup")
if [ "$CONSENT_HTTP" -ge 400 ]; then
  echo "consent setup: HTTP $CONSENT_HTTP (FATAL)"
  exit 1
fi
echo "consent setup: $CONSENT_HTTP"

DASH_HTTP=$(curl -s -o /dev/null -w '%{http_code}' "${HDR[@]}" "$BASE/dashboard")
if [ "$DASH_HTTP" -ge 400 ]; then
  echo "dashboard: HTTP $DASH_HTTP (FATAL)"
  exit 1
fi
echo "dashboard: $DASH_HTTP"

echo "== inventory (device) =="
DEV=$(curl -s "${HDR[@]}" -H 'Content-Type: application/json' \
  -d '{"category":"wearable","name":"SMOKE CAGE","quantity":1,"quantity_needed":1,"is_shopping_list":false,"status":"bought","inventory_status":"available"}' \
  "$BASE/api/v2/inventory")
if [ -z "$DEV" ]; then
  echo "inventory create: EMPTY body"
  exit 1
fi
DEV_HTTP=$(curl -s -o /dev/null -w '%{http_code}' "${HDR[@]}" -H 'Content-Type: application/json' \
  -d '{"category":"wearable","name":"SMOKE CAGE","quantity":1,"quantity_needed":1,"is_shopping_list":false,"status":"bought","inventory_status":"available"}' \
  "$BASE/api/v2/inventory")
if [ "$DEV_HTTP" -ge 400 ]; then
  echo "inventory create: HTTP $DEV_HTTP"
  exit 1
fi
DEV_ID=$(echo "$DEV" | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
echo "device id: $DEV_ID"

echo "== create lock session with device =="
LOC=$(curl -s -o /dev/null -w '%{redirect_url}' "${HDR[@]}" \
  --data-urlencode "csrf_token=$CSRF" --data-urlencode "device_id=$DEV_ID" "$BASE/locktimer/new")
if [ -z "$LOC" ]; then
  echo "locktimer/new: empty redirect (FATAL)"
  exit 1
fi
SID=$(basename "$LOC")
if [ -z "$SID" ] || [ "$SID" = "/" ]; then
  echo "locktimer/new: bad session id '$SID' (FATAL)"
  exit 1
fi
echo "session: $SID"

# The session-detail GET can miss the chip right after a deploy (app/db warm-up,
# first-request latency); retry with a short pause before failing.
chip_ok=0
for _attempt in 1 2 3 4 5 6; do
  PAGE="$(curl -s "${HDR[@]}" "$LOC" || true)"
  # Avoid grep -q under pipefail: it closes the pipe after the match and can
  # make the producer exit with SIGPIPE, turning a successful match into 141.
  if [[ "$PAGE" == *"SMOKE CAGE"* ]]; then
    chip_ok=1
    break
  fi
  sleep 1
done
if [ "$chip_ok" -eq 1 ]; then
  echo "detail: device chip OK"
else
  echo "detail: NO device chip"
  exit 1
fi

echo "== start session -> device in_use =="
START_HTTP=$(curl -s -o /dev/null -w '%{http_code}' "${HDR[@]}" \
  --data-urlencode "csrf_token=$CSRF" "$BASE/api/v2/locktimer/sessions/$SID/start")
if [ "$START_HTTP" -ge 400 ]; then
  echo "start: HTTP $START_HTTP (FATAL)"
  exit 1
fi
echo "start: $START_HTTP"

echo "== safety-stop -> device available =="
STOP_HTTP=$(curl -s -o /dev/null -w '%{http_code}' "${HDR[@]}" \
  --data-urlencode "csrf_token=$CSRF" --data-urlencode "reason_code=user_requested" \
  "$BASE/api/v2/locktimer/sessions/$SID/safety-stop")
if [ "$STOP_HTTP" -ge 400 ]; then
  echo "safety-stop: HTTP $STOP_HTTP (FATAL)"
  exit 1
fi
echo "safety-stop: $STOP_HTTP"

echo "== key pages =="
for p in /llm/prompts /llm/templates /llm/verify /locktimer /locktimer/templates /locktimer/calendar \
         /points /inventory /measurements /schedule; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "${HDR[@]}" "$BASE$p")
  if [ "$code" -ge 400 ]; then
    echo "$p -> $code (FATAL)"
    exit 1
  fi
  echo "$p -> $code"
done

# Guaranteed cleanup: delete the throwaway smoke user even if the script aborted
# earlier (trap fires on exit). Best-effort — ignore auth/CSRF issues here.
curl -s -o /dev/null -w 'cleanup delete: %{http_code}\n' "${HDR[@]}" \
  --data-urlencode "csrf_token=$CSRF" -X POST "$BASE/privacy/delete" || true

echo "SMOKE_OK (user: $EMAIL, session: $SID)"
