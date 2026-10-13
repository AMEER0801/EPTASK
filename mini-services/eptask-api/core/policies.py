"""
policies.py -- one interface for every decision-maker, plus the rollout
harness that every V7.1 experiment shares.

  act(env, obs) -> (offload[K], priority[K])
  logits(obs)   -> (offload_logits (K,4), priority_logits (K,10), value)
  cfg_kw        -> Config fields recorded with the policy. At evaluation ONLY
                   STATE_MODE is taken from it: the EXPERIMENT defines the world
                   (disaster or not, floors on or off); the policy only dictates
                   how that world is encoded for it. So a 29-dim policy is never
                   fed a 33-dim state, and two policies are always compared in
                   the same world.
"""
import json
import os

import numpy as np

from env import VECEnv


class TorchGroupPolicy:
    """Deterministic (argmax) evaluation of one group of a trained MEPPO --
    exactly what v6.1's evaluation did with agent.act(..., deterministic=True)."""
    kind = "torch"

    def __init__(self, agent, group, device="cpu", cfg_kw=None, name=None):
        self.agent, self.g, self.device = agent, int(group), device
        self.cfg_kw = dict(cfg_kw or {})
        self.state_dim = int(agent.net.a1.w.shape[1])
        self.name = name or f"torch[g={group}]"

    def logits(self, obs):
        import torch
        s = torch.zeros(self.agent.G, 1, self.state_dim, device=self.device)
        s[self.g, 0] = torch.as_tensor(np.asarray(obs, np.float32), device=self.device)
        with torch.no_grad():
            off, pri, v = self.agent.net(s)
        return (off[self.g, 0].cpu().numpy(), pri[self.g, 0].cpu().numpy(),
                float(v[self.g, 0]))

    def act(self, env, obs):
        off, pri, _ = self.logits(obs)
        return off.argmax(-1), pri.argmax(-1)


class OnnxPolicy:
    """The exported actor (what the demo runs). Reads the V7.1 sidecar JSON
    written next to the .onnx file for its state encoding."""
    kind = "onnx"

    def __init__(self, path, name=None):
        import onnxruntime as ort
        self.path = path
        self.sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
        self.state_dim = int(self.sess.get_inputs()[0].shape[1])
        side = path + ".json"
        self.meta = json.load(open(side)) if os.path.exists(side) else {}
        self.cfg_kw = dict(self.meta.get("cfg_kw", {}))
        self.name = name or os.path.basename(path)

    def logits(self, obs):
        off, pri = self.sess.run(None, {"state": np.asarray(obs, np.float32).reshape(1, -1)})
        return off[0], pri[0], float("nan")

    def act(self, env, obs):
        off, pri, _ = self.logits(obs)
        return off.argmax(-1), pri.argmax(-1)


class RulePolicy:
    """Fixed comparators.
      local       -- everything on board: failure-proof by construction (C3 bound)
      alive_aware -- the obvious hand-written rule: edge if reachable, else V2V
                     if a service vehicle is in range, else local; LPT ranking.
                     A learned policy must beat THIS to be worth training.
      random      -- untrained / adversarial policy: isolates a mechanism (a
                     floor) from anything learning could contribute
      edge        -- always offload to the edge (fallback rules apply)"""
    kind = "rule"

    def __init__(self, rule, seed=0, cfg_kw=None):
        assert rule in ("local", "alive_aware", "random", "edge"), rule
        self.rule, self.rng = rule, np.random.default_rng(seed)
        self.cfg_kw = dict(cfg_kw or {})
        self.name, self.state_dim = rule, None

    def act(self, env, obs):
        K = env.K
        if self.rule == "random":
            return self.rng.integers(0, 4, K), self.rng.integers(0, 10, K)
        if self.rule == "local":
            return np.full(K, 2), np.arange(K)
        if self.rule == "edge":
            return np.full(K, 0), np.arange(K)
        i = env.cursor
        if env.in_range[i]:
            a = 0
        elif env._select_sev(i)[0] is not None:
            a = 1
        else:
            a = 2
        pri = np.zeros(K)
        n = env.n_tasks
        pri[:n] = env.cycles[:n]
        return np.full(K, a), pri


def env_kw_for(policy, kw=None):
    """Experiment kw define the world; the policy contributes only STATE_MODE."""
    merged = {"TRACK_TRUE_T": True, "RANDOM_DISASTERS": False}
    merged.update(kw or {})
    sm = (getattr(policy, "cfg_kw", None) or {}).get("STATE_MODE")
    if sm is not None:
        merged["STATE_MODE"] = sm
    return merged


