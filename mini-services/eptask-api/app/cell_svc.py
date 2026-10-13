"""app/cell_svc.py -- live VEC-cell (micro-scale) simulation service.

Runs the ORIGINAL env.VECEnv, driven by the shipped ONNX export of a trained
MEPPO policy (model A static / model B disaster-responsive), with C2
counterfactual explanations from the ORIGINAL contributions.explain_decision.
This is the same pipeline that produced the demo's cell trace
(tools/make_traces.py: cell_trace), exposed as a live request.
"""
from __future__ import annotations

import json
import math
import time

import numpy as np

from .state import STATE

POLICY_LABEL = {"A": "model A (static MEPPO)", "B": "model B (DR-MEPPO)"}


def _softmax(x):
    e = np.exp(x - x.max(axis=-1, keepdims=True))
    return e / e.sum(axis=-1, keepdims=True)


def run_cell(params: dict, progress=None) -> dict:
    """Params (validated by the caller):
      policy     A|B
      version    10|30|50
      V          4..60 vehicles
      seed       int >= 0
      ticks      20..3000
      event      {at, k, dur}  -- scripted RSU outage + sensing window
      floor      safety/emergency floor on (default) or off
      explain    attach per-tick counterfactual explanations (default true)
    """
    from config import Config        # original eptask module
    from env import VECEnv           # original eptask module
    import contributions as CT       # original eptask module

    t_wall = time.time()
    model, version = params["policy"], int(params["version"])
    V, seed = int(params["V"]), int(params["seed"])
    ticks = int(params["ticks"])
    ev = params["event"]
    at, k, dur = int(ev["at"]), int(ev["k"]), int(ev["dur"])
    floor = bool(params.get("floor", True))
    explain = bool(params.get("explain", True))
    S_cfg = Config.NUM_EDGE_SERVERS
    if at + dur >= ticks:
        raise ValueError("event.at + event.dur must be < ticks (the outage must end inside the run)")
    if not 1 <= k <= S_cfg:
        raise ValueError(f"event.k must be within 1..{S_cfg}")
    pol = STATE.policy(model, version)
    cfg = Config.derive()
    cfg.PRIORITY_TX = False
    S = cfg.NUM_EDGE_SERVERS
    s0 = (S - k) // 2
    kw = dict(DISASTER_MODE=True, RANDOM_DISASTERS=False, TRACK_TRUE_T=True,
              RESERVE_TOP_LEVEL=True, PRIORITY_TX=False,
              USE_SAFETY_FLOOR=floor, USE_EMERGENCY_FLOOR=floor,
              STATE_MODE=pol.cfg_kw.get("STATE_MODE", 33))

    report = progress or (lambda f, s=None: None)
    report(0.02, "building environment")
    out = []
    t0 = time.time()
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
                      onnx=f"meppo_{model}_v{version}.onnx", policy=POLICY_LABEL[model],
                      deadline_mult=dict(cfg.DEADLINE_MULT),
                      floor_level=int(cfg.SAFETY_FLOOR_LEVEL),
                      cwp_thresholds=[float(cfg.CWP_IMMEDIATE), float(cfg.CWP_DELAYED)],
                      modalities=list(cfg.MODALITIES),
                      generator="env.VECEnv + OnnxPolicy (eptask v7.1, executed live)")
        for step in range(ticks):
            if step == at:
                env.trigger_disaster(s0, k, dur)
            i, n = int(env.cursor), int(env.n_tasks)
            m = env.request_meta()
            rec = dict(t=step, x=[round(float(v), 1) for v in env.veh_x],
                       alive=[int(b) for b in env.server_alive], i=i, n=n, role=m["role"],
                       key=m["key"], prot=int(m["prot"]), cwp=round(m["cwp"], 2), tier=m["tier"],
                       ppl=m["people"], est=m["est"], mod=m["mod"], edge_ok=int(m["edge_ok"]))
            a_off, a_pri = pol.act(env, obs)          # the policy acts every tick
            if n:
                if explain:
                    ex = CT.explain_decision(pol, env)
                    off_l, pri_l, _ = pol.logits(obs)
                else:
                    ex = None
                    off_l, pri_l, _ = pol.logits(obs)
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
                rec.update(p=np.round(_softmax(off_l[:n]).astype(np.float64), 3).tolist(),
                           a=[int(a) for a in a_off[:n]], real=real,
                           lvl=[int(v) for v in lvl], s=-1 if s is None else int(s),
                           sev=-1 if sev is None else int(sev))
                if ex is not None:
                    rec.update(cf=[round(c["T"], 3) for c in ex["counterfactual"]],
                               cfi=[int(c["infeasible"]) for c in ex["counterfactual"]],
                               kx=ex["explained_task"])
            obs, r, inf = env.step(a_off, a_pri)
            rec.update(T=round(inf["T"], 3), D=round(cfg.DEADLINE_MULT[m["key"]] * inf["Tl"], 3))
            out.append(rec)
            if step % max(1, ticks // 20) == 0:
                report(0.02 + 0.9 * step / ticks, f"tick {step}/{ticks}")
        settled = {(round(mm["t"], 3), mm["veh"]): tT
                   for (tT, _rep, _loc, _tag), mm in zip(env.true_pairs, env.true_meta)}
        settled_meta = {(round(mm["t"], 3), mm["veh"]): mm
                        for (_tT, _rep, _loc, _tag), mm in zip(env.true_pairs, env.true_meta)}
    for rec in out:
        key = (round(float(rec["t"]), 3), rec["i"])
        if key in settled:
            rec["Tt"] = round(settled[key], 3)
            rec["ok"] = int(settled[key] <= rec["D"])

    # ---- honest summary over SETTLED requests ----
    rows = [r for r in out if "Tt" in r]
    def _blk(sel):
        if not sel:
            return dict(n=0, mean_T=None, miss_pct=None)
        T = np.array([r["Tt"] for r in sel]); D = np.array([r["D"] for r in sel])
        return dict(n=len(sel), mean_T=round(float(T.mean()), 3),
                    miss_pct=round(float(100.0 * (T > D).mean()), 2))
    win = (at, at + dur)
    summary = dict(
        settled=len(rows), pending=ticks - len(rows),
        all=_blk(rows),
        outage=_blk([r for r in rows if win[0] <= r["t"] < win[1]]),
        emergency=_blk([r for r in rows if r["role"] == 1]),
        emergency_outage=_blk([r for r in rows if r["role"] == 1 and win[0] <= r["t"] < win[1]]),
        protected=_blk([r for r in rows if r["prot"]]),
    )
    # realised target shares over the whole run (from settled recs' real arrays)
    tg = [0, 0, 0, 0]
    for r in out:
        if "real" in r:
            for a in r["real"]:
                tg[int(a)] += 1
    tot = sum(tg) or 1
    summary["targets"] = {"edge": round(100 * tg[0] / tot, 2), "v2v": round(100 * tg[1] / tot, 2),
                          "local": round(100 * tg[2] / tot, 2), "cloud": round(100 * tg[3] / tot, 2)}
    n_det = sum(1 for r in out if r["role"] == 2)
    n_em = sum(1 for r in out if r["role"] == 1)
    static["counts"] = dict(detections=n_det, emergency=n_em, settled=len(rows))
    report(1.0, "done")
    return dict(config=static, ticks=out, summary=summary,
                timing=dict(sim_seconds=round(time.time() - t0, 3),
                            total_seconds=round(time.time() - t_wall, 3)))
