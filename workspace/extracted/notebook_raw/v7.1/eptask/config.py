"""
EPtask / MEPPO replication -- config.py  (v4 Table III audit; V7.1 switches at the end)

EVERY numeric value below is either (a) verbatim from Table III, or (b) explicitly
tagged ASSUMPTION with the reason. No silent parameter tuning.

--------------------------------------------------------------------------
TABLE III AS PRINTED (23 rows, transcribed from a 900 dpi render of p.1841)
--------------------------------------------------------------------------
  Number of vehicles ................. 10-50
  Number of edge servers ............. 8
  Number of tasks .................... 0-10
  Required CPU cycles of the tasks C.. 2-20 cpu cycles      <-- exponent stripped
  Computation power of edge servers .. 2 cpu cycles/s       <-- exponent stripped
  Computation power of vehicles ...... 1 cpu cycles/s       <-- exponent stripped
  data size S ........................ 2-20 Mb
  Bandwidth of edge server ........... 100 MHz
  Speed of vehicles .................. ~ 25 m/s
  Transmit power of vehicles ......... 1 dBm
  Execution power of vehicles ........ 3-4 dBm
  White Gaussian noise ............... -174 dBm/Hz
  Power consumption coefficient xi ... 10^-11
  Power consumption coefficient gamma. 2
  RSSI ............................... -65 dBm
  Transmit antenna gain TX ........... 20 dBi
  Receive antenna gain RX ............ -8 dBi
  Signal attenuation SA .............. 7 dB
  Working frequency f ................ 5 GHz
  Learning rate ...................... 0.0003
  Size of Mini-batch ................. 32
  Number of steps in each episode .... 2048
  Entropy loss coefficient ........... 0.01

NOT in Table III (hence ASSUMPTION): cloud CPU frequency, vehicle bandwidth,
discount factor, clip epsilon, GAE lambda, K epochs, highway length, number of
episodes (taken from Fig. 9's x-axis, which runs to ~1000).

--------------------------------------------------------------------------
THE THREE UNIT AMBIGUITIES, AND HOW THEY ARE RESOLVED
--------------------------------------------------------------------------
Table III has had its scientific-notation exponents stripped by typesetting
("2 cpu cycles/s" is not a CPU frequency). Three readings must be fixed. The
resolution below is the *unique* one that makes Table III internally consistent
AND reproduces the paper's own qualitative orderings (Fig. 10a/10b) with no
free parameters left over.

  (U1) PATH LOSS, Eq. (20):  L = 32.4 + 26*lg(d) + 20*lg(f)
       The constant 32.4 belongs to the standard FSPL calibration
       FSPL = 32.44 + 20*lg(d_km) + 20*lg(f_MHz).  The paper's text says
       "d in m", which is off by 60 dB and produces the notorious d_max = 4 cm.
       RESOLVED: d in km, f in MHz.  ->  d_max = 43.6 m at Table III's values.

  (U2) SPATIAL SCALE.  d_max = 43.6 m follows from Table III with zero
       deviation.  The highway length is NOT specified by the paper, so it is
       the free variable -- not the transmit power.  We therefore scale the
       road to the radio, giving 8 servers continuous coverage.
       (The alternative -- inflating P_max/TX to reach a preset 8 km road --
       breaks Eq. (14) energy accounting by ~30 dB and inverts Fig. 10(b).)

  (U3) ENERGY, Eq. (10):  E = xi * f^gamma * C, xi = 1e-11, gamma = 2.
       With f in Hz this yields ~1e16 J/task; with f in GHz and C in raw
       cycles it yields 2-10 mJ/task, which is the physically correct order
       for an embedded automotive SoC. RESOLVED: f in GHz, C in cycles.
       (This is why the popular "xi = 1e-27" substitution is unnecessary --
       1e-27 is the Hz-convention equivalent of Table III's 1e-11 GHz value:
       1e-11 / (1e9)^2 = 1e-29, same ballpark, but Table III's own number is
       used here.)
"""
import contextlib
import math