def rollout(cfg, V, policy, steps, seed, kw=None, events=(), fail_blocks=()):
    """One world, one policy, `steps` ticks, recorded so that every summary
    number can be recomputed from the returned records.

    events      : [(t, s0, k, dur)] scripted disasters (forces DISASTER_MODE):
                  RSUs s0..s0+k-1 offline AND the sensing window open
    fail_blocks : [(t, s0, k, dur)] bare RSU outages (C3-style, no sensing)

    Returns req (one dict per SETTLED request: metadata + true/reported/local
    T, deadline, on-time flag), step (per-tick arrays), and bookkeeping.
    Requests still unsettled at the end are excluded and counted in `pending`
    (right-censoring: run past your measurement window).
    """
    merged = env_kw_for(policy, kw)
    if events:
        merged["DISASTER_MODE"] = True
    ev = {int(a): (s0, k, d) for (a, s0, k, d) in events}
    fb = {}
    for (a, s0, k, d) in fail_blocks:
        fb.setdefault(int(a), []).append((s0, k, d))
    st = {k: [] for k in ("t", "T", "E", "alive", "dis", "prot", "role", "edge_ok")}
    tg = []
    with cfg.override(**merged):
        env = VECEnv(cfg, V, seed=seed)
        if policy.state_dim is not None and policy.state_dim != env.state_dim:
            raise ValueError(f"{policy.name} expects state_dim {policy.state_dim}, "
                             f"the environment produces {env.state_dim}")
        obs = env.observe()
        for step in range(steps):
            if step in ev:
                env.trigger_disaster(*ev[step])
            for (s0, k, d) in fb.get(step, ()):
                for j in range(s0, s0 + k):
                    env.fail_server(j, d)
            off, pri = policy.act(env, obs)
            obs, _, inf = env.step(off, pri)
            m = inf["meta"]
            st["t"].append(m["t"]); st["T"].append(inf["T"]); st["E"].append(inf["E"])
            st["alive"].append(inf["alive"]); st["dis"].append(inf["dis"])
            st["prot"].append(m["prot"]); st["role"].append(m["role"])
            st["edge_ok"].append(m["edge_ok"]); tg.append(inf["tg"])
        req = []
        for (tT, rep, loc, _tag), m in zip(env.true_pairs, env.true_meta):
            D = cfg.DEADLINE_MULT[m["key"]] * loc
            q = dict(m)
            q.update(Ttrue=float(tT), Trep=float(rep), Tloc=float(loc), D=float(D),
                     ontime=bool(tT <= D))
            req.append(q)
        out = dict(req=req, pending=len(env._pending), V=V, seed=seed, kw=merged,
                   disaster_log=list(env.disaster.log) if env.disaster is not None else [],
                   n_emergency=int(env.is_emergency.sum()), n_tav=int(len(env.tav_idx)))
    s = {k: np.asarray(v) for k, v in st.items()}
    s["tg"] = np.asarray(tg, dtype=np.int64).reshape(-1, 4)
    out["step"] = s
    return out


def summarize(req, pred=None, t0=None, t1=None, weight=None):
    """n, mean TRUE completion time, miss % (and value-weighted on-time % if
    `weight` is given) over settled requests matching pred, issued in [t0, t1)."""
    sel = [q for q in req if q["n"] > 0 and (pred is None or pred(q))
           and (t0 is None or q["t"] >= t0) and (t1 is None or q["t"] < t1)]
    if not sel:
        return dict(n=0, T=float("nan"), miss=float("nan"), wontime=float("nan"))
    T = np.array([q["Ttrue"] for q in sel])
    on = np.array([q["ontime"] for q in sel], dtype=float)
    out = dict(n=len(sel), T=float(T.mean()), miss=float(100.0 * (1.0 - on.mean())),
               wontime=float("nan"))
    if weight is not None:
        w = np.array([weight(q) for q in sel], dtype=float)
        out["wontime"] = float(100.0 * (w * on).sum() / max(w.sum(), 1e-12))
    return out


def window_share(step, t0, t1, col):
    """Share (%) of tasks issued in [t0, t1) whose REALISED target was `col`
    (0 edge, 1 V2V, 2 local, 3 cloud), after the infeasibility fallback."""
    t = step["t"]
    w = (t >= t0) & (t < t1)
    tot = step["tg"][w].sum(0)
    return float(100.0 * tot[col] / max(tot.sum(), 1))
