"""
novelties.py -- N1 and N2 evidence INSIDE the VEC cell (micro scale, V7.1).

One mechanism, three selection rules. C1 showed that a deterministic floor
works only for a RARE, identified subset, because general priority cannot beat
FIFO (the replication's central finding). N1 and N2 are new SELECTION RULES for
that same floor -- vehicle role (N1) and casualty tier (N2) -- evaluated in a
disaster: a contiguous block of RSUs is down and victim detections arrive.

  n1_emergency      EMERGENCY-class miss rate and latency during an RSU outage,
                    for each policy, floor OFF / ON. (A priority transmit lane,
                    PRIORITY_TX / 802.11p EDCA, was measured and dropped: queues
                    are per SENDER, and an emergency vehicle's uplink only ever
                    holds its own top-priority work -- the lane gives it nothing.
                    Placement and the shared execution queues are the levers.)
  n2_casualty       CWP floor OFF / ON / ON with the original time decay, scored
                    on ground truth: value-weighted on-time rate (weight =
                    log1p(TRUE people)) and on-time rate of large groups.
  floor_dilution    The limit of the mechanism: widen the floor and watch a
                    FIXED, always-protected core (ASIL-D + EMERGENCY). Random
                    policy and shared seeds, so the arms are paired.
  latency_samples   EMERGENCY-class (T, deadline) pairs during an outage --
                    the hand-off from this micro model to corridor.py.

Every function returns (figure_path, result_dict) and keeps the per-seed raw
values, so each printed mean can be recomputed.
"""
import math
import os

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from disaster import ROLE_EMERGENCY, ROLE_SENSING
from policies import RulePolicy, rollout, summarize, window_share
from runlog import mean_ci, fmt_ci

PALETTE = ["#1f4e79", "#c0392b", "#7f8c8d", "#e6a020", "#2e7d32", "#8e44ad",
           "#00838f", "#6d4c41", "#ad1457"]

N1_ARMS = (("floor OFF", dict(USE_EMERGENCY_FLOOR=False)),
           ("floor ON", dict(USE_EMERGENCY_FLOOR=True)))
N2_ARMS = (("CWP off", dict(USE_CWP_FLOOR=False)),
           ("CWP floor", dict(USE_CWP_FLOOR=True, CWP_AGE_MODE="none")),
           ("CWP floor + decay", dict(USE_CWP_FLOOR=True, CWP_AGE_MODE="decay")))


def _save(fig, outdir, name):
    os.makedirs(outdir, exist_ok=True)
    p = os.path.join(outdir, name)
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return p


def middle_block(cfg, k):
    return (cfg.NUM_EDGE_SERVERS - k) // 2


def _bar_ci(ax, x, ci, **kw):
    ax.bar(x, ci[0] if np.isfinite(ci[0]) else 0.0,
           yerr=0.0 if not np.isfinite(ci[1]) else ci[1], capsize=3, **kw)


