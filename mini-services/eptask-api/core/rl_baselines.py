"""
rl_baselines.py -- the two learned comparators from Section V-B that the v3
notebook left unimplemented.

  (a) DDPG [20] -- "mainly aims to optimize the request completion time".
      DDPG is defined for continuous actions, so the 20 discrete heads are
      relaxed with straight-through Gumbel-softmax: the actor emits logits,
      the critic consumes the relaxed one-hot, and the environment receives
      the hard argmax. Reward weights time only (alpha=1, beta=0), matching
      the paper's description of what this comparator optimises.

  (b) SAC [21] -- "joint optimization of completion time and energy usage".
      Discrete SAC with factored heads: the entropy term and the soft value
      are summed over the 20 independent categorical heads, and the actor
      loss uses the exact expectation over each head rather than a sample
      estimate. Reward weights time and energy equally, as MEPPO does.

Both share the identical environment, state, action space and reward machinery
as MEPPO so the Fig. 10 comparison is apples to apples.
"""
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

K, A, P = 10, 4, 10          # tasks, offload classes, priority classes
HEADS = [A] * K + [P] * K    # 20 factored categorical heads
TOT = sum(HEADS)


def _mlp(i, o, h=64):
    return nn.Sequential(nn.Linear(i, h), nn.Tanh(), nn.Linear(h, h),
                         nn.Tanh(), nn.Linear(h, o))


def _split(x):
    return torch.split(x, HEADS, dim=-1)


def _to_env(a):
    return a[:K], a[K:]


# ======================================================================
class DDPG:
    def __init__(self, sdim, device, lr=3e-4, gamma=0.99, tau=0.005):
        self.dev, self.gamma, self.tau = device, gamma, tau
        self.actor = _mlp(sdim, TOT).to(device)
        self.actor_t = _mlp(sdim, TOT).to(device)
        self.critic = _mlp(sdim + TOT, 1).to(device)
        self.critic_t = _mlp(sdim + TOT, 1).to(device)
        self.actor_t.load_state_dict(self.actor.state_dict())
        self.critic_t.load_state_dict(self.critic.state_dict())
        self.oa = torch.optim.Adam(self.actor.parameters(), lr=lr)
        self.oc = torch.optim.Adam(self.critic.parameters(), lr=lr)
        self.buf, self.cap = [], 100_000

    def _relax(self, logits, hard=True, tau=1.0):
        outs = []
        for lg in _split(logits):
            outs.append(F.gumbel_softmax(lg, tau=tau, hard=hard))
        return torch.cat(outs, -1)

    @torch.no_grad()
    def act(self, s, explore=True):
        s = torch.as_tensor(s, dtype=torch.float32, device=self.dev)[None]
        lg = self.actor(s)
        if explore:
            oh = self._relax(lg, hard=True, tau=1.0)[0]
        else:
            oh = torch.cat([F.one_hot(l.argmax(-1), n).float()
                            for l, n in zip(_split(lg[0]), HEADS)], -1)
        idx, out = 0, []
        for n in HEADS:
            out.append(int(oh[idx:idx + n].argmax().item())); idx += n
        return np.array(out), oh.cpu().numpy()

    def store(self, s, a, r, s2):
        self.buf.append((s, a, r, s2))
        if len(self.buf) > self.cap:
            self.buf.pop(0)

    def update(self, batch=64):
        if len(self.buf) < 1000:
            return
        i = np.random.randint(0, len(self.buf), batch)
        s, a, r, s2 = (torch.as_tensor(np.stack([self.buf[j][k] for j in i]),
                                       dtype=torch.float32, device=self.dev)
                       for k in range(4))
        r = r.view(-1, 1)
        with torch.no_grad():
            a2 = self._relax(self.actor_t(s2), hard=True)
            y = r + self.gamma * self.critic_t(torch.cat([s2, a2], -1))
        cl = F.mse_loss(self.critic(torch.cat([s, a], -1)), y)
        self.oc.zero_grad(); cl.backward(); self.oc.step()

        ar = self._relax(self.actor(s), hard=True)     # straight-through
        al = -self.critic(torch.cat([s, ar], -1)).mean()
        self.oa.zero_grad(); al.backward(); self.oa.step()

        for net, tgt in ((self.actor, self.actor_t), (self.critic, self.critic_t)):
            for p, pt in zip(net.parameters(), tgt.parameters()):
                pt.data.mul_(1 - self.tau).add_(self.tau * p.data)


