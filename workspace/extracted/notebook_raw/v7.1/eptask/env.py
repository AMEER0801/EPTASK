"""
env.py -- Vehicular Edge Computing environment, faithful to Sections III-IV.

V7.1: three additions, each behind a Config switch. With RESERVE_TOP_LEVEL,
LOCAL_COST_AT_ARRIVAL and DISASTER_MODE all off this file reproduces v6.1
bit-for-bit (asserted in the notebook pre-flight against golden v6.1 values):
  * RESERVE_TOP_LEVEL     -- the floor level is exclusive to protected work
  * LOCAL_COST_AT_ARRIVAL -- Local-only counterfactual from the arrival state
  * DISASTER_MODE         -- request roles (N1 emergency, N2 sensing/CWP),
                            contiguous-RSU disaster events, value-weighted
                            deadline reward, 33-dim state (STATE_MODE 33)

Key fidelity points (each flagged with the equation it implements):

  Eq. (1)-(2)   2-D distances; RSUs sit RSU_OFFSET_M off the carriageway so
                d_(i,r) is never 0.
  Eq. (3)-(4)   V2V SNR and rate, full bandwidth (paper states full BW for V2V).
  Eq. (5)-(6)   V2E interference from N_r co-connected vehicles AND the
                bandwidth share eta_i = 1/N_r that v3 omitted.
  Eq. (7)-(8)   E2C interference-limited rate (no longer a flat 1 Gb/s stub).
  Eq. (9)-(10)  Local time and energy; f enters Eq. (10) in GHz (see config U3).
  Eq. (11)-(13) SEPARATE transmission and processing queues. Transmission
                queues are SENDER-side (a vehicle has one radio, so its own
                tasks serialise; different vehicles transmit concurrently,
                which is exactly what Eq. (5)'s interference term models).
                Indexing them receiver-side, as Eq. (12) literally reads,
                double-counts contention -- documented deviation.
  Eq. (14)      Energy scoped to vehicles: edge computation energy excluded,
                V2V receiver computation energy included.
  Eq. (18)      T = MAX over entities, not the sum. This is the single most
                consequential correction versus the v3 notebook.
  Eq. (19)-(20) Dynamic transmit power p = d * P_max / d_max (floored).
  Eq. (21)-(22) Vehicle Selection Strategy, range-filtered, SeV-only.
  Eq. (23)/(26) 19-dim state (Fig. 5) or 29-dim (Eq. 26); null-task padding.
  Eq. (25)      Reward, sign-corrected (see report).

PRIORITY MODEL
--------------
Each compute entity keeps W[0..9]: queued execution seconds per priority level
(9 = highest). A task arriving at time t with priority p waits for all queued
work of priority >= p:

    wait   = sum_{q >= p} W[q]
    finish = max(data_arrival, t + wait) + duration
    W[p]  += duration

Draining is exact and fully vectorised: over dt seconds the server consumes
work strictly in priority order. This is what makes Fig. 11 (priority vs
FIFO) measurable at all -- with v3's scalar finish-timestamp queues a
high-priority arrival could never overtake queued low-priority work.
"""
import numpy as np

from disaster import (ROLE_NORMAL, ROLE_EMERGENCY, ROLE_SENSING, TIER_NONE,
                      TIER_IMMEDIATE, DisasterProcess, assign_emergency,
                      sample_detection, sensing_weight)


# ----------------------------------------------------------------------
def drain_priority(W, dt):
    """Consume dt seconds of work from each row of W, highest priority first.

    W : (N, P) float array, column index = priority (P-1 is highest)
    Exact, vectorised, O(N*P), fully in place. One call drains every entity
    in the world at once -- vehicles, edge servers and cloud share a single
    backing array so this is a single numpy pass per tick.
    """
    rev = W[:, ::-1]
    cum = np.cumsum(rev, axis=1)
    ahead = cum - rev                      # work of strictly higher priority
    avail = dt - ahead                     # budget left when we reach level p
    np.maximum(avail, 0.0, out=avail)
    np.minimum(avail, rev, out=avail)      # can't consume more than is queued
    rev -= avail


def drain_fifo(w, dt):
    """Scalar backlog drain (transmission queues, Eq. 12)."""
    np.maximum(w - dt, 0.0, out=w)


