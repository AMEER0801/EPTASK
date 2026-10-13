# EPtask V7.1: holographic 3D demo

A holographic twin of the Trishuli valley, played as an 8-step story from the hazard to reaching the people. It covers the replica, C1–C3, N1 and N2.

## Open it

- **Offline:** double-click `index.html`.
- **Online copy:** `eptask_3d_demo.html` loads three.js from a CDN.

Address options (combine them with `&`):

| option | what it does |
|---|---|
| `?fx=0` | turns the glow off, for slow laptops and projectors |
| `?debug=1` | shows the HUD (fps, draw calls, triangles, vehicles drawn) and mirrors debug log lines to the console |
| `?selftest=1` | runs the self-test right after loading; results appear in the Log window |
| `?legacy=1` | restores the pre-fix vehicle placement, for before/after testing only |

Keyboard and mouse:
- Space: play/pause
- ← / →: previous/next step; 1–8: jump to a step
- Drag to rotate, scroll to zoom, right-drag to pan

## On the roads

**Emergency convoy**, staged at Bidur:
- ambulance (the notebook's N1 vehicle);
- police patrol;
- fire engine;
- a three-truck army convoy.

Each one's route is simulated by `corridor.py` with the same blockage, traffic and roadside units, one at a time, so convoy members do not interact. Dispatch times are an ASSUMPTION in `tools/make_traces.py`.

**Non-emergency traffic** is cars, motorbikes, buses and trucks. The type mix is an assumption; every position is recorded from the simulation.

**Illustration only:** the holographic relief, the shockwave, the debris and the water.

## Log: finding and fixing problems

Open **Log** from the dock (bottom right). It opens by itself on any error.

Every entry follows the same schema:

```
{seq, ts, level, cat, msg, ctx, data}
```

| field | meaning |
|---|---|
| `seq` | sequence number |
| `ts` | milliseconds since the page loaded |
| `level` | `debug`, `info`, `warn` or `error` |
| `cat` | `boot`, `data`, `scenario`, `step`, `sim`, `render`, `perf`, `ui`, `test` or `js` |
| `msg` | what happened, in plain words |
| `ctx` | `{hz, mode, step, t}`, the scenario at that moment |
| `data` | details for that event |

What gets logged:
- **Errors:** script errors, unhandled promises, WebGL context loss.
- **Warnings:** bloom falling back to a plain render; a low frame rate for 3 seconds in a row.
- **Story events** while the story plays: hazard, first warning, dispatches, Betrawati, arrivals.

**To report a bug:** open the Log window, press **Copy** (or **Download**), and send the JSON. It contains the URL, the browser, the self-test result and every entry.

## Tests

Inside any browser: **Log → Run self-test**. It replays all 3 hazards × 4 warning networks × 8 steps, plus the last recorded minute, the end of the timeline, full zoom-out and full zoom-in, for 122 checks in total. Each check confirms:
- every recorded vehicle is drawn;
- no vehicle is under the terrain;
- every emergency vehicle on the road is visible;
- no frame is blank;
- no script error occurs.

From the command line (needs Node 18+ and `npm i puppeteer-core`; set `CHROME` to your Chrome executable):

```bash
tools/run_tests.sh       # check_data.py -> test_e2e.mjs (fixed + legacy) -> test_shots.mjs
```

Results in the build sandbox (headless Chrome, software WebGL):

| check | result |
|---|---|
| `check_data.py` | DATA OK |
| `test_e2e.mjs` on the fixed build | 122/122 pass; 0 script, page or console errors; boot logged |
| `test_e2e.mjs` with `?legacy=1` | 41/122 fail (28 vehicles under the terrain, 13 vehicles not drawn at the timeline end) |

The legacy run proves the test catches the bug that was fixed.

## The "vehicles disappear" bug: four causes, all fixed

1. **Timeline end.** The recording stops when the run ends, so everything vanished on the last stretch of the timeline. It now holds the last recorded frame.
2. **Steep valley walls.** Vehicles were placed by bilinear interpolation while the terrain is drawn as triangles. Heights now come from the same triangles.
3. **Earthquake ripple.** It raised the terrain over vehicles and roads in the damage zone. Vehicles, roadside units, roads and the river now ride the same wave.
4. **Far zoom.** Scaling models up pushed their lower half underground. Models now have their base at ground level, and they stay readable when fully zoomed out.

## Regenerate from another run

```bash
python tools/make_traces.py --bundle <results/demo_bundle> --eptask <the eptask/ folder from the same run> --out demo_data.json
python tools/check_data.py demo_data.json
python tools/build_demo.py
tools/run_tests.sh
```

This build replays the FULL notebook run 20261008-124455-ba2667: model A 1000 episodes, model B 1200 episodes, 5 seeds. The corridor roads are the SCHEMATIC two-route map and the hazard prior is UNIFORM (the run had no internet for OpenStreetMap or NASA). The motion is replayed from recorded simulations; the numbers in the windows come from `results_v71.json`.

## Not tested

- real GPUs;
- Safari, Firefox and mobile touch;
- the online copy's CDN loading (the build sandbox cannot reach the CDNs).
