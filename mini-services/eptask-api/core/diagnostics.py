"""
diagnostics.py -- the four measurements that decide whether this replication
supports the base paper's claims.

Each function returns (figure_path, result_dict) and prints a table, so the
numbers can go straight into the report. Nothing here is cosmetic: every one
of these was written because a v4 figure turned out to be measuring something
other than what it claimed.

  D1  reward_degeneracy  -- Eq. (25)'s running-max normaliser drifts upward
                            under a FROZEN policy, so the Fig. 9 reward curve
                            is not evidence of learning.
  D2  priority_levels    -- how a rank becomes a global queue level, and why
                            v4's map made request SIZE decide precedence.
  D3  true_vs_reported   -- the arrival-time estimate never charges later
                            preemption, and the resulting optimism is larger
                            exactly when priority is switched on.
  D4  critical_path      -- what fraction of a task's critical path the
                            priority mechanism can physically influence.
  D5  priority_rules     -- every priority discipline vs FIFO, scored both
                            ways.
"""
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from env import VECEnv

PALETTE = ["#1f4e79", "#c0392b", "#7f8c8d", "#e6a020", "#2e7d32", "#8e44ad"]


def _save(fig, outdir, name):
    os.makedirs(outdir, exist_ok=True)
    p = os.path.join(outdir, name)
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return p


def _roll(cfg, V, steps, rule, seed, tag_fn=None):
    """One rollout under a scripted priority rule. Offloading is random and
    seed-matched across rules, so only the priority discipline differs."""
    env = VECEnv(cfg, V, seed=seed)
    rng = np.random.default_rng(seed)
    rep = []
    for _ in range(steps):
        off = rng.integers(0, 4, 10)
        n = env.n_tasks
        if rule == "fifo":
            pri = np.zeros(10)
        elif rule == "random":
            pri = rng.integers(0, 10, 10)
        elif rule == "lpt":                       # longest task first
            pri = np.r_[env.cycles[:n], np.zeros(10 - n)]
        elif rule == "spt":                       # shortest task first
            pri = np.r_[-env.cycles[:n], np.zeros(10 - n)]
        elif rule == "gspt":                      # short REQUESTS first
            pri = np.full(10, np.clip(9.0 - env._local_cost()[0] * 1.5, 0, 9))
        else:
            raise ValueError(rule)
        if tag_fn is not None:
            env.req_tag = tag_fn(rng)
        _, _, inf = env.step(off, pri)
        rep.append(inf["T"])
    true = np.mean(env.true_T) if env.true_T else float("nan")
    return float(np.mean(rep)), float(true)


# ======================================================================
def d1_reward_degeneracy(cfg, outdir, V=30, steps=4000, seed=0):
    """Eq. (25) normalises by max_T / max_E -- the largest values the agent has
    EVER reached. Those are hidden, monotone and non-stationary, so the reward
    climbs on its own. Measured here with a fixed random policy: no learning
    can possibly be occurring, yet the time penalty decays."""
    cfg = cfg.derive()
    env = VECEnv(cfg, V, seed=seed)
    rng = np.random.default_rng(seed)
    Ts, mx = [], []
    for _ in range(steps):
        _, _, inf = env.step(rng.integers(0, 4, 10), rng.integers(0, 10, 10))
        Ts.append(inf["T"]); mx.append(env.max_T)
    Ts, mx = np.array(Ts), np.array(mx)
    ratio = Ts / mx
    w = 200
    sm = np.convolve(ratio, np.ones(w) / w, mode="valid")
    drift = float(sm[0] / sm[-1])

    fig, ax = plt.subplots(1, 2, figsize=(11.5, 4.0))
    ax[0].plot(mx, color=PALETTE[1], lw=1.6)
    ax[0].set_title("running max$_T$ under a FROZEN random policy")
    ax[0].set_xlabel("step"); ax[0].set_ylabel(r"$\max\,\exp_{time}$ (s)")
    ax[1].plot(np.arange(len(sm)) + w, sm, color=PALETTE[0], lw=1.6)
    ax[1].set_title(f"Eq. (25) time penalty $T/\\max_T$  "
                    f"(decays {drift:.2f}$\\times$ with no learning)")
    ax[1].set_xlabel("step"); ax[1].set_ylabel(r"$T/\max_T$")
    for a in ax:
        a.grid(alpha=.3)
    print(f"D1  frozen policy, V={V}, {steps} steps")
    print(f"      median T                 : {np.median(Ts):.2f} s  (stationary)")
    print(f"      max_T at step 100 / end  : {mx[99]:.1f} -> {mx[-1]:.1f} s")
    print(f"      Eq.(25) time penalty      : decays {drift:.2f}x on its own")
    print("      => a rising Fig. 9 curve is NOT evidence that the policy improved.")
    return _save(fig, outdir, "d1_reward_degeneracy.png"), dict(
        drift=drift, median_T=float(np.median(Ts)), max_T_end=float(mx[-1]))


