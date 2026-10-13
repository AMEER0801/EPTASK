"""
contributions.py -- the three v6 feature extensions (C1, C2, C3), V7.1 edition.

What changed from v6.1, and why. Each change answers a MEASUREMENT problem
found in the V7 audit, not a stylistic preference.

  C1  Safety-integrity floor.
      The floor level was never exclusive (config.RESERVE_TOP_LEVEL), and the
      v6.1 evidence was ONE seed. c1_multiseed() measures three arms over
      several seeds with 95% CIs and per-seed PAIRED gains: floor OFF, floor
      ON as v6.1 implemented it (level 9 shared), floor ON with level 9
      reserved. With the random policy the arms are exactly paired (same
      actions, same request stream), so the gain is the mechanism alone.
      v6.1's single-seed function is kept unchanged as c1_safety_floor() so
      the old table can still be reproduced.

  C2  Explainability.
      explain_decision() takes ANY policy object (torch or ONNX), so the
      notebook and the Streamlit demo explain decisions with the same code. It
      now also reports the request's role, protection and whether the edge was
      reachable -- a decision in a dead zone can be explained, not just a calm
      one. Counterfactuals still come from env.peek(): exact, not estimated.

  C3  Node-failure resilience.
      v6.1 compared pre- and post-outage windows of ONE run, so slow queue
      drift was read as failure impact (its +5.2% "post-recovery" gap exceeded
      its +3.5% spike). c3_paired() runs a NO-FAILURE CONTROL with the same
      seed. The exogenous request stream is identical by construction
      (env.rng is never consumed by actions), so the difference is the
      outage's effect alone. Contiguous k-RSU outages, several seeds, and two
      comparators: Local-only (failure-proof bound) and an alive-aware rule
      (the obvious hand-written baseline a learned policy has to beat).
"""
import os

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from env import VECEnv
from disaster import ROLE_EMERGENCY, ROLE_NAMES, TIER_NAMES
from policies import RulePolicy, env_kw_for, rollout, summarize
from runlog import mean_ci, fmt_ci

PALETTE = ["#1f4e79", "#c0392b", "#7f8c8d", "#e6a020", "#2e7d32", "#8e44ad"]
OFFLOAD_NAMES = ["Edge server", "Nearby vehicle", "Local (on-board)", "Cloud"]


def _save(fig, outdir, name):
    os.makedirs(outdir, exist_ok=True)
    p = os.path.join(outdir, name)
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return p


def _softmax(x):
    e = np.exp(x - x.max(axis=-1, keepdims=True))
    return e / e.sum(axis=-1, keepdims=True)


def _eb(ax, xs, cis, **kw):
    m = [c[0] for c in cis]
    h = [0.0 if not np.isfinite(c[1]) else c[1] for c in cis]
    ax.errorbar(xs, m, yerr=h, capsize=3, **kw)


# ======================================================================
# C1 -- v6.1 original, kept verbatim so the v6.1 table can be reproduced
# ======================================================================
def c1_safety_floor(cfg, outdir, steps=4000, seed=5):
    """v6.1's C1 (single seed, random priority). Reproduce v6.1 by calling it
    under cfg.override(RESERVE_TOP_LEVEL=False, LOCAL_COST_AT_ARRIVAL=False,
    PRIORITY_TX=False)."""
    cfg = cfg.derive()
    prev_floor, prev_track = cfg.USE_SAFETY_FLOOR, cfg.TRACK_TRUE_T
    cfg.TRACK_TRUE_T = True
    counts = list(cfg.VEHICLE_COUNTS)
    out = {True: [], False: []}
    print("C1 (v6.1 single-seed)  ASIL-D protection: floor ON vs OFF (random priority)")
    print(f"    {'V':>3} {'floor':>6} {'ASIL-D true T':>14} {'ASIL-D miss%':>13} {'QM miss% (ref)':>15}")
    for V in counts:
        for floor in (True, False):
            cfg.USE_SAFETY_FLOOR = floor
            env = VECEnv(cfg, V, seed=seed)
            rng = np.random.default_rng(seed)
            for _ in range(steps):
                env.req_tag = float(env.req_class)
                env.step(rng.integers(0, 4, 10), rng.integers(0, 10, 10))
            P = np.array(env.true_pairs)
            cls = P[:, 3].astype(int)
            D = np.array([cfg.ASIL_DEADLINE_MULT[cfg.ASIL_CLASSES[c]] for c in cls]) * P[:, 2]
            miss = P[:, 0] > D
            d_mask, qm_mask = cls == 0, cls == 2
            row = (P[d_mask, 0].mean() if d_mask.any() else float("nan"),
                   miss[d_mask].mean() * 100 if d_mask.any() else float("nan"),
                   miss[qm_mask].mean() * 100 if qm_mask.any() else float("nan"))
            out[floor].append(row)
            print(f"    {V:3d} {str(floor):>6} {row[0]:14.3f} {row[1]:13.1f} {row[2]:15.1f}")
    cfg.USE_SAFETY_FLOOR, cfg.TRACK_TRUE_T = prev_floor, prev_track
    on, off = np.array(out[True]), np.array(out[False])
    gain = (off[:, 0] - on[:, 0]) / off[:, 0] * 100
    return dict(counts=counts, on=on.tolist(), off=off.tolist(), gain_pct=gain.tolist(),
                seed=seed, steps=steps)


