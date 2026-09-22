#!/usr/bin/env bash
# Telegram: discover everyone who has messaged the bot, then message them.
#   ./scripts/tg-test.sh            -> list opted-in chats
#   ./scripts/tg-test.sh send       -> send a test to all of them
set -uo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && { set -a; source .env; set +a; }
: "${TELEGRAM_BOT_TOKEN:?set TELEGRAM_BOT_TOKEN in .env — get one from @BotFather}"

API="https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN"
BOT=$(curl -s "$API/getMe" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print('@'+d['result']['username'] if d.get('ok') else 'INVALID TOKEN')")
echo "  bot: $BOT"
[ "$BOT" = "INVALID TOKEN" ] && exit 1

echo "  people who have messaged the bot (= opted in):"
curl -s "$API/getUpdates" | python3 -c "
import json,sys
d=json.load(sys.stdin)
seen={}
for u in d.get('result',[]):
    m=u.get('message') or u.get('edited_message') or {}
    c=m.get('chat') or {}
    if c.get('id'): seen[c['id']]=c
if not seen:
    print('    (none yet — open '+ '$BOT' +' in Telegram and press Start)')
for cid,c in seen.items():
    name=' '.join(x for x in (c.get('first_name'),c.get('last_name')) if x)
    print(f\"    {cid}  {name or c.get('username')}\")
"
[ "${1:-}" != "send" ] && { echo ""; echo "  to send a test:  ./scripts/tg-test.sh send"; exit 0; }

echo ""
echo "  sending test message to each..."
curl -s "$API/getUpdates" | python3 -c "
import json,sys,urllib.request,urllib.parse
d=json.load(sys.stdin)
ids={ (u.get('message') or u.get('edited_message') or {}).get('chat',{}).get('id')
      for u in d.get('result',[]) }
ids.discard(None)
for cid in ids:
    body=urllib.parse.urlencode({'chat_id':cid,
        'text':'The Sentinel: flood early-warning test. Please ignore.'}).encode()
    try:
        r=json.load(urllib.request.urlopen('$API/sendMessage', body, timeout=20))
        print(f\"    {cid}: {'DELIVERED' if r.get('ok') else r.get('description')}\")
    except Exception as e:
        print(f'    {cid}: FAILED {e}')
"
