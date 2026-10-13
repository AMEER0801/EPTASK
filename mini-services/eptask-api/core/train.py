"""
train.py -- rollout collection and evaluation driver.

One call to train() trains ALL vehicle-count configurations simultaneously
(group g <-> Config.VEHICLE_COUNTS[g]) via the grouped network in nets.py.
"""
import time
import numpy as np
import torch

from env import VECEnv
from meppo import MEPPO, FIXED_POLICIES
from runlog import cfg_snapshot


# ----------------------------------------------------------------------
class GroupedWorlds:
    """G configurations x N parallel actors, stepped together.

    Layout is (G, N): group g holds N independent worlds all sized at
    VEHICLE_COUNTS[g]. Observations come back as (G, N, state_dim), which is
    exactly the shape the grouped network consumes.
    """

    def __init__(self, cfg, vehicle_counts, n_actors, seed=0):
        self.cfg = cfg
        self.counts = list(vehicle_counts)
        self.G, self.N = len(self.counts), n_actors
        self.envs = [[VECEnv(cfg, V, seed=seed + 7919 * g + k)
                      for k in range(n_actors)]
                     for g, V in enumerate(self.counts)]
        self.state_dim = self.envs[0][0].state_dim
        # V7.1: protected-class deadline misses, accumulated per episode
        self.prot_n = np.zeros(self.G)
        self.prot_miss = np.zeros(self.G)

    def reset(self):
        return np.stack([[e.reset() for e in row] for row in self.envs])

    def observe(self):
        return np.stack([[e.observe() for e in row] for row in self.envs])

    def step(self, a_off, a_pri):
        obs = np.empty((self.G, self.N, self.state_dim), dtype=np.float32)
        rew = np.empty((self.G, self.N), dtype=np.float32)
        T = np.empty((self.G, self.N), dtype=np.float32)
        E = np.empty((self.G, self.N), dtype=np.float32)
        for g in range(self.G):
            for k in range(self.N):
                o, r, inf = self.envs[g][k].step(a_off[g, k], a_pri[g, k])
                obs[g, k], rew[g, k] = o, r
                T[g, k], E[g, k] = inf["T"], inf["E"]
                m = inf["meta"]
                if m["prot"] and m["n"]:
                    self.prot_n[g] += 1
                    if inf["T"] > self.cfg.DEADLINE_MULT[m["key"]] * inf["Tl"]:
                        self.prot_miss[g] += 1
        return obs, rew, T, E

    def peek_fixed(self, rng):
        """Counterfactual T/E for each Section V-B policy, on the SAME request
        and the SAME queue state the agent is about to act on. This is the fix
        for the v3 off-by-one, where baselines were scored on the *next*
        vehicle's request after the cursor had already advanced."""
        out = {n: (np.zeros((self.G, self.N)), np.zeros((self.G, self.N)))
               for n in FIXED_POLICIES}
        for g in range(self.G):
            for k in range(self.N):
                e = self.envs[g][k]
                for name, pol in FIXED_POLICIES.items():
                    off, pri = pol(rng, e)
                    t, en, _ = e.peek(off, pri)
                    out[name][0][g, k] = t
                    out[name][1][g, k] = en
        return out


