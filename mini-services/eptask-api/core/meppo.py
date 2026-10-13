"""
meppo.py -- Multi-action, Environment-adaptive PPO (Section IV-F, Algorithm 1).

Faithful pieces:
  Eq. (24)      multi-action: one categorical head for offloading (4-way) and
                one for priority (10-way), per task slot -> the "M" in MEPPO.
  Eq. (26)      environment-adaptive: null-task padding, handled in the env.
  Eq. (27)-(30) clipped surrogate objective.
  Eq. (31)      truncated GAE.
  Algorithm 1   N parallel actors x T timesteps -> one update; K epochs of
                minibatch SGD at Table III's minibatch size of 32.

Corrections versus the v3 notebook:
  * critic target is the TD(lambda) return (advantage + value), consistent with
    the GAE advantages, instead of a Monte-Carlo return computed separately;
  * advantages are normalised PER GROUP, never pooled across configurations;
  * the RNG is seeded BEFORE the networks are constructed, so weight init is
    actually reproducible from Config.SEED;
  * one learning rate for actor and critic, as Table III specifies;
  * bootstrapped value at the rollout boundary (the VEC task is continuing;
    treating the 2048th step as terminal silently truncates every return).
"""
import numpy as np
import torch
import torch.nn as nn

from nets import GroupedActorCritic


class MEPPO:
    def __init__(self, cfg, groups, state_dim, device):
        self.cfg, self.G, self.device = cfg, groups, device
        torch.manual_seed(cfg.SEED)          # BEFORE net construction
        self.net = GroupedActorCritic(groups, state_dim).to(device)
        self.opt = torch.optim.Adam(self.net.parameters(), lr=cfg.LR, eps=1e-5)

    # ------------------------------------------------------------------
    @torch.no_grad()
    def act(self, obs_np, deterministic=False):
        s = torch.as_tensor(obs_np, dtype=torch.float32, device=self.device)
        a_off, a_pri, lp, v = self.net.act(s, deterministic)
        return (a_off.cpu().numpy(), a_pri.cpu().numpy(),
                lp.cpu().numpy(), v.cpu().numpy())

    # ------------------------------------------------------------------
    def gae(self, rew, val, last_val):
        """Eq. (31), truncated GAE over (T, G, N). No terminals inside a
        rollout -- the VEC scheduling task is continuing, so the tail is
        bootstrapped from V(s_T) rather than zeroed."""
        c = self.cfg
        T = rew.shape[0]
        adv = np.zeros_like(rew)
        gae = np.zeros_like(last_val)
        nxt = last_val
        for t in reversed(range(T)):
            delta = rew[t] + c.GAMMA * nxt - val[t]
            gae = delta + c.GAMMA * c.GAE_LAMBDA * gae
            adv[t] = gae
            nxt = val[t]
        return adv, adv + val

    # ------------------------------------------------------------------
    def update(self, buf):
        c, dev = self.cfg, self.device
        # buf tensors arrive as (T, G, N, ...) -> flatten time+actors per group
        def flat(x, *tail):
            T, G, N = x.shape[0], x.shape[1], x.shape[2]
            return torch.as_tensor(
                np.ascontiguousarray(x.transpose(1, 0, 2, *range(3, x.ndim))
                                     .reshape(G, T * N, *tail)),
                dtype=torch.float32, device=dev)

        obs = flat(buf["obs"], buf["obs"].shape[-1])
        a_off = flat(buf["a_off"], 10).long()
        a_pri = flat(buf["a_pri"], 10).long()
        old_lp = flat(buf["logp"])
        adv = flat(buf["adv"])
        ret = flat(buf["ret"])

        # per-group normalisation: configurations must not rescale each other
        adv = (adv - adv.mean(dim=1, keepdim=True)) / (
            adv.std(dim=1, keepdim=True) + 1e-8)

        n = obs.shape[1]
        mb = min(c.MINIBATCH_SIZE, n)
        stats = {"pi": 0.0, "v": 0.0, "ent": 0.0, "kl": 0.0, "clip": 0.0, "k": 0}

        for _ in range(c.K_EPOCHS):
            perm = torch.randperm(n, device=dev)
            for i in range(0, n, mb):
                idx = perm[i:i + mb]
                lp, v, ent = self.net.evaluate(obs[:, idx], a_off[:, idx],
                                               a_pri[:, idx])
                ratio = torch.exp(lp - old_lp[:, idx])
                a = adv[:, idx]
                s1 = ratio * a
                s2 = torch.clamp(ratio, 1 - c.EPS_CLIP, 1 + c.EPS_CLIP) * a

                # per-group means, summed over groups: group g's gradient is
                # exactly what it would be if trained alone.
                pi_loss = -torch.min(s1, s2).mean(dim=1).sum()
                v_loss = ((v - ret[:, idx]) ** 2).mean(dim=1).sum()
                ent_loss = ent.mean(dim=1).sum()
                loss = pi_loss + c.VALUE_COEF * v_loss - c.ENTROPY_COEF * ent_loss

                self.opt.zero_grad(set_to_none=True)
                loss.backward()
                nn.utils.clip_grad_norm_(self.net.parameters(), c.MAX_GRAD_NORM)
                self.opt.step()

                with torch.no_grad():
                    stats["pi"] += pi_loss.item()
                    stats["v"] += v_loss.item()
                    stats["ent"] += ent_loss.item() / self.G
                    stats["kl"] += (old_lp[:, idx] - lp).mean().item()
                    stats["clip"] += ((ratio - 1).abs() > c.EPS_CLIP
                                      ).float().mean().item()
                    stats["k"] += 1
        k = max(stats.pop("k"), 1)
        return {a: b / k for a, b in stats.items()}


# ----------------------------------------------------------------------
# fixed comparison policies -- definitions taken verbatim from Section V-B
# ----------------------------------------------------------------------
def policy_local(rng, env):
    """(e) Local-only: all tasks executed on the Task Vehicle itself."""
    return np.full(env.K, 2), rng.integers(0, 10, env.K)


def policy_offload(rng, env):
    """(d) Offloading-only: all tasks assigned to edge servers AND the cloud."""
    return rng.choice([0, 3], env.K), rng.integers(0, 10, env.K)


def policy_random(rng, env):
    """(c) Random: tasks randomly allocated to edge servers OR vehicles."""
    return rng.choice([0, 1], env.K), rng.integers(0, 10, env.K)


FIXED_POLICIES = {"Local-only": policy_local,
                  "Offloading-only": policy_offload,
                  "Random": policy_random}


def make_lpt_oracle(base_offload):
    """Longest-Processing-Time priority oracle.

    Eq. (18) makes a request's completion time a MAX, so the task that would
    otherwise finish last is the binding constraint; giving it the top priority
    slot is the makespan-optimal ranking. This oracle reads env.cycles directly
    and therefore upper-bounds what any learned priority head can achieve.

    Used as the third arm of Fig. 11: if trained-MEPPO sits near FIFO and far
    from this oracle, the priority head has not converged yet -- which is a
    training-budget statement, not evidence that priority does not help.
    """
    def pol(rng, env):
        off = base_offload(rng, env)[0]
        pri = np.zeros(env.K)
        pri[:env.n_tasks] = env.cycles[:env.n_tasks]   # longest -> best rank
        return off, pri
    return pol
