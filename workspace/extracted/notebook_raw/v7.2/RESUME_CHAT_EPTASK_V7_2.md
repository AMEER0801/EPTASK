# EPtask V7.2 - RESUME PROMPT (paste into a fresh incognito chat, then ATTACH the files listed at the bottom)

Written 2026-10-09. Submission: first week of November 2026.

═══════════════════════════════════════════════════════════════════
COPY FROM HERE
═══════════════════════════════════════════════════════════════════

Vanakkam nanba. Reply preference: Tanglish, SIMPLE: numbered steps, one tiny example for every new word, a small table at most, no dense paragraphs. If I say "purila", cut the answer down and add a toy example; do not add content. Naan incognito mode-la irukken, so munnadi chat memory illa. Idhu dhaan full context. Vera projects (EV project, payment project, AXIOM BENCH) edhuvum idhula kalakkaadha; idhu thani project.

**Project**: M.Tech AI mini-project, M Mohamed Ameer (RegNo 127162017), SASTRA, guide Dr. Manjula KR. Base paper (replicated): Li et al., "EPtask: DRL Based Energy-Efficient and Priority-Aware Task Scheduling for Dynamic VEC", IEEE T-IV 9(1), 2024; algorithm MEPPO (one RL agent picks offload target, priority 0-9 and transmit power per task). Standing wish: every novelty is my own design, plagiarism concern is serious, be honest, never over-claim.

**What I want from the project now**: a real-world application, not only a simulator: after an incident, send the nearest hospital's ambulances, reroute or warn other traffic, reach people inside the golden hour, and show that with real Nepal disaster data. I want named priority classes (not just numbers 0-9) in both the replica and the new work, and an explanation (C2) that anyone can understand. I asked for "15 -> 5 minutes" and "lives saved"; we agreed these cannot be promised: the wording is "modelled" and "retrospective simulation", with success criteria written before running.

## The journey, from scratch to now

| Stage | What was built | What was found |
|---|---|---|
| 1. v5.1 | From-scratch replication of EPtask/MEPPO (1000 episodes) | Paper's Eq.(25) reward correlated -0.83 with completion time; `local_ratio` reward behind a switch gives +0.976 |
| 2. v6.1 | Features C1 floor, C2 explainability, C3 node-failure resilience | Priority scheduling has almost no leverage: the vehicle uplink is busy only 0-2% of the time |
| 3. V7.1 | Two v6.1 bugs fixed behind switches (`RESERVE_TOP_LEVEL`, `LOCAL_COST_AT_ARRIVAL`); disaster environment; N1 emergency floor + disaster-trained model B; N2 casualty-weighted priority; two-scale road co-simulation; datasets; ONNX | With all switches off it reproduces v6.1 bit-for-bit; QUICK run 32/32 cells, 0 errors |
| 4. 3D demo | Three.js neon holographic demo, emergency convoy, hazards, logs, 122-check self-test | 4 'vanishing vehicle' bugs fixed; legacy build fails 41/122, fixed 122/122 |
| 5. FULL run | Agent ran the notebook: run `20261008-124455-ba2667`, ep_A 1000, ep_B 1200, 5 seeds, CPU, 2 h 51 m | Verified by me (checksum, 16/16 modules identical, 32/32 cells); claims rewritten from verified numbers |
| 6. Real roads and NASA | OpenStreetMap fetch, plausibility gate, NASA COOLR attempts | OSM works from Colab at times; real graph fails the gate (13 national-highway ways missing vs the July snapshot); NASA 404 from Colab, dropped |
| 7. Real-data pivot | Copernicus EMSR927, BIPAD, hospitals; pilots for N1 and N2 | N1 access pilot: damage map saves 0.0 min; N2 golden-hour WSPT helps when ambulances are scarce |
| 8. V7.2 patch | No-retrain real-data notebook, dependency-free GeoPackage reader, dispatch module with capacity limit | Fresh unzip: 22/22 checksums, 6 tests, 8/8 checks; **not yet run by the agent** |
| 9. Next | Pilot gates P-0 and P-1, gate review 13 Oct, results freeze 24 Oct, report, viva | PENDING |

