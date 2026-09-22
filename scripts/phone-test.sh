#!/usr/bin/env bash
# Android SMS gateway: is the phone reachable, and can it send?
#   ./scripts/phone-test.sh                 -> reachability only
#   ./scripts/phone-test.sh +919182813006   -> send a real test SMS
set -uo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && { set -a; source .env; set +a; }
: "${ANDROID_SMS_URL:?set ANDROID_SMS_URL in .env, e.g. http://192.168.1.5:8080}"
AUTH=()
[ -n "${ANDROID_SMS_USER:-}" ] && AUTH=(-u "$ANDROID_SMS_USER:${ANDROID_SMS_PASS:-}")

echo "  gateway: $ANDROID_SMS_URL"
CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 6 "${AUTH[@]}" "$ANDROID_SMS_URL/health" 2>/dev/null)
[ "$CODE" = "000" ] && CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 6 "${AUTH[@]}" "$ANDROID_SMS_URL/message" 2>/dev/null)
if [ "$CODE" = "000" ]; then
  echo "  UNREACHABLE"
  echo ""
  echo "  Most likely the network, not the app:"
  echo "   · are both devices on the same wifi?"
  echo "   · venue/campus wifi usually blocks device-to-device traffic —"
  echo "     turn on the phone's hotspot and connect this Mac to it"
  echo "   · is the app's local server actually started?"
  exit 1
fi
echo "  reachable (HTTP $CODE)"

TO=${1:-}
[ -z "$TO" ] && { echo ""; echo "  to send a real SMS:  ./scripts/phone-test.sh +91XXXXXXXXXX"; exit 0; }

echo "  sending to $TO via the phone's SIM ..."
curl -s --max-time 25 "${AUTH[@]}" -H 'Content-Type: application/json' \
  -X POST "$ANDROID_SMS_URL/message" \
  -d "{\"message\":\"The Sentinel: flood early-warning test. Please ignore.\",\"phoneNumbers\":[\"$TO\"]}" \
  | python3 -c "
import json,sys
raw=sys.stdin.read()
try:
    d=json.loads(raw)
    print(f\"  accepted: id={d.get('id')} state={d.get('state')}\")
    print('  -> check the handset. This goes out on your own SIM.')
except Exception:
    print('  response:', raw[:200])"
