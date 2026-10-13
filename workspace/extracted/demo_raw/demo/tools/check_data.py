"""Validate demo_data.json before building: structure, monotonic clocks, finite numbers. Exit 1 on any problem."""
import json, math, sys
d = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "demo_data.json"))
bad = []
def fin(*v): return all(isinstance(x, (int, float)) and math.isfinite(x) for x in v)
for k in ("meta", "results", "graph", "corridor", "cell"):
    if k not in d: bad.append("missing section " + k)
tr = d.get("corridor", {})
if len(tr) != len(d["meta"]["hazards"]) * len(d["meta"]["modes"]): bad.append(f"expected {len(d['meta']['hazards']) * len(d['meta']['modes'])} traces, found {len(tr)}")
for key, t in tr.items():
    ft = t["frame_t"]
    if any(b <= a for a, b in zip(ft, ft[1:])): bad.append(key + ": frame clock not increasing")
    for r in t["veh"]:
        if (len(r) - 5) % 2 or r[1] < 0 or r[1] + (len(r) - 5) // 2 > len(ft): bad.append(f"{key}: vehicle {r[0]} track out of range"); break
    for name, rows in [("ambulance", t["amb"])] + [(f["label"], f["track"]) for f in t.get("fleet", [])]:
        ts = [r[0] for r in rows]
        if not rows or any(b < a for a, b in zip(ts, ts[1:])): bad.append(f"{key}: {name} clock not increasing"); continue
        if not all(fin(r[1], r[2]) for r in rows): bad.append(f"{key}: {name} has non-finite positions")
    if len(t["rsu"]["xy"]) != len(t["rsu"]["alive"]): bad.append(key + ": roadside unit arrays differ in length")
    if not fin(*t["hazard_mid"]): bad.append(key + ": hazard position not finite")
    if len(t.get("fleet", [])) != len(d["meta"].get("fleet", [])) - 1: bad.append(key + ": convoy incomplete")
c = d["cell"]
if any(len(r["x"]) != c["V"] or len(r["alive"]) != c["S"] for r in c["ticks"]): bad.append("cell: tick arrays have the wrong size")
print(f"traces {len(tr)}, convoy per trace {len(d['meta'].get('fleet', []))}, cell ticks {len(c['ticks'])}, run {d['meta']['run_id']} ({d['meta']['mode']})")
print("DATA OK" if not bad else "DATA PROBLEMS:\n  " + "\n  ".join(bad[:20])); sys.exit(1 if bad else 0)
