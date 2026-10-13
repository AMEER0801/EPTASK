"""
make_traces.py -- turn an EPtask V7.1 results bundle into the data the 3D demo replays.

Everything that MOVES in the demo comes from here, computed by the V7.1 code itself:
  * corridor traces: corridor.run_trial with a recording hook, for
    3 hazard presets x 4 warning routes = 12 paired trials (same blockage and
    traffic per preset; only the warning route differs)
  * cell trace: env.VECEnv in disaster mode, driven by the exported ONNX model B,
    with C2 counterfactuals from env.peek() at every request
The hazard VISUALS (shaking, debris, water) are illustration. The simulation
models any hazard as one blocked road edge plus destroyed roadside units inside
a footprint; the presets below differ only in those parameters.

The hook is injected into the ORIGINAL run_trial source by an anchored patch,
and every trial is re-run with the untouched function: results must be equal,
otherwise the script aborts.

usage:
  python make_traces.py --bundle <demo_bundle> --eptask <eptask dir> --out demo_data.json
"""
import argparse
import inspect
import json
import math
import os
import sys
import time

import numpy as np

HAZARDS = {   # ASSUMPTION presets -- only footprint and traffic differ in the model
    "earthquake": dict(label="Earthquake", footprint_m=20000.0, traffic_vph=30.0, seed=3),
    "landslide": dict(label="Landslide", footprint_m=2000.0, traffic_vph=30.0, seed=7),
    "flood": dict(label="Outburst flood", footprint_m=12000.0, traffic_vph=30.0, seed=11),
}
# Emergency convoy staged at Bidur (Bidur was the main SAR staging ground in Aug 2026).
# Dispatch times are an ASSUMPTION. Each vehicle is simulated by corridor.run_trial as the
# trial's emergency vehicle, with the SAME blockage, traffic seed and roadside units -- one at a
# time, so convoy members do not interact. The ambulance (600 s) is the notebook's N1 vehicle.
FLEET = [("ambulance", "Ambulance", 600), ("police", "Police patrol", 720), ("fire", "Fire engine", 840),
         ("army1", "Army convoy, truck 1", 960), ("army2", "Army convoy, truck 2", 990),
         ("army3", "Army convoy, truck 3", 1020)]


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
    src = inspect.getsource(CO.run_trial)
    a = "              rsu=None):"
    b = "        if amb is not None and (amb.done or amb.stuck):\n            break\n        t += dt"
    if src.count(a) != 1 or src.count(b) != 1:
        raise SystemExit("corridor.run_trial changed shape -- update the hook anchors")
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
                    raise SystemExit(f"vehicle {vid} track is not continuous")
                r["xy"] += [x, y]
                r["last"] = fi
                if inf and r["inf"] < 0:
                    r["inf"] = fi
                if stuck and r["stuck"] < 0:
                    r["stuck"] = fi
                r["trapped"] |= trapped
        return [[vid, r["f0"], r["inf"], r["stuck"], r["trapped"] | (r["amb"] << 1)] + r["xy"]
                for vid, r in sorted(tr.items())]


def softmax(x):
    e = np.exp(x - x.max(axis=-1, keepdims=True))
    return e / e.sum(axis=-1, keepdims=True)


