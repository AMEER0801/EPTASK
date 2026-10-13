"""
experiments.py -- reproduces Figs. 7-13 of the paper.

Every figure is generated from an INDEPENDENT rollout of the method in
question, in its own world with its own queue history. Scoring a comparator
against queues that the trained agent built answers a different question.
"""
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from env import VECEnv
from meppo import FIXED_POLICIES
from train import run_independent

PALETTE = ["#1f4e79", "#c0392b", "#7f8c8d", "#e6a020", "#2e7d32", "#8e44ad"]


def _save(fig, outdir, name):
    os.makedirs(outdir, exist_ok=True)
    p = os.path.join(outdir, name)
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return p


# ======================================================================
def fig7_vehicle_distribution(cfg, outdir, num_vehicles=30, seed=0):
    """Fig. 7: node position, marker area = tasks in the request, colour =
    CPU cycles required."""
    cfg = cfg.derive()
    env = VECEnv(cfg, num_vehicles, seed=seed)
    xs, ys, ns, cs = [], [], [], []
    for _ in range(num_vehicles * 3):
        xs.append(env.veh_x[env.cursor]); ys.append(env.veh_y[env.cursor])
        ns.append(env.n_tasks)
        cs.append(env.cycles[:max(env.n_tasks, 1)].mean() / 1e8)
        env.step(np.full(10, 2), np.arange(10))
    fig, ax = plt.subplots(figsize=(9, 3.6))
    sc = ax.scatter(xs, ys, s=[20 + 26 * n for n in ns], c=cs,
                    cmap="viridis", alpha=.85, edgecolor="k", linewidth=.3)
    ax.scatter(env.edge_x, env.edge_y, marker="^", s=150, c="#c0392b",
               label="edge server", zorder=5)
    ax.axhline(0, color="k", lw=.8, ls="--")
    ax.set_xlabel("position along highway (m)"); ax.set_ylabel("lane offset (m)")
    ax.set_title(f"Fig. 7 -- vehicle distribution ({num_vehicles} vehicles); "
                 "area = tasks in request")
    fig.colorbar(sc, ax=ax, label=r"mean CPU cycles ($\times 10^8$)")
    ax.legend(loc="upper right")
    return _save(fig, outdir, "fig07_vehicle_distribution.png")


def fig8_task_distribution(cfg, outdir, seed=0, samples=4000):
    """Fig. 8: distribution of tasks per service request, per scenario.
    Paper: 0 tasks occur, max is 10, most requests carry 2-6."""
    cfg = cfg.derive()
    fig, ax = plt.subplots(figsize=(7.5, 4.4))
    for i, V in enumerate(cfg.VEHICLE_COUNTS):
        env = VECEnv(cfg, V, seed=seed + i)
        counts = []
        for _ in range(samples):
            counts.append(env.n_tasks)
            env.step(np.full(10, 2), np.arange(10))
        h = np.bincount(counts, minlength=11)[:11] / samples
        ax.plot(np.arange(11), h + i * 0.05, color=PALETTE[i], lw=1.8)
        ax.fill_between(np.arange(11), i * 0.05, h + i * 0.05,
                        color=PALETTE[i], alpha=.35)
        ax.text(10.3, i * 0.05, f"{V} vehicles", va="center", fontsize=9)
    ax.set_xlabel("number of tasks in the request")
    ax.set_ylabel("density (offset per scenario)")
    ax.set_xlim(-1, 12); ax.set_xticks(range(11))
    ax.set_title("Fig. 8 -- distribution of tasks in service requests")
    return _save(fig, outdir, "fig08_task_distribution.png")


