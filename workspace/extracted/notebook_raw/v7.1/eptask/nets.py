"""
nets.py -- Fig. 4(a) actor/critic, replicated G times and fused into batched
matmuls so that all G independent policies train in ONE set of GPU kernels.

WHY THIS EXISTS
---------------
The paper's Figs. 9-12 all sweep the vehicle count over {10,20,30,40,50}.
That is five completely independent training runs. Each policy is a 19->64->64
MLP -- far too small to saturate a T4, so five sequential runs would leave the
GPU ~95% idle and take 5x the wall clock.

Instead the five policies are stored as parameter tensors with a leading group
axis, and every layer is a `torch.baddbmm`. Group g only ever touches
parameter slice g, so the runs remain mathematically independent (there is a
gradient-isolation unit test in test_isolation()), but the GPU sees one batched
op instead of five small ones. On a Colab T4 this turns ~3 hours into ~35 min.

This is not a deviation from the paper: each group is a bit-for-bit ordinary
PPO run of the Fig. 4(a) architecture. It is purely an execution strategy, and
one the paper itself gestures at in Section I-A when it credits PPO2 with
"better GPU utilization by batching observations from multiple simulation
environments".

ARCHITECTURE (Fig. 4(a), unchanged)
-----------------------------------
  Actor : Linear(state,64) - Tanh - Linear(64,64) - Tanh
          -> offload head  Linear(64, 10*4)   (categorical, from logits)
          -> priority head Linear(64, 10*10)  (categorical, from logits)
  Critic: Linear(state,64) - Tanh - Linear(64,64) - Tanh - Linear(64,1)
No softmax layer: the paper samples from a categorical built on raw logits.
"""
import math
import torch
import torch.nn as nn
from torch.distributions import Categorical


class GroupedLinear(nn.Module):
    """G independent Linear(in,out) layers evaluated as one bmm."""

    def __init__(self, groups, d_in, d_out):
        super().__init__()
        self.w = nn.Parameter(torch.empty(groups, d_in, d_out))
        self.b = nn.Parameter(torch.zeros(groups, 1, d_out))
        # per-group Kaiming-uniform, identical in distribution to nn.Linear
        bound = 1.0 / math.sqrt(d_in)
        nn.init.uniform_(self.w, -bound, bound)
        nn.init.uniform_(self.b, -bound, bound)

    def forward(self, x):                      # x: (G, B, d_in)
        return torch.baddbmm(self.b, x, self.w)


class GroupedActorCritic(nn.Module):
    def __init__(self, groups, state_dim, n_tasks=10, n_offload=4, n_prio=10,
                 hidden=64):
        super().__init__()
        self.G, self.K, self.A, self.P = groups, n_tasks, n_offload, n_prio
        self.a1 = GroupedLinear(groups, state_dim, hidden)
        self.a2 = GroupedLinear(groups, hidden, hidden)
        self.h_off = GroupedLinear(groups, hidden, n_tasks * n_offload)
        self.h_pri = GroupedLinear(groups, hidden, n_tasks * n_prio)
        self.c1 = GroupedLinear(groups, state_dim, hidden)
        self.c2 = GroupedLinear(groups, hidden, hidden)
        self.c3 = GroupedLinear(groups, hidden, 1)
        # smaller final-layer gain keeps the initial policy near-uniform,
        # which matters because the joint action factorises over 20 heads
        for h in (self.h_off, self.h_pri):
            nn.init.uniform_(h.w, -0.01, 0.01)
            nn.init.zeros_(h.b)

    def forward(self, s):                      # s: (G, B, state_dim)
        x = torch.tanh(self.a2(torch.tanh(self.a1(s))))
        G, B = s.shape[0], s.shape[1]
        off = self.h_off(x).view(G, B, self.K, self.A)
        pri = self.h_pri(x).view(G, B, self.K, self.P)
        v = self.c3(torch.tanh(self.c2(torch.tanh(self.c1(s))))).squeeze(-1)
        return off, pri, v

    # ------------------------------------------------------------------
    @torch.no_grad()
    def act(self, s, deterministic=False):
        off, pri, v = self.forward(s)
        if deterministic:
            a_off, a_pri = off.argmax(-1), pri.argmax(-1)
        else:
            a_off = Categorical(logits=off).sample()
            a_pri = Categorical(logits=pri).sample()
        lp = (Categorical(logits=off).log_prob(a_off).sum(-1)
              + Categorical(logits=pri).log_prob(a_pri).sum(-1))
        return a_off, a_pri, lp, v

    def evaluate(self, s, a_off, a_pri):
        off, pri, v = self.forward(s)
        d_off, d_pri = Categorical(logits=off), Categorical(logits=pri)
        lp = d_off.log_prob(a_off).sum(-1) + d_pri.log_prob(a_pri).sum(-1)
        ent = d_off.entropy().sum(-1) + d_pri.entropy().sum(-1)
        return lp, v, ent


# ----------------------------------------------------------------------
def test_isolation(state_dim=19, groups=3, device="cpu"):
    """Assert that a loss touching only group 0 leaves groups 1..G-1 with
    exactly zero gradient. If this ever fails, the grouped trick is silently
    mixing runs together and every figure is invalid."""
    net = GroupedActorCritic(groups, state_dim).to(device)
    s = torch.randn(groups, 8, state_dim, device=device)
    off, pri, v = net(s)
    (off[0].sum() + pri[0].sum() + v[0].sum()).backward()
    ok = True
    for name, p in net.named_parameters():
        if p.grad is None:
            continue
        other = p.grad[1:]
        if other.abs().max().item() > 0:
            ok = False
            print(f"  LEAK in {name}: {other.abs().max().item():.3e}")
    assert ok, "grouped policies are NOT independent"
    return True
