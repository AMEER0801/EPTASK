# RUN REPORT — EPtask / MEPPO V7.1 notebook, FULL mode

## (1) Verdict

**COMPLETE WITH WARNINGS** — every cell of the notebook executed (32/32 code cells, zero error outputs, nbconvert exit code 0, every in-notebook assert passed); the only warnings are (a) both live-data fetches failed (the notebook fell back to its labelled SYNTHETIC/UNIFORM corridor, which it is designed to do offline) and (b) the notebook's own FULL budget (ep_A=1000, ep_B=1200) does not match the 400/600 figures quoted in the delivery instructions (no edit was made — the notebook as shipped defines FULL this way; see W2).

## (2) DATA MODE (verbatim, Section 3, cell 40)

```
DATA MODE: roads=SYNTHETIC | hazard prior=UNIFORM
```

This is the fallback branch, not OSM-live/COOLR-live and not cache. Fetch error lines, verbatim:

```
  osm   : status=failed, source=OpenStreetMap
          errors: ["https://overpass-api.de/api/interpreter attempt 1: URLError(OSError(101, 'Network is unreachable'))", "https://overpass-api.de/api/interpreter attempt 2: URLError(OSError(101, 'Network is unreachable'))"]
  coolr : status=failed, source=NASA COOLR
          errors: ["attempt 1: <HTTPError 404: 'Not Found'>", "attempt 2: <HTTPError 404: 'Not Found'>"]
```

Corridor description, verbatim:

```
corridor graph : synthetic -- synthetic (schematic geometry, published route lengths)
why            : no OSM data (offline, blocked, or fetch disabled)
size           : 388 nodes, 388 edges
open route     : 43.0 km, 98 min (origin Bidur -> Syaphrubesi)
detour         : exists for 100% of tested hazard positions; median detour 186 min
decision point : node 48 'Betrawati', 12.0 km from origin
named places   : Bidur, Betrawati, Mailung, Syaphrubesi, Dhunche
```

`results/demo_bundle/coolr_points.json` contains `{"points": []}` (no COOLR points). `results/data/` does not exist (no fetch succeeded, so no cache or `*.prov.json` files were written).

## (3a) STEP 0 pre-check table

| Check | Result | Evidence |
|---|---|---|
| a. notebook valid JSON, loads in nbformat | **PASS** | `raw json.loads: OK`; `nbformat.read` + `nbformat.validate` OK (nbformat 5.10.4); 65 cells (33 markdown, 32 code); file size **326691 bytes**; sha256 **`9e1b1cc8a215c0a0c2f3f07ee10bb1cc10d7d11996059e385d76a6e33d489928`** |
| b. run-config cell RUN_MODE = "FULL" | **PASS** | parameters cell is the first code cell (index 1), tagged `parameters`; exact line: `RUN_MODE = "FULL"            # "QUICK": proves every cell runs (smoke numbers) | "FULL": report numbers` |
| c. USE_DRIVE / FETCH_REAL_DATA / SEED | **PASS** | `USE_DRIVE = False` (comment: "keep False for agents"), `FETCH_REAL_DATA = True`, `SEED = 42` — all unchanged |
| d. machine + install | **PASS** | Python 3.12.14 (venv), 2 CPU cores (Intel Xeon), RAM 4.1 Gi total / 3.6 Gi available, free disk 8.2 GB (≥ 6 GB required), **no GPU** → installed CPU torch `torch-2.14.1+cpu` via `--index-url https://download.pytorch.org/whl/cpu`; installed/verified numpy 2.1.3, matplotlib 3.9.2, networkx 3.6.1, onnx 1.23.2, onnxruntime 1.30.0, onnxscript 0.7.2, nbformat 5.10.4, nbclient 0.10.4, nbconvert 7.17.1, ipykernel 7.2.0 (full list in pip_freeze.txt) |
| e. network: overpass-api.de | **NO** | single curl probe: `HTTP 000`, exit 7 (connection refused on both IPv4 endpoints 162.55.144.139 / 65.109.112.52, IPv6 "Network is unreachable"). The notebook's own fetch later got `URLError(OSError(101, 'Network is unreachable'))`. The notebook's configured mirror `overpass.kumi.systems` was also unreachable from this machine (first probe: timeout exit 28; later probe: exit 6) |
| e. network: gis.earthdata.nasa.gov | **YES (root), service 404** | single curl probe: `HTTP 301` (exit 0) — host reachable. During the run, the COOLR ArcGIS service path itself returned `<HTTPError 404: 'Not Found'>` on both attempts, so the COOLR fetch failed |
| f. can run ~2 h | **PASS** | run executed for 2 h 51 m 23 s (see (4)). Infrastructure note: this platform kills all user-spawned processes at the end of every tool call, so the run was executed inside a single long call with an in-call 60 s progress-snapshot loop (run_progress.log); kernel stdout is captured inside the executed notebook, so run.log only contains nbconvert's own two lines |

## (3b) STEP 2 verification table