# ======================================================================
def d2_priority_levels(cfg, outdir):
    """rank -> global queue level, under both maps."""
    cfg = cfg.derive()
    P, rows = 10, {}
    desc = np.arange(P - 1, -1, -1)
    print("D2  rank -> global queue level")
    print(f"    {'n tasks':>8} | {'rank_tail (v4)':>28} | {'rank_spread (v5)':>28}")
    for n in (1, 2, 3, 5, 8, 10):
        tail = list(desc[P - n:])
        spread = ([(P - 1) // 2] if n == 1
                  else list(np.round(np.linspace(P - 1, 0, n)).astype(int)))
        rows[n] = (tail, spread)
        print(f"    {n:>8} | {str(tail):>28} | {str(spread):>28}")
    print("    => under rank_tail a 1-task request is pinned to level 0 and can")
    print("       never preempt anything; a 10-task request's median task outranks")
    print("       every task of every small request. Precedence follows SIZE.")

    fig, ax = plt.subplots(1, 2, figsize=(11, 3.8), sharey=True)
    for j, (title, key) in enumerate((("rank_tail (v4)", 0),
                                      ("rank_spread (v5)", 1))):
        for n in (1, 2, 3, 5, 8, 10):
            lv = rows[n][key]
            ax[j].scatter([n] * len(lv), lv, s=42, color=PALETTE[0])
        ax[j].set_title(title); ax[j].set_xlabel("tasks in the request")
        ax[j].grid(alpha=.3); ax[j].set_yticks(range(10))
    ax[0].set_ylabel("global queue level")
    return _save(fig, outdir, "d2_priority_levels.png"), rows


# ======================================================================
def d3_true_vs_reported(cfg, outdir, steps=4000, seed=3):
    """Reported T is the estimate made at arrival. A later higher-priority
    arrival then preempts that queued work and the estimate is never revised.
    The optimism this creates is LARGER when priority is on, which is exactly
    the direction that flatters Fig. 11."""
    cfg = cfg.derive()
    prev = cfg.TRACK_TRUE_T
    cfg.TRACK_TRUE_T = True
    counts = list(cfg.VEHICLE_COUNTS)
    out = {True: [], False: []}
    print("D3  reported (arrival estimate) vs true (preemption charged)")
    print(f"    {'V':>3} {'priority':>9} {'reported':>9} {'true':>8} {'optimism':>9}")
    for V in counts:
        for use in (True, False):
            cfg.USE_PRIORITY = use
            r, t = _roll(cfg, V, steps, "random" if use else "fifo", seed)
            out[use].append((r, t))
            print(f"    {V:3d} {str(use):>9} {r:9.3f} {t:8.3f} "
                  f"{(t - r) / r * 100:8.1f}%")
    cfg.USE_PRIORITY = True
    cfg.TRACK_TRUE_T = prev

    on = np.array(out[True]); off = np.array(out[False])
    x = np.arange(len(counts)); w = .35
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.2))
    ax[0].bar(x - w / 2, (on[:, 1] - on[:, 0]) / on[:, 0] * 100, w,
              label="priority ON", color=PALETTE[1])
    ax[0].bar(x + w / 2, (off[:, 1] - off[:, 0]) / off[:, 0] * 100, w,
              label="priority OFF (FIFO)", color=PALETTE[2])
    ax[0].set_ylabel("optimism of the reported metric (%)")
    ax[0].set_title("D3(a) -- the bias is larger when priority is on")
    ax[1].plot(counts, (off[:, 0] - on[:, 0]) / off[:, 0] * 100, "o-",
               color=PALETTE[0], lw=2, label="as reported (Fig. 11 metric)")
    ax[1].plot(counts, (off[:, 1] - on[:, 1]) / off[:, 1] * 100, "s--",
               color=PALETTE[1], lw=2, label="true (preemption charged)")
    ax[1].axhline(0, color="k", lw=.8)
    ax[1].set_ylabel("gain from priority (%)")
    ax[1].set_title("D3(b) -- the Fig. 11 gap, scored honestly")
    for a, xt in ((ax[0], True), (ax[1], False)):
        a.grid(alpha=.3); a.legend(fontsize=9); a.set_xlabel("number of vehicles")
    ax[0].set_xticks(x); ax[0].set_xticklabels(counts)
    return _save(fig, outdir, "d3_true_vs_reported.png"), dict(
        counts=counts, on=on.tolist(), off=off.tolist())


