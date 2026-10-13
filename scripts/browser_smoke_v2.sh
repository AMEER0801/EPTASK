#!/usr/bin/env bash
# browser_smoke_v2.sh -- full UI smoke test in one shot: the sandbox reaps
# user processes between tool calls, so services AND the browser flow live
# inside this single invocation.
set -u
cd /home/z/my-project
PY=/home/z/.venv/bin/python
API=http://localhost:8100
SHOTS=/home/z/my-project/workspace
PASS=0; FAIL=0
ok()   { echo "PASS: $1"; PASS=$((PASS+1)); }
bad()  { echo "FAIL: $1"; FAIL=$((FAIL+1)); }

# ---------- services ----------
pkill -f "uvicorn main:app" 2>/dev/null; sleep 1
pkill -9 -f "uvicorn main:app" 2>/dev/null; sleep 1
setsid nohup $PY -m uvicorn main:app --host 127.0.0.1 --port 8100 --app-dir mini-services/eptask-api \
  > /tmp/uvicorn_smoke.log 2>&1 < /dev/null &
setsid nohup env NODE_ENV=production PORT=3000 bun .next/standalone/server.js \
  > /tmp/next_smoke.log 2>&1 < /dev/null &
for i in $(seq 1 40); do curl -sf --max-time 2 $API/health >/dev/null && break; sleep 0.5; done
for i in $(seq 1 60); do curl -sf --max-time 3 http://localhost:81 >/dev/null && break; sleep 1; done
curl -sf $API/health >/dev/null && ok "backend up" || { bad "backend up"; exit 1; }
curl -sf http://localhost:81 >/dev/null && ok "gateway+frontend up" || { bad "gateway+frontend up"; exit 1; }

# ---------- browser ----------
AB="agent-browser"
$AB set viewport 1440 900 >/dev/null
$AB open http://localhost:81 >/dev/null 2>&1 && ok "page opened" || bad "page opened"
$AB wait --load networkidle >/dev/null 2>&1

# tabs present?
if $AB snapshot -i 2>/dev/null | grep -q "Compare networks"; then ok "Compare tab rendered"; else bad "Compare tab rendered"; fi
if $AB snapshot -i 2>/dev/null | grep -q "Corridor"; then ok "Corridor tab present"; else bad "Corridor tab present"; fi

# ---------- compare flow ----------
$AB find text "Compare networks" click >/dev/null 2>&1
sleep 1
if $AB snapshot -i 2>/dev/null | grep -qi "Run side-by-side comparison"; then ok "compare form rendered"; else bad "compare form rendered"; fi
$AB find text "Run side-by-side comparison" click >/dev/null 2>&1
echo "... waiting for comparison results (up to 120 s)"
$AB wait --text "Metrics · side B vs side A" --timeout 120000 >/dev/null 2>&1 \
  && ok "compare results rendered" || bad "compare results rendered"
sleep 1
if $AB snapshot -c 2>/dev/null | grep -q "Warning reach over time"; then ok "coverage chart rendered"; else bad "coverage chart rendered"; fi
MAPS=$($AB get count "figure svg" 2>/dev/null)
[ "${MAPS:-0}" -ge 2 ] && ok "two side-by-side maps rendered ($MAPS svg)" || bad "two side-by-side maps rendered ($MAPS svg)"
$AB screenshot $SHOTS/v2_compare.png >/dev/null 2>&1 && ok "screenshot compare"

# ---------- corridor + OSM flow ----------
$AB find text "Corridor · N1" click >/dev/null 2>&1
sleep 1
if $AB snapshot -c 2>/dev/null | grep -qi "road network source"; then ok "OSM source card rendered"; else bad "OSM source card rendered"; fi
$AB find text "Load real OSM roads" click >/dev/null 2>&1
echo "... waiting for OSM rebuild from cache (up to 180 s)"
$AB wait --text "OSM graph is connected and has a detour" --timeout 180000 >/dev/null 2>&1 \
  && ok "OSM graph live (reason shown)" || bad "OSM graph live (reason shown)"
echo "... waiting for the OSM graph to reach the map"
$AB wait --text "OpenStreetMap" --timeout 120000 >/dev/null 2>&1 \
  && ok "map switched to OpenStreetMap roads" || bad "map switched to OpenStreetMap roads"
sleep 2
$AB screenshot $SHOTS/v2_osm_corridor.png >/dev/null 2>&1 && ok "screenshot osm corridor"

# run a live corridor simulation on the real OSM roads
$AB find text "Run simulation" click >/dev/null 2>&1
echo "... running corridor simulation on OSM roads"
$AB wait --text "Ambulance arrival" --timeout 180000 >/dev/null 2>&1 \
  && ok "corridor simulation on OSM roads completed" || bad "corridor simulation on OSM roads completed"
sleep 2
$AB screenshot $SHOTS/v2_osm_run.png >/dev/null 2>&1 && ok "screenshot osm run"

# console + errors
ERRS=$($AB errors 2>/dev/null | grep -c -i -E "error|uncaught" || true)
CONSOLE=$($AB console 2>/dev/null | grep -c -i -E "\[error\]" || true)
[ "${ERRS:-0}" -eq 0 ] && ok "no page errors" || bad "no page errors ($ERRS)"
[ "${CONSOLE:-0}" -eq 0 ] && ok "no console errors" || bad "no console errors ($CONSOLE)"
$AB close >/dev/null 2>&1

echo "=============================="
echo "SMOKE RESULT: $PASS passed, $FAIL failed"
exit $([ "$FAIL" -eq 0 ] && echo 0 || echo 1)