## Verified numbers (FULL run, run of record = V7.1 notebook, run `20261008-124455-ba2667`)
- Agent zip `EPtask_V7_1_FULL_20261008-124455-ba2667.zip`, sha256 `70d42c035bfb07287230e8ca78ae7ab881dbbae6bf6e14e185a7f62ffc6aa394`, 90 files. Notebook sha256 `9e1b1cc8a215c0a0c2f3f07ee10bb1cc10d7d11996059e385d76a6e33d489928`. The agent had no internet: DATA MODE roads=SYNTHETIC, hazard prior=UNIFORM.
- corr(reward, -T) at V=30 = +0.958 (model A); ONNX vs torch decisions disagree 0/500; local-only excess exactly 0% (C3 validity check).
- **C3 (paired B - A):** calm traffic A 2.49 s, B 2.64 s (B slower); 1 unit down +0.100 +/- 0.018 s (A better, B better in 0/5 seeds); 4 units down -0.172 +/- 0.057 s (B better in 5/5). B also trained 1200 vs 1000 episodes, with a 33- vs 29-dim state and a different reward, so the cause is confounded (ablation not yet run).
- **C1 floor:** random policy 2.3 +/- 1.9 ... 4.6 +/- 0.8% time gain (V=10..50); with model A 7.1 +/- 0.7 / 3.7 +/- 0.8 / 2.1 +/- 0.6% at V=10 / 30 / 50; deadline-miss improvement at most 1.1 pp.
- **N1 in the cell:** emergency miss 49-91% for learned policies (deadline is a strict 0.5x Local-only); **N2 in the cell:** 81.1 +/- 3.7 vs 81.4 +/- 4.6, no effect.
- **Corridor (schematic roads, 20 trials):** extra minutes for the ambulance: roadside-unit warning 0 when RSUs survive; V2V relay 15-33; no warning 70-79; floor ON vs OFF <= 0.04 min. Sensitivity (valley leg 17 -> 23 km, 8 trials): the ordering holds, delays about 10 min longer.
- **Request-level audit:** the earlier "identical to the digit" was rounding: 513 newly protected requests got 0.16 s faster, the core changed 0.0001 s, other traffic slowed 0.017 s.

## Real-data pilots and the V7.2 patch (my sandbox, not yet re-run by the agent)
- **Data received** (all inside the patch zip): OSM roads 8 Oct (12.5 MB) + July national-highway ways (snapshot 24 Jul 2026); Copernicus EMSR927 AOI01 Syaphrubesi grading (6.15 km road destroyed, 5 bridges, 2 helipads, 433 buildings graded, 323 destroyed); osgeonepal OSM hospitals (16 in the corridor box, 4 named ones used); BIPAD Bagmati 2016-2026 (1,821 incidents, 268 with injured or missing people, median 1, max 56). BIPAD export lacks the 26 Aug event and has no coordinates; the Copernicus file covers Syaphrubesi only.
- **N1 access (Rasuwa District Hospital -> destroyed area):** informed vs uninformed difference **0.0 min in all 6 settings** (dead-end valley); drive about 30 min + walk; 58.8-132.0 min to the victims. So the N1 lever is **dispatching on the warning**, not on the damage report: modelled saving = R + min(L, drive time), where L (warning lead time) must come from the real 26 Aug timeline and R (report delay) is an assumption. Not measured yet.
- **N2 dispatch, baseline nearest-first, 4 patients per trip, 400 paired scenarios:** golden-hour WSPT with 2 ambulances for 20 incidents: golden-hour share 7.1% -> 8.5% (+1.40 +/- 0.26 pp), modelled survivors +6 / +10 / +14% (half-life 30 / 60 / 120 min). With 4 ambulances for 10 incidents: +1.01 +/- 0.83 pp, survivors -5% / -1% / +1%. **Do not quote the unlimited-capacity pilot (+4.44 pp, +43%).**
- **Patch**: `EPtask_V7_2_realdata_patch.zip` (no retraining; 13-cell notebook, about 80 s); agent prompt `PROMPT_agent_V72.md`.

## Not verified / not done: be honest about these
- The agent has NOT run V7.2 yet; P-0 (deadline sweep) and P-1 (surge-load regime map) NOT run; no retraining decision yet.
- Named priority classes P0 LIFE-CRITICAL, P1 RESCUE, P2 HAZARD ALERT, P3 COORDINATION, P4 BULK are a design only: not in the code, not in the replica yet.
- C2 "why card" and the classmates comprehension test: not built, not run.
- N1 warning-race backtest: needs the minute-level timeline of 26 Aug 2026 (not yet available). The AI-chat timeline I was given is NOT usable.
- B vs A ablation (A trained 1200 episodes; a disaster-trained model on the 29-dim state): not run.
- Streamlit app still shows the QUICK sample bundle (not rebuilt from FULL); the 3D demo was regenerated from the FULL bundle but keeps the FULL run's schematic corridor (its approximate place positions, e.g. Mailung about 5.5 km off), not the V7.2 real data.
- Facts to re-verify before quoting: the Aug 2026 flood toll (sources differ: NDRRMA situation report is the one to cite, with its date); EMSR927 and UNOSAT 4257/4259 product pages (I saw the numbers, not the pages); BIPAD download; survival-curve papers (7-10% per minute is cardiac-arrest registry material citing Larsen et al. 1993, Ann Emerg Med 22:1652-1658; earthquake entrapment has no single time window: Macintyre et al. 2006 and 2010).
- Nearest prior work to cite and read myself: Chen & Englund 2018; Liu et al. 2021/2023; Khaliq et al. 2019. Never say "first to combine", never give a "% new" figure, never "lives saved".