# ======================================================================
# N1 -- emergency vehicles during an RSU outage
# ======================================================================
def n1_emergency(cfg, factories, outdir, counts=(10, 30, 50), seeds=(0, 1), at=600,
                 k=3, dur=1200, settle=300, env_kw=None, fname="n1_emergency.png"):
    s0 = middle_block(cfg, k)
    steps = at + dur + settle
    base = dict(env_kw or {})
    base.update(DISASTER_MODE=True, RESERVE_TOP_LEVEL=True)
    res = {}
    print(f"N1  emergency requests during a {k}-RSU outage [{at}, {at + dur}) s "
          f"(RSUs {s0}..{s0 + k - 1}), {len(seeds)} seeds")
    for pname, fac in factories.items():
        for aname, akw in N1_ARMS:
            key = f"{pname} | {aname}"
            rows = []
            for V in counts:
                em_miss, em_T, qm_miss, v2v, loc, share = [], [], [], [], [], []
                for sd in seeds:
                    pol = fac(V, sd)
                    if pol is None:
                        continue
                    R = rollout(cfg, V, pol, steps, sd, kw={**base, **akw},
                                events=[(at, s0, k, dur)])
                    em = summarize(R["req"], pred=lambda q: q["role"] == ROLE_EMERGENCY,
                                   t0=at, t1=at + dur)
                    qm = summarize(R["req"], pred=lambda q: q["key"] == "QM", t0=at, t1=at + dur)
                    em_miss.append(em["miss"]); em_T.append(em["T"]); qm_miss.append(qm["miss"])
                    v2v.append(window_share(R["step"], at, at + dur, 1))
                    loc.append(window_share(R["step"], at, at + dur, 2))
                    share.append(100.0 * R["n_emergency"] / max(R["n_tav"], 1))
                if not em_miss:
                    continue
                rows.append(dict(V=V, em_miss=mean_ci(em_miss), em_T=mean_ci(em_T),
                                 qm_miss=mean_ci(qm_miss), v2v=mean_ci(v2v), local=mean_ci(loc),
                                 emergency_share=mean_ci(share),
                                 raw=dict(em_miss=em_miss, em_T=em_T, qm_miss=qm_miss,
                                          v2v=v2v, local=loc)))
                r = rows[-1]
                print(f"    V={V:2d} {key:<34} EMERGENCY miss {fmt_ci(r['em_miss'], 1, '%'):<22} "
                      f"T {fmt_ci(r['em_T'], 2, 's'):<22} QM miss {fmt_ci(r['qm_miss'], 1, '%'):<22} "
                      f"V2V share {fmt_ci(r['v2v'], 1, '%')}")
            if rows:
                res[key] = rows

    fig, ax = plt.subplots(1, 3, figsize=(16.5, 4.4))
    styles = ("s--", "o-", "D-")
    for j, (key, rows) in enumerate(res.items()):
        pname, aname = key.split(" | ")
        col = PALETTE[list(factories).index(pname) % len(PALETTE)]
        mk = styles[[a for a, _ in N1_ARMS].index(aname)]
        Vs = [r["V"] for r in rows]
        for a_, m in ((ax[0], "em_miss"), (ax[1], "qm_miss"), (ax[2], "v2v")):
            cis = [r[m] for r in rows]
            a_.errorbar(Vs, [c[0] for c in cis], yerr=[0 if not np.isfinite(c[1]) else c[1] for c in cis],
                        fmt=mk, color=col, capsize=3, lw=1.5, label=key)
    ax[0].set_ylabel("EMERGENCY deadline miss (%)")
    ax[0].set_title("N1(a) emergency requests during the outage")
    ax[1].set_ylabel("QM deadline miss (%)")
    ax[1].set_title("N1(b) cost to ordinary traffic")
    ax[2].set_ylabel("tasks served by V2V during outage (%)")
    ax[2].set_title("N1(c) does the policy use V2V when RSUs die?")
    for a_ in ax:
        a_.set_xlabel("number of vehicles"); a_.grid(alpha=.3)
    ax[0].legend(fontsize=6.5)
    return _save(fig, outdir, fname), dict(counts=list(counts), seeds=list(seeds),
                                           event=dict(at=at, s0=s0, k=k, dur=dur), arms=res)


