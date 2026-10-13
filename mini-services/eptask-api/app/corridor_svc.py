"""app/corridor_svc.py -- live road-scale (N1) simulation service.

Runs the ORIGINAL corridor.py `run_trial` on demand and records vehicle
trajectories with the same anchoring-hook + Recorder approach that the demo's
tools/make_traces.py used, so a recorded live run is bit-identical to an
unrecorded one (verified after every ambulance / convoy trial, like
make_traces.py does).

Nothing here re-implements the notebook's algorithm: blockages, V2V relay,
RSUs, store-carry-forward, micro-latency retries all come from core/corridor.py.
"""
from __future__ import annotations

import inspect
import json
import math
import time

import numpy as np

from .state import STATE

# --- verbatim from the demo's tools/make_traces.py (demo.zip), attributed ---
HAZARDS = {   # ASSUMPTION presets -- only footprint and traffic differ in the model
    "earthquake": dict(label="Earthquake", footprint_m=20000.0, traffic_vph=30.0, seed=3),
    "landslide": dict(label="Landslide", footprint_m=2000.0, traffic_vph=30.0, seed=7),
    "flood": dict(label="Outburst flood", footprint_m=12000.0, traffic_vph=30.0, seed=11),
}
# Emergency convoy staged at Bidur. Dispatch times are an ASSUMPTION in
# make_traces.py; each member is simulated by corridor.run_trial as the trial's
# emergency vehicle with the SAME blockage, traffic seed and roadside units,
# one at a time, so convoy members do not interact.
FLEET = [("ambulance", "Ambulance", 600), ("police", "Police patrol", 720),
         ("fire", "Fire engine", 840), ("army1", "Army convoy, truck 1", 960),
         ("army2", "Army convoy, truck 2", 990), ("army3", "Army convoy, truck 3", 1020)]
SUMMARY_KEYS = ("arrival_min", "oracle_min", "extra_min", "missed_junction",
                "informed_min", "saw_block", "unreachable", "service_wait_s",
                "trapped", "civilians", "rsu_alive", "rsu_verified_s")


