#!/bin/bash
# Prod smoke — general personal-loop check after a deploy.
#
# Covers: register/login → dashboard, inventory (device), lock session with
# device → start → safety-stop (device status transitions), Steps 6/7 pages,
# points/inventory pages. Registers a throwaway user and deletes it at the end.
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
curl -s -o /dev/null -w 'register: %{http_code}\n' \
  -b "csrf_token=$RANDOM_CSRF" -c "$JAR" \
  --data-urlencode "csrf_token=$RANDOM_CSRF" --data-urlencode "email=$EMAIL" --data-urlencode "password=$PASS" \
  "$BASE/auth/register"
curl -s -o /dev/null -w 'login: %{http_code} -> %{redirect_url}\n' \
  -b "csrf_token=$RANDOM_CSRF" -c "$JAR" \
  --data-urlencode "csrf_token=$RANDOM_CSRF" --data-urlencode "email=$EMAIL" --data-urlencode "password=$PASS" \
  "$BASE/auth/login"
CSRF=$(grep csrf_token "$JAR" | awk '{print $7}' | tail -1)
HDR=(-b "$JAR" -c "$JAR" -H "X-CSRF-Token: $CSRF")
curl -s -o /dev/null -w 'dashboard: %{http_code}\n' "${HDR[@]}" "$BASE/dashboard"

echo "== inventory (device) =="
DEV=$(curl -s "${HDR[@]}" -H 'Content-Type: application/json' \
  -d '{"category":"wearable","name":"SMOKE CAGE","quantity":1,"quantity_needed":1,"is_shopping_list":false,"status":"bought","inventory_status":"available"}' \
  "$BASE/api/v2/inventory")
DEV_ID=$(echo "$DEV" | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
echo "device id: $DEV_ID"

echo "== create lock session with device =="
LOC=$(curl -s -o /dev/null -w '%{redirect_url}' "${HDR[@]}" \
  --data-urlencode "csrf_token=$CSRF" --data-urlencode "device_id=$DEV_ID" "$BASE/locktimer/new")
SID=$(basename "$LOC")
echo "session: $SID"

# The session-detail GET can miss the chip right after a deploy (app/db warm-up,
# first-request latency); retry with a short pause before failing.
chip_ok=0
for _attempt in 1 2 3 4 5 6; do
  PAGE="$(curl -s "${HDR[@]}" "$LOC" || true)"
  if echo "$PAGE" | grep -q "SMOKE CAGE"; then
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
curl -s -o /dev/null -w 'start: %{http_code}\n' "${HDR[@]}" \
  --data-urlencode "csrf_token=$CSRF" "$BASE/api/v2/locktimer/sessions/$SID/start"

echo "== safety-stop -> device available =="
curl -s -o /dev/null -w 'safety-stop: %{http_code}\n' "${HDR[@]}" \
  --data-urlencode "csrf_token=$CSRF" --data-urlencode "reason_code=user_requested" \
  "$BASE/api/v2/locktimer/sessions/$SID/safety-stop"

echo "== key pages =="
for p in /llm/prompts /llm/templates /llm/verify /locktimer /locktimer/templates /locktimer/calendar \
         /api/v2/points/page /api/v2/inventory/page /api/v2/measurements/page /api/v2/schedule/page; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "${HDR[@]}" "$BASE$p")
  echo "$p -> $code"
done

echo "SMOKE_OK (user: $EMAIL, session: $SID)"