# ======================================================================
# N2 -- casualty-weighted priority
# ======================================================================
def n2_casualty(cfg, policy_factory, outdir, V=30, seeds=(0, 1), at=600, k=3, dur=1200,
                settle=300, label="policy", env_kw=None, fname="n2_casualty.png"):
    s0 = middle_block(cfg, k)
    steps = at + dur + settle
    base = dict(env_kw or {})
    base.update(DISASTER_MODE=True, RESERVE_TOP_LEVEL=True)
    wtrue = lambda q: math.log1p(q["people"])
    res = {}
    print(f"N2  victim detections during a {k}-RSU outage, V={V}, {len(seeds)} seeds, {label}")
    for aname, akw in N2_ARMS:
        vals = {m: [] for m in ("value_ontime", "big_ontime", "sens_miss", "imm_miss",
                                "protected_share", "qm_miss", "n_sensing", "n_immediate")}
        for sd in seeds:
            pol = policy_factory(V, sd)
            if pol is None:
                continue
            R = rollout(cfg, V, pol, steps, sd, kw={**base, **akw}, events=[(at, s0, k, dur)])
            sens = summarize(R["req"], pred=lambda q: q["role"] == ROLE_SENSING,
                             t0=at, t1=at + dur, weight=wtrue)
            big = summarize(R["req"], pred=lambda q: q["role"] == ROLE_SENSING and q["people"] >= 4,
                            t0=at, t1=at + dur)
            imm = summarize(R["req"], pred=lambda q: q["role"] == ROLE_SENSING and q["tier"] == 3,
                            t0=at, t1=at + dur)
            qm = summarize(R["req"], pred=lambda q: q["key"] == "QM", t0=at, t1=at + dur)
            t = R["step"]["t"]
            w = (t >= at) & (t < at + dur)
            vals["value_ontime"].append(sens["wontime"])
            vals["big_ontime"].append(100.0 - big["miss"] if big["n"] else float("nan"))
            vals["sens_miss"].append(sens["miss"]); vals["imm_miss"].append(imm["miss"])
            vals["protected_share"].append(100.0 * float(R["step"]["prot"][w].mean()))
            vals["qm_miss"].append(qm["miss"])
            vals["n_sensing"].append(sens["n"]); vals["n_immediate"].append(imm["n"])
        res[aname] = {m: mean_ci(v) for m, v in vals.items()}
        res[aname]["raw"] = vals
        r = res[aname]
        print(f"    {aname:<20} value-weighted on-time {fmt_ci(r['value_ontime'], 1, '%'):<22} "
              f"large groups (>=4) on-time {fmt_ci(r['big_ontime'], 1, '%'):<22} "
              f"protected share {fmt_ci(r['protected_share'], 1, '%'):<20} QM miss {fmt_ci(r['qm_miss'], 1, '%')}")

    names = [a for a, _ in N2_ARMS]
    fig, ax = plt.subplots(1, 2, figsize=(12.6, 4.3))
    x = np.arange(len(names))
    for j, (m, lab) in enumerate((("value_ontime", "value-weighted (log1p people)"),
                                  ("big_ontime", "large groups, >= 4 people"))):
        for i, a in enumerate(names):
            _bar_ci(ax[0], x[i] + (j - 0.5) * 0.38, res[a][m], width=0.36,
                    color=PALETTE[[0, 4][j]], label=lab if i == 0 else None)
    for i, a in enumerate(names):
        _bar_ci(ax[1], x[i] - 0.19, res[a]["protected_share"], width=0.36, color=PALETTE[3],
                label="protected share of traffic" if i == 0 else None)
        _bar_ci(ax[1], x[i] + 0.19, res[a]["qm_miss"], width=0.36, color=PALETTE[2],
                label="QM miss (cost)" if i == 0 else None)
    for a_ in ax:
        a_.set_xticks(x); a_.set_xticklabels(names); a_.grid(alpha=.3, axis="y"); a_.legend(fontsize=8)
    ax[0].set_ylabel("detections processed on time (%)")
    ax[0].set_title(f"N2(a) casualty outcomes, scored on TRUE head-count ({label})")
    ax[1].set_ylabel("%")
    ax[1].set_title("N2(b) what protection costs")
    return _save(fig, outdir, fname), dict(V=V, seeds=list(seeds), label=label,
                                           event=dict(at=at, s0=s0, k=k, dur=dur), arms=res)


