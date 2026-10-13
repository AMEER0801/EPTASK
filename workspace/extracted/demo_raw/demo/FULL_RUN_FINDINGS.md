# FULL run 20261008-124455-ba2667: what it shows

Every number below was read from `results_v71.json` or computed from its per-seed raw values by me, after checking the agent's report. Intervals are 95% CI over 5 seeds unless stated.

## Provenance (checked, not taken from the report)
- Zip sha256 matches the sidecar; `unzip -t` clean.
- The 16 modules that ran are byte-identical to the notebook delivered earlier.
- 32/32 code cells executed, 0 errors. `RUN_MODE` is FULL, model A 1000 episodes, model B 1200 episodes, seeds 0-4.
- Data mode: `roads=SYNTHETIC | hazard prior=UNIFORM` (no internet to OpenStreetMap, NASA address unreachable). CPU run, 2 h 51 m.

## 1. Model B (disaster-aware) vs model A (static), outage test, paired by seed
| RSUs down | mean time during outage A | B | B minus A | seeds where B is faster |
|---|---|---|---|---|
| 1 of 8 | 2.68 s | 2.78 s | +0.100 ± 0.018 s | 0/5 (A better) |
| 2 of 8 | 2.86 s | 2.90 s | +0.037 ± 0.052 s | no clear difference |
| 4 of 8 | 3.34 s | 3.17 s | -0.172 ± 0.057 s | 5/5 |
| none (calm) | 2.49 s | 2.64 s | +0.146 ± 0.030 s | A better |

- Reference at 4 RSUs down: Local-only 4.39 s, alive-aware rule 6.62 s.
- **Read it as a trade:** B gives up about 6% in calm traffic and in small outages, and wins only in a severe outage.
- **Do not quote the percentages alone** (B +20.2% vs A +34.2% extra latency at 4 down): they are relative to each policy's own calm time, and B's calm time is slower.
- **B uses neighbours when roadside units die.** Share of tasks sent to nearby vehicles during the 3-RSU outage at V=30: B 23.9%, A 10.1%.
- **Confound:** B trained 1200 episodes vs A's 1000, with a different state, reward and training worlds. The difference cannot be assigned to one design choice.

## 2. C1, safety floor (random policy, paired, V=10..50)
- Time gain for safety-critical requests: 2.3±1.9, 3.1±1.0, 4.4±0.9, 4.3±0.5, 4.6±0.8 %. Deadline-miss improvement is at most 1.1 percentage points, and the CI touches zero at V=40 and V=50.
- With trained model A: 7.1±0.7 % (V=10), 3.7±0.8 % (V=30), 2.1±0.6 % (V=50).
- Reserved vs shared top level gives the same result (4.4 vs 4.3 % at V=30). A vehicle's uplink is busy at its next request only 0.1-1.5% of the time, so the fix has almost nothing to act on.

## 3. N1 and N2 inside the cell: mostly null
- **Emergency requests during a 3-RSU outage:** deadline miss is 50-91% for every learned policy at V=10..50, because the deadline is half the request's own Local-only time. Floor on vs off is within the CIs for A and B. The weak alive-aware rule gains more (V=30 time 10.11 -> 7.86 s).
- **N2 casualty floor:** value-weighted on-time rate is 81.1±3.7 (off) vs 81.4±4.6 (floor) for model B. No effect.
- **Request-level audit** (same seed, floor widened from 12% to 55% of traffic): the 513 newly protected requests got faster by 0.16 s on average. The always-protected core changed by +0.0001 s. Other traffic slowed by 0.017 s on average (worst +2.6 s). So the floor works, but too little to flip a deadline, and widening it did not dilute the core. The earlier "identical to the digit" was rounding.

## 4. Road scale (20 trials, schematic corridor): the warning network is the lever
| Scenario | none | vehicle relay | roadside units | relay + roadside |
|---|---|---|---|---|
| local damage, 30 veh/h | 78.7 ± 15.2 | 32.9 ± 12.6 | 0 | 0 |
| wide damage, 30 veh/h | 70.0 ± 17.0 | 30.7 ± 9.9 | 70.0 ± 17.0 | 30.3 ± 10.1 |
| wide damage, 90 veh/h | 76.0 ± 17.2 | 15.6 ± 8.6 | 76.0 ± 17.2 | 15.6 ± 8.6 |

Ambulance extra minutes against an oracle that knew at departure (floor off). The paired difference floor on - floor off is at most 0.04 min in every cell.

## What you can claim
- Two fixes to the v6.1 replication, each behind a switch that reproduces v6.1 exactly.
- Queue priority and the floor have small, measurable effects here, and I can say why (uplink rarely busy; deadlines tight).
- Disaster-aware training helps only in severe outages and costs a little in calm traffic.
- At road scale the warning network decides the ambulance delay, not the scheduler.

## What you cannot claim
- A benefit of N1 or N2 scheduling: all measured effects are within noise at the deadline level.
- Real-road results: the corridor is the schematic map, and blockage positions are uniform.
- "First", "saves lives", or any single-cause explanation for B beating A.

## Open items
- Real OpenStreetMap roads: the extract fetched had gaps (Betrawati to Mailung 69.6 km vs about 14 km published; Syaphrubesi's own roads disconnected by 679 m), so the code rejects it and uses the schematic map through real place positions. Cause unknown; `osm_nh_extra.json` may explain it.
- NASA landslide reports: the server returned 404 on every path from Colab (probe output). Treat COOLR as dropped unless it works from another network.
- Add an emergency-deadline sensitivity row (1.0x instead of 0.5x) before relying on the N1 miss rates.
