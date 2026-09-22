#!/usr/bin/env bash
# Does WhatsApp reach a handset? Run this after the recipient has joined the
# sandbox. Sends one message and reports the real delivery status.
#
#   ./scripts/wa-test.sh +919182813006
set -uo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && { set -a; source .env; set +a; }

TO=${1:-}
[ -z "$TO" ] && { echo "usage: ./scripts/wa-test.sh +91XXXXXXXXXX"; exit 1; }
: "${TWILIO_ACCOUNT_SID:?set TWILIO_ACCOUNT_SID in .env}"
: "${TWILIO_AUTH_TOKEN:?set TWILIO_AUTH_TOKEN in .env}"
FROM=${TWILIO_WHATSAPP_FROM:-+14155238886}

BODY="The Sentinel: flood early-warning test. Please ignore."
echo "  sending WhatsApp $FROM -> $TO"
R=$(curl -s -X POST "https://api.twilio.com/2010-04-01/Accounts/$TWILIO_ACCOUNT_SID/Messages.json" \
  --data-urlencode "To=whatsapp:$TO" --data-urlencode "From=whatsapp:$FROM" \
  --data-urlencode "Body=$BODY" -u "$TWILIO_ACCOUNT_SID:$TWILIO_AUTH_TOKEN")

SID=$(printf '%s' "$R" | python3 -c "import json,sys; print(json.load(sys.stdin).get('sid') or '')" 2>/dev/null)
if [ -z "$SID" ]; then
  printf '%s' "$R" | python3 -c "
import json,sys
d=json.load(sys.stdin)
c=d.get('code'); m=d.get('message','')
print(f'  rejected ({c}): {m}')
if c in (63015, 63007, 63016):
    print('')
    print('  -> that number has not joined the sandbox, or its 24h window lapsed.')
    print('     From the phone, WhatsApp the sandbox number the join code shown in')
    print('     Twilio Console > Messaging > Try it out > WhatsApp.')"
  exit 1
fi
echo "  accepted, sid=$SID  (not yet delivery)"
for i in 1 2 3 4 5; do
  sleep 4
  OUT=$(curl -s "https://api.twilio.com/2010-04-01/Accounts/$TWILIO_ACCOUNT_SID/Messages/$SID.json" \
    -u "$TWILIO_ACCOUNT_SID:$TWILIO_AUTH_TOKEN" \
    | python3 -c "
import json,sys
d=json.load(sys.stdin)
print(d.get('status','?'), d.get('error_code') or '', (d.get('error_message') or '')[:80])")
  echo "  +$((i*4))s  $OUT"
  case "$OUT" in
    delivered*|read*) echo ""; echo "  DELIVERED — WhatsApp works. Use this for the demo."; exit 0;;
    undelivered*|failed*) echo ""; echo "  NOT DELIVERED — see the error code above."; exit 1;;
  esac
done
echo "  still queued — check the phone, and confirm it joined the sandbox."
