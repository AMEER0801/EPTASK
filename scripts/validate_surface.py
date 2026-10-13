"""Validate the full eptask integration surface for the live backend.

Loads every module the app needs, runs one real corridor trial and one real
cell tick with the shipped ONNX policy, and times both.
"""
import json
import os
import sys
import time

EPTASK = '/home/z/my-project/workspace/extracted/notebook_raw/v7.1/eptask'
BUNDLE = '/home/z/my-project/workspace/extracted/notebook_raw/v7.1/results/demo_bundle'
sys.path.insert(0, EPTASK)

t0 = time.time()
import numpy as np
import corridor as CO
import contributions as CT
from config import Config
from env import VECEnv
from policies import OnnxPolicy, RulePolicy
print(f"[imports] {time.time()-t0:.2f}s")

# ---- graph ----
t0 = time.time()
G = CO.graph_from_json(json.load(open(os.path.join(BUNDLE, 'corridor_graph.json'))))
info = G.graph.get('analysis')
print(f"[graph] {time.time()-t0:.2f}s  nodes={G.number_of_nodes()} edges={G.number_of_edges()} "
      f"source={G.graph.get('source','')[:40]}")

# ---- latency samples ----
lat_raw = json.load(open(os.path.join(BUNDLE, 'latency_samples.json')))
LAT = {k: dict(T=np.asarray(v['T'], float), D=np.asarray(v['D'], float)) for k, v in lat_raw.items()}
lat = LAT.get('floor ON') or next(iter(LAT.values()))
print(f"[latency] arms={list(LAT)}  n={len(lat['T'])}")

# ---- one corridor trial ----
o, d = G.graph['origin'], G.graph['dest']
cands = G.graph['cands']
e = cands[len(cands)//2]
trees = CO.build_trees(G, e)
P = dict(CO.DEFAULTS, footprint_m=20000.0, traffic_vph=30.0)
rsu = CO.place_rsus(G, e, P, trees)
t0 = time.time()
res = CO.run_trial(G, 'V2V+RSU', lat, seed=301, hazard=e, params=P, trees=trees, rsu=rsu)
dt = time.time() - t0
print(f"[corridor trial] {dt:.2f}s  extra_min={res['extra_min']:.1f} arrival={res['arrival_min']:.1f} "
      f"civilians={res['civilians']} trapped={res['trapped']}")

# ---- cell trace (like make_traces.cell_trace, shortened) ----
onnx_b = os.path.join(BUNDLE, 'onnx', 'meppo_B_v30.onnx')
t0 = time.time()
pol = OnnxPolicy(onnx_b)
print(f"[onnx load] {time.time()-t0:.2f}s  state_dim={pol.state_dim} cfg_kw={pol.cfg_kw}")

cfg = Config.derive()
cfg.PRIORITY_TX = False
S = cfg.NUM_EDGE_SERVERS
k = 3
s0 = (S - k) // 2
kw = dict(DISASTER_MODE=True, RANDOM_DISASTERS=False, TRACK_TRUE_T=True,
          RESERVE_TOP_LEVEL=True, PRIORITY_TX=False,
          STATE_MODE=pol.cfg_kw.get('STATE_MODE', 33))
t0 = time.time()
with cfg.override(**kw):
    env = VECEnv(cfg, 30, seed=21)
    obs = env.observe()
    n_decided = 0
    for step in range(60):
        if step == 30:
            env.trigger_disaster(s0, k, 360)
        off, pri = pol.act(env, obs)
        if int(env.n_tasks) > 0:
            ex = CT.explain_decision(pol, env)
            n_decided += 1
        obs, r, inf = env.step(off, pri)
dt = time.time() - t0
print(f"[cell 60 ticks, V=30] {dt:.2f}s  decisions explained={n_decided} "
      f"last T={inf['T']:.3f}s alive={int(inf['alive'])}/{S}")

# ---- policy catalogue ----
import glob
print("[onnx catalogue]:", sorted(os.path.basename(p) for p in glob.glob(os.path.join(BUNDLE, 'onnx', '*.onnx'))))
print("OK - integration surface verified")
