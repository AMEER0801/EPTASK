"""
disaster.py -- V7 application layer inside the VEC cell (N1 + N2).

What this module adds to the replicated environment, and what it does NOT do.

ADDS
  * Request ROLES. A request is NORMAL (as in v6.1, carrying an ASIL-inspired
    class), EMERGENCY (issued by an emergency vehicle), or SENSING (carries a
    victim detection from an on-board sensor during a disaster event).
  * N2 casualty-weighted priority (CWP): a 0..9 score from the detection's
    modality, estimated head-count and (optionally) age, plus a START-inspired
    tier. Only the IMMEDIATE tier is floor-protected.
  * A disaster PROCESS: events that take a CONTIGUOUS block of RSUs offline for
    a while (a debris footprint is spatially correlated) and open the sensing
    window. Random during training, scripted during evaluation.

DOES NOT
  * detect people. The sensing process is a stochastic abstraction of the
    detection EVENT (modality, estimated count with noise); there is no
    computer vision, acoustics or thermal physics here. Say so in the report.
  * route vehicles. Road-level routing lives in corridor.py, at a different
    spatial scale (see ADR-001).

Why not the earlier earthquake draft (USGS MMI + HAZUS fragility)?
  Measured on this replication's geometry: the corridor is 558 m long, the
  draft's MMI field varied by < 0.1 MMI across it, so every RSU got the same
  ~0.91 failure probability -- all-or-nothing loss, never graceful
  degradation. MMI/HAZUS also model ground SHAKING; the Aug-2026 Nepal event
  was an ice-rock-avalanche-triggered outburst flood. A contiguous-block
  outage with explicit size and duration is both more honest and sweepable.

All randomness here uses the generator passed in (the env's `drng`), never the
env's base `rng`, so the base request stream is unchanged by disaster mode.
"""
import math
import numpy as np

ROLE_NORMAL, ROLE_EMERGENCY, ROLE_SENSING = 0, 1, 2
ROLE_NAMES = ("NORMAL", "EMERGENCY", "SENSING")

TIER_NONE, TIER_MINOR, TIER_DELAYED, TIER_IMMEDIATE = 0, 1, 2, 3
TIER_NAMES = ("-", "MINOR", "DELAYED", "IMMEDIATE")


# ======================================================================
# N2 -- casualty-weighted priority
# ======================================================================
def cwp_score(weight, people_est, age_s=0.0, tau_s=120.0, mode="none"):
    """CWP = clip(weight * log1p(people_est) * decay(age), 0, 9).

    log1p makes the score concave in head-count: 5 people score
    log1p(5)/log1p(1) = 2.58x one person, not 5x -- more people matter more,
    with diminishing increments. mode="decay" multiplies by exp(-age/tau)
    (the original formula); mode="none" drops the time term (V7 default).
    """
    if people_est <= 0:
        return 0.0
    s = float(weight) * math.log1p(float(people_est))
    if mode == "decay":
        s *= math.exp(-max(float(age_s), 0.0) / float(tau_s))
    return float(min(max(s, 0.0), 9.0))


def cwp_tier(score, thr_immediate, thr_delayed):
    if score >= thr_immediate:
        return TIER_IMMEDIATE
    if score >= thr_delayed:
        return TIER_DELAYED
    return TIER_MINOR


def sensing_weight(cfg, people_true):
    """Reward weight of a sensing request: grows with the TRUE head-count."""
    return float(min(cfg.W_SENSING_MAX,
                     cfg.W_SENSING_MAX * math.log1p(people_true) / math.log1p(5.0)))


def sample_detection(cfg, drng, age_max_s):
    """One victim detection: modality, true and estimated head-count, age.

    True count ~ Geometric(PEOPLE_GEOM_P) on {1, 2, ...} (mostly 1-2 people, a
    tail of larger groups). The sensor's estimate carries multiplicative
    log-normal noise whose spread depends on the modality. Age is uniform over
    the vehicle's round-robin wait -- a detection made between two of its
    request slots waits for the next one.
    """
    k = int(drng.choice(len(cfg.MODALITIES), p=cfg.MODALITY_PROBS))
    mod = cfg.MODALITIES[k]
    people = int(drng.geometric(cfg.PEOPLE_GEOM_P))
    sig = cfg.MODALITY_COUNT_SIGMA[mod]
    est = max(1, int(round(people * math.exp(drng.normal(0.0, sig)))))
    age = float(drng.uniform(0.0, max(age_max_s, 1e-9)))
    score = cwp_score(cfg.MODALITY_WEIGHT[mod], est, age, cfg.CWP_TAU_S,
                      cfg.CWP_AGE_MODE)
    tier = cwp_tier(score, cfg.CWP_IMMEDIATE, cfg.CWP_DELAYED)
    return dict(modality=k, people=people, people_est=est, age=age,
                cwp=score, tier=tier)


# ======================================================================
# N1 -- emergency vehicles
# ======================================================================
def assign_emergency(cfg, drng, tav_idx, V):
    """Boolean mask over all V vehicles: which Task Vehicles are emergency
    vehicles. At least one per world, so every world produces EMERGENCY
    traffic to measure (at V=10 that one vehicle is 1 of 8 Task Vehicles,
    i.e. 12.5% of requests -- report the realised share, not the nominal)."""
    mask = np.zeros(V, dtype=bool)
    if len(tav_idx) == 0:
        return mask
    n = max(1, int(round(cfg.EMERGENCY_FRACTION * len(tav_idx))))
    mask[drng.choice(tav_idx, size=min(n, len(tav_idx)), replace=False)] = True
    return mask


# ======================================================================
# disaster events in the VEC cell
# ======================================================================
class DisasterProcess:
    """Owns event timing; the ENV owns RSU state (server_alive, fail_server),
    so the C3 machinery is reused unchanged."""

    def __init__(self, cfg, n_servers, drng):
        self.cfg, self.S, self.drng = cfg, n_servers, drng
        self.active_until = -1.0
        self.block = ()             # RSU indices of the current/last event
        self.n_events = 0
        self.log = []               # (t_start, t_end, block) -- for provenance

    def active(self, t):
        return t < self.active_until

    def trigger(self, env, s0, k, duration):
        """Scripted event: RSUs s0..s0+k-1 offline for `duration` seconds."""
        s0 = int(np.clip(s0, 0, self.S - 1))
        k = int(np.clip(k, 1, self.S - s0))
        blk = tuple(range(s0, s0 + k))
        for j in blk:
            env.fail_server(j, duration)
        self.active_until = max(self.active_until, env.t + duration)
        self.block = blk
        self.n_events += 1
        self.log.append((float(env.t), float(env.t + duration), blk))
        return blk

    def tick(self, env):
        """Random event arrival (training-time domain randomisation)."""
        c = self.cfg
        if not c.RANDOM_DISASTERS or self.active(env.t):
            return
        if self.drng.random() < c.DISASTER_RATE_PER_S * c.SIM_TICK_S:
            lo, hi = c.DISASTER_RSU_BLOCK
            k = int(self.drng.integers(lo, hi + 1))
            s0 = int(self.drng.integers(0, self.S - k + 1))
            dlo, dhi = c.DISASTER_DURATION_S
            dur = float(self.drng.integers(dlo, dhi + 1))
            self.trigger(env, s0, k, dur)
