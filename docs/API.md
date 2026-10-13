# eptask-api — endpoint reference (v2)

Base URL: `http://<host>:8100` (behind the sandbox gateway: `/api/...?XTransformPort=8100`).
All responses include `X-Process-Time` and `X-Request-Id` headers. Errors are
JSON; validation failures return 422 with per-field messages.

## Authentication (v2)

Unset by default. When the server is started with `EPTASK_API_KEY` set, every
`/api/*` request must carry the key — `X-API-Key: <key>` header or
`?api_key=<key>` query parameter (the latter exists for `<img>` sources).
`/health`, `/docs` and `/openapi.json` stay open. Wrong or missing key →
`401 {"detail": "missing or invalid API key…", "request_id": …}` with a
constant-time comparison. `/api/meta` reports `auth_required` so clients can
detect the mode.

## Health & metadata

### `GET /health`
Service readiness. `status: ok | degraded`, loaded graph size, latency arms,
cached ONNX policies, uptime.

### `GET /api/meta`
Run provenance (run id, mode, budgets, seeds), corridor-graph analysis, hazard
presets, convoy definition, notebook checks (incl. ONNX-vs-torch disagreements),
figure list.

### `GET /api/graph`
The corridor graph in the demo's rendering format: nodes `[id, x, y, name]`,
edges `[u, v, route]`, named places, open path/valley/hill routes, bbox, COOLR
points, hazard candidates. On real OpenStreetMap graphs the payload is
filtered to major roads plus everything within ≈1.2 km of the open path, so
the browser payload stays small.

### `GET /api/graph/source` (v2)
Which road graph is live and why: Overpass mirrors, cache state
(available / fetched_at / elements / size), current `graph_source`, and the
latest graph analysis (open km/min, candidate count, detour fraction).

### `POST /api/graph/osm` (v2, async job)
```json
{ "prefer_osm": true, "refresh": false }
```
Rebuilds the road network. `refresh: true` re-fetches from the Overpass API
(4 public mirrors, 30 s timeout each); otherwise a cached extract is used
when present. The extract is handed to the ORIGINAL `corridor.build_corridor`,
which keeps the OSM graph only if it is connected **and** a detour exists,
otherwise falls back to the synthetic schematic. The job result reports
`chosen: "osm" | "synthetic"`, the full `reason`, fetch statistics,
node/edge counts, analysis summary and the place-snapping distances
(`named_snapped`, metres). The service graph is swapped atomically; in-flight
runs are unaffected.

### `POST /api/corridor/compare` (v2, async job)
```json
{ "modes": ["NONE", "V2V+RSU"], "hazard": "landslide",
  "footprint_m": null, "traffic_vph": null, "hazard_seed": 7,
  "dispatch_s": 600, "seed": null, "latency_arm": "floor ON",
  "trace": true, "frame_dt": 60 }
```
Side-by-side warning-network comparison: exactly two information modes, one
hazard scenario, everything else identical (same hazard draw, traffic seed,
RSU layout). Convoy is intentionally off. Result: `runs[2]` (each a full
corridor result incl. geometry + ambulance trace), `delta` = per-metric
B − A (null for non-numeric), and the shared config. ~4–8 s.

## Jobs & history (v2)

- `GET /api/jobs` — newest 100 rows merged from the hot cache and the SQLite
  store; never includes result payloads.
- `GET /api/jobs/{id}` — full job record; finished jobs are served from the
  SQLite store (`EPTASK_DB`, default `data/jobs.db`), so history — including
  complete results — **survives restarts**.
- The store keeps the newest 500 jobs; results are stored zlib-compressed.

## Simulations (async jobs)

All three run endpoints return `{ "job_id", "poll" }` immediately. Poll
`GET /api/jobs/{job_id}` until `status` is `done` or `error`; `progress`
(0..1) and `stage` report real simulation progress. `GET /api/jobs` lists the
last 40 jobs for the session.

### `POST /api/corridor/run` — road-scale N1 trials
```json
{ "hazard": "landslide|earthquake|flood|custom",
  "info_mode": "NONE|V2V|RSU|V2V+RSU",
  "footprint_m": 2000, "traffic_vph": 30,
  "hazard_seed": 7, "candidate_index": null,
  "dispatch_s": 600, "seed": null,
  "latency_arm": "floor ON|floor OFF", "convoy": true, "trace": true, "frame_dt": 60 }
```
Executes `corridor.run_trial` once per convoy member (same blockage, traffic
seed, RSUs) plus one unrecorded verification rerun. Result: summary metrics
(arrival/oracle/extra/informed, missed junction, trapped, RSU alive, coverage),
`frame_t`, civilian `veh` tracks `[vid, f0, inf, stuck, flags, x0, y0, ...]`,
`amb` rows `[t, x/10, y/10, inf, reroute, passed, seen, missed, stuck, done]`,
per-member fleet table and per-RSU status. ~6-14 s with convoy.

### `POST /api/cell/run` — VEC cell policy run
```json
{ "policy": "A|B", "version": 10, "V": 30, "seed": 21, "ticks": 520,
  "event": { "at": 60, "k": 3, "dur": 360 },
  "floor": true, "explain": true }
```
Runs `env.VECEnv` in disaster mode driven by the selected ONNX actor. Per tick:
vehicle positions, RSU alive flags, request metadata (role, deadline class, CWP
tier, people estimate, modality, edge reachability), policy probabilities,
chosen vs realised targets, queue levels, exact `env.peek` counterfactuals,
reported T and deadline, settled true T + on-time flag. Summary aggregates
(all / outage window / emergency / protected; target shares). ~0.5-2 s.

### `POST /api/outage/run` — paired C3 study
```json
{ "policies": ["A", "B", "alive_aware", "local"], "V": 30, "k_list": [1, 2, 4],
  "seeds": [0, 1, 2], "fail_at": 600, "fail_dur": 300, "post": 200 }
```
For every (k, policy, seed): one `policies.rollout` run with the outage and one
identical control run; excess = paired difference of mean reported T. Returns
per-row mean +/- 95% CI (over seeds) for during/post windows and raw per-seed
values. Runtime ~ 2 x rollouts x ~0.9 s.

## Reference artifacts (static, recorded by the notebook)

### `GET /api/reference/{section}`
`run | budget | checks | corridor_graph | data | training | c1 | c2 | c3 | n1 |
n2 | latency | corridor | onnx | cfg | figures` from `results_v71.json`,
explicitly labeled as recorded (not recomputed).

### `GET /api/figures/{name}.png`
The notebook's figure files (basename-validated path).

## Operational notes

- Job pool: 2 workers; jobs are rejected only by validation, never queued away.
- Input bounds: V <= 60, ticks <= 3000, seeds <= 6, k_list <= 4 values in 1..6,
  footprint 500..30000 m, traffic 5..120 veh/h, dispatch 60..3600 s.
- No user input reaches a filesystem path; figures/references are allow-listed.
- Job history persists in SQLite (`EPTASK_DB`, newest 500 jobs, results
  zlib-compressed); an in-memory LRU (40) stays the hot cache.
- The Overpass fetch runs inside the normal job pool and blocks one worker
  for up to ~2 minutes on a slow network; the cached extract makes offline
  rebuilds possible.
