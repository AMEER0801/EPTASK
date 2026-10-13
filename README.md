# EPtask Ops Console

A real, runnable operations console that merges the EPtask V7.1 research
notebook (MEPPO task-offloading for emergency-response networks in the
Trishuli corridor) with the original 3D demo's visual language. Every number,
map and trace is computed **live** by the notebook's own code — no replays,
no mock data.

**New in v2**

- 🗺️ **Real OpenStreetMap roads** — fetch → cache → `corridor.build_corridor()`,
  with the notebook's own connectivity/detour checks and an honest fallback.
- ⚖️ **Compare networks** — hazard preset editor + two warning-network modes
  side by side (maps, informed-share curves, per-metric deltas).
- 💾 **Persistent job history** — SQLite-backed; runs (including full results)
  survive restarts.
- 🔑 **Optional API-key auth** — `EPTASK_API_KEY` locks the HTTP surface;
  the console ships a key gate.

## Run it on your laptop

See **[SETUP_GUIDE.md](SETUP_GUIDE.md)** for the full walkthrough. Short
version:

```bash
# terminal 1 -- simulation service
cd mini-services/eptask-api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
bash run.sh                      # http://localhost:8100

# terminal 2 -- console
npm install
npm run build && npm run start   # http://localhost:3000
```

## Layout

| Path | What it is |
|---|---|
| `src/` | Next.js 16 console (Overview, Corridor 3D map, Compare, VEC cell, Outage, Reference, About) |
| `mini-services/eptask-api/app/` | FastAPI services: corridor/cell/outage runs, jobs + SQLite history, auth, OSM integration |
| `mini-services/eptask-api/core/` | the ORIGINAL eptask notebook modules — imported unmodified |
| `mini-services/eptask-api/assets/` | demo bundle: reference results, ONNX policy exports, latency samples, corridor graph, bundled OSM extract |
| `mini-services/eptask-api/tests/` | 55 pytest cases incl. byte-identical reproduction of the notebook's recorded traces |
| `docs/` | API.md · ARCHITECTURE.md · LIMITATIONS.md |

## Documentation

- `SETUP_GUIDE.md` — laptop installation, configuration, troubleshooting
- `docs/API.md` — every endpoint, auth behaviour, examples
- `docs/ARCHITECTURE.md` — how notebook code becomes a service
- `docs/LIMITATIONS.md` — what is live, what is static, what is assumed