def jsonable(o):
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    if isinstance(o, np.ndarray):
        return jsonable(o.tolist())
    if isinstance(o, (np.bool_, bool)):
        return bool(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return f if math.isfinite(f) else None
    return o


def hooked_run_trial(CO):
    """Original demo-builder technique: inject a recording hook into
    corridor.run_trial's source between two anchored lines, exec it, and
    verify on the caller's side that recorded and unrecorded runs agree."""
    src = inspect.getsource(CO.run_trial)
    a = "              rsu=None):"
    b = "        if amb is not None and (amb.done or amb.stuck):\n            break\n        t += dt"
    if src.count(a) != 1 or src.count(b) != 1:
        raise RuntimeError("corridor.run_trial changed shape -- update the hook anchors")
    src = src.replace(a, "              rsu=None, _rec=None):")
    src = src.replace(b, "        if _rec is not None:\n            _rec(t, vehs, amb, state, pos)\n" + b)
    ns = dict(vars(CO))
    exec(compile(src, "<run_trial+recorder>", "exec"), ns)
    return ns["run_trial"]


class Recorder:
    def __init__(self, t_start, frame_dt):
        self.t_start, self.fdt, self.next_t = t_start, frame_dt, t_start
        self.frames, self.amb, self.ids, self.rsu_t = [], [], {}, None

    def __call__(self, t, vehs, amb, state, pos):
        if amb is not None and t >= self.t_start:
            x, y = pos(amb)
            self.amb.append([round(t, 1), round(x / 10), round(y / 10), int(amb.inf),
                             int(amb.reroute_at is not None), int(amb.passed), int(amb.seen),
                             int(amb.missed), int(amb.stuck), int(amb.done)])
        if state.get("rsu_t") is not None:
            self.rsu_t = state["rsu_t"]
        if t + 1e-9 >= self.next_t:
            fr = {}
            for v in vehs:
                if v.done:
                    continue
                vid = self.ids.setdefault(id(v), len(self.ids))
                x, y = pos(v)
                fr[vid] = (round(x / 10), round(y / 10), int(v.inf), int(v.stuck),
                           int(v.trapped), int(v.amb))
            self.frames.append((round(t, 1), fr))
            self.next_t += self.fdt

    def tracks(self):
        tr = {}
        for fi, (_, fr) in enumerate(self.frames):
            for vid, (x, y, inf, stuck, trapped, isamb) in fr.items():
                r = tr.setdefault(vid, dict(f0=fi, last=fi - 1, xy=[], inf=-1, stuck=-1,
                                            trapped=0, amb=isamb))
                if fi != r["last"] + 1:
                    raise RuntimeError(f"vehicle {vid} track is not continuous")
                r["xy"] += [x, y]
                r["last"] = fi
                if inf and r["inf"] < 0:
                    r["inf"] = fi
                if stuck and r["stuck"] < 0:
                    r["stuck"] = fi
                r["trapped"] |= trapped
        return [[vid, r["f0"], r["inf"], r["stuck"], r["trapped"] | (r["amb"] << 1)] + r["xy"]
                for vid, r in sorted(tr.items())]


def _pick_hazard(CO, G, preset: str, hazard_seed: int, candidate_index: int | None):
    """The demo's candidate draw: sample candidates until a detour exists.
    Deterministic in (preset | hazard_seed, candidate_index)."""
    o, d = G.graph["origin"], G.graph["dest"]
    cands = G.graph["cands"]
    if candidate_index is not None:
        if not 0 <= candidate_index < len(cands):
            raise ValueError(f"candidate_index must be 0..{len(cands) - 1}")
        e = cands[candidate_index]
        trees = CO.build_trees(G, e)
        if o not in trees[(d, True)][1]:
            raise ValueError(f"candidate {candidate_index} leaves no detour to the destination")
        return e, trees
    rng = np.random.default_rng(int(hazard_seed))
    for _ in range(60):
        e = cands[int(rng.integers(len(cands)))]
        trees = CO.build_trees(G, e)
        if o in trees[(d, True)][1]:
            return e, trees
    raise ValueError("no usable hazard candidate found for this seed (no detour in 60 draws)")


def run_corridor(params: dict, progress=None) -> dict:
    """One live corridor request. Params (validated by the caller):
      hazard       earthquake|landslide|flood|custom
      info_mode    NONE|V2V|RSU|V2V+RSU
      footprint_m  (custom only) 500..30000
      traffic_vph  (custom only) 5..120
      dispatch_s   ambulance dispatch 60..3600
      seed         traffic/latency seed (default: preset convention seed*100+1)
      latency_arm  floor ON|floor OFF
      convoy       include the 5-vehicle convoy (5 extra trials)
      trace        record + return the replayable trace
    """
    import corridor as CO  # original eptask module

    t_wall = time.time()
    hazard = params["hazard"]
    mode = params["info_mode"]
    convoy = bool(params.get("convoy", True))
    want_trace = bool(params.get("trace", True))
    arm = params.get("latency_arm") or STATE.default_latency_arm()
    lat = STATE.latency_arm(arm)
    G = STATE.graph

    preset = HAZARDS.get(hazard)
    if preset:
        footprint, vph, hseed = preset["footprint_m"], preset["traffic_vph"], preset["seed"]
    else:
        footprint = float(params.get("footprint_m", 2000.0))
        vph = float(params.get("traffic_vph", 30.0))
        hseed = int(params.get("hazard_seed", 7))
    e, trees = _pick_hazard(CO, G, hazard, hseed, params.get("candidate_index"))
    P = dict(CO.DEFAULTS, footprint_m=footprint, traffic_vph=vph)
    P["dispatch_s"] = float(params.get("dispatch_s", 600))
    seed = int(params.get("seed") if params.get("seed") is not None else hseed * 100 + 1)
    rsu = CO.place_rsus(G, e, P, trees)

    run_rec = hooked_run_trial(CO)
    report_progress = progress or (lambda f, s=None: None)

    # ---- ambulance (the notebook's N1 vehicle), recorded ----
    report_progress(0.05, "simulating ambulance")
    t0 = time.time()
    rec, res = None, None
    if want_trace:
        rec = Recorder(-600.0, float(params.get("frame_dt", 60.0)))
        res = run_rec(G, mode, lat, seed=seed, hazard=e, params=P, trees=trees, rsu=rsu, _rec=rec)
    ref = CO.run_trial(G, mode, lat, seed=seed, hazard=e, params=P, trees=trees, rsu=rsu)
    if rec is not None:
        ref2 = {k: v for k, v in ref.items()}
        got = {k: v for k, v in res.items()}
        # prove the hook changes nothing (same equality the demo builder asserted)
        if json.dumps(jsonable(got), sort_keys=True) != json.dumps(jsonable(ref2), sort_keys=True):
            raise RuntimeError("recording hook changed the simulation result -- refusing to serve it")
    t_sim = time.time() - t0
    summ = {k: jsonable(ref[k]) for k in SUMMARY_KEYS}

    # ---- convoy ----
    fleet, cov = [], None
    civ_rec = None      # civilian frames come from the LONGEST convoy run (make_traces convention)
    if convoy:
        members = FLEET[1:]
        for i, (key, label, disp) in enumerate(members):
            report_progress(0.05 + 0.9 * (i + 1) / (len(members) + 1), f"simulating {label}")
            Pk = dict(P, dispatch_s=float(disp))
            frec = Recorder(-600.0, float(params.get("frame_dt", 60.0))) if want_trace else None
            fres = run_rec(G, mode, lat, seed=seed, hazard=e, params=Pk, trees=trees, rsu=rsu,
                           _rec=frec) if frec is not None else \
                CO.run_trial(G, mode, lat, seed=seed, hazard=e, params=Pk, trees=trees, rsu=rsu)
            rows = []
            if frec is not None and frec.amb:
                rows = [[r[0], r[1], r[2], r[3] | r[4] << 1 | r[5] << 2 | r[6] << 3 | r[7] << 4 | r[8] << 5 | r[9] << 6]
                        for r in frec.amb]
                if len(rows) > 1:
                    rows = (rows[::3] + [rows[-1]]) if (len(rows) - 1) % 3 else rows[::3]
            fleet.append(dict(key=key, label=label, dispatch_s=disp, track=rows,
                              summary=jsonable({k: fres[k] for k in SUMMARY_KEYS if k in fres})))
        civ_rec = frec        # last member = army3, longest run (make_traces convention)
        cov_src = fres
    else:
        cov_src = ref
        civ_rec = rec         # without a convoy, the ambulance run frames are the trace

    xy = lambda n: [round(G.nodes[n]["x"], 1), round(G.nodes[n]["y"], 1)]
    ex, ey = (G.nodes[e[0]]["x"] + G.nodes[e[1]]["x"]) / 2, (G.nodes[e[0]]["y"] + G.nodes[e[1]]["y"]) / 2
    coverage = [[round(a_, 1), None if b_ is None or not math.isfinite(b_) else round(b_, 3)]
                for a_, b_ in zip(cov_src["cov_t"], cov_src["cov_f"])]

    out = dict(
        config=dict(
            hazard=hazard, hazard_label=(preset or {}).get("label", "Custom hazard"),
            hazard_seed=hseed, candidate_index=params.get("candidate_index"),
            info_mode=mode, seed=seed, latency_arm=arm, convoy=convoy,
            params=dict(footprint_m=P["footprint_m"], traffic_vph=P["traffic_vph"],
                        v2v_range_m=P["v2v_range_m"], rsu_range_m=P["rsu_range_m"],
                        rsu_spacing_m=P["rsu_spacing_m"], dispatch_s=P["dispatch_s"], dt=P["dt"]),
            generator="corridor.py run_trial (eptask v7.1, executed live)",
        ),
        hazard_edge=[xy(e[0]), xy(e[1])], hazard_mid=[round(ex, 1), round(ey, 1)],
        rsu=dict(xy=[[round(float(a_), 1), round(float(b_), 1)] for a_, b_ in rsu[0]],
                 alive=[int(v) for v in rsu[1]]),
        summary=summ, coverage=coverage, fleet=fleet,
        timing=dict(sim_seconds=round(t_sim, 3), total_seconds=round(time.time() - t_wall, 3)),
    )
    if want_trace and civ_rec is not None and civ_rec.frames:
        out.update(frame_dt=float(params.get("frame_dt", 60.0)),
                   t0=civ_rec.frames[0][0],
                   n_frames=len(civ_rec.frames),
                   frame_t=[f[0] for f in civ_rec.frames],
                   veh=civ_rec.tracks(),
                   amb=rec.amb if rec is not None else [],
                   rsu_t=civ_rec.rsu_t)
    report_progress(1.0, "done")
    return out


# ----------------------------------------------------------------------
# v2: side-by-side warning-network comparison
# ----------------------------------------------------------------------
def run_compare(params: dict, progress=None) -> dict:
    """One hazard scenario, two information modes, everything else identical.

    Runs the ORIGINAL run_corridor twice (convoy off -- the comparison is
    about the warning network, not convoy logistics) and returns both runs
    plus a per-metric delta (B minus A). Each run keeps its own geometry
    (hazard edge, RSUs, ambulance trace) so the UI can draw two maps.
    """
    report = progress or (lambda f, s=None: None)
    modes: list[str] = params["modes"]
    t0 = time.time()

    runs = []
    for i, mode in enumerate(modes):
        p = {k: v for k, v in params.items() if k != "modes"}
        p["info_mode"] = mode
        p["convoy"] = False
        off, scale = i / len(modes), 1.0 / len(modes)

        def cb(f, s=None, _off=off, _scale=scale, _mode=mode):
            report(_off + _scale * f, f"[{_mode}] {s}" if s else _mode)

        runs.append(run_corridor(p, cb))

    a, b = runs[0]["summary"], runs[1]["summary"]
    delta = {}
    for k in SUMMARY_KEYS:
        va, vb = a.get(k), b.get(k)
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)) \
                and isfinite_val(va) and isfinite_val(vb):
            delta[k] = round(float(vb) - float(va), 2)
        else:
            delta[k] = None

    report(1.0, "done")
    return dict(
        config=dict(
            modes=modes, hazard=params["hazard"],
            hazard_label=runs[0]["config"]["hazard_label"],
            hazard_seed=runs[0]["config"]["hazard_seed"],
            candidate_index=params.get("candidate_index"),
            dispatch_s=params.get("dispatch_s", 600),
            seed=runs[0]["config"]["seed"], latency_arm=runs[0]["config"]["latency_arm"],
            params=runs[0]["config"]["params"],
            generator="corridor.py run_trial (eptask v7.1, executed live, x2)",
        ),
        delta=delta,
        runs=runs,
        timing=dict(total_seconds=round(time.time() - t0, 3)),
    )


def isfinite_val(v) -> bool:
    return math.isfinite(float(v))