| # | Check | Result | Evidence (verbatim) |
|---|---|---|---|
| 1 | nbconvert exit 0; all code cells executed; zero error outputs | **PASS** | `=== nbconvert exited: 2026-10-08 12:45:34 UTC, exit code 0 ===`; 32/32 code cells have execution counts; 0 cells with error outputs; 0 stderr stream blocks in the executed notebook |
| 2 | Section 2 "all pre-flight checks passed" (incl. exact v6.1 regression) | **PASS** | `all pre-flight checks passed`; `[ok] with V7.1 switches off, env reproduces the original v6.1 exactly: ['paper_fifo_tx', 'priority_tx']`; also `[ok] base request stream identical with DISASTER_MODE on/off -> on/off comparisons are paired` |
| 3 | DATA MODE line | **REPORTED** | `DATA MODE: roads=SYNTHETIC | hazard prior=UNIFORM` (fallback branch; errors quoted in section (2) above) |
| 4 | Section 5 training lines | **PASS** | `model A: corr(reward, -T) at V=30 = +0.958  (must be strongly positive in FULL; meaningless with a handful of QUICK episodes)`; `model B: protected-class deadline miss % (first vs last tenth of training) per V (10, 30, 50): [30.8, 72.3, 86.7] -> [25.3, 64.4, 79.6]` |
| 5 | ONNX vs torch disagreement count (out of 500) | **PASS** | `[ok] ONNX vs torch decision disagreements on 500 live states: 0` (notebook asserts `dis <= 5`; also `verify: PASSED` for all 6 exports, max diff 9.54e-07 vs tolerance 1e-04) |
| 6 | C3 Local-only excess exactly 0 for every k | **PASS** | `[ok] validity: Local-only excess is exactly 0 for every k`; rows: `k=1/2/4 RSU(s) Local-only  excess during 0.0 +- 0.0% (n=5)   after 0.0 +- 0.0% (n=5)` |
| 7 | results_v71.json exists, parses, run.mode == FULL, budget, five seeds | **PASS with discrepancy (W2)** | file exists and parses; `run.run_id = 20261008-124455-ba2667`; `run.mode = FULL`; `budget.ep_A = 1000`, `budget.ep_B = 1200`, `budget.seeds = [0, 1, 2, 3, 4]` (five seeds). **The delivery instructions expected ep_A=400, ep_B=600 — the notebook as shipped (sha-verified, unedited) defines FULL as ep_A=1000, ep_B=1200 (BUDGETS["FULL"]), and it ran with those values. The delivered budget is the notebook's own, not the instructions' expectation.** |
| 8 | demo_bundle contents | **PASS** | `results_v71.json` (527907 bytes), `corridor_graph.json`, `latency_samples.json`, `coolr_points.json`, `figures/` (14 PNGs), `onnx/` with `meppo_A_v10/v30/v50` and `meppo_B_v10/v30/v50`, each `.onnx` plus its `.onnx.json` sidecar (12 files); final print: `contents : ['coolr_points.json', 'corridor_graph.json', 'figures', 'latency_samples.json', 'onnx', 'results_v71.json']` |
| 9a | floor-dilution table: identical core numbers across thresholds? | **REPORTED** | Core columns are identical across all six IMMEDIATE thresholds 9.5/7.5/6.0/4.5/3.0/0.0: `core T 4.83 +- 0.89s (n=5)` and `core miss 91.5 +- 5.1% (n=5)` on every row. `QM miss` is `6.6 +- 2.4% (n=5)` at thresholds 9.5–3.0 and `6.7 +- 2.3% (n=5)` at threshold 0.0 (differs at that one threshold). `floor covers` grows from `11.8 +- 0.8%` (9.5) to `55.5 +- 1.2%` (0.0). |
| 9b | C1/N1/N2 gains whose 95% CI includes zero | **REPORTED** | Printed gain lines whose CI includes/touches zero (all are C1, random policy, "paired gain vs floor OFF"): `floor ON, v6.1 (level 9 shared)  miss -pp  V20:0.8 +- 0.8 (n=5) ... V40:0.3 +- 0.3 (n=5) ... V50:0.1 +- 0.2 (n=5)` and `floor ON, V7.1 (level 9 reserved)  miss -pp  V20:0.8 +- 0.8 (n=5) ... V50:0.1 +- 0.2 (n=5)`. All printed C1 T-gain CIs exclude zero (smallest: V10 2.3 +- 1.9 → [0.4, 4.2]). The N1 (Section 10) and N2 (Section 11) tables print per-policy/per-threshold levels with CIs, not paired gain±CI lines, so no N1/N2 gain line exists to test. (Section 12 latency prints paired floor-ON−floor-OFF differences whose CIs include zero: under V2V `0.04 +- 0.09`, `-0.04 +- 0.10`, `-0.03 +- 0.11 min (n=20)` and under V2V+RSU `-0.04 +- 0.11`, `0.00 +- 0.10 min (n=20)`.) |

## (4) Wall time and device

