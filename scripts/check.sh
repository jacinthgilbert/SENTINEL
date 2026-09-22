#!/usr/bin/env bash
# Pre-demo smoke test. Run this before you walk on stage, not after.
set -uo pipefail
API=${API:-http://localhost:8000}
WEB=${WEB:-http://localhost:3000}
pass=0; fail=0

chk () {  # chk <label> <url> [jq-ish python expr on the parsed body]
  local label=$1 url=$2 expr=${3:-}
  local body code
  body=$(curl -fsS --max-time 12 "$url" 2>/dev/null); code=$?
  if [ $code -ne 0 ]; then printf "  \033[31mFAIL\033[0m %-34s unreachable\n" "$label"; fail=$((fail+1)); return; fi
  if [ -n "$expr" ]; then
    local out
    out=$(printf '%s' "$body" | python3 -c "
import json,sys
d=json.load(sys.stdin)
try: print($expr)
except Exception as e: print('ERR',e)
" 2>/dev/null)
    case "$out" in ERR*|"") printf "  \033[31mFAIL\033[0m %-34s %s\n" "$label" "$out"; fail=$((fail+1)); return;; esac
    printf "  \033[32m ok \033[0m %-34s %s\n" "$label" "$out"
  else
    printf "  \033[32m ok \033[0m %-34s\n" "$label"
  fi
  pass=$((pass+1))
}

echo ""
echo "The Sentinel — pre-demo check"
echo ""
chk "api health"          "$API/health"                       "d['status']"
chk "world state"         "$API/state"                        "f\"tick {d['tick']} {d['mode']}\""
chk "sim console"         "$API/sim"                          "f\"{d['speed']}x rain {d['rain_mm_hr']}\""
chk "inundation"          "$API/inundation?stage_m=1.0"       "f\"{d['properties']['flooded_km2']} km2\""
chk "zones"               "$API/zones"                        "f\"{len(d['features'])} zones\""
chk "facilities"          "$API/facilities"                   "f\"{len(d['features'])} sites\""
chk "risk"                "$API/risk?zones=false"             "f\"{sum(d['summary']['by_severity'].values())} zones rated\""
chk "nowcast"             "$API/nowcast"                      "('ready' if d.get('ready') else 'WARMING')"
chk "nowcast skill"       "$API/nowcast/skill"                "f\"+60m skill {d['metrics']['60']['skill_vs_persistence']:.0%}\""
chk "routing coverage"    "$API/routes/coverage"              "f\"{d['reachable_dry']}/{d['nodes_total']} reachable\""
chk "priority routes"     "$API/routes/priority?limit=3"      "f\"{d['count']} routed\""
chk "alerts"              "$API/alerts"                       "f\"{d['count']} issued, {len(d['languages'])} languages\""
chk "reports"             "$API/reports"                      "f\"{d['total']} filed\""
chk "dispatch"            "$API/dispatch?limit=3"             "f\"{d['teams_assigned']} teams\""
chk "situation"           "$API/situation"                    "f\"gauge {d['world']['gauge_cm']} cm\""
chk "hazards"             "$API/hazards"                      "f\"{len(d['implemented'])} implemented, {len(d['declared'])} declared\""
chk "web citizen view"    "$WEB"
chk "web authority view"  "$WEB/authority"

echo ""
if [ $fail -eq 0 ]; then
  printf "  \033[32mall %d checks passed\033[0m\n\n" "$pass"
else
  printf "  \033[31m%d FAILED\033[0m, %d passed\n\n" "$fail" "$pass"
  exit 1
fi