# ======================================================================
# C1 -- V7.1: multi-seed, three arms, paired gains
# ======================================================================
C1_ARMS = (("floor OFF", dict(USE_SAFETY_FLOOR=False, RESERVE_TOP_LEVEL=False)),
           ("floor ON, v6.1 (level 9 shared)", dict(USE_SAFETY_FLOOR=True, RESERVE_TOP_LEVEL=False)),
           ("floor ON, V7.1 (level 9 reserved)", dict(USE_SAFETY_FLOOR=True, RESERVE_TOP_LEVEL=True)))


def c1_multiseed(cfg, outdir, seeds=(0, 1, 2), steps=3000, counts=None,
                 policy_factory=None, label="random policy", env_kw=None,
                 fname="c1_multiseed.png"):
    counts = list(counts or cfg.VEHICLE_COUNTS)
    base = dict(env_kw or {})
    base["DISASTER_MODE"] = False
    arms = {a: dict(T=[], miss=[], qm_miss=[], raw=[]) for a, _ in C1_ARMS}
    paired = {a: dict(T_gain=[], miss_pp=[]) for a, _ in C1_ARMS[1:]}
    print(f"C1  ASIL-D protection, {len(seeds)} seeds x {steps} steps, {label}  (mean +- 95% CI)")
    for V in counts:
        per_arm = {}
        for a, kw in C1_ARMS:
            Ts, Ms, Qs = [], [], []
            for sd in seeds:
                pol = policy_factory(V, sd) if policy_factory else RulePolicy("random", sd)
                if pol is None:
                    continue
                R = rollout(cfg, V, pol, steps, sd, kw={**base, **kw})
                d = summarize(R["req"], pred=lambda q: q["key"] == "ASIL-D")
                qm = summarize(R["req"], pred=lambda q: q["key"] == "QM")
                Ts.append(d["T"]); Ms.append(d["miss"]); Qs.append(qm["miss"])
            per_arm[a] = (np.array(Ts), np.array(Ms))
            for k_, v_ in (("T", Ts), ("miss", Ms), ("qm_miss", Qs)):
                arms[a][k_].append(mean_ci(v_))
            arms[a]["raw"].append(dict(V=V, T=Ts, miss=Ms, qm_miss=Qs))
            print(f"    V={V:2d}  {a:<34} T {fmt_ci(mean_ci(Ts), 3, 's'):<26} "
                  f"miss {fmt_ci(mean_ci(Ms), 1, '%'):<24} QM miss {fmt_ci(mean_ci(Qs), 1, '%')}")
        T0, M0 = per_arm[C1_ARMS[0][0]]
        for a, _ in C1_ARMS[1:]:
            T1, M1 = per_arm[a]
            n = min(len(T0), len(T1))
            paired[a]["T_gain"].append(mean_ci(((T0[:n] - T1[:n]) / T0[:n] * 100).tolist()))
            paired[a]["miss_pp"].append(mean_ci((M0[:n] - M1[:n]).tolist()))
    print("    paired gain vs floor OFF (per seed, then averaged):")
    for a in paired:
        print(f"      {a:<34} T gain % " +
              "  ".join(f"V{V}:{fmt_ci(c, 1)}" for V, c in zip(counts, paired[a]['T_gain'])))
        print(f"      {'':<34} miss -pp  " +
              "  ".join(f"V{V}:{fmt_ci(c, 1)}" for V, c in zip(counts, paired[a]['miss_pp'])))

    fig, ax = plt.subplots(1, 2, figsize=(12.6, 4.3))
    sty = (("s--", PALETTE[1]), ("o-", PALETTE[3]), ("D-", PALETTE[4]))
    for (a, _), (mk, col) in zip(C1_ARMS, sty):
        _eb(ax[0], counts, arms[a]["T"], fmt=mk, color=col, lw=1.8, label=a)
        _eb(ax[1], counts, arms[a]["miss"], fmt=mk, color=col, lw=1.8, label=f"ASIL-D, {a}")
    _eb(ax[1], counts, arms[C1_ARMS[2][0]]["qm_miss"], fmt="^:", color=PALETTE[2], lw=1.3,
        label="QM (reference)")
    ax[0].set_ylabel("ASIL-D true completion time (s)")
    ax[0].set_title(f"C1(a) floor effect on safety-critical latency ({label})")
    ax[1].set_ylabel("deadline miss rate (%)")
    ax[1].set_title(f"C1(b) miss rate, {len(seeds)} seeds, 95% CI")
    for a_ in ax:
        a_.set_xlabel("number of vehicles"); a_.grid(alpha=.3); a_.legend(fontsize=7)
    return _save(fig, outdir, fname), dict(counts=counts, seeds=list(seeds), steps=steps,
                                           label=label, arms=arms, paired=paired)