## From research prototype to a real-world product: what exists, what is missing
| Layer | Exists now | Gap to a product |
|---|---|---|
| Edge scheduling (MEPPO) | trained, ONNX export, 0/500 disagreement | real hardware latency, security, the named classes P0-P4 |
| Warning service | simulated V2V and RSU relay; signed-message design on paper | radio stack, key management, store-carry-forward tests |
| Dispatch service | golden-hour WSPT on the real road graph with real hospitals (simulation) | live ambulance positions, hospital load, patient capacity, a dispatcher interface |
| Road and damage data | static OSM + Copernicus snapshot | live feeds, validation, the missing valley road north of Mailung |
| Evidence | modelled, retrospective | field trial or at least a table-top exercise with an emergency service |
Say plainly: this is a validated simulation study on real data, not a deployed system.

## Demo improvement plan (in priority order; each has a test)
1. **Rebuild both demos from FULL + V7.2 results** (Streamlit still on QUICK). Test: run id and data hashes visible on screen; every number comes from `results_v72.json` or the FULL bundle, none typed.
2. **Real Syaphrubesi scene in the 3D demo**: pre-flood roads, Copernicus destroyed roads (red), destroyed bridges, helipads, graded buildings, the hazard extent, the best stopping point. Export a small scene JSON from V7.2 (tools like `make_traces.py` in the demo zip). Test: extend the 122-check self-test with 'every destroyed bridge drawn' and 'no object under terrain'.
3. **Dispatch layer**: hospitals, ambulances driving real routes, incident clusters with head-counts, a 60-minute golden-hour clock, nearest-first vs golden-hour WSPT side by side on the same scenario. Test: the replay's reached-within-60-min share equals the notebook's number.
4. **Warning race** once the timeline exists: flood front along the Bhote Koshi-Trishuli road, vehicles turning green when warned, lead-time histogram.
5. **Named priority classes P0-P4** with colours on tasks, and a per-class result table (replica and new work).
6. **C2 'why card'**: click a task, see one plain sentence, three numbers and one 'what would change it' line (exact counterfactual from `env.peek()`).
7. **Regime map panel** (benefit of the floor vs surge load and units down) after P-1.
8. **Honesty layer in the UI**: badges 'retrospective simulation', 'modelled', 'assumption' with the assumptions list; data-source and licence footer (OSM ODbL, Copernicus EMS, BIPAD).
9. **Presentation mode**: 8-step story auto-play, a 10-minute demo script, keyboard shortcuts; readable on a projector.
10. **Robustness**: offline single-file build, mobile viewport, error log opens on failure (already in the 3D demo), publish a hosted artifact only if I ask.
Never put an invented number on screen (EPT-AP-012).

## Dates
- 13 Oct gate review (retrain or not); 24 Oct results freeze; 24-28 Oct guide meeting with the claims table; 29 Oct-1 Nov final package; first week of November submission and viva. No new feature after the freeze.

## Standing rules (keep following)
- Run it, don't just read it; every real bug here was found by execution.
- Every behaviour change is a config switch; prove off == old with golden values.
- Pair everything (same seed, twin run, a comparator that must read zero); multi-seed with 95% CI; strongest realistic baseline.
- Measure the mechanism before explaining a null; diff raw items before saying 'identical'.
- Label every number measured / assumed / published; write which way each simplification biases the claim.
- Open every received data file first (coverage, vintage, coordinates, duplicates); real data goes through a plausibility gate; print its vintage.
- AI-chat tables and timelines are not data. No statistic or citation I did not obtain.
- Assert which branch a test took; show a test can fail on the bad version.
- Tool shell is /bin/sh: use `bash -c` for brace expansion, process substitution, `date +%s` for timing. Long jobs: nohup + a progress log.
- Deliver a verified increment before starting the next; do a fresh-unzip dry run of any package an agent will run.

