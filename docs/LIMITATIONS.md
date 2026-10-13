# Limitations & remaining requirements (v2)

v1 documented four known gaps; v2 closes three of them (real roads,
persistence, auth) and is honest about what remains.

## Live vs static vs assumed

| Element | Status |
|---|---|
| Corridor trials (12 presets + any custom config) | **live** — `corridor.run_trial` per request |
| Convoy behaviour | **live** (one trial per member; no inter-member interaction — notebook's own convention) |
| VEC cell rollouts + decision explanations | **live** — `env.VECEnv` + shipped ONNX actors |
| C3 paired outage studies | **live** — `policies.rollout` with the notebook's pairing |
| Side-by-side warning-network comparison | **live** — two `run_trial` executions per request |
| Real OpenStreetMap road graph | **live when network allows** — Overpass fetch (4 mirrors) → disk cache → `corridor.build_corridor()`; a 17 MB extract of the corridor ships bundled so the OSM mode works offline too |
| Micro-latency samples feeding corridor service delays | **static arm** — recorded `latency_samples.json` ("floor ON"/"floor OFF"); recomputing live would double run time for identical numbers (they are themselves notebook outputs) |
| `results_v71.json` tables & figures | **static reference**, labeled as such in the UI |
| NASA COOLR landslide points | **bundled sample** — live COOLR needs an Earthdata login a laptop deployment does not have |
| Hazard presets (footprint/traffic), dispatch times, vehicle mix, road speeds | **assumptions inherited from the sources**, declared in code and UI |

## Known gaps (v2, after the v2 upgrades)

1. **Real roads depend on the network.** Where every Overpass mirror is
   unreachable, the service keeps the schematic graph and reports the exact
   fetch errors; the bundled extract and the disk cache cover offline use
   after the first successful fetch. On real road networks some blockage
   candidates genuinely have **no detour** (the notebook's own
   `frac_with_detour` can be ≪ 1) — in those scenarios warnings cannot
   shorten the trip, and the compare panel will honestly show Δ = 0.
2. **Torch checkpoints vs ONNX.** Outage/cell runs evaluate the exported ONNX
   actors (v10/v30/v50), not the `.pt` files. The notebook measured 0/500
   decision disagreements; loading `meppo_{A,B}_static/dr.pt` would require
   the full training-time module graph and buys no behavioural difference.
3. **Persistence is single-file SQLite.** `data/jobs.db` keeps the newest 500
   jobs with zlib-compressed results — history survives restarts, but there
   is no multi-user access control on the history and no migration tooling.
   Delete the file to reset history.
4. **Auth is a single shared key.** Constant-time compared, read from the
   environment per request, `X-API-Key` header or `?api_key=` for images,
   `/health` stays open. This is proportionate for a research console; it is
   not a multi-user identity system, rate limiter, or audit log.
5. **Performance envelope (measured).** Schematic corridor run with convoy
   ≈ 8–14 s; **on real OSM roads the same convoy run takes ≈ 40–70 s**
   (routing trees over ≈ 160 k nodes per trial) and the first OSM rebuild
   ≈ 15–30 s from cache (plus 10–60 s network time for a fresh fetch, and
   ≈ 2–3 GB peak RAM during the graph build). Cell 520 ticks ≈ 0.6–2 s;
   paired outage ≈ 6–10 s. Two simulations run concurrently; further
   requests queue with live progress.
6. **Browser payload on OSM graphs.** `/api/graph` filters the extract to
   major roads plus ≈1.2 km around the open path (≈ 27 k edges for this
   corridor); the compare maps additionally cap minor-road rendering for
   smoothness. The full extract is never shipped to the client.
7. **Browser support verified** in headless Chromium (WebGL2) and standard
   desktop Chrome paths; Safari/Firefox untested. Without WebGL the consoles
   remain usable (tables/charts/forms), the 3D map shows a fallback notice.
8. **The demo's self-test/story mode was not ported** — it validated the
   *recorded* replay, which live runs replace; server-side consistency tests
   supersede it.
