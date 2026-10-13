import json
import sys

sys.path.insert(0, "/home/z/my-project/mini-services/eptask-api")
from app.corridor_svc import run_corridor
from app.state import STATE

STATE.load()
DEMO = json.load(open("/home/z/my-project/workspace/extracted/demo_raw/demo/demo_data.json"))
ref = DEMO["corridor"]["earthquake|NONE"]
out = run_corridor(dict(hazard="earthquake", info_mode="NONE", convoy=False, trace=True))

print("frame_t: mine", len(out["frame_t"]), "ref", len(ref["frame_t"]))
print("first frame_t:", out["frame_t"][:3], "vs", ref["frame_t"][:3])
print("last frame_t:", out["frame_t"][-3:], "vs", ref["frame_t"][-3:])
print("t0:", out["t0"], "ref t0:", ref["frame_t"][0])
print("amb equal:", out["amb"] == ref["amb"], "amb len:", len(out["amb"]), len(ref["amb"]))
print("rsu_t mine:", out.get("rsu_t"), "ref rsu_t:", ref.get("rsu_t"))
print("summary extra:", out["summary"]["extra_min"], "ref:", ref["summary"]["extra_min"])
print("coverage len mine:", len(out["coverage"]), "ref:", len(ref["coverage"]))

# find first differing frame
myv = out["veh"]
rv = ref["veh"]
print("veh lens:", len(myv), len(rv))
for i, (a, b) in enumerate(zip(myv, rv)):
    if a != b:
        print(f"first veh diff at track idx {i}: mine {a[:8]}... ref {b[:8]}...")
        break
else:
    print("common prefix identical; one is a prefix of the other or tail differs")
# check ids
ma = [r[0] for r in myv]; ra = [r[0] for r in rv]
print("id sets equal:", set(ma) == set(ra), "mine-only:", sorted(set(ma) - set(ra))[:10], "ref-only:", sorted(set(ra) - set(ma))[:10])
