#!/usr/bin/env bash
# Does SMS actually reach an Indian handset? Find out now, not on stage.
#
#   ./scripts/sms-test.sh +919876543210
#
# Sends ONE message, waits, then reports the DELIVERY status from Twilio.
# "accepted" means nothing. "delivered" means a phone got it.
set -uo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && { set -a; source .env; set +a; }

TO=${1:-}
[ -z "$TO" ] && { echo "usage: ./scripts/sms-test.sh +91XXXXXXXXXX"; exit 1; }
: "${TWILIO_ACCOUNT_SID:?set TWILIO_ACCOUNT_SID in .env}"
: "${TWILIO_AUTH_TOKEN:?set TWILIO_AUTH_TOKEN in .env}"
: "${TWILIO_FROM:?set TWILIO_FROM in .env}"

# Twilio TRIAL accounts reject free-form text: "Invalid template name. Trial
# accounts can only use predefined SMS templates." So the default probe uses an
# allowed template. That still answers the question that matters first — can a
# message reach this handset AT ALL — separately from whether arbitrary text can.
#   make sms-test TO=+91...            -> template probe (works on trial)
#   make sms-test TO=+91... FREE=1     -> free-form (needs an upgraded account)
if [ "${FREE:-0}" = "1" ]; then
  BODY="The Sentinel: flood warning system test. Please ignore."
else
  BODY="Your Sentinel code is 4821"
fi
echo "  sending to $TO ..."
SID=$(curl -s -X POST "https://api.twilio.com/2010-04-01/Accounts/$TWILIO_ACCOUNT_SID/Messages.json" \
  --data-urlencode "To=$TO" --data-urlencode "From=$TWILIO_FROM" --data-urlencode "Body=$BODY" \
  -u "$TWILIO_ACCOUNT_SID:$TWILIO_AUTH_TOKEN" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('sid') or 'ERR:'+str(d.get('message')))")

case "$SID" in ERR:*) echo "  send rejected: ${SID#ERR:}"; exit 1;; esac
echo "  accepted, sid=$SID   (this is NOT delivery)"

for i in 1 2 3 4 5 6; do
  sleep 5
  OUT=$(curl -s "https://api.twilio.com/2010-04-01/Accounts/$TWILIO_ACCOUNT_SID/Messages/$SID.json" \
    -u "$TWILIO_ACCOUNT_SID:$TWILIO_AUTH_TOKEN" \
    | python3 -c "
import json,sys
d=json.load(sys.stdin)
print(d.get('status','?'), d.get('error_code') or '', (d.get('error_message') or '')[:90])")
  echo "  +$((i*5))s  status: $OUT"
  case "$OUT" in delivered*) echo ""; echo \
    "  DELIVERED — SMS works to this number. You can demo with it."; exit 0;;
    undelivered*|failed*) echo ""
      echo "  NOT DELIVERED. If the error is 30034/30032/30007 this is the India"
      echo "  DLT block: accepted by Twilio, dropped by the carrier. No retry fixes"
      echo "  it. Use a DLT-registered Indian aggregator, or demo on the simulated"
      echo "  handset and say so plainly."; exit 1;;
  esac
done
echo ""
echo "  still queued after 30s — usually means it will not arrive. Re-check with:"
echo "  curl -s https://api.twilio.com/2010-04-01/Accounts/\$TWILIO_ACCOUNT_SID/Messages/$SID.json -u \$TWILIO_ACCOUNT_SID:\$TWILIO_AUTH_TOKEN"
