#!/usr/bin/env bash
# validate_v2.sh -- one-shot end-to-end validation of the eptask-api v2
# upgrades against real HTTP. Services live only for the duration of this
# script (the sandbox reaps user processes between tool calls).
set -u
API=http://localhost:8100
AUTH_API=http://localhost:8101
PY=/home/z/.venv/bin/python
cd /home/z/my-project/mini-services/eptask-api

start_api() {  # $1 port, extra env before this
  setsid nohup $PY -m uvicorn main:app --host 127.0.0.1 --port "$1" > /tmp/uvicorn_$1.log 2>&1 < /dev/null &
  for i in $(seq 1 40); do
    curl -sf --max-time 2 "http://localhost:$1/health" >/dev/null && return 0
    sleep 0.5
  done
  echo "FAIL: api on :$1 did not start"; tail -5 /tmp/uvicorn_$1.log; exit 1
}

wait_job() {   # $1 jid -> prints final status
  for i in $(seq 1 200); do
    S=$(curl -sf "$API/api/jobs/$1" | $PY -c "import json,sys; j=json.load(sys.stdin); print(j['status'])")
    case "$S" in done|error) echo "$S"; return 0;; esac
    sleep 1
  done
  echo timeout
}

echo "===== 1. start backend :8100"
start_api 8100

echo "===== 2. meta block"
curl -sf $API/api/meta | $PY -c "
import json,sys; m=json.load(sys.stdin)
print('auth_required:', m['auth_required'])
print('osm mirrors:', len(m['osm']['overpass_urls']), '| cache available:', m['osm']['cache']['available'])
print('history:', m['history'])
assert m['auth_required'] is False
assert 'overpass_urls' in m['osm'] and 'jobs_stored' in m['history']
print('META OK')"

echo "===== 3. compare job (NONE vs V2V+RSU)"
JID=$(curl -sf -X POST $API/api/corridor/compare -H 'Content-Type: application/json' \
  -d '{"modes":["NONE","V2V+RSU"],"hazard":"landslide"}' | $PY -c "import json,sys;print(json.load(sys.stdin)['job_id'])")
echo "job: $JID"
ST=$(wait_job "$JID"); echo "status: $ST"; [ "$ST" = done ] || { curl -s "$API/api/jobs/$JID" | head -c 600; exit 1; }
curl -sf "$API/api/jobs/$JID" | $PY -c "
import json,sys; j=json.load(sys.stdin); r=j['result']
modes=[x['config']['info_mode'] for x in r['runs']]
a,b=r['runs'][0]['summary'],r['runs'][1]['summary']
print('modes:', modes)
print('arrival A(NONE):', round(a['arrival_min'],2), ' B(V2V+RSU):', round(b['arrival_min'],2), ' delta:', r['delta']['arrival_min'])
print('informed A:', a['informed_min'], ' B:', b['informed_min'])
print('coverage pts:', len(r['runs'][0]['coverage']), len(r['runs'][1]['coverage']), '| amb trace pts A:', len(r['runs'][0]['amb']), 'B:', len(r['runs'][1]['amb']))
assert modes==['NONE','V2V+RSU']
assert b['arrival_min'] <= a['arrival_min'], 'warnings should not slow the ambulance'
assert len(r['runs'][0]['amb'])>0
print('COMPARE OK')"

echo "===== 4. OSM rebuild, real fetch (expect honest offline fallback in sandbox)"
JID=$(curl -sf -X POST $API/api/graph/osm -H 'Content-Type: application/json' \
  -d '{"prefer_osm":true,"refresh":true}' | $PY -c "import json,sys;print(json.load(sys.stdin)['job_id'])")
ST=$(wait_job "$JID"); echo "status: $ST"; [ "$ST" = done ] || exit 1
curl -sf "$API/api/jobs/$JID" | $PY -c "
import json,sys; r=json.load(sys.stdin)['result']
print('chosen:', r['chosen'], '| fetch ok:', r['fetch']['ok'] if r.get('fetch') else None)
print('reason:', r['reason'][:220])
assert r['chosen'] in ('osm','synthetic')
if r['chosen']=='synthetic':
    assert r['fetch'] and r['fetch']['ok'] is False
