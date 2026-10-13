"""app/outage_svc.py -- live paired outage study (the notebook's C3).

Reuses the ORIGINAL policies.rollout harness with the SAME pairing semantics
as contributions.c3_paired: for every (k, policy, seed) one run with RSUs
s0..s0+k-1 down during [fail_at, fail_at+fail_dur) and one identical run
without the outage; excess = paired difference of mean reported T. Policies:
the shipped ONNX exports of model A / model B, plus the two RulePolicy
comparators from the notebook.
"""
from __future__ import annotations

import time

import numpy as np

from .state import STATE

MODEL_LABEL = {"A": "model A (static)", "B": "model B (DR-MEPPO)"}
BASELINE_LABEL = {"alive_aware": "alive-aware rule", "local": "Local-only"}


def _factory(spec: str):
    """spec: 'A' | 'B' (ONNX exports) | 'alive_aware' | 'local' (RulePolicy)."""
    if spec in ("A", "B"):
        pol = STATE.policy(spec, 30)

        def fac(V, seed, _pol=pol):
            return _pol
        return fac, MODEL_LABEL[spec]
    from policies import RulePolicy  # original eptask module

    def fac(V, seed, _rule=spec):
        return RulePolicy(_rule, seed=seed)
    return fac, BASELINE_LABEL[spec]


def run_outage(params: dict, progress=None) -> dict:
    """Params: policies (subset of A,B,alive_aware,local), V, k_list, seeds,
    fail_at, fail_dur, post. Uses policies.rollout exactly like
    contributions.c3_paired (TRACK_TRUE_T=False, calm world, bare outage)."""
    from config import Config       # original eptask module
    from policies import rollout    # original eptask module
    from runlog import mean_ci      # original eptask module

    t_wall = time.time()
    V = int(params["V"])
    k_list = [int(k) for k in params["k_list"]]
    seeds = [int(s) for s in params["seeds"]]
    fail_at, fail_dur, post = int(params["fail_at"]), int(params["fail_dur"]), int(params["post"])
    specs = params["policies"]
    cfg = Config.derive()
    kw = {"TRACK_TRUE_T": False}
    steps = fail_at + fail_dur + post + 1
    S = cfg.NUM_EDGE_SERVERS

    report = progress or (lambda f, s=None: None)
    facs = {}
    for i, sp in enumerate(specs):
        fac, label = _factory(sp)
        facs[sp] = (fac, label)
        report(0.02 + 0.05 * i / len(specs), f"loading {label}")

    rows, order = {}, []
    n_runs = len(k_list) * len(seeds) * (len(facs) + 1)
    done = 0
    for k in k_list:
        s0 = (S - k) // 2
        for sp, (fac, label) in facs.items():
            ex_d, ex_p, absT, ctrlT = [], [], [], []
            for sd in seeds:
                pf, pc = fac(V, sd), fac(V, sd)
                Rf = rollout(cfg, V, pf, steps, sd, kw=kw,
                             fail_blocks=[(fail_at, s0, k, fail_dur)])
                Rc = rollout(cfg, V, pc, steps, sd, kw=kw)
                Tf, Tc = Rf["step"]["T"], Rc["step"]["T"]
                w = slice(fail_at, fail_at + fail_dur)
                p = slice(fail_at + fail_dur, fail_at + fail_dur + post)
                ex_d.append(float((Tf[w].mean() - Tc[w].mean()) / Tc[w].mean() * 100))
                ex_p.append(float((Tf[p].mean() - Tc[p].mean()) / Tc[p].mean() * 100))
                absT.append(float(Tf[w].mean()))
                ctrlT.append(float(Tc[w].mean()))
                done += 2
                report(0.1 + 0.85 * done / n_runs, f"k={k} {label} seed {sd}")
            key = f"k={k} | {label}"
            rows[key] = dict(k=k, policy=label, spec=sp,
                             during_pct=list(mean_ci(ex_d)), post_pct=list(mean_ci(ex_p)),
                             T_outage=list(mean_ci(absT)), T_control=list(mean_ci(ctrlT)),
                             raw=dict(during=ex_d, post=ex_p, T_outage=absT, T_control=ctrlT))
            order.append(key)
    report(1.0, "done")
    return dict(config=dict(V=V, k_list=k_list, seeds=seeds, fail_at=fail_at,
                            fail_dur=fail_dur, post=post, steps=steps,
                            policies=[facs[sp][1] for sp in specs],
                            generator="policies.rollout (eptask v7.1, executed live)"),
                rows=rows, order=order,
                timing=dict(total_seconds=round(time.time() - t_wall, 3)))