# ======================================================================
def fig9_convergence(hist, outdir):
    """Fig. 9: reward convergence, one curve per vehicle count."""
    fig, ax = plt.subplots(figsize=(8, 4.6))
    R = np.asarray(hist["return"])
    w = max(1, len(R) // 60)
    for i, V in enumerate(hist["counts"]):
        y = np.convolve(R[:, i], np.ones(w) / w, mode="valid")
        ax.plot(np.arange(len(y)) + w, y, color=PALETTE[i], lw=1.5,
                label=f"{V} vehicles")
    ax.set_xlabel("Episodes"); ax.set_ylabel("Reward")
    ax.set_title("Fig. 9 -- convergence of the MEPPO algorithm")
    ax.legend(ncol=5, fontsize=9, loc="lower right"); ax.grid(alpha=.3)
    return _save(fig, outdir, "fig09_convergence.png")


# ======================================================================
def fig10_method_comparison(cfg, agent, outdir, device, eval_steps=1500,
                            rl_results=None, seed=99):
    """Fig. 10(a)(b): completion time and energy for every Section V-B method,
    across the vehicle-count sweep. Each point is an independent rollout."""
    cfg = cfg.derive()
    counts = list(cfg.VEHICLE_COUNTS)
    res = {"MEPPO": ([], [])}
    for name in FIXED_POLICIES:
        res[name] = ([], [])

    for g, V in enumerate(counts):
        t, e = run_independent(cfg, V, eval_steps, agent=agent, group=g,
                               seed=seed, device=device, deterministic=True)
        res["MEPPO"][0].append(t); res["MEPPO"][1].append(e)
        for name, pol in FIXED_POLICIES.items():
            t, e = run_independent(cfg, V, eval_steps, policy=pol, seed=seed)
            res[name][0].append(t); res[name][1].append(e)
    if rl_results:
        res.update(rl_results)

    fig, axes = plt.subplots(1, 2, figsize=(13.5, 4.8))
    order = ["MEPPO", "DDPG", "SAC", "Random", "Offloading-only", "Local-only"]
    for i, name in enumerate([n for n in order if n in res]):
        st = dict(marker="o", lw=2, color=PALETTE[i % len(PALETTE)],
                  label=name, zorder=5 if name == "MEPPO" else 3)
        axes[0].plot(counts, res[name][0], **st)
        axes[1].plot(counts, res[name][1], **st)
    axes[0].set_ylabel("request completion time (s)")
    axes[0].set_title("Fig. 10(a) -- request completion time")
    axes[1].set_ylabel("energy consumption (J)")
    axes[1].set_yscale("log")
    axes[1].set_title("Fig. 10(b) -- overall energy consumption")
    for a in axes:
        a.set_xlabel("number of vehicles"); a.grid(alpha=.3); a.legend(fontsize=9)
    return _save(fig, outdir, "fig10_method_comparison.png"), res


# ======================================================================
def fig11_priority_ablation(cfg, agent, outdir, device, eval_steps=1500, seed=7):
    """Fig. 11: prioritised versus non-prioritised execution.

    The control arm sets Config.USE_PRIORITY = False, which collapses every
    entity's priority queue to FIFO. This ablation is only measurable because
    execution queues are genuine priority queues -- with scalar finish-time
    markers there is nothing to turn off.
    """
    cfg = cfg.derive()
    counts, on, off, orc = list(cfg.VEHICLE_COUNTS), [], [], []
    # All three arms use the SAME offloading decisions (the agent's); only the
    # priority rule differs, so the bars isolate the priority mechanism alone.
    for g, V in enumerate(counts):
        cfg.USE_PRIORITY = True
        on.append(run_independent(cfg, V, eval_steps, agent=agent, group=g,
                                  seed=seed, device=device)[0])
        orc.append(run_independent(cfg, V, eval_steps, agent=agent, group=g,
                                   seed=seed, device=device,
                                   priority_rule="lpt")[0])
        cfg.USE_PRIORITY = False
        off.append(run_independent(cfg, V, eval_steps, agent=agent, group=g,
                                   seed=seed, device=device)[0])
    cfg.USE_PRIORITY = True

    x = np.arange(len(counts)); w = .27
    fig, ax = plt.subplots(figsize=(8.4, 4.4))
    ax.bar(x - w, on, w, label="MEPPO, learned priority", color=PALETTE[0])
    ax.bar(x, off, w, label="MEPPO, priority disabled (FIFO)", color=PALETTE[2])
    ax.bar(x + w, orc, w, label="LPT priority oracle (upper bound)",
           color=PALETTE[4], alpha=.85)
    for i, (a, b) in enumerate(zip(on, off)):
        if b > 0:
            ax.text(i - w / 2, max(a, b) * 1.02, f"{(b - a) / b * 100:+.1f}%",
                    ha="center", fontsize=8)
    ax.set_xticks(x); ax.set_xticklabels(counts)
    ax.set_xlabel("number of vehicles")
    ax.set_ylabel("request completion time (s)")
    ax.set_title("Fig. 11 -- influence of priority assignment")
    ax.legend(); ax.grid(alpha=.3, axis="y")
    return _save(fig, outdir, "fig11_priority.png"), dict(
        counts=counts, with_priority=on, without_priority=off, lpt_oracle=orc)


# ======================================================================
def fig12_power_ablation(cfg, outdir, eval_steps=1500, seed=11):
    """Fig. 12: dynamic (Eq. 19-20) versus fixed transmit power, measured on
    transmission energy with an offloading-heavy policy so the effect is not
    masked by local execution energy."""
    cfg = cfg.derive()
    counts, dyn, fix = list(cfg.VEHICLE_COUNTS), [], []
    pol = lambda rng, env: (np.full(env.K, 0), rng.integers(0, 10, env.K))
    for V in counts:
        cfg.USE_DYNAMIC_POWER = True
        dyn.append(run_independent(cfg, V, eval_steps, policy=pol, seed=seed)[1])
        cfg.USE_DYNAMIC_POWER = False
        fix.append(run_independent(cfg, V, eval_steps, policy=pol, seed=seed)[1])
    cfg.USE_DYNAMIC_POWER = True

    fig, ax = plt.subplots(figsize=(7.6, 4.4))
    ax.plot(counts, dyn, "o-", lw=2, color=PALETTE[0], label="dynamic transmit power")
    ax.plot(counts, fix, "s--", lw=2, color=PALETTE[1], label="fixed transmit power")
    ax.set_xlabel("number of vehicles")
    ax.set_ylabel("transmission energy consumption (J)")
    ax.set_title("Fig. 12 -- influence of dynamic transmit power allocation")
    ax.legend(); ax.grid(alpha=.3)
    return _save(fig, outdir, "fig12_transmit_power.png"), dict(
        counts=counts, dynamic=dyn, fixed=fix)


# ======================================================================
def load_nyc_traffic(cache_path=None, verbose=True, street="STATE STREET",
                     min_hours=12):
    """Ref. [34]: NYC OpenData Automated Traffic Volume Counts (7ym2-wayt).

    v6: fetches whatever the ACTUAL latest counted day is, instead of a
    hardcoded month. NYC DOT's Automated Traffic Recorders do not sample
    every street every month -- coverage is rotating and lagged -- so
    "August/September of the current year" cannot be promised for any one
    named street. What CAN be promised is that this function finds the truly
    most recent day this dataset has data for, tries the paper's own street
    first, and says on-screen exactly which date it used.

    Fallback chain, each tried only if the one above fails or returns too
    little data:
      1. most recent day with >= min_hours hourly readings for `street`
      2. most recent day with a citywide-wide sample (any street), same day
      3. a stored, dated copy of NYC's 19-25 Oct 2022 STATE STREET week --
         used only if the network is unreachable, and always labelled as such
    """
    if cache_path and os.path.exists(cache_path):
        d = np.loadtxt(cache_path, delimiter=",", skiprows=1)
        return d[:, 1], "cache", "cached copy"

    try:
        import requests
        base = "https://data.cityofnewyork.us/resource/7ym2-wayt.json"

        def get(params, timeout=45):
            r = requests.get(base, params=params, timeout=timeout)
            r.raise_for_status()
            return r.json()

        def latest_day(where):
            """Most recent (yr, m, d) with >= min_hours rows for `where`."""
            rows = get({"$select": "yr,m,d,count(*) as n", "$where": where,
                       "$group": "yr,m,d", "$having": f"count(*) >= {min_hours}",
                       "$order": "yr desc,m desc,d desc", "$limit": 1})
            return (int(float(rows[0]["yr"])), int(float(rows[0]["m"])),
                    int(float(rows[0]["d"]))) if rows else None

        def hourly(where, y, m, d):
            rows = get({"$select": "hh,avg(vol) as avg_vol",
                       "$where": f"{where} and yr={y} and m={m} and d={d}",
                       "$group": "hh", "$limit": 30})
            vol = np.full(24, np.nan)
            for row in rows:
                vol[int(float(row["hh"]))] = float(row["avg_vol"])
            if np.isnan(vol).sum() > 6:            # too sparse to trust
                return None
            idx = np.arange(24)
            ok = ~np.isnan(vol)
            return np.interp(idx, idx[ok], vol[ok])

        street_where = f"upper(street) like '%25{street.upper()}%25'"

        day = latest_day(street_where)
        if day is not None:
            vol = hourly(street_where, *day)
            if vol is not None:
                label = f"{street.title()}, {day[0]}-{day[1]:02d}-{day[2]:02d}"
                if verbose:
                    print(f"NYC OpenData: latest available day for {street.title()} "
                          f"is {label.split(', ')[1]} -- fetched, live.")
                return vol, "live", label

        if verbose:
            print(f"{street.title()} has no recent well-sampled day; "
                  "falling back to a citywide average for the most recent "
                  "well-sampled day (any location).")
        day = latest_day("1=1")
        if day is not None:
            vol = hourly("1=1", *day)
            if vol is not None:
                label = f"citywide average, {day[0]}-{day[1]:02d}-{day[2]:02d}"
                if verbose:
                    print(f"NYC OpenData: latest citywide day is "
                          f"{label.split(', ')[1]} -- fetched, live.")
                return vol, "live", label

        raise RuntimeError("no sufficiently-sampled recent day found")

    except Exception as exc:
        if verbose:
            print(f"NYC OpenData fetch failed ({exc!r}).")
            print("Using the STORED copy of STATE STREET, 19-25 Oct 2022. "
                  "This is archived real data, not synthetic -- but it is a "
                  "cache dated 2022, and your report must say so if it is used.")
        return (_STATE_STREET_OCT2022.copy(), "cache",
                "STATE STREET, 2022-10-19 (offline fallback)")


# Deepest fallback only -- used solely when the live query above fails
# entirely (e.g. no internet in this runtime). Not used when live data of
# ANY recency is reachable, including from a different street than the
# paper's.
_STATE_STREET_OCT2022 = np.array([
    143, 88, 62, 51, 82, 193, 332, 352, 316, 318, 287, 289,
    301, 312, 319, 324, 306, 320, 325, 329, 310, 304, 291, 227], dtype=float)


def fig13_traffic_adaptivity(cfg, agent, outdir, device, eval_steps=500, seed=5,
                             cache_path=None):
    """Fig. 13: time-saving and energy-saving ratios (Eq. 32) under the real
    24-hour traffic profile, and under a varying task load.

    Vehicle counts derived from traffic are usually NOT one of the five trained
    configurations, so the nearest-count policy is applied. That is precisely
    the environment-adaptivity claim (contribution 3) under test.
    """
    cfg = cfg.derive()
    vol, src, label = load_nyc_traffic(cache_path)
    norm = (vol - vol.min()) / max(float(np.ptp(vol)), 1e-9)
    counts = np.asarray(cfg.VEHICLE_COUNTS)
    lo, hi = counts.min(), counts.max()
    veh_by_hour = np.round(lo + norm * (hi - lo)).astype(int)

    TS, ES = [], []
    for V in veh_by_hour:
        g = int(np.argmin(np.abs(counts - V)))
        tm, em = run_independent(cfg, int(V), eval_steps, agent=agent, group=g,
                                 seed=seed, device=device)
        tl, el = run_independent(cfg, int(V), eval_steps,
                                 policy=FIXED_POLICIES["Local-only"], seed=seed)
        TS.append(1 - tm / tl if tl > 0 else 0)          # Eq. (32)
        ES.append(1 - em / el if el > 0 else 0)

    hours = np.arange(24)
    fig, axes = plt.subplots(1, 3, figsize=(16.5, 4.4))
    axes[0].plot(hours, vol, "o-", color=PALETTE[0])
    axes[0].set_title(f"Fig. 13(a) -- NYC DOT traffic volume\n{label}  [{src}]")
    axes[0].set_ylabel("vehicles / hour")

    axes[1].plot(hours, norm, color=PALETTE[4], lw=1.4, label="traffic (norm.)")
    axes[1].plot(hours, TS, "o-", color=PALETTE[1], label="time saving  TS")
    axes[1].plot(hours, ES, "s-", color=PALETTE[0], label="energy saving  ES")
    axes[1].set_title("Fig. 13(b) -- saving vs. changing traffic volume")
    axes[1].legend(fontsize=9)

    # Fig. 13(c): hold traffic fixed, vary the task load instead
    tsc, esc = [], []
    base_p = cfg.TASK_COUNT_BINOM_P
    for p in np.linspace(0.15, 0.85, 12):
        cfg.TASK_COUNT_BINOM_P = float(p)
        tm, em = run_independent(cfg, 30, eval_steps, agent=agent,
                                 group=int(np.argmin(np.abs(counts - 30))),
                                 seed=seed, device=device)
        tl, el = run_independent(cfg, 30, eval_steps,
                                 policy=FIXED_POLICIES["Local-only"], seed=seed)
        tsc.append(1 - tm / tl if tl > 0 else 0)
        esc.append(1 - em / el if el > 0 else 0)
    cfg.TASK_COUNT_BINOM_P = base_p
    load = np.linspace(0.15, 0.85, 12) * cfg.MAX_TASKS
    axes[2].plot(load, tsc, "o-", color=PALETTE[1], label="time saving  TS")
    axes[2].plot(load, esc, "s-", color=PALETTE[0], label="energy saving  ES")
    axes[2].set_xlabel("mean tasks per request")
    axes[2].set_title("Fig. 13(c) -- saving vs. changing task load")
    axes[2].legend(fontsize=9)

    for a in axes[:2]:
        a.set_xlabel("hour of day"); a.set_xticks(range(0, 24, 3))
    for a in axes:
        a.grid(alpha=.3)
    return _save(fig, outdir, "fig13_traffic_adaptivity.png"), dict(
        volume=vol.tolist(), vehicles=veh_by_hour.tolist(), TS=TS, ES=ES,
        source=src, date=label)
