#!/usr/bin/env bash
# validate_osm_live.sh -- prove the real OpenStreetMap graph works end to end:
# rebuild from the cached extract, inspect the served graph, run a corridor
# simulation and a comparison on the real roads.
set -u
API=http://localhost:8100
PY=/home/z/.venv/bin/python
cd /home/z/my-project/mini-services/eptask-api

setsid nohup $PY -m uvicorn main:app --host 127.0.0.1 --port 8100 > /tmp/uvicorn_8100.log 2>&1 < /dev/null &
for i in $(seq 1 40); do curl -sf --max-time 2 $API/health >/dev/null && break; sleep 0.5; done

wait_job() {
  for i in $(seq 1 200); do
    S=$(curl -sf "$API/api/jobs/$1" | $PY -c "import json,sys; print(json.load(sys.stdin)['status'])")
    case "$S" in done|error) echo "$S"; return 0;; esac
    sleep 1
  done; echo timeout
}

echo "== rebuild from cache (no refetch)"
JID=$(curl -sf -X POST $API/api/graph/osm -H 'Content-Type: application/json' \
  -d '{"prefer_osm":true,"refresh":false}' | $PY -c "import json,sys;print(json.load(sys.stdin)['job_id'])")
ST=$(wait_job "$JID"); echo "status: $ST"; [ "$ST" = done ] || exit 1
curl -sf "$API/api/jobs/$JID" | $PY -c "
import json,sys; r=json.load(sys.stdin)['result']
print('chosen:', r['chosen'], '| payload:', r['osm_payload'], '| nodes:', r['nodes'], '| edges:', r['edges'])
print('analysis:', json.dumps(r['analysis'])[:220])
print('snapped places:', {k: v['snap_m'] for k, v in r['named_snapped'].items()})
assert r['chosen']=='osm', 'cached extract must rebuild the OSM graph'
assert r['osm_payload']=='cache'
print('CACHE REBUILD OK')"

echo "== served graph"
curl -sf $API/api/graph | $PY -c "
import json,sys; g=json.load(sys.stdin)
print('source:', g['source'], '| nodes:', len(g['nodes']), '| edges:', len(g['edges']))
print('named:', g['named'])
print('routes keys:', list(g['routes']), '| sample route pts:', len(g['routes']['valley']))
assert g['source']=='OpenStreetMap'
assert len(g['nodes'])>50 and len(g['edges'])>50
print('GRAPH SERVED OK')"

echo "== corridor simulation on the real OSM roads"
JID=$(curl -sf -X POST $API/api/corridor/run -H 'Content-Type: application/json' \
  -d '{"hazard":"landslide","info_mode":"V2V+RSU","convoy":false,"trace":true}' \
  | $PY -c "import json,sys;print(json.load(sys.stdin)['job_id'])")
ST=$(wait_job "$JID"); echo "status: $ST"; [ "$ST" = done ] || { curl -s $API/api/jobs/$JID | head -c 500; exit 1; }
curl -sf "$API/api/jobs/$JID" | $PY -c "
import json,sys; j=json.load(sys.stdin); r=j['result']
print('hazard edge:', r['hazard_edge'])
print('rsus:', len(r['rsu']['xy']), 'alive:', sum(r['rsu']['alive']))
print('arrival_min:', round(r['summary']['arrival_min'],1), '| extra_min:', round(r['summary']['extra_min'],1), '| informed_min:', r['summary']['informed_min'])
print('amb points:', len(r['amb']), '| generator:', r['config']['generator'])
assert r['summary']['arrival_min']>0 and len(r['amb'])>10
print('CORRIDOR ON OSM ROADS OK')"

echo "== compare on the real OSM roads (NONE vs V2V+RSU)"
JID=$(curl -sf -X POST $API/api/corridor/compare -H 'Content-Type: application/json' \
  -d '{"modes":["NONE","V2V+RSU"],"hazard":"flood"}' \
  | $PY -c "import json,sys;print(json.load(sys.stdin)['job_id'])")
ST=$(wait_job "$JID"); echo "status: $ST"; [ "$ST" = done ] || exit 1
curl -sf "$API/api/jobs/$JID" | $PY -c "
import json,sys; j=json.load(sys.stdin); r=j['result']
a,b=r['runs'][0]['summary'],r['runs'][1]['summary']
print('arrival NONE:', round(a['arrival_min'],1), '| V2V+RSU:', round(b['arrival_min'],1), '| delta:', r['delta']['arrival_min'])
print('COMPARE ON OSM OK')"

echo "== restore schematic for the packaged default"
JID=$(curl -sf -X POST $API/api/graph/osm -H 'Content-Type: application/json' \
  -d '{"prefer_osm":false}' | $PY -c "import json,sys;print(json.load(sys.stdin)['job_id'])")
wait_job "$JID" >/dev/null
curl -sf $API/graph/source 2>/dev/null || curl -sf $API/api/graph/source | $PY -c "import json,sys; print('source:', json.load(sys.stdin)['graph_source'])"
echo "OSM LIVE VALIDATION PASSED"