# ======================================================================
class SACD:
    """Discrete SAC with factored heads."""

    def __init__(self, sdim, device, lr=3e-4, gamma=0.99, tau=0.005,
                 target_entropy_scale=0.6):
        self.dev, self.gamma, self.tau = device, gamma, tau
        self.actor = _mlp(sdim, TOT).to(device)
        self.q1, self.q2 = _mlp(sdim, TOT).to(device), _mlp(sdim, TOT).to(device)
        self.q1t, self.q2t = _mlp(sdim, TOT).to(device), _mlp(sdim, TOT).to(device)
        self.q1t.load_state_dict(self.q1.state_dict())
        self.q2t.load_state_dict(self.q2.state_dict())
        self.oa = torch.optim.Adam(self.actor.parameters(), lr=lr)
        self.oq = torch.optim.Adam(list(self.q1.parameters())
                                   + list(self.q2.parameters()), lr=lr)
        self.log_alpha = torch.zeros(1, requires_grad=True, device=device)
        self.oal = torch.optim.Adam([self.log_alpha], lr=lr)
        self.target_ent = -target_entropy_scale * sum(np.log(n) for n in HEADS)
        self.buf, self.cap = [], 100_000

    @torch.no_grad()
    def act(self, s, explore=True):
        s = torch.as_tensor(s, dtype=torch.float32, device=self.dev)[None]
        out = []
        for lg in _split(self.actor(s)[0]):
            p = F.softmax(lg, -1)
            out.append(int(torch.multinomial(p, 1) if explore else p.argmax()))
        return np.array(out)

    def store(self, s, a, r, s2):
        self.buf.append((s, a, r, s2))
        if len(self.buf) > self.cap:
            self.buf.pop(0)

    def _dist(self, net, s):
        return [F.softmax(l, -1) for l in _split(net(s))]

    def update(self, batch=64):
        if len(self.buf) < 1000:
            return
        i = np.random.randint(0, len(self.buf), batch)
        s = torch.as_tensor(np.stack([self.buf[j][0] for j in i]),
                            dtype=torch.float32, device=self.dev)
        a = torch.as_tensor(np.stack([self.buf[j][1] for j in i]),
                            dtype=torch.long, device=self.dev)
        r = torch.as_tensor(np.array([self.buf[j][2] for j in i]),
                            dtype=torch.float32, device=self.dev).view(-1, 1)
        s2 = torch.as_tensor(np.stack([self.buf[j][3] for j in i]),
                             dtype=torch.float32, device=self.dev)
        alpha = self.log_alpha.exp().detach()

        with torch.no_grad():
            p2 = self._dist(self.actor, s2)
            q1n, q2n = _split(self.q1t(s2)), _split(self.q2t(s2))
            soft_v = 0.0
            for pp, qa, qb in zip(p2, q1n, q2n):
                lp = torch.log(pp + 1e-8)
                soft_v = soft_v + (pp * (torch.min(qa, qb) - alpha * lp)).sum(-1, keepdim=True)
            y = r + self.gamma * soft_v

        loss_q = 0.0
        for net in (self.q1, self.q2):
            qs = _split(net(s))
            q_tot = sum(q.gather(1, a[:, h:h + 1]) for h, q in enumerate(qs))
            loss_q = loss_q + F.mse_loss(q_tot, y)
        self.oq.zero_grad(); loss_q.backward(); self.oq.step()

        p = self._dist(self.actor, s)
        q1s, q2s = _split(self.q1(s)), _split(self.q2(s))
        ent, obj = 0.0, 0.0
        for pp, qa, qb in zip(p, q1s, q2s):
            lp = torch.log(pp + 1e-8)
            ent = ent + (-(pp * lp).sum(-1, keepdim=True))
            obj = obj + (pp * torch.min(qa, qb).detach()).sum(-1, keepdim=True)
        loss_a = (-(obj) - alpha * ent).mean()
        self.oa.zero_grad(); loss_a.backward(); self.oa.step()

        loss_al = -(self.log_alpha * (self.target_ent - ent.detach()).mean())
        self.oal.zero_grad(); loss_al.backward(); self.oal.step()

        for net, tgt in ((self.q1, self.q1t), (self.q2, self.q2t)):
            for pa, pt in zip(net.parameters(), tgt.parameters()):
                pt.data.mul_(1 - self.tau).add_(self.tau * pa.data)


# ======================================================================
def train_offpolicy(cfg, algo, num_vehicles, steps, device, seed=0,
                    update_every=2, energy_weight=None):
    """Shared loop for DDPG / SAC. `energy_weight` overrides Eq. (25)'s beta:
    DDPG is described as time-only, SAC as joint."""
    from env import VECEnv
    cfg = cfg.derive()
    env = VECEnv(cfg, num_vehicles, seed=seed)
    torch.manual_seed(cfg.SEED + seed)
    agent = (DDPG if algo == "ddpg" else SACD)(env.state_dim, device)
    beta = cfg.BETA_R if energy_weight is None else energy_weight
    alpha = 1.0 - beta if energy_weight is not None else cfg.ALPHA_R

    s = env.reset()
    for t in range(steps):
        if algo == "ddpg":
            a, a_oh = agent.act(s)
        else:
            a = agent.act(s)
        off, pri = _to_env(a)
        s2, _, inf = env.step(off, pri)
        env.max_T = max(env.max_T, inf["T"]); env.max_E = max(env.max_E, inf["E"])
        r = 1.0 - (alpha * inf["T"] / env.max_T + beta * inf["E"] / env.max_E) - inf["pen"]
        agent.store(s, a_oh if algo == "ddpg" else a, r, s2)
        s = s2
        if t % update_every == 0:
            agent.update()
    return agent, env


@torch.no_grad()
def eval_offpolicy(cfg, agent, algo, num_vehicles, steps, seed=123):
    from env import VECEnv
    env = VECEnv(cfg.derive(), num_vehicles, seed=seed)
    s = env.reset(); Ts, Es = [], []
    for _ in range(steps):
        a = agent.act(s, explore=False)
        a = a[0] if algo == "ddpg" else a
        off, pri = _to_env(a)
        s, _, inf = env.step(off, pri)
        Ts.append(inf["T"]); Es.append(inf["E"])
    return float(np.mean(Ts)), float(np.mean(Es))