def cell_trace(cfg, VECEnv, OnnxPolicy, CT, onnx_path, V=30, seed=21, ticks=520, at=60, k=3, dur=360):
    pol = OnnxPolicy(onnx_path)
    S = cfg.NUM_EDGE_SERVERS
    s0 = (S - k) // 2
    kw = dict(DISASTER_MODE=True, RANDOM_DISASTERS=False, TRACK_TRUE_T=True,
              RESERVE_TOP_LEVEL=True, PRIORITY_TX=False,
              STATE_MODE=pol.cfg_kw.get("STATE_MODE", 33))
    out = []
    with cfg.override(**kw):
        env = VECEnv(cfg, V, seed=seed)
        obs = env.observe()
        tav = sorted(int(i) for i in env.tav_idx)
        edge_x = getattr(env, "edge_x", None)
        if edge_x is None:
            edge_x = (np.arange(S) + 0.5) * cfg.HIGHWAY_LENGTH_M / S
        static = dict(L=float(cfg.HIGHWAY_LENGTH_M), V=V, S=S, d_max=float(cfg.D_MAX_M),
                      edge_x=[round(float(x), 1) for x in edge_x], tav=tav,
                      dir=[int(d) for d in env.veh_dir],
                      emergency=[int(i) for i in np.flatnonzero(env.is_emergency)],
                      event=dict(at=at, s0=s0, k=k, dur=dur), seed=seed,
                      onnx=os.path.basename(onnx_path), policy="model B (DR-MEPPO)",
                      deadline_mult=dict(cfg.DEADLINE_MULT), floor_level=int(cfg.SAFETY_FLOOR_LEVEL),
                      cwp_thresholds=[float(cfg.CWP_IMMEDIATE), float(cfg.CWP_DELAYED)],
                      modalities=list(cfg.MODALITIES))
        for step in range(ticks):
            if step == at:
                env.trigger_disaster(s0, k, dur)
            i, n = int(env.cursor), int(env.n_tasks)
            m = env.request_meta()
            rec = dict(t=step, x=[round(float(v), 1) for v in env.veh_x],
                       alive=[int(b) for b in env.server_alive], i=i, n=n, role=m["role"],
                       key=m["key"], prot=int(m["prot"]), cwp=round(m["cwp"], 2), tier=m["tier"],
                       ppl=m["people"], est=m["est"], mod=m["mod"], edge_ok=int(m["edge_ok"]))
            off_l, pri_l, _ = pol.logits(obs)
            a_off, a_pri = pol.act(env, obs)
            if n:
                s, _ = env._nearest_edge(i)
                sev, _ = env._select_sev(i)
                real = []
                for a in a_off[:n]:
                    a = int(a)
                    if a in (0, 3) and s is None:
                        a = 2
                    elif a == 1 and sev is None:
                        a = 2
                    real.append(a)
                top = env._unprotected_top()
                rank = np.argsort(-np.asarray(a_pri[:n], dtype=np.float64), kind="stable")
                lvl = np.empty(n, dtype=np.int64)
                lvl[rank] = env._levels(n, top)
                if env._protected():
                    lvl[:] = cfg.SAFETY_FLOOR_LEVEL
                ex = CT.explain_decision(pol, env)
                rec.update(p=np.round(softmax(off_l[:n]).astype(np.float64), 3).tolist(), a=[int(a) for a in a_off[:n]],
                           real=real, lvl=[int(v) for v in lvl], s=-1 if s is None else int(s),
                           sev=-1 if sev is None else int(sev),
                           cf=[round(c["T"], 3) for c in ex["counterfactual"]],
                           cfi=[int(c["infeasible"]) for c in ex["counterfactual"]],
                           kx=ex["explained_task"])
            obs, r, inf = env.step(a_off, a_pri)
            rec.update(T=round(inf["T"], 3), D=round(cfg.DEADLINE_MULT[m["key"]] * inf["Tl"], 3))
            out.append(rec)
        settled = {(round(mm["t"], 3), mm["veh"]): tT
                   for (tT, _rep, _loc, _tag), mm in zip(env.true_pairs, env.true_meta)}
    for rec in out:
        key = (round(float(rec["t"]), 3), rec["i"])
        if key in settled:
            rec["Tt"] = round(settled[key], 3)
            rec["ok"] = int(settled[key] <= rec["D"])
    static["ticks"] = out
    return static


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--eptask", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--frame-dt", type=float, default=60.0)
    ap.add_argument("--start", type=float, default=-600.0)
    args = ap.parse_args()
    sys.path.insert(0, os.path.abspath(args.eptask))
    import corridor as CO
    import contributions as CT
    from config import Config
    from env import VECEnv
    from policies import OnnxPolicy

    t0 = time.time()
    B = args.bundle
    R = json.load(open(os.path.join(B, "results_v71.json")))
    G = CO.graph_from_json(json.load(open(os.path.join(B, "corridor_graph.json"))))
    lat_raw = json.load(open(os.path.join(B, "latency_samples.json")))
    LAT = {k: dict(T=np.asarray(v["T"], float), D=np.asarray(v["D"], float)) for k, v in lat_raw.items()}
    lat = LAT.get("floor ON") or next(iter(LAT.values()))
    pts = []
    pp = os.path.join(B, "coolr_points.json")
    if os.path.exists(pp):
        pts = json.load(open(pp)).get("points", []) or []
    coolr = CO.coolr_xy(G, pts)

    # ---------------- graph + routes for rendering ----------------
    o, d = G.graph["origin"], G.graph["dest"]
    jn = G.graph.get("junction_node", G.graph["junction"])
    p = G.graph["open_path"]
    cands = G.graph["cands"]
    pb, db = CO.tree(G, d, blocked=cands[len(cands) // 2])
    q = CO.path_from(pb, o, d)
    xy = lambda n: [round(G.nodes[n]["x"], 1), round(G.nodes[n]["y"], 1)]
    ji = p.index(jn) if jn in p else 0
    qi = q.index(jn) if jn in q else 0
    edges = [[int(u), int(v), dd.get("route", "")] for u, v, dd in G.edges(data=True)]
    if len(edges) > 25000:                       # big OSM extracts: keep the two routes only
        keep = set(zip(p[:-1], p[1:])) | set(zip(q[:-1], q[1:]))
        edges = [e for e in edges if (e[0], e[1]) in keep or (e[1], e[0]) in keep]
    used = {e[0] for e in edges} | {e[1] for e in edges} | set(G.graph.get("named", {}).values())
    allx = [G.nodes[n]["x"] for n in G]
    ally = [G.nodes[n]["y"] for n in G]
    graph = dict(source=G.graph.get("source", ""),
                 nodes=[[int(n)] + xy(n) + [G.nodes[n].get("name", "")] for n in G if n in used],
                 edges=edges, origin=int(o), dest=int(d), junction=int(jn),
                 named={k: int(v) for k, v in G.graph.get("named", {}).items()},
                 routes=dict(access=[xy(n) for n in p[:ji + 1]], valley=[xy(n) for n in p[ji:]],
                             hill=[xy(n) for n in q[qi:]]),
                 bbox=[min(allx), min(ally), max(allx), max(ally)],
                 coolr=[[round(float(a), 1), round(float(b), 1)] for a, b in coolr])

    # ---------------- corridor traces ----------------
    run_rec = hooked_run_trial(CO)
    corridor = {}
    for hname, hp in HAZARDS.items():
        rng = np.random.default_rng(hp["seed"])
        for _ in range(60):
            e = cands[int(rng.integers(len(cands)))]
            trees = CO.build_trees(G, e)
            if o in trees[(d, True)][1]:
                break
        P = dict(CO.DEFAULTS, footprint_m=hp["footprint_m"], traffic_vph=hp["traffic_vph"])
        rsu = CO.place_rsus(G, e, P, trees)
        ex, ey = (G.nodes[e[0]]["x"] + G.nodes[e[1]]["x"]) / 2, (G.nodes[e[0]]["y"] + G.nodes[e[1]]["y"]) / 2
        for mode in CO.INFO_MODES:
            seed = hp["seed"] * 100 + 1
            runs = {}
            for key, label, disp in FLEET:
                Pk = dict(P, dispatch_s=float(disp))
                rec = Recorder(args.start, args.frame_dt)
                res = run_rec(G, mode, lat, seed=seed, hazard=e, params=Pk, trees=trees, rsu=rsu, _rec=rec)
                if key in ("ambulance", FLEET[-1][0]):     # prove the hook changes nothing
                    ref = CO.run_trial(G, mode, lat, seed=seed, hazard=e, params=Pk, trees=trees, rsu=rsu)
                    if json.dumps(jsonable(res), sort_keys=True) != json.dumps(jsonable(ref), sort_keys=True):
                        raise SystemExit(f"recording hook changed the result for {hname}/{mode}/{key}")
                runs[key] = (rec, res)
            arec, ares = runs["ambulance"]
            crec, cres = runs[FLEET[-1][0]]          # longest run: civilian traffic shown until the convoy arrives
            summ = {k: v for k, v in ares.items() if k not in ("cov_t", "cov_f")}
            fleet = []
            for key, label, disp in FLEET[1:]:
                rec, res = runs[key]
                rows = [[r[0], r[1], r[2], r[3] | r[4] << 1 | r[5] << 2 | r[6] << 3 | r[7] << 4 | r[8] << 5 | r[9] << 6]
                        for r in rec.amb]
                if len(rows) > 1:
                    if (len(rows) - 1) % 3:
                        rows = rows[::3] + [rows[-1]]
                    else:
                        rows = rows[::3]
                fleet.append(dict(key=key, label=label, dispatch_s=disp, track=rows,
                                  summary=jsonable({k: res[k] for k in ("arrival_min", "oracle_min", "extra_min",
                                                                         "missed_junction", "informed_min",
                                                                         "saw_block", "unreachable")})))
            corridor[f"{hname}|{mode}"] = dict(
                hazard=hname, mode=mode, frame_dt=args.frame_dt, t0=crec.frames[0][0],
                n_frames=len(crec.frames), frame_t=[f[0] for f in crec.frames], veh=crec.tracks(),
                amb=arec.amb, rsu_t=crec.rsu_t, summary=jsonable(summ), fleet=fleet,
                civilians_from=FLEET[-1][1],
                coverage=[[round(a_, 1), None if b_ is None or not math.isfinite(b_) else round(b_, 3)]
                          for a_, b_ in zip(cres["cov_t"], cres["cov_f"])],
                hazard_edge=[xy(e[0]), xy(e[1])], hazard_mid=[round(ex, 1), round(ey, 1)],
                rsu=dict(xy=[[round(float(a_), 1), round(float(b_), 1)] for a_, b_ in rsu[0]],
                         alive=[int(v) for v in rsu[1]]),
                params=dict(footprint_m=P["footprint_m"], traffic_vph=P["traffic_vph"],
                            v2v_range_m=P["v2v_range_m"], rsu_range_m=P["rsu_range_m"],
                            rsu_spacing_m=P["rsu_spacing_m"], dispatch_s=P["dispatch_s"], dt=P["dt"]))
            s = summ
            print(f"  {hname:<10} {mode:<8} civilians={len(crec.ids):4d} frames={len(crec.frames):4d} "
                  f"ambulance extra={s['extra_min']:.1f} min  convoy arrivals (min)=" +
                  ",".join(f"{f['summary']['arrival_min']:.0f}" for f in fleet))

    # ---------------- cell trace (model B through the real env) ----------------
    onnx_b = os.path.join(B, "onnx", "meppo_B_v30.onnx")
    cfg = Config.derive()
    cfg.PRIORITY_TX = False
    cell = cell_trace(cfg, VECEnv, OnnxPolicy, CT, onnx_b)
    n_det = sum(1 for r in cell["ticks"] if r["role"] == 2)
    n_em = sum(1 for r in cell["ticks"] if r["role"] == 1)
    print(f"  cell: {len(cell['ticks'])} ticks, {n_det} detections, {n_em} emergency requests")

    data = dict(meta=dict(generated=time.strftime("%Y-%m-%d %H:%M:%S"), generator="make_traces.py v1",
                          run_id=R["run"]["run_id"], mode=R["run"]["mode"], data_mode=R["data"]["mode"],
                          code_digest=R["run"]["code_digest"],
                          hazards={k: dict(label=v["label"], footprint_m=v["footprint_m"],
                                           traffic_vph=v["traffic_vph"]) for k, v in HAZARDS.items()},
                          modes=list(CO.INFO_MODES), fleet=[dict(key=k, label=l, dispatch_s=t) for k, l, t in FLEET], latency_arm="floor ON" if "floor ON" in LAT else list(LAT)[0]),
                results=R, graph=graph, corridor=corridor, cell=cell)
    with open(args.out, "w") as fh:
        json.dump(jsonable(data), fh, separators=(",", ":"))
    print(f"wrote {args.out}: {os.path.getsize(args.out) / 1e6:.2f} MB in {time.time() - t0:.0f}s "
          f"(all 12 corridor trials identical with and without the recorder)")


if __name__ == "__main__":
    main()