# ----------------------------------------------------------------------
class VECEnv:
    """One VEC world. Vectorised internally; see VecVEC for parallel worlds."""

    N_PRIO = 10

    def __init__(self, cfg, num_vehicles, seed=0):
        self.cfg = cfg.derive()
        self.V = int(num_vehicles)
        self.S = cfg.NUM_EDGE_SERVERS
        self.K = cfg.MAX_TASKS
        self.rng = np.random.default_rng(seed)
        # V7.1: disaster-mode draws use this SEPARATE stream so self.rng -- the
        # base request stream -- is identical with disaster mode on or off.
        self.drng = np.random.default_rng([int(seed) & 0xFFFFFFFF, 0xD15A57])
        self._spd_buf, self._spd_i = np.empty(0), 0
        self._u_buf, self._u_i = np.empty(0), 0
        self._desc = np.arange(cfg.MAX_TASKS - 1, -1, -1, dtype=np.int64)
        self._lvl_cache = {}
        self.state_dim = cfg.STATE_MODE
        self.reset()

    # ------------------------------------------------------------------
    def reset(self):
        c, V = self.cfg, self.V
        L = c.HIGHWAY_LENGTH_M

        # --- vehicles: 2-way highway, lanes, Poisson speeds (Section III-B)
        self.veh_x = self.rng.uniform(0, L, V)
        self.veh_dir = np.where(self.rng.random(V) < 0.5, 1.0, -1.0)
        lane = self.rng.integers(0, c.LANES_PER_DIRECTION, V)
        self.veh_y = self.veh_dir * (lane + 0.5) * c.LANE_WIDTH_M
        self.veh_v = self._sample_speeds(V)

        # --- Task Vehicles vs Service Vehicles (Section III-A)
        n_sev = max(1, int(round(c.SERVICE_VEHICLE_FRACTION * V)))
        self.is_sev = np.zeros(V, dtype=bool)
        self.is_sev[self.rng.choice(V, n_sev, replace=False)] = True
        self.tav_idx = np.flatnonzero(~self.is_sev)
        self.sev_idx = np.flatnonzero(self.is_sev)

        # --- edge servers: roadside, evenly spaced (Fig. 1 / Fig. 7)
        self.edge_x = (np.arange(self.S) + 0.5) * c.EDGE_SPACING_M
        self.edge_y = np.full(self.S, c.RSU_OFFSET_M)

        # --- dual queues: transmission (FIFO, sender-side) + execution
        # (priority). All execution queues live in ONE array so a tick drains
        # the whole world in a single numpy pass; the named attributes are
        # views into it, so writes through either alias stay consistent.
        self.W = np.zeros((V + self.S + 1, self.N_PRIO))
        self.veh_W = self.W[:V]                    # Eq. (13), vehicles
        self.edge_W = self.W[V:V + self.S]         # Eq. (13), edge servers
        self.cloud_W = self.W[V + self.S:]         # Eq. (17), cloud
        # v5: the transmission queue is the DOMINANT term of the critical
        # path (measured: 64% at V=50), yet Eq. (12) is FIFO, so priority --
        # which Eq. (13) applies to the execution queue only -- can reach at
        # most 2.3% of the path. PRIORITY_TX makes Eq. (12) priority-ordered
        # too, which is the one change that gives the mechanism leverage.
        self.TX = np.zeros((V + self.S, self.N_PRIO))
        self.veh_up = self.TX[:V]                  # Eq. (12) uplink radio queue
        self.e2c = self.TX[V:]                     # Eq. (16) E2C link queue

        self.veh_done = np.zeros(V)
        self.edge_done = np.zeros(self.S)
        self.cloud_done = 0.0

        # v5 true-completion bookkeeping. _recs[e] holds [level, est_finish]
        # records for every task still outstanding on entity e; _pending holds
        # requests whose true T is not yet settled.
        self._recs = [[] for _ in range(V + self.S + 1)]
        self._pending = []              # (arrival_time, [record, ...])
        self.true_T = []                # settled true completion times
        self.true_pairs = []            # (true_T, reported_T, local_T, tag)
        self.req_tag = 0.0              # caller-set label, carried to true_pairs

        # C3 (v6 proposal): edge-server outage state. Every server starts
        # alive; fail_server() takes one offline for a scripted duration.
        # Training never touches this -- Table III's environment stays
        # static -- it exists only for the post-hoc resilience diagnostic.
        self.server_alive = np.ones(self.S, dtype=bool)
        self._fail_until = np.zeros(self.S)

        # V7.1 (N1/N2): disaster process + emergency vehicles (None / all-False
        # when DISASTER_MODE is off, leaving every v6.1 code path untouched)
        if c.DISASTER_MODE:
            self.disaster = DisasterProcess(c, self.S, self.drng)
            self.is_emergency = assign_emergency(c, self.drng, self.tav_idx, V)
        else:
            self.disaster = None
            self.is_emergency = np.zeros(V, dtype=bool)
        self.req_role, self.req_det = ROLE_NORMAL, None
        self.true_meta = []             # parallel to true_pairs: per-request metadata
        self._last_local = (0.0, 0.0)   # Local-only (T, E) snapshot at arrival
        self._last_targets = np.zeros(4, dtype=np.int64)
        self._last_infeasible = 0

        self._refresh_geometry()
        self.t = 0.0
        self.step_i = 0
        self.cursor_ptr = 0
        self.max_T, self.max_E = 1e-6, 1e-9
        self._new_request()
        return self.observe()

    # ------------------------------------------------------------------
    def _track(self, eidx, level, fin, dur, bag):
        """Insert a task record on entity `eidx` and charge its externality.

        Inserting `dur` seconds of work at `level` delays every outstanding
        record on the same entity that sits at a STRICTLY LOWER level by
        exactly `dur` -- that is the cost of preemption that the arrival-time
        estimate in _execute never pays. Recording it here is what makes the
        true/reported gap measurable.
        """
        now, recs = self.t, self._recs[eidx]
        if recs:
            keep = []
            for r in recs:
                if r[1] <= now:          # already finished; cannot be delayed
                    continue
                if r[0] < level:
                    r[1] += dur
                keep.append(r)
            recs = keep
            self._recs[eidx] = recs
        rec = [level, fin]
        recs.append(rec)
        bag.append(rec)

    _BLOCK = 512

    def _levels(self, n, top=None):
        """rank index (0 = best) -> global queue level in 0..top.

        top defaults to N_PRIO-1 (= v6.1); RESERVE_TOP_LEVEL passes floor-1 for
        unprotected requests. Cached per (n, top) -- called on every request.
        """
        P = self.N_PRIO
        top = P - 1 if top is None else int(top)
        hit = self._lvl_cache.get((n, top))
        if hit is None:
            if self.cfg.PRIORITY_MAP == "rank_tail":       # v4 behaviour
                hit = np.minimum(self._desc[P - n:], top).astype(np.int64)
            elif n == 1:
                hit = np.array([top // 2], dtype=np.int64)  # neutral
            else:
                hit = np.round(np.linspace(top, 0, n)).astype(np.int64)
            self._lvl_cache[(n, top)] = hit
        return hit

    # ------------------------------------------------------------------
    # V7.1: who a floor protects, and the level ceiling for everyone else
    # ------------------------------------------------------------------
    def _floors_active(self):
        c = self.cfg
        return bool(c.USE_SAFETY_FLOOR or (self.disaster is not None and
                    (c.USE_EMERGENCY_FLOOR or c.USE_CWP_FLOOR)))

    def _protected(self):
        """Is the CURRENT request floor-protected? One mechanism, three
        selection rules: C1 criticality class, N1 vehicle role, N2 casualty tier."""
        c = self.cfg
        if c.USE_SAFETY_FLOOR and getattr(self, "req_class", -1) == 0:
            return True
        if self.disaster is not None:
            if c.USE_EMERGENCY_FLOOR and self.req_role == ROLE_EMERGENCY:
                return True
            if (c.USE_CWP_FLOOR and self.req_role == ROLE_SENSING
                    and self.req_det is not None
                    and self.req_det["tier"] == TIER_IMMEDIATE):
                return True
        return False

    def _unprotected_top(self):
        if self.cfg.RESERVE_TOP_LEVEL and self._floors_active():
            return min(self.N_PRIO - 1, self.cfg.SAFETY_FLOOR_LEVEL - 1)
        return self.N_PRIO - 1

    def _deadline_key(self):
        if self.req_role == ROLE_EMERGENCY:
            return "EMERGENCY"
        if self.req_role == ROLE_SENSING:
            return "SENSING"
        return self.cfg.ASIL_CLASSES[getattr(self, "req_class", 2)]

    def request_meta(self):
        """Metadata of the CURRENT request (the one about to be executed)."""
        d = self.req_det or {}
        return dict(t=float(self.t), role=int(self.req_role),
                    cls=int(getattr(self, "req_class", 2)), prot=bool(self._protected()),
                    n=int(self.n_tasks), people=int(d.get("people", 0)),
                    est=int(d.get("people_est", 0)), cwp=float(d.get("cwp", 0.0)),
                    tier=int(d.get("tier", TIER_NONE)), mod=int(d.get("modality", -1)),
                    age=float(d.get("age", 0.0)), key=self._deadline_key(),
                    veh=int(self.cursor), edge_ok=bool(self.in_range[self.cursor]))

    def _req_weight(self, m):
        """Weight of a deadline miss in the disaster-aware reward."""
        c = self.cfg
        if m["key"] in ("ASIL-D", "EMERGENCY"):
            return c.W_LIFE
        if m["role"] == ROLE_SENSING:
            return sensing_weight(c, m["people"])
        return 0.0

    def _sample_speeds(self, n):
        """Section III-B: speed varies continuously and is Poisson distributed.
        Drawn in blocks -- one rng call per 512 ticks instead of per tick.
        Statistically identical, ~20% faster overall."""
        if self._spd_i + n > len(self._spd_buf):
            self._spd_buf = np.maximum(
                1.0, self.rng.poisson(self.cfg.MEAN_SPEED_MPS,
                                      max(self._BLOCK, n * 8)).astype(float))
            self._spd_i = 0
        out = self._spd_buf[self._spd_i:self._spd_i + n]
        self._spd_i += n
        return out

    def _u(self, n):
        """Block-cached uniforms for task generation."""
        if self._u_i + n > len(self._u_buf):
            self._u_buf = self.rng.random(self._BLOCK * 4)
            self._u_i = 0
        out = self._u_buf[self._u_i:self._u_i + n]
        self._u_i += n
        return out

    # ------------------------------------------------------------------
    def _new_request(self):
        """Next Task Vehicle in round robin issues a service request."""
        c = self.cfg
        self.cursor = int(self.tav_idx[self.cursor_ptr % len(self.tav_idx)])
        self.cursor_ptr += 1
        n = int(self.rng.binomial(c.MAX_TASKS, c.TASK_COUNT_BINOM_P))  # Fig. 8
        n = int(np.clip(n, c.MIN_TASKS, c.MAX_TASKS))
        self.n_tasks = n
        self.cycles = np.zeros(self.K)
        self.bits = np.zeros(self.K)
        if n:
            u = self._u(2 * n)
            self.cycles[:n] = c.MIN_CPU_CYCLES + u[:n] * (c.MAX_CPU_CYCLES - c.MIN_CPU_CYCLES)
            self.bits[:n] = c.MIN_DATA_BITS + u[n:] * (c.MAX_DATA_BITS - c.MIN_DATA_BITS)
        # Eq. (26): slots n..K-1 stay at 0 -- the null-task padding scheme

        # C1 (v6 proposal): tag this request with an ASIL-inspired criticality
        # class. Index 0 = ASIL_CLASSES[0] = "ASIL-D" (highest). Sampled
        # independently of task count/size -- criticality is a property of
        # WHAT the request is for (braking vs. streaming), not how big it is.
        u_cls = float(self._u(1)[0])
        self.req_class = int(np.searchsorted(np.cumsum(c.ASIL_PROBS), u_cls))

        # V7.1 (N1/N2): request role, drawn ONLY from self.drng and after every
        # base-stream draw above, so the base stream is untouched.
        self.req_role, self.req_det = ROLE_NORMAL, None
        if self.disaster is not None:
            if self.is_emergency[self.cursor]:
                self.req_role = ROLE_EMERGENCY
            elif self.disaster.active(self.t) and self.drng.random() < c.SENSING_FRACTION:
                self.req_role = ROLE_SENSING
                self.req_det = sample_detection(
                    c, self.drng, age_max_s=len(self.tav_idx) * c.SIM_TICK_S)

    # ------------------------------------------------------------------
    # geometry / radio
    # ------------------------------------------------------------------
    def _refresh_geometry(self):
        """One O(V*S) pass per tick instead of one per query -- this is the
        env's hot path. Caches nearest server, its distance, and Eq. (5)'s
        N_r for every server."""
        dx = self.veh_x[:, None] - self.edge_x[None, :]
        dy = self.veh_y[:, None] - self.edge_y[None, :]
        d = np.sqrt(dx * dx + dy * dy)
        # C3 (v6 proposal): a dead server is invisible to routing -- treated
        # exactly like "out of range", which the existing C2/C3 constraint
        # in _execute already falls back from (offload -> local). No new
        # fallback path was needed; failure re-uses the infeasibility path
        # the base replication already has.
        if not self.server_alive.all():
            d = np.where(self.server_alive[None, :], d, np.inf)
        self.near_s = np.argmin(d, axis=1)
        self.near_d = d[np.arange(self.V), self.near_s]
        in_range = self.near_d <= self.cfg.D_MAX_M
        self.n_conn = np.maximum(
            1, np.bincount(self.near_s[in_range], minlength=self.S))
        self.in_range = in_range

    def fail_server(self, idx, duration):
        """C3 (v6 proposal): take edge server `idx` offline for `duration`
        sim-seconds. Scripted by a diagnostic at evaluation time -- never
        called during training, so this is a pure generalisation test."""
        self.server_alive[idx] = False
        self._fail_until[idx] = self.t + duration
        self._refresh_geometry()

    def trigger_disaster(self, s0, k, duration):
        """V7.1: scripted event -- RSUs s0..s0+k-1 offline for `duration` s and
        the sensing window open for the same period (needs DISASTER_MODE; for a
        bare outage use fail_server, as C3 does)."""
        if self.disaster is None:
            raise RuntimeError("trigger_disaster needs Config.DISASTER_MODE = True")
        return self.disaster.trigger(self, s0, k, duration)

    def _recover_servers(self):
        due = (~self.server_alive) & (self._fail_until > 0) & (self.t >= self._fail_until)
        if due.any():
            self.server_alive[due] = True
            self._fail_until[due] = 0.0

    def _nearest_edge(self, i):
        j, dj = int(self.near_s[i]), float(self.near_d[i])
        return (j, dj) if self.in_range[i] else (None, dj)

    def _n_connected(self, s):
        return int(self.n_conn[s])

    def _alloc_power(self, d):
        """Eq. (19)-(20): p = d * P_max / d_max, floored. Fig. 12 ablation
        switches this off in favour of always transmitting at P_max."""
        c = self.cfg
        if not c.USE_DYNAMIC_POWER:
            return c.P_MAX_W
        p = d * (c.P_MAX_W / c.D_MAX_M)
        return float(np.clip(p, c.P_MIN_FRACTION * c.P_MAX_W, c.P_MAX_W))

    def _channel(self, d):
        """Linear channel gain: antenna gain minus Eq. (20) path loss."""
        d_km = max(d, 1.0) / 1000.0
        L_db = 32.4 + 26 * np.log10(d_km) + 20 * np.log10(self.cfg.FREQ_MHZ)
        return self.cfg.ANTENNA_GAIN_LIN * 10 ** (-L_db / 10.0)

    def _rate_v2v(self, d):
        """Eq. (3)-(4). Full bandwidth, as the paper states for V2V."""
        c = self.cfg
        p = self._alloc_power(d)
        snr = p * self._channel(d) / c.NOISE_VEH_W
        return p, c.VEHICLE_BANDWIDTH_HZ * np.log2(1.0 + snr)

    def _rate_v2e(self, d, N_r):
        """Eq. (5)-(6), including the bandwidth share eta_i = 1/N_r."""
        c = self.cfg
        p = self._alloc_power(d)
        g = self._channel(d)
        I = (N_r - 1) * p * g                      # Eq. (5)
        sinr = p * g / (I + c.NOISE_EDGE_W)        # Eq. (6)
        eta = 1.0 / N_r
        return p, eta * c.EDGE_BANDWIDTH_HZ * np.log2(1.0 + sinr)

    def _rate_e2c(self):
        """Eq. (7)-(8). Interference from the other S-1 edge->cloud links."""
        c = self.cfg
        I = (self.S - 1) * c.E2C_TX_POWER_W * c.E2C_CHANNEL_GAIN
        sinr = c.E2C_TX_POWER_W * c.E2C_CHANNEL_GAIN / (I + c.E2C_NOISE_W)
        return c.E2C_BANDWIDTH_HZ * np.log2(1.0 + sinr)

    # ------------------------------------------------------------------
    # Eq. (21)-(22) Vehicle Selection Strategy
    # ------------------------------------------------------------------
    def _select_sev(self, i):
        """Range-filtered, SeV-only candidates; picks the MINIMUM Eq. (22)
        score. The paper says 'highest', but Eq. (22) scores normalised
        distance and workload -- both of which must be minimised for the
        rule to do anything useful. Documented deviation."""
        c = self.cfg
        cand = self.sev_idx
        if cand.size == 0:
            return None, np.inf
        d = np.hypot(self.veh_x[cand] - self.veh_x[i], self.veh_y[cand] - self.veh_y[i])
        m = d <= c.D_MAX_M                                   # constraint C2
        if not m.any():
            return None, float(d.min())
        cand, d = cand[m], d[m]
        w = self.veh_W[cand].sum(axis=1)                     # real backlog
        dn = (d - d.min()) / max(float(np.ptp(d)), 1e-9)
        wn = (w - w.min()) / max(float(np.ptp(w)), 1e-9)
        score = 0.5 * dn + 0.5 * wn                          # Eq. (22)
        b = int(np.argmin(score))
        return int(cand[b]), float(d[b])

    # ------------------------------------------------------------------
    # Eq. (23) state
    # ------------------------------------------------------------------
    def observe(self):
        c, i = self.cfg, self.cursor
        s, de = self._nearest_edge(i)
        if s is None:
            s = int(self.near_s[i])
        L = c.HIGHWAY_LENGTH_M

        pos = [self.veh_x[i] / L, self.edge_x[s] / L, 1.0]              # P^e(t)
        comm = [np.tanh(self.veh_up[i].sum()),                                # M^v(t):
                self._n_connected(s) / max(self.V, 1),                  #  own uplink,
                np.tanh(self.e2c[s].sum())]                                   #  cell load, E2C
        comp = [np.tanh(self.veh_W[i].sum()), np.tanh(self.edge_W[s].sum()),
                np.tanh(self.cloud_W[0].sum())]                         # C^e(t)

        st = pos + comm + comp + list(self.bits / c.MAX_DATA_BITS)
        if c.STATE_MODE in (29, 33):
            st += list(self.cycles / c.MAX_CPU_CYCLES)                  # Eq. (26)
        if c.STATE_MODE == 33:
            # V7.1: what a disaster-aware policy needs and Fig. 5's state lacks:
            # does the edge path exist at all (a dead RSU otherwise looks like
            # any far RSU), is V2V possible, and how much does this request matter.
            sev, _ = self._select_sev(i)
            d = self.req_det
            st += [float(self.in_range[i]), float(sev is not None),
                   float(self._protected()), (d["cwp"] / 9.0) if d is not None else 0.0]
        return np.asarray(st, dtype=np.float32)

    # ------------------------------------------------------------------
    # Eq. (9)-(18) execution
    # ------------------------------------------------------------------
    def _execute(self, offload, priority, queues, commit):
        """Run the current request against `queues`. Returns (T, E, penalty).

        queues = (veh_W, veh_up, edge_W, e2c, cloud_W)
        When commit is False the caller passes copies, so counterfactual
        baselines cannot perturb the live trajectory.
        """
        c, i, now = self.cfg, self.cursor, self.t
        vW, vUP, eW, eC, cW = queues
        if self.n_tasks == 0:
            if commit:
                self._last_local = (0.0, 0.0)
                self._last_targets = np.zeros(4, dtype=np.int64)
                self._last_infeasible = 0
            return 0.0, 0.0, 0.0
        loc0 = self._local_cost()        # V7.1 FIX 2: BEFORE anything is enqueued
        tgt = np.zeros(4, dtype=np.int64)

        s, d_edge = self._nearest_edge(i)
        sev, d_sev = self._select_sev(i)
        N_r = self._n_connected(s) if s is not None else 1
        finishes, energy, infeasible = [], 0.0, 0
        track = commit and c.TRACK_TRUE_T          # v5 diagnostic only
        bag = []

        # ---- priority is a RANKING within the request, not a free label.
        # Section III-D orders a queue as l1 >= l2 >= ... and Fig. 6 shows one
        # request's four tasks carrying four DISTINCT priorities (4..1).
        # Treating the head's output as an absolute level instead has a
        # degenerate equilibrium: every vehicle maxes every priority, all work
        # lands on one level, and the queue silently reverts to FIFO -- which
        # is exactly why the Fig. 11 ablation reads ~0% in that formulation.
        # Ranking the head's scores removes the free lunch: promoting one task
        # necessarily demotes another, so the agent has to decide WHICH task
        # is the makespan bottleneck (Eq. 18 is a max, so the right answer is
        # the longest task -- an LPT rule it must learn from Eq. 26's cycles).
        #
        # v5 -- but the rank must then be mapped onto a GLOBAL level in 0..9,
        # and v4's map (lvl = desc[10-n:]) made that level depend on how many
        # tasks the request happened to contain: a 1-task request was pinned to
        # level 0 forever, a 10-task request's median task outranked every task
        # of every small request. "rank_spread" spreads the n ranks evenly over
        # the whole 0..9 range instead, so the top-ranked task of any request
        # reaches level 9 and precedence is decided by the head, not by size.
        n = self.n_tasks
        top = self._unprotected_top()          # V7.1 FIX 1: 9 in v6.1, 8 when reserved
        if c.USE_PRIORITY:
            sc = np.asarray(priority[:n], dtype=np.float64)
            rank = np.argsort(-sc, kind="stable")
            if c.PRIORITY_MAP == "absolute":
                # the head's score IS the global level. Can express
                # cross-request urgency, but admits the degenerate
                # all-max equilibrium unless the reward charges for it.
                lvl = np.clip(np.rint(sc), 0, top).astype(np.int64)
            else:
                lvl = np.empty(n, dtype=np.int64)
                lvl[rank] = self._levels(n, top)
        else:                                            # Fig. 11 control arm
            rank = np.arange(n)
            lvl = np.zeros(n, dtype=np.int64)

        # C1 (v6) / N1 / N2 (V7.1): deterministic floor, NOT learned. Overrides
        # the priority head whenever the request is protected -- ASIL-D (C1),
        # an emergency vehicle's request (N1) or an IMMEDIATE-tier detection
        # (N2) -- so it holds even for an untrained or adversarial policy.
        if n and self._protected():
            lvl[:] = c.SAFETY_FLOOR_LEVEL

        # `rank` is already the descending-priority execution order, so the
        # second argsort the naive version needs is redundant.
        for k in rank:
            C, S_bits, p = self.cycles[k], self.bits[k], int(lvl[k])
            a = int(offload[k])

            # constraints C2 / C3 of Eq. (18)
            if a in (0, 3) and s is None:
                a, infeasible = 2, infeasible + 1
            elif a == 1 and sev is None:
                a, infeasible = 2, infeasible + 1
            tgt[a] += 1                                      # V7.1: realised target

            if a == 2:                                       # local, Eq. (9)-(10)
                dur = C / c.VEHICLE_CPU_HZ
                wait = vW[i, p:].sum()
                fin = now + wait + dur
                vW[i, p] += dur
                if track: self._track(i, p, fin, dur, bag)
                energy += c.XI * (c.VEHICLE_CPU_HZ / 1e9) ** c.GAMMA_E * C

            elif a == 0:                                     # edge, Eq. (11)-(14)
                pw, R = self._rate_v2e(d_edge, N_r)
                tt = S_bits / max(R, 1.0)
                arrive = now + self._txq(vUP, i, p) + tt     # Eq. (12) uplink queue
                self._txput(vUP, i, p, tt)
                dur = C / c.EDGE_CPU_HZ                      # Eq. (13) exec queue
                wait = eW[s, p:].sum()
                fin = max(arrive, now + wait) + dur
                eW[s, p] += dur
                if track: self._track(self.V + s, p, fin, dur, bag)
                energy += pw * tt                            # Eq. (14): TX only

            elif a == 1:                                     # V2V, Eq. (3)-(4)
                pw, R = self._rate_v2v(d_sev)
                tt = S_bits / max(R, 1.0)
                arrive = now + self._txq(vUP, i, p) + tt     # sender's own radio
                self._txput(vUP, i, p, tt)
                dur = C / c.VEHICLE_CPU_HZ
                wait = vW[sev, p:].sum()
                fin = max(arrive, now + wait) + dur
                vW[sev, p] += dur
                if track: self._track(sev, p, fin, dur, bag)
                # Eq. (14) alpha=1: transmit energy + receiver's compute energy
                energy += pw * tt + c.XI * (c.VEHICLE_CPU_HZ / 1e9) ** c.GAMMA_E * C

            else:                                            # cloud, Eq. (15)-(17)
                pw, R = self._rate_v2e(d_edge, N_r)
                t_v2e = S_bits / max(R, 1.0)
                t_e2c = S_bits / max(self._rate_e2c(), 1.0)
                # V2E leg queues on the vehicle's radio, E2C leg on the
                # edge->cloud backhaul (Eq. 16)
                arrive = (now + self._txq(vUP, i, p) + t_v2e
                          + self._txq(eC, s, p) + t_e2c)
                self._txput(vUP, i, p, t_v2e)
                self._txput(eC, s, p, t_e2c)
                dur = C / c.CLOUD_CPU_HZ
                wait = cW[0, p:].sum()
                fin = max(arrive, now + wait) + dur
                cW[0, p] += dur
                if track: self._track(self.V + self.S, p, fin, dur, bag)
                energy += pw * t_v2e                         # vehicle-side only

            finishes.append(fin)

        if commit:
            self.veh_done[i] += self.n_tasks
            self._last_local, self._last_targets = loc0, tgt
            self._last_infeasible = infeasible
        if track and bag:
            # carry the arrival-time estimate and the Local-only cost so the
            # diagnostic can score deadlines (C4) post hoc without a re-run
            loc_T = loc0[0] if c.LOCAL_COST_AT_ARRIVAL else self._local_cost()[0]
            self._pending.append((now, bag, float(max(finishes) - now),
                                  loc_T, self.req_tag, self.request_meta()))

        # Eq. (18): the request finishes when the LAST entity finishes.
        T = max(finishes) - now
        pen = c.INFEASIBLE_PENALTY * infeasible / max(self.n_tasks, 1)
        return float(T), float(energy), float(pen)

    def _live_queues(self):
        return (self.veh_W, self.veh_up, self.edge_W, self.e2c, self.cloud_W)

    def _snapshot(self):
        """Deep copy of the whole queue state, re-sliced so counterfactual
        evaluation can never touch the live trajectory."""
        W, TX, V, S = self.W.copy(), self.TX.copy(), self.V, self.S
        return (W[:V], TX[:V], W[V:V + S], TX[V:], W[V + S:])

    # ------------------------------------------------------------------
    def peek(self, offload, priority):
        """Counterfactual: evaluate a policy on THIS request and THIS queue
        state without mutating anything. Fixes the v3 off-by-one where
        baselines were scored on the next vehicle's request."""
        return self._execute(np.asarray(offload), np.asarray(priority),
                             self._snapshot(), commit=False)

    def step(self, offload, priority):
        c = self.cfg
        meta = self.request_meta()                     # V7.1: the request executed now
        T, E, pen = self._execute(np.asarray(offload), np.asarray(priority),
                                  self._live_queues(), commit=True)
        # V7.1 FIX 2: arrival-state Local-only cost; False = v6.1's post-commit value
        Tl, El = self._last_local if c.LOCAL_COST_AT_ARRIVAL else self._local_cost()

        # ---- reward
        self.max_T = max(self.max_T, T)
        self.max_E = max(self.max_E, E)
        if c.REWARD_MODE == "running_max":
            # Eq. (25) verbatim, sign-corrected. Kept for the ablation only:
            # max_T / max_E are hidden, non-stationary and monotone, so this
            # reward drifts upward under a FROZEN policy.
            reward = 1.0 - (c.ALPHA_R * T / self.max_T
                            + c.BETA_R * E / self.max_E) - pen
        else:
            # v5 default: normalise against what THIS request would have cost
            # under Local-only. r = alpha*TS + beta*ES, i.e. Eq. (32) used
            # directly as the reward. Stationary and per-request.
            if Tl <= 0.0 or El <= 0.0:
                reward = 0.0
            else:
                reward = (c.ALPHA_R * (1.0 - T / Tl)
                          + c.BETA_R * (1.0 - E / El)) - pen
                if self.disaster is not None and c.DISASTER_REWARD:
                    # V7.1 DR-MEPPO: value-weighted deadline-miss penalty
                    if T > c.DEADLINE_MULT[meta["key"]] * Tl:
                        reward -= c.MISS_PENALTY * self._req_weight(meta)
                reward = float(np.clip(reward, -c.REWARD_CLIP, c.REWARD_CLIP))

        # ---- advance the world one tick
        dt = c.SIM_TICK_S
        self.t += dt
        drain_priority(self.W, dt)     # every entity, one pass
        drain_priority(self.TX, dt) if c.PRIORITY_TX else drain_fifo(self.TX, dt)

        self.veh_v = self._sample_speeds(self.V)        # speed varies each tick
        self.veh_x = np.mod(self.veh_x + self.veh_dir * self.veh_v * dt,
                            c.HIGHWAY_LENGTH_M)
        self._recover_servers()                          # C3: end scripted outages
        if self.disaster is not None:
            self.disaster.tick(self)                     # V7.1: random events (training)
        self._refresh_geometry()

        # ---- settle any request that can no longer be preempted
        if c.TRACK_TRUE_T and self._pending:
            still = []
            for arrival, bag, rep, loc, tag, m in self._pending:
                fin = max(r[1] for r in bag)
                if fin <= self.t:
                    self.true_T.append(fin - arrival)
                    self.true_pairs.append((fin - arrival, rep, loc, tag))
                    self.true_meta.append(m)
                else:
                    still.append((arrival, bag, rep, loc, tag, m))
            self._pending = still

        self.step_i += 1
        alive = int(self.server_alive.sum())
        dis_on = bool(self.disaster is not None and self.disaster.active(self.t))
        self._new_request()
        # "n" is the NEXT request's task count (kept from v6.1 for compatibility);
        # "meta" describes the request that was just executed.
        return self.observe(), float(reward), {
            "T": T, "E": E, "pen": pen, "n": self.n_tasks, "meta": meta,
            "Tl": float(Tl), "tg": self._last_targets, "inf": self._last_infeasible,
            "alive": alive, "dis": dis_on}

    # ------------------------------------------------------------------
    def _txq(self, q, row, p):
        """Queueing delay on transmission row `row` for a task at level p."""
        return q[row, p:].sum() if self.cfg.PRIORITY_TX else q[row].sum()

    def _txput(self, q, row, p, dur):
        q[row, p if self.cfg.PRIORITY_TX else 0] += dur

    def _local_cost(self):
        """(T, E) if the CURRENT request ran entirely on the Task Vehicle.

        The Local-only arm of Section V-B, evaluated in closed form -- no
        rollout needed, because local execution touches no radio and no other
        entity. This is the denominator of Eq. (32).
        """
        c, i, n = self.cfg, self.cursor, self.n_tasks
        if n == 0:
            return 0.0, 0.0
        C = self.cycles[:n].sum()
        T = float(self.veh_W[i].sum() + C / c.VEHICLE_CPU_HZ)
        E = float(c.XI * (c.VEHICLE_CPU_HZ / 1e9) ** c.GAMMA_E * C)
        return T, E


# ----------------------------------------------------------------------
class VecVEC:
    """N independent worlds stepped together so the policy forward pass is
    batched. This is Algorithm 1's `for actor = 1 to N` loop, and the PPO2
    batching the paper endorses in Section I-A."""

    def __init__(self, cfg, num_vehicles, n_actors, seed=0):
        self.envs = [VECEnv(cfg, num_vehicles, seed=seed * 1000 + k)
                     for k in range(n_actors)]
        self.n = n_actors
        self.state_dim = self.envs[0].state_dim

    def reset(self):
        return np.stack([e.reset() for e in self.envs])

    def step(self, offload, priority):
        obs, rew, infos = [], [], []
        for k, e in enumerate(self.envs):
            o, r, inf = e.step(offload[k], priority[k])
            obs.append(o); rew.append(r); infos.append(inf)
        return np.stack(obs), np.asarray(rew, dtype=np.float32), infos

    def peek(self, offload, priority):
        return [e.peek(offload[k], priority[k]) for k, e in enumerate(self.envs)]