- **Total wall time (attempt 2, the delivered run): 2 h 51 m 23 s** — launched 2026-10-08 09:54:11 UTC, nbconvert exited 12:45:34 UTC (run_progress.log records the per-minute timeline).
- **Device: cpu** — 2 vCPU Intel Xeon, no GPU, torch 2.14.1+cpu (CUDA unavailable).
- Section 4 projection line, verbatim: `4.3 s/episode on cpu  ->  model A (1000 ep) ~ 72 min,  model B (1200 ep) ~ 86 min`
- Actual training time from results_v71.json: model A `minutes = 64.6304604768753` (1000 episodes), model B `minutes = 81.96047011216481` (1200 episodes). Checkpoint-file timeline: model A last checkpoint 10:59:45 UTC, model B last checkpoint 12:21:42 UTC; ONNX export + all experiments 12:21–12:45 UTC.

## (5) Every warning and anomaly, verbatim

Notebook output (all quoted exactly as printed):

1. `DATA MODE: roads=SYNTHETIC | hazard prior=UNIFORM` — both live fetches failed (this is the notebook's designed labelled fallback, anticipated in the run instructions).
2. `errors: ["https://overpass-api.de/api/interpreter attempt 1: URLError(OSError(101, 'Network is unreachable'))", "https://overpass-api.de/api/interpreter attempt 2: URLError(OSError(101, 'Network is unreachable'))"]`
3. `errors: ["attempt 1: <HTTPError 404: 'Not Found'>", "attempt 2: <HTTPError 404: 'Not Found'>"]` (NASA COOLR service; the host root itself was reachable — HTTP 301 — but the ArcGIS service path 404s)
4. `corridor graph : synthetic -- synthetic (schematic geometry, published route lengths)` / `why            : no OSM data (offline, blocked, or fetch disabled)`
5. `coolr_points.json` contains `{"points": []}`; `results/data/` was never created (no fetch succeeded, hence no `*.prov.json` cache files exist in the bundle).
6. (W2, expectation mismatch, not a notebook failure) The instructions' expected budget `ep_A = 400, ep_B = 600` does not appear anywhere in the shipped notebook; its `BUDGETS["FULL"]` is `ep_A=1000, ep_B=1200, seeds=(0, 1, 2, 3, 4)` and that is what ran and what results_v71.json records. The run trained MORE, not less, than the instructions expected. No configuration was changed by the operator.

Infrastructure anomalies (disclosed for honesty; none altered the notebook's computation):

7. First launch attempt (09:35:18 UTC) was killed by this platform's tool-call cleanup ~20 s after start — during the module `%%writefile` cells, before pre-flight and before any training. No results, checkpoints or caches had been written; the working tree was verified pristine (results/figures empty) before relaunching. Its two log lines are preserved as `run_attempt1_infra_kill.log` / `pid_attempt1.txt`.
8. The delivered run (attempt 2) was started inside one long tool call; the call itself returned a platform-level "context deadline exceeded" at ~10 min, but the nohup'd nbconvert + kernel survived (verified by PID and continued checkpoint writes) and ran to completion, monitored via the in-call snapshot loop writing `run_progress.log`. Progress was therefore reported from run_progress.log + filesystem evidence, not from live cell stdout (kernel stdout is captured inside the executed notebook).
9. A standalone calibration replicating the notebook's own Section-4 benchmark code (exact same 2-episode measurement, scratch EPTASK_HOME, no side effects) was run once before the real launch to size the timeout: it printed `5.1 s/episode on cpu -> model A (1000 ep) ~ 85 min, model B (1200 ep) ~ 102 min`. It did not touch the delivered run's directories.
10. `sudo` is unavailable and `/app` is unreadable on this machine; none of this affects the notebook.

No cell emitted stderr; no Python warnings appear in any cell output; zero error outputs; every assert in the notebook passed.

## (6) sha256 of the zip

The zip cannot contain its own digest; the sha256 of `EPtask_V7_1_FULL_20261008-124455-ba2667.zip` is recorded in the sidecar `EPtask_V7_1_FULL_20261008-124455-ba2667.zip.sha256` delivered next to the zip (and in the copy of this report delivered outside the zip).

## Zip contents

- `EPtask_MEPPO_v7_1_FULL_executed.ipynb` — the executed notebook (2056292 bytes; nbconvert: `Writing 2056160 bytes`)
- `results/` — the whole folder: `demo_bundle/` (results_v71.json, corridor_graph.json, latency_samples.json, coolr_points.json, figures/, onnx/), `figures/` (14 PNGs), `onnx/` (6 models + 6 sidecars), `checkpoints/` (meppo_A_static.pt, meppo_B_dr.pt). Note: `results/data/` does not exist because both fetches failed (no cache written).
- `eptask/` — the 16 module files the notebook wrote (the exact code that ran; `run.code_digest` in results_v71.json stamps their digest)
- `run.log`, `run_progress.log`, `pip_freeze.txt`, `environment.txt`
- `run_attempt1_infra_kill.log`, `pid_attempt1.txt` — attempt-1 evidence (see (5) item 7)
- `RUN_REPORT.md` — this report

Run identity: `run_id = 20261008-124455-ba2667`, `run.mode = FULL`, seed 42, device cpu, `code_digest` stamped in results_v71.json. Source notebook sha256: `9e1b1cc8a215c0a0c2f3f07ee10bb1cc10d7d11996059e385d76a6e33d489928` (unedited; the copy executed is byte-identical).
