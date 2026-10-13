# Seed memory from the EPtask / MEPPO project, v2  (Tanglish)

Nanba, idhu **EPtask M.Tech mini-project**-oda full journey-oda failure + experience harvest: from-scratch replication (v5.1) -> v6.1 features -> V7.1 disaster-aware system -> FULL run -> real Nepal data -> V7.2 patch. Idhu **v2**: munnadi pack-oda ellaa entries-um irukku (IDs maaralai), pudhu entries `EPT-AP-020`, `EPT-DN-016`, `EPT-SK-013` la irundhu start aagudhu.
Vera projects-oda material (EV project, payment project, AXIOM BENCH build) **intentionally exclude** pannirukken. ID prefix: `EPT-` (AXIOM BENCH-oda `AXR-` IDs-oda kalakkaadhu).

## Folder layout
```
import_into_axiom_bench/   <- idhula irukkura files-a mattum AXIOM BENCH-la import pannunga
  anti_patterns.json  project_dna.json  skills.json
  reflections/*.md  (5 files, exactly 3 lines each)
docs/                      <- import pannaadhinga; padikka mattum
  README_SEED_FROM_EPTASK.md   (idhu)
  RESUME_CHAT_EPTASK_V7_2.md   (next fresh chat-la paste panna)
```

## Counts (import aana piragu check pannunga)
| file | count |
|---|---|
| `anti_patterns.json` | 36 anti-patterns (19 old + 17 new) |
| `project_dna.json` | 27 decision forks (15 old + 12 new) + 17 meta-lessons |
| `skills.json` | 21 skills: 16 passed Rule 1, 5 marked false honestly |
| `reflections/*.md` | 5 files (2 old + 3 new), 3 lines each, `Best:` / `Worst:` / `Surprise:` line START-la |

## Drop panra vazhi (AXIOM BENCH)
1. AXIOM BENCH -> MMA Memory -> Import (`.json` and `.md` accept aagum; exact button name-a naan paarkala).
2. `import_into_axiom_bench/` ullla 3 JSON + 5 reflection `.md` mattum select pannunga. `docs/` files-a import pannaadhinga (adhula Best/Worst/Surprise line illa, skip aagidum).
3. Munnadi pack-a already import pannirundha, **duplicate IDs** varum: oru vaati old EPT- entries-a delete pannitu v2 import pannunga, illa merge tool (`python/mma_merge.py`) use pannunga.

## Pudhusa enna add aachu (FULL run -> real data -> V7.2)
### Anti-patterns
- `EPT-AP-020` [visualization-engineering] Entities vanish when their recorded trace ends before the timeline does
- `EPT-AP-021` [visualization-engineering] Objects placed by a different rule than the surface they stand on (height, displacement, scale origin)
- `EPT-AP-022` [evaluation-methodology] Calling two results 'identical to the digit' from a rounded table
- `EPT-AP-023` [data-access] Varying the request to fix an endpoint that is blocked at network level
- `EPT-AP-024` [data-quality] Using a real dataset without a plausibility check against published values
- `EPT-AP-025` [data-quality] A mirror or fallback source silently serves an older snapshot
- `EPT-AP-026` [geospatial-modelling] Overlaying event damage on a post-event road map
- `EPT-AP-027` [simulation-modelling] A hard-coded model constant contradicts real geometry once real coordinates are loaded
- `EPT-AP-028` [testing] A test whose fixture never reaches the code under test
- `EPT-AP-029` [evaluation-methodology] A weak baseline inflates the improvement
- `EPT-AP-030` [evaluation-methodology] A simplification that favours the new method inflated the headline
- `EPT-AP-031` [research-integrity] Using AI-chat output as a data source
- `EPT-AP-032` [data-access] An export filter silently excluded the event of interest
- `EPT-AP-033` [research-integrity] Promising a numeric outcome before any measurement
- `EPT-AP-034` [evaluation-methodology] Attributing a gain to a feature when the arms differ in four ways
- `EPT-AP-035` [communication] Dense, jargon-heavy answers to a user who asked for simple steps
- `EPT-AP-036` [sandbox-environment] Assuming bash features in a /bin/sh tool shell