# ======================================================================
def d4_critical_path(cfg, outdir, steps=3000, seed=5):
    """Split an offloaded task's critical path into the four terms of
    Eq. (11)-(13). Priority governs ONE of them: the execution queue."""
    cfg = cfg.derive()
    counts = list(cfg.VEHICLE_COUNTS)
    parts = []
    print("D4  critical-path decomposition of an offloaded task")
    print(f"    {'V':>3} {'tx WAIT':>9} {'tx time':>8} {'exec WAIT':>10} "
          f"{'exec time':>10} {'priority reaches':>17}")
    for V in counts:
        env = VECEnv(cfg, V, seed=seed)
        acc, cnt = np.zeros(4), 0
        for _ in range(steps):
            i, n = env.cursor, env.n_tasks
            s, de = env._nearest_edge(i)
            if n == 0 or s is None:
                env.step(np.full(10, 0), np.zeros(10)); continue
            _, R = env._rate_v2e(de, env._n_connected(s))
            txw = env.veh_up[i].sum()
            for k in range(n):
                tt = env.bits[k] / max(R, 1.0)
                acc += [txw, tt, env.edge_W[s].sum(),
                        env.cycles[k] / cfg.EDGE_CPU_HZ]
                txw += tt; cnt += 1
            env.step(np.full(10, 0), np.zeros(10))
        a = acc / max(cnt, 1)
        parts.append(a)
        print(f"    {V:3d} {a[0]:9.2f} {a[1]:8.2f} {a[2]:10.2f} {a[3]:10.2f} "
              f"{a[2] / a.sum() * 100:16.1f}%")
    parts = np.array(parts)
    print("    => the dominant term is Eq. (12)'s transmission queue, which the")
    print("       paper defines as FIFO. Priority's reach SHRINKS as congestion")
    print("       grows -- the opposite of the trend Fig. 11 reports.")

    lab = ["tx WAIT (Eq. 12, FIFO)", "tx time", "exec WAIT (Eq. 13, priority)",
           "exec time"]
    frac = parts / parts.sum(axis=1, keepdims=True) * 100
    fig, ax = plt.subplots(1, 2, figsize=(12.5, 4.3))
    bot = np.zeros(len(counts))
    for j in range(4):
        ax[0].bar(counts, frac[:, j], 6, bottom=bot, label=lab[j],
                  color=PALETTE[j])
        bot += frac[:, j]
    ax[0].set_ylabel("share of critical path (%)")
    ax[0].set_title("D4(a) -- where the completion time goes")
    ax[0].legend(fontsize=8, loc="lower left")
    ax[1].plot(counts, frac[:, 2], "o-", lw=2, color=PALETTE[1])
    ax[1].set_ylabel("share priority can influence (%)")
    ax[1].set_title("D4(b) -- the priority mechanism's leverage")
    for a in ax:
        a.set_xlabel("number of vehicles"); a.grid(alpha=.3)
    return _save(fig, outdir, "d4_critical_path.png"), dict(
        counts=counts, parts=parts.tolist(), reach=frac[:, 2].tolist())


# ======================================================================
def d5_priority_rules(cfg, outdir, steps=4000, seed=3):
    """Every priority discipline against FIFO, scored both ways. If any rule
    beat FIFO on true completion time, the mechanism would be sound and only
    the learning would be at fault. None does."""
    cfg = cfg.derive()
    prev = cfg.TRACK_TRUE_T
    cfg.TRACK_TRUE_T = True
    counts = list(cfg.VEHICLE_COUNTS)
    rules = ("random", "lpt", "spt", "gspt")
    res = {r: {"rep": [], "true": []} for r in ("fifo",) + rules}
    print("D5  priority disciplines vs FIFO  (+ = better than FIFO)")
    print(f"    {'V':>3} {'rule':>7} {'reported':>9} {'true':>8} "
          f"{'vs FIFO rep':>12} {'vs FIFO true':>13}")
    for V in counts:
        cfg.USE_PRIORITY = False
        br, bt = _roll(cfg, V, steps, "fifo", seed)
        res["fifo"]["rep"].append(br); res["fifo"]["true"].append(bt)
        print(f"    {V:3d} {'FIFO':>7} {br:9.3f} {bt:8.3f}")
        cfg.USE_PRIORITY = True
        for r in rules:
            rr, tt = _roll(cfg, V, steps, r, seed)
            res[r]["rep"].append(rr); res[r]["true"].append(tt)
            print(f"    {'':>3} {r:>7} {rr:9.3f} {tt:8.3f} "
                  f"{(br - rr) / br * 100:+11.1f}% {(bt - tt) / bt * 100:+12.1f}%")
    cfg.TRACK_TRUE_T = prev

    fig, ax = plt.subplots(1, 2, figsize=(12.5, 4.3), sharey=True)
    for j, key in enumerate(("rep", "true")):
        base = np.array(res["fifo"][key])
        for i, r in enumerate(rules):
            g = (base - np.array(res[r][key])) / base * 100
            ax[j].plot(counts, g, "o-", lw=1.8, color=PALETTE[i], label=r)
        ax[j].axhline(0, color="k", lw=1)
        ax[j].set_xlabel("number of vehicles"); ax[j].grid(alpha=.3)
        ax[j].set_title("D5 -- gain over FIFO, "
                        + ("as reported" if key == "rep" else "true"))
    ax[0].set_ylabel("completion-time gain over FIFO (%)")
    ax[0].legend(fontsize=9)
    return _save(fig, outdir, "d5_priority_rules.png"), res