# ======================================================================
# C2 -- explainability, for any policy
# ======================================================================
def explain_decision(policy, env):
    """Raw per-task logits before sampling, each head's confidence and
    entropy, and an exact env.peek() counterfactual over every offload target
    for the request's largest task. Works for torch and ONNX policies."""
    obs = env.observe()
    off_l, pri_l, value = policy.logits(obs)
    n = env.n_tasks
    off_p, pri_p = _softmax(off_l), _softmax(pri_l)
    a_off, a_pri = off_p.argmax(-1), pri_p.argmax(-1)
    off_ent = -(off_p * np.log(off_p + 1e-9)).sum(-1)
    pri_ent = -(pri_p * np.log(pri_p + 1e-9)).sum(-1)
    cf, explained = [], None
    if n > 0:
        k = int(np.argmax(env.cycles[:n]))
        explained = k
        # request-level baseline penalty, so only a NEW infeasibility caused by
        # moving task k is flagged (pen is an aggregate over the request)
        _, _, base_pen = env.peek(a_off, a_pri)
        for alt in range(4):
            off_try = a_off.copy()
            off_try[k] = alt
            T, E, pen = env.peek(off_try, a_pri)
            cf.append(dict(target=OFFLOAD_NAMES[alt], T=float(T), E=float(E),
                           infeasible=bool(pen > base_pen + 1e-9)))
    m = env.request_meta()
    return dict(
        n_tasks=n, value=float(value), t=float(env.t),
        role=ROLE_NAMES[m["role"]], deadline_class=m["key"], protected=m["prot"],
        edge_reachable=bool(env.in_range[env.cursor]),
        v2v_reachable=env._select_sev(env.cursor)[0] is not None,
        people=m["people"], cwp=m["cwp"], tier=TIER_NAMES[m["tier"]],
        offload_choice=[OFFLOAD_NAMES[a] for a in a_off[:n]],
        offload_confidence=[float(off_p[i, a_off[i]]) for i in range(n)],
        offload_entropy=[float(x) for x in off_ent[:n]],
        priority_choice=[int(x) for x in a_pri[:n]],
        priority_confidence=[float(pri_p[i, a_pri[i]]) for i in range(n)],
        priority_entropy=[float(x) for x in pri_ent[:n]],
        explained_task=explained, counterfactual=cf)