# ======================================================================
# limit of the mechanism
# ======================================================================
def floor_dilution(cfg, outdir, V=30, seeds=(0, 1), at=600, k=3, dur=1200, settle=300,
                   thresholds=(9.5, 7.5, 6.0, 4.5, 3.0, 0.0), env_kw=None,
                   fname="floor_dilution.png"):
    """Widen the floor (lower the IMMEDIATE threshold) and track a FIXED core
    that is protected in every arm -- ASIL-D + EMERGENCY requests -- plus the
    QM class as the cost reference. (Averaging over "whatever is protected"
    would be confounded: the protected set changes composition and deadline
    mix as the threshold moves.) Random policy and a shared seed make the arms
    paired: the same requests, the same detections, only the tier cut differs."""
    s0 = middle_block(cfg, k)
    steps = at + dur + settle
    base = dict(env_kw or {})
    base.update(DISASTER_MODE=True, RESERVE_TOP_LEVEL=True, USE_CWP_FLOOR=True,
                SENSING_FRACTION=0.5)
    core = lambda q: q["key"] in ("ASIL-D", "EMERGENCY")
    rows = []
    print(f"Floor dilution: widen the floor and watch the always-protected core "
          f"(ASIL-D + EMERGENCY), V={V}, random policy, {len(seeds)} seeds")
    for thr in thresholds:
        sh, cm, ct, qm = [], [], [], []
        for sd in seeds:
            R = rollout(cfg, V, RulePolicy("random", sd), steps, sd,
                        kw={**base, "CWP_IMMEDIATE": thr,
                            "CWP_DELAYED": min(cfg.CWP_DELAYED, thr)},
                        events=[(at, s0, k, dur)])
            t = R["step"]["t"]
            w = (t >= at) & (t < at + dur)
            sh.append(100.0 * float(R["step"]["prot"][w].mean()))
            c = summarize(R["req"], pred=core, t0=at, t1=at + dur)
            cm.append(c["miss"]); ct.append(c["T"])
            qm.append(summarize(R["req"], pred=lambda q: q["key"] == "QM", t0=at, t1=at + dur)["miss"])
        rows.append(dict(threshold=thr, share=mean_ci(sh), core_miss=mean_ci(cm), core_T=mean_ci(ct),
                         qm_miss=mean_ci(qm), raw=dict(share=sh, core_miss=cm, core_T=ct, qm_miss=qm)))
        r = rows[-1]
        print(f"    IMMEDIATE threshold {thr:4.1f}: floor covers {fmt_ci(r['share'], 1, '%'):<22} "
              f"core T {fmt_ci(r['core_T'], 2, 's'):<22} core miss {fmt_ci(r['core_miss'], 1, '%'):<22} "
              f"QM miss {fmt_ci(r['qm_miss'], 1, '%')}")
    fig, ax = plt.subplots(1, 2, figsize=(12.4, 4.2))
    xs = [r["share"][0] for r in rows]
    for a_, m, lab, col, mk in ((ax[0], "core_T", "ASIL-D + EMERGENCY (always protected)", PALETTE[4], "o-"),
                                (ax[1], "core_miss", "ASIL-D + EMERGENCY miss", PALETTE[4], "o-"),
                                (ax[1], "qm_miss", "QM miss (cost reference)", PALETTE[1], "s--")):
        cis = [r[m] for r in rows]
        a_.errorbar(xs, [c[0] for c in cis], yerr=[0 if not np.isfinite(c[1]) else c[1] for c in cis],
                    fmt=mk, color=col, capsize=3, lw=1.8, label=lab)
    ax[0].set_ylabel("core true completion time (s)")
    ax[0].set_title("Does widening the floor slow the requests it was built for?")
    ax[1].set_ylabel("deadline miss (%)")
    ax[1].set_title("Core vs. ordinary traffic as the floor widens")
    for a_ in ax:
        a_.set_xlabel("share of traffic under the floor (%)"); a_.grid(alpha=.3); a_.legend(fontsize=8)
    return _save(fig, outdir, fname), dict(V=V, seeds=list(seeds), rows=rows,
                                           event=dict(at=at, s0=s0, k=k, dur=dur))


# ======================================================================
# micro -> macro hand-off
# ======================================================================
def latency_samples(cfg, policy_factory, V=30, seeds=(0, 1), at=600, k=3, dur=1200,
                    settle=300, floor=True, env_kw=None):
    """True completion time and deadline of every EMERGENCY request issued
    during the outage. corridor.py draws its route-computation and
    hazard-verification delays from these, retrying on a deadline miss."""
    s0 = middle_block(cfg, k)
    base = dict(env_kw or {})
    base.update(DISASTER_MODE=True, RESERVE_TOP_LEVEL=True, USE_EMERGENCY_FLOOR=bool(floor))
    T, D = [], []
    for sd in seeds:
        pol = policy_factory(V, sd)
        if pol is None:
            continue
        R = rollout(cfg, V, pol, at + dur + settle, sd, kw=base, events=[(at, s0, k, dur)])
        for q in R["req"]:
            if q["role"] == ROLE_EMERGENCY and at <= q["t"] < at + dur:
                T.append(q["Ttrue"]); D.append(q["D"])
    T, D = np.asarray(T), np.asarray(D)
    return dict(T=T, D=D, n=int(len(T)), V=V, floor=bool(floor), seeds=list(seeds),
                miss_pct=float(100.0 * np.mean(T > D)) if len(T) else float("nan"),
                median_T=float(np.median(T)) if len(T) else float("nan"))