### Decision forks
- `EPT-DN-016` An agent ran the FULL notebook with no internet; can its report be trusted? -> Verify independently: checksum against the sidecar, byte-compare all 16 modules with the d
- `EPT-DN-017` How to word the FULL-run findings. -> FULL_RUN_FINDINGS.md with explicit claim and do-not-claim lists
- `EPT-DN-018` NASA COOLR is unreachable from Colab. -> Drop it; hazard prior = UNIFORM, stated in the data mode
- `EPT-DN-019` The real OSM road graph fails the plausibility gate. -> Plausibility gate plus schematic corridor; diagnose the gap with the July snapshot
- `EPT-DN-020` Rerun V7.1 with the post-run fixes? -> Keep V7.1 as the run of record; list the fixes after the run
- `EPT-DN-021` The user demands 'lives saved' and a 15 -> 5 minute ambulance result. -> Reframe with success criteria written before running
- `EPT-DN-022` Where can N1 and N2 matter if queue priority has no leverage? -> Move N1 to warning and dispatch timing, N2 to ambulance triage, C1 to disaster surge load
- `EPT-DN-023` Which real data to use. -> Primary sources, audited by opening each file
- `EPT-DN-024` Which road base for the damage overlay. -> Pre-flood network: July NH ways replace the October ones
- `EPT-DN-025` Which N2 rule and baseline. -> Golden-hour WSPT against nearest-first, 4 patients per trip as the main setting
- `EPT-DN-026` How to hand the V7.2 work to an agent that has no internet. -> Dependency-free reader; everything in one zip; no retraining
- `EPT-DN-027` Next steps after the V7.2 patch. -> Pilot gates first; gate review 13 Oct; results freeze 24 Oct; report; submit in the first 

### Skills
- `EPT-SK-013` Move the novelty to where the resource is scarce (Rule 1: passed)
- `EPT-SK-014` State the bias direction of every simplification (Rule 1: passed)
- `EPT-SK-015` Verify a delivered run from its raw artifacts (Rule 1: passed)
- `EPT-SK-016` Probe the layer above before changing the request (Rule 1: passed)
- `EPT-SK-017` Audit a received data file before analysing it (Rule 1: passed)
- `EPT-SK-018` Prove the test can fail (Rule 1: passed)
- `EPT-SK-019` Pilot before retraining (Rule 1: passed)
- `EPT-SK-020` Write the claims table before the run (Rule 1: NOT passed)
- `EPT-SK-021` Explain in numbered steps with one toy example per new term (Rule 1: NOT passed)

### Updated old entries
- `EPT-DN-015`: 'NOT YET DONE' -> DONE (FULL run by an agent, verified).
- `EPT-SK-001`: now has a genuine second example (V7.2 rewrite reproduced the geopandas pilot) -> Rule 1 passed.
- `EPT-AP-010`, `EPT-AP-017`: recurrence noted in `evidence`.

## Honest status
- **Verified (executed):** ellaa JSON-um parse aagudhu; required fields, unique and contiguous IDs, confidence 0-1, Rule 1 flag matches `second_example`, links point to existing forks, reflection 3-line format (line-start regex), scan for excluded-project names and credential-like strings: `validate_memory.py`.
- **NOT verified:** AXIOM BENCH-oda real importer-a naan run pannala; format-a nee kuduthha description-oda match pannen, avvalavu dhaan.
- **Evidence quality:** numbers ellaam indha project-oda real runs-la irundhu (FULL run, pilots, file audits). Pilot numbers (N1 access, N2 dispatch) **my sandbox**-la measure pannadhu, synthetic incident placement + assumed survival half-lives; agent innum V7.2-a run pannala.
- **Skills:** 5 skills-ku genuine second example illa (`EPT-SK-010`, `EPT-SK-011`, `EPT-SK-012`, `EPT-SK-020`, `EPT-SK-021`), so `rule1_passed:false`. Fake second example podala.