# ----------------------------------------------------------------------
def train(cfg, device, n_episodes=None, track_baselines_every=8, log_every=25,
          progress=None, checkpoint_path=None, checkpoint_every=50,
          vehicle_counts=None, cfg_kw=None):
    """
    checkpoint_path, if given, is where agent.net.state_dict() is
    auto-saved every `checkpoint_every` episodes AND once more at the very
    end. A checkpoint written mid-run is directly usable for ONNX export,
    so even a run that disconnects early leaves a usable, if
    less-converged, policy behind.
    """
    cfg = cfg.derive()
    n_episodes = n_episodes or cfg.N_EPISODES
    rng = np.random.default_rng(cfg.SEED)

    counts = list(vehicle_counts or cfg.VEHICLE_COUNTS)     # V7.1: subset allowed
    worlds = GroupedWorlds(cfg, counts, cfg.N_ACTORS, seed=cfg.SEED)
    agent = MEPPO(cfg, worlds.G, worlds.state_dim, device)

    G, N, T = worlds.G, worlds.N, cfg.STEPS_PER_ACTOR
    obs = worlds.reset()

    hist = {"return": [], "T": [], "E": [], "kl": [], "clip": [], "ent": [], "prot_miss": [],
            "base": {n: {"T": [], "E": []} for n in FIXED_POLICIES},
            "base_ep": []}
    t0 = time.time()

    def _save_checkpoint(ep):
        if not checkpoint_path:
            return
        import os
        os.makedirs(os.path.dirname(checkpoint_path) or ".", exist_ok=True)
        torch.save({
            "state_dict": agent.net.state_dict(),
            "vehicle_counts": counts,
            "cfg_kw": dict(cfg_kw or {}), "cfg": cfg_snapshot(cfg),
            "state_dim": worlds.state_dim,
            "n_tasks": agent.net.K, "n_offload": agent.net.A,
            "n_prio": agent.net.P,
            "episode": ep, "n_episodes": n_episodes,
        }, checkpoint_path)

    for ep in range(1, n_episodes + 1):
        buf = {
            "obs": np.zeros((T, G, N, worlds.state_dim), np.float32),
            "a_off": np.zeros((T, G, N, 10), np.float32),
            "a_pri": np.zeros((T, G, N, 10), np.float32),
            "logp": np.zeros((T, G, N), np.float32),
            "val": np.zeros((T, G, N), np.float32),
            "rew": np.zeros((T, G, N), np.float32),
        }
        ep_T = np.zeros((T, G, N), np.float32)
        ep_E = np.zeros((T, G, N), np.float32)
        want_base = (ep % track_baselines_every == 0) or ep == 1
        bacc = {n: [np.zeros((G, N)), np.zeros((G, N)), 0] for n in FIXED_POLICIES}

        for t in range(T):
            if want_base and t % 16 == 0:          # subsample: peek is not free
                for name, (bt, be) in worlds.peek_fixed(rng).items():
                    bacc[name][0] += bt
                    bacc[name][1] += be
                    bacc[name][2] += 1

            a_off, a_pri, logp, val = agent.act(obs)
            buf["obs"][t], buf["a_off"][t], buf["a_pri"][t] = obs, a_off, a_pri
            buf["logp"][t], buf["val"][t] = logp, val
            obs, rew, Tt, Ee = worlds.step(a_off, a_pri)
            buf["rew"][t], ep_T[t], ep_E[t] = rew, Tt, Ee

        with torch.no_grad():
            _, _, last_v = agent.net(
                torch.as_tensor(obs, dtype=torch.float32, device=device))
            last_v = last_v.cpu().numpy()

        buf["adv"], buf["ret"] = agent.gae(buf["rew"], buf["val"], last_v)
        stats = agent.update(buf)

        # Fig. 9 plots CUMULATIVE episode return (its y-axis reaches ~1200
        # over 2048 steps), not the per-step mean.
        # Rescaled to a full ROLLOUT_STEPS-long episode so the y-axis is
        # directly comparable with Fig. 9 (which reaches ~1200 over 2048 steps).
        hist["return"].append(buf["rew"].mean(axis=(0, 2)) * cfg.ROLLOUT_STEPS)
        hist["T"].append(ep_T.mean(axis=(0, 2)))
        hist["E"].append(ep_E.mean(axis=(0, 2)))
        hist["prot_miss"].append(worlds.prot_miss / np.maximum(worlds.prot_n, 1) * 100)
        worlds.prot_n[:] = 0
        worlds.prot_miss[:] = 0
        hist["kl"].append(stats["kl"]); hist["clip"].append(stats["clip"])
        hist["ent"].append(stats["ent"])
        if want_base:
            hist["base_ep"].append(ep - 1)
            for name, (bt, be, cnt) in bacc.items():
                hist["base"][name]["T"].append((bt / cnt).mean(axis=1))
                hist["base"][name]["E"].append((be / cnt).mean(axis=1))

        if progress is not None:
            progress(ep, n_episodes)
        if ep % log_every == 0 or ep == 1:
            el = time.time() - t0
            r = hist["return"][-1]
            print(f"ep {ep:4d}/{n_episodes} | return " +
                  " ".join(f"{v:7.1f}" for v in r) +
                  f" | T {hist['T'][-1].mean():6.2f}s"
                  f" | KL {stats['kl']:+.4f} clip {stats['clip']:.2f}"
                  f" | {el/60:5.1f}m  eta {el/ep*(n_episodes-ep)/60:5.1f}m")
        if checkpoint_path and (ep % checkpoint_every == 0 or ep == n_episodes):
            _save_checkpoint(ep)

    for k in ("return", "T", "E", "prot_miss"):
        hist[k] = np.array(hist[k])
    for n in FIXED_POLICIES:
        for k in ("T", "E"):
            hist["base"][n][k] = np.array(hist["base"][n][k])
    hist["counts"] = counts
    hist["minutes"] = (time.time() - t0) / 60
    _save_checkpoint(n_episodes)          # guaranteed final save
    return agent, hist


# ----------------------------------------------------------------------
def run_independent(cfg, num_vehicles, steps, agent=None, group=None,
                    policy=None, seed=0, device="cpu", deterministic=True,
                    priority_rule="agent"):
    """One FULL independent rollout of a single method in its own world.

    Fig. 10 compares methods that each evolved their own queues from scratch.
    Scoring a baseline against queues that the trained agent built is a
    different (and easier) question -- so the final comparison uses this, not
    the per-step counterfactual peek.

    `priority_rule` isolates the priority head for Fig. 11 while holding the
    offloading decisions fixed at whatever the agent chose:
      "agent" -- use the priority head's own output
      "lpt"   -- overwrite it with the Longest-Processing-Time ranking, which
                 is makespan-optimal because Eq. (18) is a max. This is the
                 oracle upper bound on what the priority head could learn.
    """
    cfg = cfg.derive()
    env = VECEnv(cfg, num_vehicles, seed=seed)
    rng = np.random.default_rng(seed)
    obs = env.reset()
    Ts, Es = [], []
    for _ in range(steps):
        if policy is not None:
            off, pri = policy(rng, env)
        else:
            s = torch.zeros(agent.G, 1, env.state_dim, device=device)
            s[group, 0] = torch.as_tensor(obs, device=device)
            a_off, a_pri, _, _ = agent.act(s.cpu().numpy(),
                                           deterministic=deterministic)
            off, pri = a_off[group, 0], a_pri[group, 0]
            if priority_rule == "lpt":
                pri = np.zeros(env.K)
                pri[:env.n_tasks] = env.cycles[:env.n_tasks]
        obs, _, inf = env.step(off, pri)
        Ts.append(inf["T"]); Es.append(inf["E"])
    return float(np.mean(Ts)), float(np.mean(Es))