class Config:
    # ================= reproducibility / device =================
    SEED = 42

    # ================= scenario (Table III) =================
    VEHICLE_COUNTS = (10, 20, 30, 40, 50)   # Fig. 9-12 x-axis
    NUM_EDGE_SERVERS = 8                    # Table III
    MIN_TASKS = 0                           # Table III
    MAX_TASKS = 10                          # Table III  (= K, the padded width)

    # Table III "2-20 cpu cycles" -> 2-20 x 10^8 cycles  (see U3 note)
    MIN_CPU_CYCLES = 2e8
    MAX_CPU_CYCLES = 20e8

    # Table III "2-20 Mb" -> megaBITS (rates below are bit/s)
    MIN_DATA_BITS = 2e6
    MAX_DATA_BITS = 20e6

    # Fig. 8: "most requests comprise 2-6 tasks", some vehicles generate 0.
    # Binomial(10, 0.40) has mode 4, mass ~0.74 on 2..6 -- matches Fig. 8's shape.
    TASK_COUNT_BINOM_P = 0.40
    SERVICE_VEHICLE_FRACTION = 0.20   # ASSUMPTION: paper says "some" SeVs exist

    # ================= computation (Table III) =================
    VEHICLE_CPU_HZ = 1e9      # "1 cpu cycles/s" -> 1 GHz
    EDGE_CPU_HZ = 2e9         # "2 cpu cycles/s" -> 2 GHz
    CLOUD_CPU_HZ = 20e9       # ASSUMPTION (absent from Table III)

    # ================= energy, Eq. (10) =================
    XI = 1e-11                # Table III
    GAMMA_E = 2               # Table III
    # f enters Eq. (10) in GHz (see U3)

    # ================= radio (Table III) =================
    EDGE_BANDWIDTH_HZ = 100e6      # Table III
    VEHICLE_BANDWIDTH_HZ = 20e6    # ASSUMPTION (absent from Table III)
    NOISE_PSD_DBM_HZ = -174.0      # Table III
    P_MAX_DBM = 1.0                # Table III
    RSSI_DBM = -65.0               # Table III
    TX_GAIN_DBI = 20.0             # Table III
    RX_GAIN_DBI = -8.0             # Table III
    SA_DB = 7.0                    # Table III
    FREQ_MHZ = 5000.0              # Table III ("5GHz")
    P_MIN_FRACTION = 0.01          # ASSUMPTION: floor on Eq.(19) allocation so
                                   # p -> 0 as d -> 0 doesn't zero out the SNR

    # E2C link, Eq. (7)-(8) -- ASSUMPTIONS (absent from Table III)
    E2C_BANDWIDTH_HZ = 1e9
    E2C_TX_POWER_W = 1.0
    E2C_CHANNEL_GAIN = 1e-3
    E2C_NOISE_W = 1e-12

    # ================= mobility (Section III-B) =================
    MEAN_SPEED_MPS = 25.0          # Table III
    SIM_TICK_S = 1.0               # ASSUMPTION: 1 simulated second per RL step
    LANES_PER_DIRECTION = 2        # ASSUMPTION (two-way highway, Section III-B)
    LANE_WIDTH_M = 3.75            # ASSUMPTION
    RSU_OFFSET_M = 10.0            # ASSUMPTION: roadside, so d_(i,r) is never 0
    # HIGHWAY_LENGTH_M is derived from d_max in derive() -- see U2

    # ================= PPO / MEPPO =================
    ROLLOUT_STEPS = 2048           # Table III "steps in each episode"
    MINIBATCH_SIZE = 32            # Table III
    LR = 3e-4                      # Table III (one rate; actor AND critic)
    ENTROPY_COEF = 0.01            # Table III
    N_EPISODES = 1000              # Fig. 9 x-axis
    GAMMA = 0.99                   # ASSUMPTION
    GAE_LAMBDA = 0.95              # ASSUMPTION
    EPS_CLIP = 0.2                 # ASSUMPTION
    K_EPOCHS = 10                  # ASSUMPTION
    VALUE_COEF = 0.5
    MAX_GRAD_NORM = 0.5

    # PPO2-style parallel actors. Algorithm 1 of the paper literally reads
    # "for actor = 1 to N do / for timestep t = 1 to T do", and Section I-A
    # praises PPO2 for "batching observations from multiple simulation
    # environments". N_ACTORS is therefore paper-faithful, not a shortcut.
    N_ACTORS = 16                  # ROLLOUT_STEPS must be divisible by this

    # ================= reward, Eq. (25) =================
    ALPHA_R = 0.5
    BETA_R = 0.5
    INFEASIBLE_PENALTY = 0.1       # per-request (normalised by #tasks), C2/C3

    # v5 -------------------------------------------------------------
    # "running_max" = Eq. (25) verbatim: normalise by the largest exp_time /
    #   exp_energy the agent has ever reached. DEGENERATE -- the normaliser is
    #   a non-stationary, monotonically growing hidden variable, so the reward
    #   rises even under a frozen policy (measured: 1.7x over 3000 steps) and
    #   ends up ANTI-correlated with the objective (measured r = -0.83).
    # "local_ratio" = the repair. Normalise each request by what that SAME
    #   request would have cost under Local-only:
    #        r = alpha*(1 - T/T_local) + beta*(1 - E/E_local)
    #   which is exactly alpha*TS + beta*ES from the paper's own Eq. (32).
    #   Stationary, bounded, per-request, and identical to the metric the
    #   paper reports in Fig. 13. No new hyper-parameter is introduced.
    REWARD_MODE = "local_ratio"    # "local_ratio" | "running_max"
    REWARD_CLIP = 2.0              # bound the ratio reward's tail

    # ================= priority mapping (v5) =================
    # The offload/priority heads emit a score per task slot. That score has to
    # become a GLOBAL queue level in 0..9.
    # "rank_tail"   = v4: lvl = desc[10-n:], i.e. an n-task request only ever
    #   uses levels 0..n-1. A 1-task request is pinned to level 0 and can never
    #   preempt anything; a 10-task request's median task outranks every task
    #   of every small request. Precedence ends up decided by request SIZE.
    # "rank_spread" = v5: spread the n ranks evenly over the full 0..9 range,
    #   so the top-ranked task of ANY request reaches level 9. Preserves the
    #   anti-degeneracy property of ranking (promoting one task still demotes
    #   another) without the size bias.
    PRIORITY_MAP = "rank_spread"   # "rank_spread" | "rank_tail"

    # ================= completion-time accounting (v5) =================
    # The analytic queue model reports a request's T at ARRIVAL, from the queue
    # state it can see. A later, higher-priority arrival then preempts that
    # queued work, but the already-reported T is never revised -- so priority
    # looks free and Fig. 11's gap is overstated. TRACK_TRUE_T keeps per-task
    # records, pushes back every preempted record by the preempting duration
    # (exact, since inserting d seconds at level p delays levels < p by exactly
    # d), and finalises a request once no further preemption is possible.
    # Off by default: it costs ~15% wall clock and is only needed for the
    # diagnostic figure.
    TRACK_TRUE_T = False

    # v5: make Eq. (12)'s transmission queue priority-ordered as well.
    # This is the proposed repair, not a fidelity fix -- the paper's
    # Eq. (12) is explicitly FIFO. Set False to reproduce the paper.
    PRIORITY_TX = True

    # ================= state =================
    # 19 = 3 pos + 3 comm-overhead + 3 compute-load + 10 task slots (Fig. 5).
    # 29 additionally encodes per-task CPU cycles, honouring Eq. (26)'s K x 2
    # I^v matrix. Fig. 5 and Eq. (26) contradict each other; both are provided.
    STATE_MODE = 19                # 19 (Fig. 5) or 29 (Eq. 26)

    # ================= ablation switches (Figs. 11, 12) =================
    USE_PRIORITY = True            # False -> FIFO queues (Fig. 11 control)
    USE_DYNAMIC_POWER = True       # False -> always P_max (Fig. 12 control)

    # ================= C1: ASIL-informed criticality (v6 proposal) =================
    # Three criticality classes, loosely inspired by ISO 26262's ASIL risk
    # scheme, mapped onto Section I's own example (emergency braking vs
    # entertainment). This is NOT a certification claim: ASIL certification
    # needs a full safety lifecycle audit, out of scope here. What this
    # borrows is the PRINCIPLE -- classify by criticality, guarantee the
    # highest class never starves -- applied to task-scheduling priority.
    ASIL_CLASSES = ("ASIL-D", "ASIL-B/C", "QM")       # highest to lowest
    ASIL_PROBS = (0.08, 0.22, 0.70)                    # request generation mix
    ASIL_DEADLINE_MULT = {"ASIL-D": 0.5, "ASIL-B/C": 1.0, "QM": 2.5}  # x Local-only cost
    USE_SAFETY_FLOOR = True             # False -> ASIL-D gets no special treatment
    SAFETY_FLOOR_LEVEL = 9              # global queue level reserved for ASIL-D,
                                        # applied deterministically -- NOT learned,
                                        # so it holds even for an untrained or still-
                                        # exploring policy.

    # ================= C3: node-failure resilience (v6 proposal) =================
    # Table III's environment is static: every edge server is always reachable.
    # This flag does not change training -- MEPPO is trained exactly as in the
    # replication, on the static environment -- it only lets a diagnostic
    # (see contributions.py) script a scripted outage post hoc, at evaluation
    # time, to measure how the ALREADY-TRAINED policy generalises to an
    # out-of-distribution event it must handle only via the existing C2/C3
    # infeasibility fallback (route unreachable -> execute locally instead).
    NODE_FAILURE_ENABLED = False        # informational; env.fail_server() works
                                        # regardless -- this flag is read by the
                                        # diagnostics to decide whether to inject

    # ================= V7 FIX 1: the floor level was never exclusive =================
    # Under rank_spread the TOP-ranked task of EVERY multi-task request maps to
    # level 9 -- the level C1 forces ASIL-D onto -- so floored work queued FIFO
    # behind ordinary tasks; "reserved" was true only in the comment above.
    # With this on, whenever any floor is active, unprotected requests are
    # spread over 0..8 and level 9 holds protected work only.
    # False reproduces v6.1 bit-for-bit (asserted in the pre-flight section).
    RESERVE_TOP_LEVEL = True

    # ================= V7 FIX 2: Local-only cost taken after commit =================
    # v5/v6 computed the Local-only counterfactual AFTER the request had
    # enqueued its own locally-placed tasks, counting them twice -- inflating
    # T_local (the reward's denominator and C1's deadline base) exactly when the
    # agent chose Local. True = snapshot at arrival. False reproduces v6.1.
    LOCAL_COST_AT_ARRIVAL = True

    # ================= V7: disaster mode (N1 + N2) =================
    # Master switch. False -> the environment is exactly v6.1. Every
    # disaster-mode random draw uses a SEPARATE generator (env.drng), so even
    # with it ON the base request stream (task counts, sizes, ASIL classes,
    # speeds) is identical for a given seed: on/off comparisons are PAIRED.
    DISASTER_MODE = False

    # Deadlines as multiples of the request's own Local-only completion time
    # (C1's convention). EMERGENCY and SENSING are the new classes.
    DEADLINE_MULT = {"ASIL-D": 0.5, "ASIL-B/C": 1.0, "QM": 2.5,
                     "EMERGENCY": 0.5, "SENSING": 1.0}

    # --- N1: emergency vehicles -------------------------------------------
    # Their requests (route computation, hazard verification, telemetry) get
    # C1's deterministic floor: the floor is the mechanism, ROLE the selector.
    EMERGENCY_FRACTION = 0.05      # ASSUMPTION; at least one per world
    USE_EMERGENCY_FLOOR = True

    # --- N2: casualty-weighted priority (CWP) -------------------------------
    # During a disaster event a share of requests carry a victim detection.
    #   CWP = clip(w_modality * log1p(people_est) * decay(age), 0, 9)
    # START-inspired tiers (structure borrowed, not the clinical protocol).
    # Only IMMEDIATE gets the floor -- C1's lesson: floors work for RARE subsets.
    SENSING_FRACTION = 0.25        # ASSUMPTION
    MODALITIES = ("acoustic", "thermal", "lidar", "camera")
    MODALITY_PROBS = (0.15, 0.35, 0.15, 0.35)                        # ASSUMPTION
    MODALITY_WEIGHT = {"acoustic": 5.0, "thermal": 3.0, "lidar": 2.0, "camera": 1.0}
    MODALITY_COUNT_SIGMA = {"acoustic": 0.50, "thermal": 0.25, "lidar": 0.30,
                            "camera": 0.35}                           # ASSUMPTION
    PEOPLE_GEOM_P = 0.45           # true people per detection ~ Geometric(p), mean 2.2
    CWP_TAU_S = 120.0
    # "none" (default) or "decay" = the original exp(-age/tau), kept as an
    # ablation: it DEMOTES a detection the longer it waits (anti-aging).
    CWP_AGE_MODE = "none"
    # tier thresholds on the 0..9 score (ASSUMPTION). At 4.5 / 2.5: IMMEDIATE =
    # acoustic >= 2 people, thermal >= 4, lidar >= 9 (camera alone never).
    CWP_IMMEDIATE = 4.5
    CWP_DELAYED = 2.5
    USE_CWP_FLOOR = True

    # --- disaster events in the VEC cell -----------------------------------
    # An event takes a CONTIGUOUS block of RSUs offline (a debris footprint is
    # spatially correlated, unlike C3's single outage) and opens the sensing
    # window. Random in training (domain randomisation); scripted in evaluation.
    DISASTER_RATE_PER_S = 1.0 / 1800.0   # ASSUMPTION
    DISASTER_RSU_BLOCK = (1, 4)          # RSUs per event, inclusive
    DISASTER_DURATION_S = (300, 900)     # inclusive, seconds
    RANDOM_DISASTERS = True

    # --- disaster-aware reward (DR-MEPPO) ------------------------------------
    # local_ratio reward minus a value-weighted deadline-miss term, which makes
    # class outcomes learnable through OFFLOADING (the floor fixes queue level).
    DISASTER_REWARD = True
    MISS_PENALTY = 0.5
    W_LIFE = 2.0
    W_SENSING_MAX = 2.0

    # STATE_MODE 33 = 29 + these 4 features
    STATE_EXTRA = ("edge_reachable", "v2v_reachable", "protected", "cwp_norm")

    # ---------------------------------------------------------------
    @classmethod
    def derive(cls):
        """Everything computed from the raw Table III numbers."""
        c = cls
        c.P_MAX_W = 10 ** ((c.P_MAX_DBM - 30) / 10.0)
        c.ANTENNA_GAIN_LIN = 10 ** ((c.TX_GAIN_DBI + c.RX_GAIN_DBI - c.SA_DB) / 10.0)

        # Eq. (19) rearranged, with U1's unit convention
        L_max_db = c.P_MAX_DBM + c.TX_GAIN_DBI - c.SA_DB + c.RX_GAIN_DBI - c.RSSI_DBM
        c.D_MAX_M = 1000.0 * 10 ** ((L_max_db - 32.4 - 20 * math.log10(c.FREQ_MHZ)) / 26.0)

        # U2: scale the road to the radio, not the radio to the road.
        # 1.6 * d_max spacing -> overlapping cells, no coverage holes.
        c.EDGE_SPACING_M = 1.6 * c.D_MAX_M
        c.HIGHWAY_LENGTH_M = c.NUM_EDGE_SERVERS * c.EDGE_SPACING_M

        # thermal noise over each bandwidth, from Table III's -174 dBm/Hz
        c.NOISE_EDGE_W = 10 ** ((c.NOISE_PSD_DBM_HZ - 30) / 10.0) * c.EDGE_BANDWIDTH_HZ
        c.NOISE_VEH_W = 10 ** ((c.NOISE_PSD_DBM_HZ - 30) / 10.0) * c.VEHICLE_BANDWIDTH_HZ

        c.STEPS_PER_ACTOR = c.ROLLOUT_STEPS // c.N_ACTORS
        assert c.ROLLOUT_STEPS % c.N_ACTORS == 0

        # V7.1: fail loudly on an inconsistent configuration
        assert c.STATE_MODE in (19, 29, 33), "STATE_MODE must be 19, 29 or 33"
        assert abs(sum(c.MODALITY_PROBS) - 1.0) < 1e-9, "MODALITY_PROBS must sum to 1"
        assert len(c.MODALITY_PROBS) == len(c.MODALITIES)
        assert c.CWP_AGE_MODE in ("none", "decay")
        assert 0.0 <= c.CWP_DELAYED <= c.CWP_IMMEDIATE
        lo, hi = c.DISASTER_RSU_BLOCK
        assert 1 <= lo <= hi <= c.NUM_EDGE_SERVERS
        return c

    @classmethod
    @contextlib.contextmanager
    def override(cls, **kw):
        """V7.1: set Config fields for the duration of a with-block and restore
        them on exit, even on error. Environments read cfg LIVE every step, so a
        run must start AND finish inside one override block."""
        unknown = [k for k in kw if not hasattr(cls, k)]
        if unknown:
            raise AttributeError(f"unknown Config field(s): {unknown}")
        old = {k: getattr(cls, k) for k in kw}
        try:
            for k, v in kw.items():
                setattr(cls, k, v)
            cls.derive()
            yield cls
        finally:
            for k, v in old.items():
                setattr(cls, k, v)
            cls.derive()

    @classmethod
    def summary(cls):
        c = cls.derive()
        return (
            f"P_max      = {c.P_MAX_DBM:.1f} dBm ({c.P_MAX_W*1e3:.3f} mW)\n"
            f"d_max      = {c.D_MAX_M:.1f} m        [Eq. 19-20, Table III, no deviation]\n"
            f"RSU spacing= {c.EDGE_SPACING_M:.1f} m\n"
            f"highway    = {c.HIGHWAY_LENGTH_M:.0f} m  ({c.NUM_EDGE_SERVERS} servers)\n"
            f"noise@edge = {10*math.log10(c.NOISE_EDGE_W*1e3):.1f} dBm over "
            f"{c.EDGE_BANDWIDTH_HZ/1e6:.0f} MHz\n"
            f"antenna G  = {c.ANTENNA_GAIN_LIN:.3f} (TX+RX-SA = "
            f"{c.TX_GAIN_DBI + c.RX_GAIN_DBI - c.SA_DB:.0f} dB)\n"
            f"local E/task = {c.XI*(c.VEHICLE_CPU_HZ/1e9)**c.GAMMA_E*c.MIN_CPU_CYCLES*1e3:.2f}"
            f" - {c.XI*(c.VEHICLE_CPU_HZ/1e9)**c.GAMMA_E*c.MAX_CPU_CYCLES*1e3:.2f} mJ\n"
            f"local T/task = {c.MIN_CPU_CYCLES/c.VEHICLE_CPU_HZ:.2f}"
            f" - {c.MAX_CPU_CYCLES/c.VEHICLE_CPU_HZ:.2f} s"
        )
