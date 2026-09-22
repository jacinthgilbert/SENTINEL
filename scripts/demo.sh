#!/usr/bin/env bash
# Reset to a known-good demo state.
set -uo pipefail
API=${API:-http://localhost:8000}
body=$(curl -fsS --max-time 10 -X POST "$API/demo/reset" 2>/dev/null) || {
  echo "  API not running — start it with: make api"; exit 1; }
python3 -c '
import json, sys
d = json.loads(sys.argv[1])
print("  ready: %s @ %sx, rain %s mm/hr" % (d["mode"], d["speed"], d["rain_mm_hr"]))
print("  alerts and reports cleared, world clock at zero")
print("  -> open http://localhost:3000 and start from Calm")
' "$body"