else:
    assert r['fetch'] and r['fetch']['ok'] is True and r['graph_source']=='OpenStreetMap'
print('OSM REBUILD OK (network-dependent outcome, reason always reported)')"

echo "===== 5. schematic reload (prefer_osm=false)"
JID=$(curl -sf -X POST $API/api/graph/osm -H 'Content-Type: application/json' \
  -d '{"prefer_osm":false}' | $PY -c "import json,sys;print(json.load(sys.stdin)['job_id'])")
ST=$(wait_job "$JID"); [ "$ST" = done ] || exit 1
curl -sf "$API/api/jobs/$JID" | $PY -c "
import json,sys; r=json.load(sys.stdin)['result']
assert r['chosen']=='synthetic'
print('nodes:', r['nodes'], '| reason:', r['reason'][:80])
print('SCHEMATIC RELOAD OK')"
curl -sf $API/api/graph | $PY -c "import json,sys; g=json.load(sys.stdin); print('graph source now:', g['source'])"

echo "===== 6. quick corridor job -> persistence across restart"
JID=$(curl -sf -X POST $API/api/corridor/run -H 'Content-Type: application/json' \
  -d '{"hazard":"landslide","info_mode":"NONE","convoy":false,"trace":false}' \
  | $PY -c "import json,sys;print(json.load(sys.stdin)['job_id'])")
ST=$(wait_job "$JID"); [ "$ST" = done ] || exit 1
echo "job $JID done; killing backend..."
pkill -f "uvicorn main:app --host 127.0.0.1 --port 8100"; sleep 2
start_api 8100
curl -sf "$API/api/jobs/$JID" | $PY -c "
import json,sys; j=json.load(sys.stdin)
assert j['status']=='done' and j['result'], 'job must survive the restart'
print('restored job status:', j['status'], '| arrival_min present:', 'arrival_min' in j['result']['summary'])
print('PERSISTENCE ACROSS RESTART OK')"
curl -sf "$API/api/jobs" | $PY -c "
import json,sys; rows=json.load(sys.stdin)['jobs']
print('history rows:', len(rows), '| kinds:', sorted({r['kind'] for r in rows}))
assert all('result' not in row or row['result'] is None for row in rows)
print('LISTING OK')"

echo "===== 7. auth on :8101"
EPTASK_API_KEY=sekrit-42 start_api 8101
code() { curl -s -o /dev/null -w "%{http_code}" "$@"; }
echo "no key        -> $(code $AUTH_API/api/meta)   (expect 401)"
echo "wrong key     -> $(code -H 'X-API-Key: nope' $AUTH_API/api/meta)   (expect 401)"
echo "query key     -> $(code "$AUTH_API/api/meta?api_key=sekrit-42")   (expect 200)"
echo "header key    -> $(code -H 'X-API-Key: sekrit-42' $AUTH_API/api/meta)   (expect 200)"
echo "health open   -> $(code $AUTH_API/health)   (expect 200)"
echo "post w/o key  -> $(code -X POST -H 'Content-Type: application/json' -d '{"hazard":"landslide"}' $AUTH_API/api/corridor/run)   (expect 401)"
n=$(code $AUTH_API/api/meta); w=$(code -H "X-API-Key: nope" $AUTH_API/api/meta); q=$(code "$AUTH_API/api/meta?api_key=sekrit-42"); h=$(code -H "X-API-Key: sekrit-42" $AUTH_API/api/meta); hp=$(code $AUTH_API/health)
[ "$n" = 401 ] && [ "$w" = 401 ] && [ "$q" = 200 ] && [ "$h" = 200 ] && [ "$hp" = 200 ] && echo "AUTH OK" || { echo "AUTH FAILED"; exit 1; }
pkill -f "uvicorn main:app --host 127.0.0.1 --port 8101"

echo "===== ALL V2 HTTP VALIDATIONS PASSED"