## Compact LLM preamble (copy-paste)

```
# Seed memory - EPtask / MEPPO / V7.2 (disaster-aware VEC scheduling and rescue dispatch)

## Generalizations
- [EPT-AP-001] Before training, correlate the reward with the metric you actually care about on rollouts; if the sign or size is wrong, no optimiser can fix it.
- [EPT-AP-002] When mapping scores onto a shared scale, test n=1 and n=max explicitly; a mapping that depends on group size injects a bias nobody trained for.
- [EPT-AP-003] Decompose the critical path before optimising; an optimiser can only move the stages it controls.
- [EPT-AP-004] A reservation is a property to assert, not to describe: write the test that tries to violate it.
- [EPT-AP-005] Compute every counterfactual from the state before the action; then prove the bug size by running old and new accounting on the same trajectory.
- [EPT-AP-006] Any effect claim needs a twin run that differs only in the cause, plus a comparator that must read zero.
- [EPT-AP-007] Rule 3: every number carries uncertainty; if the interval spans zero, say so.
- [EPT-AP-008] Check that a borrowed model's spatial and physical scale matches your simulator before importing its parameters.
- [EPT-AP-009] For every time factor, ask which way it pushes an item that has been waiting, and state the half-life, not tau.
- [EPT-AP-010] Before trusting an on/off or dose-response metric, list everything else that changes between the arms.
- [EPT-AP-011] Before building a comparison, ask whether the two arms can differ at all; a quick world check is cheaper than a figure.
- [EPT-AP-012] A consumer is written against the producer's actual file; any number on screen must come from a run or a live computation.
- [EPT-AP-013] A search can only support 'nothing found' if the query was a real query and the results were actually read. 'My own idea' is not the same as 'novel'.
- [EPT-AP-014] Never output a statistic or a reference you did not obtain; if a quantity has no measurement procedure, do not give it a number.
- [EPT-AP-015] Check the factual premise of a motivating story before building a model around it.
- [EPT-AP-016] Respect robots.txt and look for the sanctioned API; design the fallback before the fetch.
- [EPT-AP-017] When a bulk install fails, find the failing package, retry individually in the foreground, and verify by importing.
- [EPT-AP-018] If the agent must react to an event, make sure the event is observable in its input.
- [EPT-AP-019] Deliver the smallest verified increment first; a half-built system that cannot be handed over is worth nothing.
- [EPT-AP-020] Define what every entity does before its first and after its last sample, and test both ends of the timeline.
- [EPT-AP-021] Anything placed on a surface must use the surface's own function for position and effects, and scale about its base; test at the extremes (steepest slope, maximum zoom, effect peak).
- [EPT-AP-022] Before explaining 'no difference', compare raw per-item values for the subset the treatment touches.
- [EPT-AP-023] Classify the failure layer (network, host, route, query) before changing the request.
- [EPT-AP-024] Real is not the same as right: compare derived quantities with published ones and gate on them.
- [EPT-AP-025] Always surface the vintage of every data source in the run's data mode.
- [EPT-AP-026] Damage overlays need a pre-event base layer; compare matched length with the damage source's own total.
- [EPT-AP-027] After loading real coordinates, check every modelled length against its straight-line distance.
- [EPT-AP-028] Assert the precondition of a test (which branch ran) before reading its result.
- [EPT-AP-029] Choose the baseline a competent practitioner would use, not the one that makes the gain largest.
- [EPT-AP-030] For every simplification, write which way it biases the claim and rerun without it before quoting.
- [EPT-AP-031] Data needs a dated, hashed, primary source; chat output is a lead to check, not a source.
- [EPT-AP-032] Before analysis, test that the dataset contains the event you are building the story around.
- [EPT-AP-033] Promise the method and a fair test, never the number.
- [EPT-AP-034] When more than one thing differs, the effect belongs to the bundle, not to any member.
- [EPT-AP-035] When the user says 'purila', shrink the answer and add a toy example; do not add content.
- [EPT-AP-036] Check the shell before using bash-only syntax in a tool call.

## Skills (Rule 1 passed)
- [EPT-SK-001] Golden-value regression before editing: Record exact outputs of the untouched code first (first-N values, sums, counts, final state); after the change, with every new switch off, assert equality.
- [EPT-SK-002] Make each audit fix a measurable switch: Give every fix a named config switch whose off-state is the old behaviour, so the size of the bug can be measured by running both settings.
- [EPT-SK-003] Paired control with a built-in zero check: Estimate an effect by running a twin that differs only in the cause (same seed, same exogenous stream) and include a comparator whose effect must be exactly zero.
- [EPT-SK-004] Measure the mechanism behind a null result: When an expected effect is absent, measure the quantity that should have carried it before offering an explanation.
- [EPT-SK-005] Ask what else differs between the arms: For any on/off or dose-response comparison, list every quantity that changes with the treatment (composition, time, load) and hold it fixed or measure it.
- [EPT-SK-006] Execute it the way the user will: Run the deliverable end to end in the user's mode (headless notebook, clicked UI) and read the output critically, not only the exit code.
- [EPT-SK-007] Read the producer's contract before writing the consumer: Inspect the real exported artifact (output arity, state encoding) first, and make the artifact carry its own contract.
- [EPT-SK-008] Cache, then live, then labelled fallback: Resolve external data in order: cache, live fetch, explicit fallback; store provenance and stamp the data mode into the results.
- [EPT-SK-009] Label every number: measured, assumed or published: Tag each parameter in code and report as MEASURED, ASSUMPTION or PUBLISHED, and list assumptions as limitations.
- [EPT-SK-013] Move the novelty to where the resource is scarce: A priority or triage rule can only change outcomes where a resource is scarce; locate the bottleneck before assigning priority.
- [EPT-SK-014] State the bias direction of every simplification: For each simplification, write which way it pushes the headline and rerun without it before quoting.
- [EPT-SK-015] Verify a delivered run from its raw artifacts: Check checksums, byte-compare the code, count executed cells, and recompute headline numbers from raw files instead of trusting the report.
- [EPT-SK-016] Probe the layer above before changing the request: Classify a failure by layer (network, host, route, query) before editing code.
- [EPT-SK-017] Audit a received data file before analysing it: Open every file the user sends and check coverage, vintage, coordinates, duplicates and provenance before building on it.
- [EPT-SK-018] Prove the test can fail: Run the check on a known-bad build or input and show it fails there and passes on the fixed one.
- [EPT-SK-019] Pilot before retraining: Decide whether an expensive retrain is needed by checking what the changed parts actually depend on, then run a cheap pilot gate.

## Meta-lessons
- Measure the mechanism before explaining a null result; the honest null is a finding.
- Reproduce the old behaviour exactly before changing it, and make every fix a switch.
- Pair everything: same seed, same request stream, a comparator that must read zero.
- Before trusting a metric, list what else differs between the arms.
- A consumer must be written against the producer's real file; every on-screen number comes from a run.
- 'My own idea' is not 'novel'; read the search results, cite nearest prior work, narrow the claim.
- Never output a statistic or citation you did not obtain; label each number measured, assumed or published.
- Name the exact unverified step instead of saying 'should work'.
- Deliver verified increments; checkpoint before the tool or time limit hits.
- Priority and triage only change outcomes where a resource is scarce; find the bottleneck first, then assign priority there.
- A rounded table can hide a real effect and an average can dilute it; diff the raw items for the affected subset before saying 'identical'.
- Real data is not correct data: gate it against published values, build the pre-event base layer, and print its vintage.
- State the direction of each simplification's bias and rerun without it before quoting a number.
- Set the success criterion before the run; promise a method and a fair test, not a number.
- AI-chat output is not data; use primary sources with a date and a hash.
- When the user says 'purila', shrink the answer and add a toy example; do not add content.
- A test must be shown to fail on the bad version and to take the intended branch.
```