def c2_explain_live(cfg, policy, outdir, V=30, warmup=200, seed=17, scenario="calm",
                    max_search=3000, env_kw=None, fname=None):
    """scenario 'calm': explain a decision after `warmup` ticks of normal traffic.
    scenario 'emergency_dead_zone': a 3-RSU disaster block goes down halfway
    through warmup; then explain the first EMERGENCY request issued from
    INSIDE the dead zone -- the decision N1 is about."""
    assert scenario in ("calm", "emergency_dead_zone")
    kw = dict(env_kw or {})
    kw["DISASTER_MODE"] = scenario != "calm"
    merged = env_kw_for(policy, kw)
    merged["TRACK_TRUE_T"] = False
    k = 3
    s0 = (cfg.NUM_EDGE_SERVERS - k) // 2
    with cfg.override(**merged):
        env = VECEnv(cfg, V, seed=seed)
        obs = env.observe()
        for t in range(warmup):
            if scenario != "calm" and t == warmup // 2:
                env.trigger_disaster(s0, k, 10 ** 7)
            off, pri = policy.act(env, obs)
            obs, _, _ = env.step(off, pri)
        if scenario != "calm" and warmup < 2:
            env.trigger_disaster(s0, k, 10 ** 7)

        def wanted():
            if env.n_tasks == 0:
                return False
            if scenario == "calm":
                return True
            return env.req_role == ROLE_EMERGENCY and not env.in_range[env.cursor]

        found, searched = wanted(), 0
        while not found and searched < max_search:
            off, pri = policy.act(env, obs)
            obs, _, _ = env.step(off, pri)
            searched += 1
            found = wanted()
        ex = explain_decision(policy, env)
    ex.update(scenario=scenario, found=bool(found), searched=searched, V=V, seed=seed,
              policy=policy.name)

    vtxt = "n/a (critic not exported)" if not np.isfinite(ex["value"]) else f"{ex['value']:.2f}"
    print(f"C2  [{scenario}] policy={policy.name}  t={ex['t']:.0f}s  V={V}  "
          f"role={ex['role']}  class={ex['deadline_class']}  protected={ex['protected']}  "
          f"edge reachable={ex['edge_reachable']}  V2V reachable={ex['v2v_reachable']}  "
          f"tasks={ex['n_tasks']}  critic value={vtxt}"
          + ("" if found else "   (no matching request found; explaining current one)"))
    if ex["n_tasks"]:
        print(f"    {'task':>5} {'offload ->':>17} {'conf':>6} {'entropy':>8} "
              f"{'priority':>9} {'conf':>6} {'entropy':>8}")
        for i in range(ex["n_tasks"]):
            print(f"    {i:5d} {ex['offload_choice'][i]:>17} {ex['offload_confidence'][i]:6.2f} "
                  f"{ex['offload_entropy'][i]:8.2f} {ex['priority_choice'][i]:9d} "
                  f"{ex['priority_confidence'][i]:6.2f} {ex['priority_entropy'][i]:8.2f}")
        print(f"    counterfactual for task {ex['explained_task']} (largest task):")
        for c in ex["counterfactual"]:
            tag = "  INFEASIBLE -> falls back to local" if c["infeasible"] else ""
            print(f"      {c['target']:>17}: T = {c['T']:7.3f}s   E = {c['E']:.5f}J{tag}")

    fig, ax = plt.subplots(figsize=(7.6, 4.2))
    if ex["counterfactual"]:
        names = [c["target"] for c in ex["counterfactual"]]
        Ts = [c["T"] for c in ex["counterfactual"]]
        chosen = ex["offload_choice"][ex["explained_task"]]
        bars = ax.bar(names, Ts, color=[PALETTE[4] if nm == chosen else PALETTE[2] for nm in names])
        for b, c in zip(bars, ex["counterfactual"]):
            if c["infeasible"]:
                ax.text(b.get_x() + b.get_width() / 2, b.get_height() * 1.02, "infeasible",
                        ha="center", fontsize=8, color=PALETTE[1])
        ax.set_ylabel("completion time (s) if THIS task went here")
        ax.set_title(f"C2 [{scenario}] why {chosen}?  {ex['role']} request, "
                     f"edge {'reachable' if ex['edge_reachable'] else 'NOT reachable'}")
        ax.grid(alpha=.3, axis="y")
    return _save(fig, outdir, fname or f"c2_{scenario}.png"), ex