## What to do next: pick the obvious one or ask me
(a) Run P-0 (deadline sweep) and P-1 (surge-load regime map) on the FULL models, then the 13 Oct gate decision
(b) Process the agent's V7.2 run (verify the returned zip against `reference/`)
(c) Add named classes P0-P4 to the replica and the new work; build the C2 why-card
(d) N1 warning-race backtest once I send the minute-level timeline
(e) Demo rebuild (plan above)
(f) Report writing from FULL_RUN_FINDINGS.md and the V7.2 results
(g) A bug I will describe: ask for the module, the exact error, and a fresh extraction of the zip, not my modified copy.

═══════════════════════════════════════════════════════════════════
COPY TILL HERE
═══════════════════════════════════════════════════════════════════

## Files to attach in the next chat

**Essential (attach these first)**
| File | Size | sha256 (first 16) | Why |
|---|---|---|---|
| `EPtask_V7_2_realdata_patch.zip` | 3,489,636 B | 9ea99fab283a1791 (full: 9ea99fab283a1791440bcb53c4a6430460daa8c417990c37d1305a9fea89715f) | the V7.2 code, data, tests, reference results |
| `FULL_RUN_FINDINGS.md` | 8,010 B | d9816a50195829c3 | verified FULL-run numbers and the claim / do-not-claim list |
| `V72_PILOTS_AND_DESIGN.md` | 16,861 B | 7df3ca08c17ec090 | pilot results, system and protocol design, metrics, reviews |
| `IDEAS_AND_REAL_DATA_GUIDE.md` | 15,007 B | 50369ffd5dfdf97b | ideas for N1, N2, C1, C2, claims table, data guide |
| `DATA_CHECK_REPORT.md` | 6,979 B | 8b27553ddb8fa6cd | what each received data file contains and its gaps |
| `eptask-mma-memory-v2-and-resume.zip` | see the delivery | - | this prompt + the memory files |

**Needed for specific tasks**
| File | Size | sha256 (first 16) | When |
|---|---|---|---|
| `EPtask_V7_1.zip` (notebook, docs, Streamlit demo) | 2,942,754 B | 59d33311bdfa955b | any change to the V7.1 modules or the Streamlit app |
| `EPtask_V7_1_FULL_20261008-124455-ba2667.zip` (agent's FULL run, 90 files) | 4.97 MB | 70d42c035bfb0728 | P-0 and P-1 pilots, the demo rebuild, report figures, the ablation baseline |
| `EPtask_V7_1_3D_demo.zip` | 7,028,557 B | e0ebb7b9ebcf64cc | demo work |
| `PROMPT_agent_V72.md` | 1,766 B | a6c686447bed679c | to send the patch to an agent again |
| `PROJECT_COMPLETION_PLAN_30_DAYS.md` | 4,630 B | 65bfa9c3ef449957 | calendar and decision list |
| `fetch_real_roads.py`, `probe_nasa.py` | 19,491 B, 1,884 B | 4034ac5342cc6686, 4b91062d4c7c7fb9 | only if the data fetch is retried from another network |
| the agent's returned `EPtask_V7_2_realdata_RUN_<timestamp>.zip` | - | - | when it exists |

**Data I still have to get (send when ready, small files first)**
1. BIPAD re-export: ALL hazard types, Rasuwa + Nuwakot + Dhading, 25 Aug-30 Sep 2026 (CSV; GeoJSON if offered).
2. Minute-level timeline of the 26 Aug 2026 flood from ICIMOD, NDRRMA situation reports, Department of Hydrology and Meteorology stations or dated news: 3-5 rows of place, latitude, longitude, time, source.
3. Nepal ward or municipality boundaries (Humanitarian Data Exchange) so BIPAD incidents can be placed.
4. UNOSAT product 4259 (Rasuwa and Nuwakot flood extent) and other EMSR927 areas if they exist.
5. Citations of the papers I read (Chen & Englund 2018; Liu et al. 2021/2023; Khaliq et al. 2019; survival curves).
6. Results of the classmates test (10-20 people, with and without the why-card).

**Not needed (superseded or duplicate; do not use or quote)**: `FINAL_ANSWER.txt`, `STRICT_PLAGIARISM_TANGLISH.txt`, `novelty_plagiarism_check.txt`, `VERIFICATION_RESULTS.txt`, `YOUR_NOVELTY_COMPOSITION_FINAL.txt`, `C1_C2_C3_vs_REAL_WORLD_NOVELTIES.txt`, `LIVE_DEMO_ARCHITECTURE.txt`, `STREAMLIT_DEMO_ALL_5_NOVELTIES.txt` (unmeasured percentages, unverified citations, hardcoded demo numbers); the BIPAD PDF/PNG (pictures, not data); the duplicate GRA .gpkg/.zip; the AI-chat tables and timeline in `audit.md`.

The old chat transcript will NOT exist in an incognito chat. This prompt, the attached files and the memory pack are the only memory.
