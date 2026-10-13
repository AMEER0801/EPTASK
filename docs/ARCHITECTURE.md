# Architecture & Integration Map

## 1. Sources and what was taken from each

### demo.zip → the interface
| Taken | Where it lives now | Changes |
|---|---|---|
| Three.js situation map (terrain, routes, river, vehicles, RSUs, playback, labels) | `src/components/eptask/CorridorMap.tsx` | Ported rendering math verbatim; restyled to restrained operational palette; bloom/aurora/stars/debris animations removed; OrbitControls via npm `three` |
| Trace playback interpolators (`prep`, `ambAt`, `trackAt`) | same file | Now consume **live API traces** with the identical schema |
| Convoy definition, hazard presets, dispatch assumptions | `app/corridor_svc.py` | Preserved verbatim (with their ASSUMPTION comments) |
| `tools/make_traces.py` recorder technique | `app/corridor_svc.py` | Same anchored hook + same post-run equality proof, now enforced on every live request |
| Story steps / narration / self-test window / log dock | dropped | Replaced by purpose-built consoles; observability moved to server logs + honest error states |

### Notebook.zip → the backend
| Taken | Where it lives now | Changes |
|---|---|---|
| 16 eptask modules (v7.1) | `mini-services/eptask-api/core/` | **Byte-for-byte unmodified**; imported by the service |
| `corridor_graph.json`, `results_v71.json`, `latency_samples.json`, `coolr_points.json`, ONNX exports (+sidecars), figures | `mini-services/eptask-api/assets/demo_bundle/` | Copied as-is |
| `cell_trace` pipeline from `make_traces.py` | `app/cell_svc.py` | Generalised: any model/version/V/seed/event/floor; same per-tick record schema |
| C3 paired protocol from `contributions.c3_paired` | `app/outage_svc.py` | Same pairing math + `runlog.mean_ci`; no figure output (frontend charts it) |
| v6.1/v5.1 notebooks, v7.2 real-data attempts | **integrated in v2** | v7.2's goal — real OSM roads — is fulfilled by `app/osm_svc.py` calling the ORIGINAL `corridor.build_corridor()` (see below) |
| v7.2 OSM/COOLR fetching intent | `app/osm_svc.py` | Overpass fetch (4 mirrors, 30 s timeouts) → disk cache → `build_corridor` with its own connectivity/detour checks; COOLR stays bundled (Earthdata login required for live data) |

## 1b. What v2 added (module map)

```
mini-services/eptask-api/
  app/jobstore.py    SQLite persistent job history (newest 500, zlib results)
  app/jobs.py        hot in-memory cache + write-through to jobstore; restart-safe
  app/auth.py        optional API-key gate (EPTASK_API_KEY, X-API-Key / ?api_key=)
  app/osm_svc.py     Overpass fetch + cache + corridor.build_corridor() wiring
  app/routes.py      /api/graph/osm · /api/graph/source · /api/corridor/compare
                     + browser-safe graph payload (major roads + 1.2 km corridor)
  app/schemas.py     OsmBuild · CompareRun validation
  core/corridor.py   UNMODIFIED — build_corridor/graph_from_osm were already here
```

Frontend v2: `ComparePanel.tsx` (hazard preset editor + side-by-side runs),
`WarningMap.tsx` (2D SVG run map: graph, hazard, RSUs, ambulance split at
first warning), OSM source card in `CorridorPanel.tsx`, API-key gate in
`page.tsx`, and a dual-mode client (`client.ts`: sandbox gateway via
XTransformPort, or direct `NEXT_PUBLIC_API_URL` for laptops).

## 2. Request flow (primary workflow)

```
Corridor launcher (form)
  → POST /api/corridor/run {hazard, mode, params}
      jobs.submit → thread pool → run_corridor()
        hooked_run_trial(CO)            # patched-source recorder
        CO.run_trial(...) ×7            # ambulance + 5 convoy + verification rerun
        equality check recorded vs unrecorded   # refuse on mismatch
  → poll /api/jobs/{id} (progress per member)
  → result: trace + summary + fleet
      → CorridorMap renders (vehicles instanced, ambulance, trail, RSUs, hazard)
      → metrics cards, convoy table, coverage chart
```

The cell and outage consoles follow the same pattern with their own services.

## 3. Design decisions

1. **Python service, not notebook execution.** The notebook's outputs are
   reproduced by importing its modules — not by running cells. The notebook
   itself remains the reference implementation.
2. **ONNX runtime for policies.** The shipped exports are what the demo used;
   the notebook verified 0/500 decision disagreements vs torch. Torch remains a
   dependency because the original modules import it.
3. **Determinism as a contract.** Same (seed, parameters) → identical outputs,
   which is what makes the consistency tests possible and meaningful.
4. **Async jobs with real progress.** Long simulations run on a bounded worker
   pool; progress comes from the simulation itself (per member/tick/rollout).
5. **Static artifacts stay static and labeled.** `results_v71.json` sections and
   figures are served as recorded references — the UI marks them "reference",
   never as live results.
6. **The notebook judges the OSM graph, not us.** v2 fetches and caches real
   roads but hands the decision to `corridor.build_corridor()`: OSM is kept
   only when connected with a detour, and the reason is always surfaced.
7. **Auth optional but real.** Environment-keyed, constant-time, per-request;
   transparent when unset — proportionate to a research console.
8. **History persists by default.** SQLite (stdlib, zero new deps),
   compressed results, bounded table; the in-memory LRU remains the hot path.

## 4. Frontend structure

```
src/app/page.tsx                  shell: header (health, run id, auth badge), tabs, footer, API-key gate
src/components/eptask/
  OverviewPanel.tsx               provenance, health polling, model registry, live-vs-static map
  CorridorPanel.tsx               N1 launcher + metrics + convoy table + coverage chart + OSM source card
  CorridorMap.tsx                 three.js map (own rAF loop, imperative handle: seek/getTime)
  ComparePanel.tsx                v2: hazard preset editor + side-by-side comparison + delta table
  WarningMap.tsx                  v2: 2D SVG run map (graph, hazard, RSUs, ambulance trajectory)
  CellPanel.tsx                   VEC cell launcher + road strip (canvas) + timeline + decision inspector
  OutagePanel.tsx                 paired study launcher + CI table + bar chart + recorded comparison
  ReferencePanel.tsx              recorded artifacts browser + figure gallery
  AboutPanel.tsx                  architecture summary served with the product
src/lib/eptask/{client,types}.ts  dual-mode client (gateway or direct), API key, polling, typed models
```

No client state library is needed: each console owns its run lifecycle
(form → job → result), which mirrors the stateless backend.