# ======================================================================
# C3 -- node failure with a paired no-failure control
# ======================================================================
def c3_paired(cfg, factories, outdir, V=30, k_list=(1, 2, 4), fail_at=1200, fail_dur=400,
              post=300, seeds=(0, 1, 2), env_kw=None, fname="c3_paired.png"):
    """factories: {name: f(V, seed) -> policy}. For every (k, policy, seed):
    one run with RSUs s0..s0+k-1 down during [fail_at, fail_at+fail_dur) and
    one identical run without the outage. Excess latency = paired difference
    of mean reported T in the outage window (and in the `post` window after)."""
    kw = {"TRACK_TRUE_T": False}
    kw.update(env_kw or {})
    steps = fail_at + fail_dur + post + 1
    rows = {}
    print(f"C3  paired outage test, V={V}, outage [{fail_at}, {fail_at + fail_dur}) s, "
          f"{len(seeds)} seeds (excess vs the SAME run without the outage)")
    for k in k_list:
        s0 = (cfg.NUM_EDGE_SERVERS - k) // 2
        for name, fac in factories.items():
            ex_d, ex_p, absT, ctrlT = [], [], [], []
            for sd in seeds:
                pf, pc = fac(V, sd), fac(V, sd)
                if pf is None:
                    continue
                Rf = rollout(cfg, V, pf, steps, sd, kw=kw,
                             fail_blocks=[(fail_at, s0, k, fail_dur)])
                Rc = rollout(cfg, V, pc, steps, sd, kw=kw)
                Tf, Tc = Rf["step"]["T"], Rc["step"]["T"]
                w = slice(fail_at, fail_at + fail_dur)
                p = slice(fail_at + fail_dur, fail_at + fail_dur + post)
                ex_d.append(float((Tf[w].mean() - Tc[w].mean()) / Tc[w].mean() * 100))
                ex_p.append(float((Tf[p].mean() - Tc[p].mean()) / Tc[p].mean() * 100))
                absT.append(float(Tf[w].mean())); ctrlT.append(float(Tc[w].mean()))
            if not ex_d:
                continue
            key = f"k={k} | {name}"
            rows[key] = dict(k=k, policy=name, during_pct=mean_ci(ex_d), post_pct=mean_ci(ex_p),
                             T_outage=mean_ci(absT), T_control=mean_ci(ctrlT),
                             raw=dict(during=ex_d, post=ex_p, T_outage=absT, T_control=ctrlT))
            print(f"    k={k} RSU(s) {name:<14} excess during {fmt_ci(mean_ci(ex_d), 1, '%'):<24} "
                  f"after {fmt_ci(mean_ci(ex_p), 1, '%'):<24} T in outage {fmt_ci(mean_ci(absT), 2, 's')}")

    names = list(factories)
    fig, ax = plt.subplots(1, 2, figsize=(12.8, 4.3))
    width = 0.8 / max(len(names), 1)
    for j, name in enumerate(names):
        ks = [k for k in k_list if f"k={k} | {name}" in rows]
        xs = np.array([k_list.index(k) for k in ks]) + (j - (len(names) - 1) / 2) * width
        for a_, metric in ((ax[0], "during_pct"), (ax[1], "T_outage")):
            cis = [rows[f"k={k} | {name}"][metric] for k in ks]
            a_.bar(xs, [c[0] for c in cis], width,
                   yerr=[0 if not np.isfinite(c[1]) else c[1] for c in cis],
                   capsize=3, color=PALETTE[j % len(PALETTE)], label=name)
    for a_ in ax:
        a_.set_xticks(range(len(k_list)))
        a_.set_xticklabels([f"{k} RSU{'s' if k > 1 else ''} down" for k in k_list])
        a_.grid(alpha=.3, axis="y")
    ax[0].axhline(0, color="k", lw=.8)
    ax[0].set_ylabel("excess latency vs paired no-failure run (%)")
    ax[0].set_title("C3(a) the outage's own effect (paired control)")
    ax[1].set_ylabel("mean completion time during outage (s)")
    ax[1].set_title("C3(b) absolute latency while RSUs are down")
    ax[0].legend(fontsize=8)
    return _save(fig, outdir, fname), dict(V=V, k_list=list(k_list), fail_at=fail_at,
                                           fail_dur=fail_dur, post=post, seeds=list(seeds),
                                           rows=rows)


def uplink_busy_share(cfg, counts=(10, 30, 50), steps=2000, seed=0):
    """Share of requests whose vehicle still has transmission backlog when the
    request is issued. A request's own tasks are enqueued in rank order, so
    FIFO transmission already follows the ranking; transmission priority (and
    the reserved floor level) can only matter for THIS share of requests."""
    out = {}
    with cfg.override(TRACK_TRUE_T=False, DISASTER_MODE=False):
        for V in counts:
            env = VECEnv(cfg, V, seed=seed)
            rng = np.random.default_rng(seed)
            busy = n = 0
            for _ in range(steps):
                if env.n_tasks:
                    n += 1
                    busy += int(env.veh_up[env.cursor].sum() > 1e-9)
                env.step(rng.integers(0, 4, 10), rng.integers(0, 10, 10))
            out[int(V)] = 100.0 * busy / max(n, 1)
    print("Uplink still busy when a vehicle issues its next request (random policy): "
          + ", ".join(f"V={V}: {s:.1f}%" for V, s in out.items()))
    return out
