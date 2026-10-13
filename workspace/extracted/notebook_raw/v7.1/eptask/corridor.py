"""
corridor.py -- road-scale co-simulation for N1 (V7.1).

WHY A SECOND SPATIAL SCALE (ADR-001)
The VEC cell replicated from Table III is a 558 m road with 8 RSUs. An
ambulance trip in Nuwakot/Rasuwa is tens of kilometres. So N1 is measured at
two scales:
  micro -- the VEC cell (novelties.latency_samples): how long an emergency
           vehicle's request takes, and whether it meets its deadline, while a
           block of RSUs is down, with the floor on or off.
  macro -- this module: a road graph where a hazard blocks the valley road,
           the warning spreads by vehicle-to-vehicle relay, store-carry-forward
           and surviving roadside units, and an ambulance reroutes when it
           learns. Route computation and the RSU's hazard verification take the
           MICRO latencies, retried after a deadline miss.

THE REAL GEOMETRY BEHIND THE DEFAULT
From Betrawati to Syaphrubesi there are two roads: the Trishuli valley road
(NH42, via Mailung, about 29-31 km) and the hill road (NH18, via Kalikasthan
and Dhunche, about 54 km). The Aug-2026 outburst flood damaged NH42 at many
points. An ambulance from Bidur that learns of a valley blockage BEFORE the
Betrawati junction takes the hill road; one that learns after must drive back.
That decision point turns information timing into kilometres.

MODELLED: a road graph (synthetic two-route schematic with published route
lengths, or the real OpenStreetMap graph), Poisson traffic from both ends, one
blocked edge, V2V relay within a fixed range (multi-hop within a tick),
store-carry-forward by vehicles that turned back, RSUs every few km with a
destruction footprint around the hazard, backhaul broadcast once an RSU has
verified the report, micro-sampled service latency with retry on miss.
NOT MODELLED: radio propagation and terrain shadowing (fixed range),
congestion (mountain traffic is sparse; queues only at the blockage), road
yielding to the ambulance, driver behaviour beyond "turn back / reroute when
informed". Speeds are ASSUMPTIONS (ROUTE_KPH, SPEED_KPH).
"""
import math
import os

import numpy as np
import networkx as nx
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection

from runlog import mean_ci, fmt_ci

R_EARTH = 6371000.0
SPEED_KPH = dict(trunk=30, trunk_link=25, primary=30, primary_link=25, secondary=25,
                 secondary_link=20, tertiary=20, tertiary_link=20, unclassified=18,
                 residential=15, road=15, track=10)                 # ASSUMPTION (mountain roads)
MAJOR = ("trunk", "primary", "secondary", "tertiary")
# published road distances: Betrawati-Mailung-Syaphrubesi ~31 km with
# Mailung-Syaphrubesi 17 km; Betrawati-Kalikasthan-Dhunche-Syaphrubesi ~54 km.
# Bidur-Betrawati (access) is an ASSUMPTION.
ROUTE_KM = dict(access=12.0, valley_a=14.0, valley_b=17.0, hill=54.0)
ROUTE_KPH = dict(access=30.0, valley=25.0, hill=20.0)              # ASSUMPTION
INFO_MODES = ("NONE", "V2V", "RSU", "V2V+RSU")
DEFAULTS = dict(dt=5.0, warmup_s=1800.0, horizon_s=6 * 3600.0, traffic_vph=30.0,
                v2v_range_m=300.0, rsu_spacing_m=3000.0, rsu_range_m=800.0,
                footprint_m=2000.0, dispatch_s=600.0, speed_jitter=0.15,
                coverage_every_s=60.0, max_retries=8, hazard_margin_m=2000.0,
                coolr_radius_m=1500.0)
ROUTE_COLORS = dict(access="#7f8c8d", valley="#1f4e79", hill="#2e7d32")


# ----------------------------------------------------------------------
# geometry helpers
# ----------------------------------------------------------------------
def proj(lat, lon, lat0, lon0):
    return (R_EARTH * math.radians(lon - lon0) * math.cos(math.radians(lat0)),
            R_EARTH * math.radians(lat - lat0))


def haversine(la1, lo1, la2, lo2):
    p1, p2 = math.radians(la1), math.radians(la2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lo2 - lo1) / 2) ** 2)
    return 2 * R_EARTH * math.asin(min(1.0, math.sqrt(a)))


def _arc(pts):
    seg = np.diff(pts, axis=0)
    return np.concatenate([[0.0], np.cumsum(np.hypot(seg[:, 0], seg[:, 1]))])


def _bezier(p0, c, p2, n=400):
    t = np.linspace(0, 1, n)[:, None]
    return (1 - t) ** 2 * p0 + 2 * (1 - t) * t * c + t ** 2 * p2


def _curve(p0, p2, length_m, side):
    """Quadratic Bezier p0 -> p2 bulging to `side` with arc length length_m
    (bisection on the bulge). Straight if length_m <= the chord."""
    p0, p2 = np.asarray(p0, float), np.asarray(p2, float)
    d = p2 - p0
    chord = float(np.hypot(*d))
    if length_m <= chord * 1.001 or chord == 0:
        return np.linspace(p0, p2, 50)
    nrm = np.array([-d[1], d[0]]) / chord * side
    mid = (p0 + p2) / 2
    lo, hi = 0.0, length_m
    for _ in range(60):
        h = (lo + hi) / 2
        if _arc(_bezier(p0, mid + nrm * h, p2))[-1] < length_m:
            lo = h
        else:
            hi = h
    return _bezier(p0, mid + nrm * (lo + hi) / 2, p2)


def _resample(pts, n):
    s = _arc(pts)
    tgt = np.linspace(0, s[-1], n + 1)
    return np.stack([np.interp(tgt, s, pts[:, 0]), np.interp(tgt, s, pts[:, 1])], axis=1)


def _ll(places, name):
    v = places[name]
    return (v["lat"], v["lon"]) if isinstance(v, dict) else (v[0], v[1])


# ----------------------------------------------------------------------
# graphs
# ----------------------------------------------------------------------
def build_synthetic(places, seg_m=250.0):
    """Two-route schematic: Bidur -> Betrawati -> {valley via Mailung | hill via
    Dhunche} -> Syaphrubesi. Route LENGTHS are the published road distances;
    the GEOMETRY is schematic (curves through the place coordinates)."""
    lat0, lon0 = _ll(places, "Betrawati")
    xy = {k: np.array(proj(*_ll(places, k), lat0, lon0))
          for k in ("Bidur", "Betrawati", "Mailung", "Dhunche", "Syaphrubesi")}
    G = nx.Graph()
    named, counter = {}, [0]

    def node(p, name=None):
        if name is not None and name in named:
            return named[name]
        i = counter[0]
        counter[0] += 1
        G.add_node(i, x=float(p[0]), y=float(p[1]), name=name or "")
        if name is not None:
            named[name] = i
        return i

    def route(a, b, km, kph, side, tag):
        L = km * 1000.0
        n = max(2, int(round(L / seg_m)))
        P = _resample(_curve(xy[a], xy[b], L, side), n)
        ids = [node(xy[a], a)] + [node(P[j]) for j in range(1, n)] + [node(xy[b], b)]
        seg, v = L / n, kph / 3.6
        for u, w in zip(ids[:-1], ids[1:]):
            G.add_edge(u, w, length=seg, speed=v, tt=seg / v, route=tag)

    route("Bidur", "Betrawati", ROUTE_KM["access"], ROUTE_KPH["access"], +1, "access")
    route("Betrawati", "Mailung", ROUTE_KM["valley_a"], ROUTE_KPH["valley"], -1, "valley")
    route("Mailung", "Syaphrubesi", ROUTE_KM["valley_b"], ROUTE_KPH["valley"], -1, "valley")
    d1 = float(np.hypot(*(xy["Dhunche"] - xy["Betrawati"])))
    d2 = float(np.hypot(*(xy["Syaphrubesi"] - xy["Dhunche"])))
    f = d1 / (d1 + d2)              # split of the 54 km at Dhunche: ASSUMPTION
    route("Betrawati", "Dhunche", ROUTE_KM["hill"] * f, ROUTE_KPH["hill"], +1, "hill")
    route("Dhunche", "Syaphrubesi", ROUTE_KM["hill"] * (1 - f), ROUTE_KPH["hill"], +1, "hill")
    G.graph.update(source="synthetic (schematic geometry, published route lengths)",
                   origin=named["Bidur"], junction=named["Betrawati"],
                   dest=named["Syaphrubesi"], named=named, lat0=lat0, lon0=lon0)
    return G


def graph_from_osm(osm_js, places):
    """Real OpenStreetMap drivable network -> undirected graph in local metres
    (largest connected component). Places are snapped to the nearest node on
    a major road (trunk/primary/secondary/tertiary)."""
    nodes, ways = {}, []
    for el in osm_js.get("elements", []):
        if el.get("type") == "node":
            nodes[el["id"]] = (el["lat"], el["lon"])
        elif el.get("type") == "way":
            ways.append(el)
    G = nx.Graph()
    for w in ways:
        tags = w.get("tags") or {}
        hw = tags.get("highway")
        if hw not in SPEED_KPH:
            continue
        v = SPEED_KPH[hw] / 3.6
        nd = w.get("nodes", [])
        for a, b in zip(nd[:-1], nd[1:]):
            if a == b or a not in nodes or b not in nodes:
                continue
            L = haversine(*nodes[a], *nodes[b])
            if L < 0.5:
                continue
            if G.has_edge(a, b) and G[a][b]["tt"] <= L / v:
                continue
            G.add_edge(a, b, length=L, speed=v, tt=L / v, route=hw,
                       name=tags.get("name", ""), ref=tags.get("ref", ""))
    if G.number_of_edges() == 0:
        raise ValueError("no drivable ways in the OSM extract")
    G = G.subgraph(max(nx.connected_components(G), key=len)).copy()
    lat0 = float(np.mean([nodes[n][0] for n in G]))
    lon0 = float(np.mean([nodes[n][1] for n in G]))
    for n in G:
        la, lo = nodes[n]
        x, y = proj(la, lo, lat0, lon0)
        G.nodes[n].update(x=x, y=y, lat=la, lon=lo, name="")
    major = sorted({n for u, v, dd in G.edges(data=True) if dd["route"] in MAJOR for n in (u, v)})
    pool = np.array(major if major else list(G.nodes))
    pxy = np.array([(G.nodes[n]["x"], G.nodes[n]["y"]) for n in pool])
    named, snap = {}, {}
    for name in ("Bidur", "Betrawati", "Mailung", "Dhunche", "Syaphrubesi"):
        px, py = proj(*_ll(places, name), lat0, lon0)
        d2 = (pxy[:, 0] - px) ** 2 + (pxy[:, 1] - py) ** 2
        j = int(np.argmin(d2))
        named[name], snap[name] = int(pool[j]), float(math.sqrt(d2[j]))
        G.nodes[int(pool[j])]["name"] = name
    G.graph.update(source="OpenStreetMap", origin=named["Bidur"], junction=named["Betrawati"],
                   dest=named["Syaphrubesi"], named=named, lat0=lat0, lon0=lon0, snap_m=snap)
    return G


def tree(G, target, blocked=None):
    """Shortest travel-time tree TOWARD target (predecessors, distances).
    `blocked` = an edge (a, b) that is impassable."""
    if blocked is None:
        w = "tt"
    else:
        a, b = blocked

        def w(u, v, d):
            return None if (u == a and v == b) or (u == b and v == a) else d["tt"]
    return nx.dijkstra_predecessor_and_distance(G, target, weight=w)


def path_from(pred, n, target):
    if n == target:
        return [n]
    if n not in pred or not pred[n]:
        return None
    path, seen = [n], {n}
    while path[-1] != target:
        nxt = pred[path[-1]][0]
        if nxt in seen:
            return None
        path.append(nxt)
        seen.add(nxt)
    return path


def analyse(G, margin_m=2000.0, n_test=12):
    """Open shortest path, hazard candidates on it (beyond the junction, away
    from both ends), whether a detour exists, and the DATA-DRIVEN junction:
    the last node the open path and the detour share, from the origin side."""
    o, d = G.graph["origin"], G.graph["dest"]
    pred_d, dist_d = tree(G, d)
    if o not in dist_d:
        return dict(ok=False, reason="origin and destination are not connected")
    p = path_from(pred_d, o, d)
    cum = np.concatenate([[0.0], np.cumsum([G[u][v]["length"] for u, v in zip(p[:-1], p[1:])])])
    j = G.graph.get("junction")
    ji = p.index(j) if j in p else 0
    cands = [(p[i], p[i + 1]) for i in range(ji, len(p) - 1)
             if cum[i] - cum[ji] >= margin_m and cum[-1] - cum[i + 1] >= margin_m]
    if not cands:
        a, b = len(p) // 3, 2 * len(p) // 3
        cands = [(p[i], p[i + 1]) for i in range(a, max(b, a + 1))]
    idx = np.unique(np.linspace(0, len(cands) - 1, min(n_test, len(cands))).astype(int))
    ok_e, det = [], []
    for i in idx:
        _, db = tree(G, d, blocked=cands[i])
        if o in db:
            ok_e.append(cands[i]); det.append(db[o])
    info = dict(ok=bool(ok_e), open_km=float(cum[-1] / 1000), open_min=float(dist_d[o] / 60),
                n_nodes=G.number_of_nodes(), n_edges=G.number_of_edges(),
                n_candidates=len(cands), frac_with_detour=len(ok_e) / max(len(idx), 1),
                reason="" if ok_e else "no detour exists around the hazard candidates")
    if ok_e:
        e = ok_e[len(ok_e) // 2]
        pb, _ = tree(G, d, blocked=e)
        q = path_from(pb, o, d)
        k = 0
        while k < min(len(p), len(q)) and p[k] == q[k]:
            k += 1
        jn = p[max(k - 1, 0)]
        info.update(detour_min=float(np.median(det)) / 60, junction_node=int(jn),
                    junction_name=G.nodes[jn].get("name", ""),
                    junction_km=float(cum[p.index(jn)] / 1000))
        G.graph["junction_node"] = jn
    G.graph["open_path"], G.graph["cands"], G.graph["analysis"] = p, cands, info
    return info


def build_corridor(data, prefer_osm=True):
    """Real OSM graph when it is usable (connected, and a detour exists);
    otherwise the synthetic schematic. The reason is always returned."""
    reasons = []
    if prefer_osm and data.get("osm"):
        try:
            G = graph_from_osm(data["osm"], data["places"])
            info = analyse(G)
            if info["ok"]:
                info.update(chosen="osm", reason="OSM graph is connected and has a detour")
                return G, info
            reasons.append("OSM graph unusable: " + info["reason"])
        except Exception as exc:
            reasons.append(f"OSM graph build failed: {exc!r}"[:300])
    G = build_synthetic(data["places"])
    info = analyse(G)
    info.update(chosen="synthetic",
                reason="; ".join(reasons) or "no OSM data (offline, blocked, or fetch disabled)")
    return G, info


def coolr_xy(G, points):
    if not points:
        return np.zeros((0, 2))
    lat0, lon0 = G.graph["lat0"], G.graph["lon0"]
    return np.array([proj(p["lat"], p["lon"], lat0, lon0) for p in points])


def _xy(G):
    if "_xy" not in G.graph:
        G.graph["_xy"] = {n: (G.nodes[n]["x"], G.nodes[n]["y"]) for n in G.nodes}
    return G.graph["_xy"]


def build_trees(G, hazard):
    o, d = G.graph["origin"], G.graph["dest"]
    return {(t, b): tree(G, t, hazard if b else None) for t in (o, d) for b in (False, True)}


def place_rsus(G, hazard, params, trees):
    """RSUs every rsu_spacing_m along the open path and the detour; those within
    footprint_m of the hazard are destroyed."""
    o, d = G.graph["origin"], G.graph["dest"]
    xy = _xy(G)
    paths = [G.graph["open_path"]]
    pb, db = trees[(d, True)]
    if o in db:
        paths.append(path_from(pb, o, d))
    sp = params["rsu_spacing_m"]
    pts = []
    for path in paths:
        acc, nxt = 0.0, sp / 2
        for u, v in zip(path[:-1], path[1:]):
            L = G[u][v]["length"]
            (xu, yu), (xv, yv) = xy[u], xy[v]
            while acc + L >= nxt:
                f = (nxt - acc) / L
                pts.append((xu + f * (xv - xu), yu + f * (yv - yu)))
                nxt += sp
            acc += L
    kept = []
    for q in pts:
        if all((q[0] - k[0]) ** 2 + (q[1] - k[1]) ** 2 > (sp / 3) ** 2 for k in kept):
            kept.append(q)
    P = np.array(kept) if kept else np.zeros((0, 2))
    (ax, ay), (bx, by) = xy[hazard[0]], xy[hazard[1]]
    hx, hy = (ax + bx) / 2, (ay + by) / 2
    alive = ((P[:, 0] - hx) ** 2 + (P[:, 1] - hy) ** 2) > params["footprint_m"] ** 2 \
        if len(P) else np.zeros(0, bool)
    return P, alive


def service_delay(rng, lat, max_retries=8):
    """Delay of one emergency request: draw (T, deadline) from the micro
    samples; a miss is treated as lost after the deadline and retried."""
    if lat is None or len(lat.get("T", [])) == 0:
        return 0.0
    T, D = np.asarray(lat["T"]), np.asarray(lat["D"])
    total, j = 0.0, 0
    for _ in range(max_retries):
        j = int(rng.integers(len(T)))
        if T[j] <= D[j]:
            return total + float(T[j])
        total += float(D[j])
    return total + float(T[j])


# ----------------------------------------------------------------------
# one trial
# ----------------------------------------------------------------------
class _Veh:
    __slots__ = ("path", "k", "off", "sf", "inf", "tinf", "amb", "target", "stuck", "done",
                 "t_done", "trapped", "reroute_at", "wait", "missed", "passed", "seen")

    def __init__(self, path, target, sf, amb=False):
        self.path, self.k, self.off, self.sf = path, 0, 0.0, sf
        self.inf, self.tinf, self.amb, self.target = False, None, amb, target
        self.stuck = self.done = self.trapped = self.missed = self.passed = self.seen = False
        self.t_done, self.reroute_at, self.wait = None, None, 0.0


def run_trial(G, info_mode, latency=None, seed=0, hazard=None, params=None, trees=None,
              rsu=None):
    assert info_mode in INFO_MODES, info_mode
    P = dict(DEFAULTS)
    P.update(params or {})
    o, d = G.graph["origin"], G.graph["dest"]
    jn = G.graph.get("junction_node", G.graph["junction"])
    trees = trees or build_trees(G, hazard)
    rsu_xy, rsu_alive = rsu if rsu is not None else place_rsus(G, hazard, P, trees)
    alive_xy = rsu_xy[rsu_alive] if len(rsu_xy) else np.zeros((0, 2))
    rng_tr = np.random.default_rng([int(seed), 1])
    rng_lat = np.random.default_rng([int(seed), 2])
    xy = _xy(G)
    ha, hb = hazard
    hx, hy = (xy[ha][0] + xy[hb][0]) / 2, (xy[ha][1] + xy[hb][1]) / 2
    use_v2v, use_rsu = "V2V" in info_mode, "RSU" in info_mode
    dt, R2, RR2 = P["dt"], P["v2v_range_m"] ** 2, P["rsu_range_m"] ** 2
    rate = P["traffic_vph"] / 3600.0
    state = dict(hz=False, rsu_t=None)
    vehs, amb = [], None
    cov_t, cov_f, next_cov = [], [], 0.0

    def is_h(u, w):
        return (u == ha and w == hb) or (u == hb and w == ha)

    def on_hazard_path(v):
        rem = v.path[v.k:]
        return any(is_h(a, b) for a, b in zip(rem[:-1], rem[1:]))

    def svc():
        return service_delay(rng_lat, latency, P["max_retries"])

    def replan(v):
        if v.k >= len(v.path) - 1:
            return
        pred, dist = trees[(v.target, True)]
        u, w = v.path[v.k], v.path[v.k + 1]
        e = G[u][w]
        L, spd = e["length"], e["speed"] * v.sf
        cA = math.inf if (is_h(u, w) or w not in dist) else (L - v.off) / spd + dist[w]
        cB = math.inf if u not in dist else v.off / spd + dist[u]
        if math.isinf(cA) and math.isinf(cB):
            v.stuck = True
            return
        if cA <= cB:
            v.path, v.k = [u, w] + path_from(pred, w, v.target)[1:], 0
        else:
            v.path, v.k, v.off = [w] + path_from(pred, u, v.target), 0, L - v.off

    def learn(v, now):                       # told by V2V or an RSU
        if v.inf:
            return
        v.inf, v.tinf = True, now
        if not on_hazard_path(v):
            return
        if v.amb:
            if v.reroute_at is None:         # route computation = an EMERGENCY request
                delay = svc()
                v.wait += delay
                v.reroute_at = now + delay
        else:
            replan(v)

    def discover(v, now):                    # saw the blockage itself
        if not v.inf:
            v.inf, v.tinf = True, now
        v.seen, v.reroute_at = True, None
        if not v.amb:
            v.trapped = True
        replan(v)

    def advance(v, now):
        tl = dt
        while tl > 1e-9:
            if v.k >= len(v.path) - 1:
                v.done, v.t_done = True, now + (dt - tl)
                return
            u, w = v.path[v.k], v.path[v.k + 1]
            if state["hz"] and v.off <= 1e-9 and is_h(u, w):
                discover(v, now)
                if v.stuck:
                    return
                continue
            e = G[u][w]
            spd = e["speed"] * v.sf
            need = (e["length"] - v.off) / spd
            if need <= tl:
                tl -= need
                v.k += 1
                v.off = 0.0
                if v.amb and not v.passed and v.path[v.k] == jn:
                    v.passed = True
                    v.missed = state["hz"] and on_hazard_path(v)
            else:
                v.off += spd * tl
                tl = 0.0

    def pos(v):
        if v.k >= len(v.path) - 1:
            return xy[v.path[-1]]
        u, w = v.path[v.k], v.path[v.k + 1]
        f = v.off / G[u][w]["length"]
        return (xy[u][0] + f * (xy[w][0] - xy[u][0]), xy[u][1] + f * (xy[w][1] - xy[u][1]))

    open_od = path_from(trees[(d, False)][0], o, d)
    open_do = path_from(trees[(o, False)][0], d, o)
    t = -P["warmup_s"]
    while t < P["horizon_s"]:
        for src_path, tgt in ((open_od, d), (open_do, o)):
            for _ in range(int(rng_tr.poisson(rate * dt))):
                vehs.append(_Veh(list(src_path), tgt,
                                 1.0 + P["speed_jitter"] * rng_tr.uniform(-1, 1)))
        if not state["hz"] and t >= 0:
            state["hz"] = True
            for v in vehs:                   # caught ON the hazard edge: stuck witnesses
                if not v.done and v.k < len(v.path) - 1 and v.off > 1e-9 \
                        and is_h(v.path[v.k], v.path[v.k + 1]):
                    v.stuck = v.inf = v.trapped = True
                    v.tinf = 0.0
            if use_rsu and len(alive_xy) and \
                    (((alive_xy[:, 0] - hx) ** 2 + (alive_xy[:, 1] - hy) ** 2) <= RR2).any():
                state["rsu_t"] = t + svc()   # a surviving RSU sees the hazard itself
        if amb is None and t >= P["dispatch_s"]:
            amb = _Veh(list(open_od), d, 1.0, amb=True)
            vehs.append(amb)
        for v in vehs:
            if not (v.done or v.stuck):
                advance(v, t)
        if amb is not None and amb.reroute_at is not None and t >= amb.reroute_at \
                and not amb.done and not amb.stuck:
            amb.reroute_at = None
            if on_hazard_path(amb):
                replan(amb)
        if state["hz"]:
            act = [v for v in vehs if not v.done]
            if act:
                X = np.array([pos(v) for v in act])
                infm = np.array([v.inf for v in act])
                if use_v2v and infm.any() and (~infm).any():
                    while True:                       # multi-hop within one tick
                        U = np.flatnonzero(~infm)
                        if len(U) == 0:
                            break
                        I = X[infm]
                        d2 = ((X[U][:, None, :] - I[None, :, :]) ** 2).sum(-1)
                        hit = U[(d2 <= R2).any(1)]
                        if len(hit) == 0:
                            break
                        infm[hit] = True
                        for h in hit:
                            learn(act[h], t)
                if use_rsu and len(alive_xy):
                    if state["rsu_t"] is None:
                        I = X[infm]
                        if len(I) and (((I[:, None, :] - alive_xy[None, :, :]) ** 2).sum(-1) <= RR2).any():
                            state["rsu_t"] = t + svc()        # RSU verifies the report
                    elif t >= state["rsu_t"]:
                        cov = (((X[:, None, :] - alive_xy[None, :, :]) ** 2).sum(-1) <= RR2).any(1)
                        for h in np.flatnonzero(cov & ~infm):
                            learn(act[h], t)
            if t >= next_cov:
                civ = [v for v in act if not v.amb]
                cov_t.append(t)
                cov_f.append(float(np.mean([v.inf for v in civ])) if civ else float("nan"))
                next_cov += P["coverage_every_s"]
        if amb is not None and (amb.done or amb.stuck):
            break
        t += dt

    disp = P["dispatch_s"]
    oracle = trees[(d, True)][1].get(o, math.inf)
    arr = (amb.t_done - disp) if (amb is not None and amb.done) else math.nan
    return dict(info_mode=info_mode, arrival_min=arr / 60, oracle_min=oracle / 60,
                open_min=trees[(d, False)][1][o] / 60, extra_min=(arr - oracle) / 60,
                informed_min=((amb.tinf - disp) / 60) if (amb and amb.tinf is not None) else math.nan,
                missed_junction=bool(amb.missed) if amb else False,
                saw_block=bool(amb.seen) if amb else False,
                service_wait_s=float(amb.wait) if amb else 0.0,
                unreachable=bool(amb.stuck) if amb else True,
                trapped=int(sum(v.trapped for v in vehs if not v.amb)),
                civilians=int(sum(1 for v in vehs if not v.amb)),
                rsu_alive=float(rsu_alive.mean()) if len(rsu_alive) else math.nan,
                rsu_verified_s=state["rsu_t"], cov_t=cov_t, cov_f=cov_f, hazard=[ha, hb])


# ----------------------------------------------------------------------
# experiment = trials x info modes x scheduling configurations (paired)
# ----------------------------------------------------------------------
def run_experiment(G, latencies, info_modes=INFO_MODES, trials=10, params=None, seed0=0,
                   coolr=None, verbose=True):
    """latencies: {scheduling label: micro samples}. Within a trial, every
    (info mode, scheduling) arm shares the hazard and the traffic stream --
    differences between arms are paired."""
    P = dict(DEFAULTS)
    P.update(params or {})
    info = G.graph.get("analysis") or analyse(G, P["hazard_margin_m"])
    o, d = G.graph["origin"], G.graph["dest"]
    xy = _xy(G)
    cands = G.graph["cands"]
    mids = np.array([((xy[a][0] + xy[b][0]) / 2, (xy[a][1] + xy[b][1]) / 2) for a, b in cands])
    w = np.ones(len(cands))
    if coolr is not None and len(coolr):
        d2 = ((mids[:, None, :] - coolr[None, :, :]) ** 2).sum(-1)
        w += (d2 <= P["coolr_radius_m"] ** 2).sum(1)
    w /= w.sum()
    results = {f"{m} | {s}": [] for m in info_modes for s in latencies}
    hazards = []
    for tr in range(trials):
        rng = np.random.default_rng([int(seed0), tr, 99])
        for _ in range(30):
            e = cands[int(rng.choice(len(cands), p=w))]
            trees = build_trees(G, e)
            if o in trees[(d, True)][1]:
                break
        else:
            continue
        rsu = place_rsus(G, e, P, trees)
        hazards.append([int(e[0]), int(e[1])])
        for m in info_modes:
            for s, lat in latencies.items():
                results[f"{m} | {s}"].append(run_trial(G, m, lat, seed=int(seed0) * 1000 + tr,
                                                       hazard=e, params=P, trees=trees, rsu=rsu))
        if verbose:
            r0 = results[f"{info_modes[-1]} | {list(latencies)[0]}"][-1]
            print(f"    trial {tr + 1}/{trials}: hazard edge {e}, {r0['civilians']} civilians, "
                  f"RSUs alive {r0['rsu_alive']:.0%}")
    summary = {}
    for key, rs in results.items():
        summary[key] = dict(
            n=len(rs), arrival_min=mean_ci([r["arrival_min"] for r in rs]),
            extra_min=mean_ci([r["extra_min"] for r in rs]),
            informed_min=mean_ci([r["informed_min"] for r in rs]),
            missed_pct=float(100 * np.mean([r["missed_junction"] for r in rs])) if rs else math.nan,
            saw_block_pct=float(100 * np.mean([r["saw_block"] for r in rs])) if rs else math.nan,
            trapped=mean_ci([r["trapped"] for r in rs]),
            service_wait_s=mean_ci([r["service_wait_s"] for r in rs]),
            unreachable=int(sum(r["unreachable"] for r in rs)))
    scheds = list(latencies)
    paired = {}
    if len(scheds) >= 2:
        a, b = scheds[0], scheds[1]
        for m in info_modes:
            ra, rb = results[f"{m} | {a}"], results[f"{m} | {b}"]
            paired[m] = mean_ci([x["arrival_min"] - y["arrival_min"] for x, y in zip(rb, ra)])
    if verbose:
        print(f"    {'info mode | scheduling':<28} {'extra vs oracle (min)':>26} "
              f"{'missed junction':>16} {'civilians trapped':>22}")
        for key, s in summary.items():
            print(f"    {key:<28} {fmt_ci(s['extra_min'], 1):>26} {s['missed_pct']:15.0f}% "
                  f"{fmt_ci(s['trapped'], 1):>22}")
        for m, ci in paired.items():
            print(f"    paired arrival difference '{scheds[1]}' - '{scheds[0]}' under {m}: "
                  f"{fmt_ci(ci, 2, ' min')}")
    return dict(results=results, summary=summary, paired=paired, hazards=hazards, params=P,
                analysis=info, hazard_prior="COOLR" if (coolr is not None and len(coolr)) else "uniform",
                schedulings=scheds, info_modes=list(info_modes))


# ----------------------------------------------------------------------
# figures, serialisation
# ----------------------------------------------------------------------
def plot_map(G, outdir, hazard=None, coolr=None, fname="corridor_map.png", params=None):
    P = dict(DEFAULTS)
    P.update(params or {})
    xy = _xy(G)
    fig, ax = plt.subplots(figsize=(7.2, 7.2))
    segs = [(xy[u], xy[v]) for u, v in G.edges()]
    cols = [ROUTE_COLORS.get(G[u][v].get("route"), "#b0b0b0") for u, v in G.edges()]
    lw = [1.8 if G[u][v].get("route") in ("valley", "hill", "access") + MAJOR else 0.5
          for u, v in G.edges()]
    ax.add_collection(LineCollection(segs, colors=cols, linewidths=lw, alpha=.8))
    if "open_path" in G.graph:
        p = G.graph["open_path"]
        ax.plot([xy[n][0] for n in p], [xy[n][1] for n in p], color="#1f4e79", lw=3, alpha=.35,
                label="open shortest route")
    if coolr is not None and len(coolr):
        ax.scatter(coolr[:, 0], coolr[:, 1], s=8, color="#e6a020", alpha=.6,
                   label=f"COOLR landslide points ({len(coolr)})")
    if hazard is not None:
        trees = build_trees(G, hazard)
        rp, alive = place_rsus(G, hazard, P, trees)
        if len(rp):
            ax.scatter(rp[alive, 0], rp[alive, 1], marker="^", s=40, color="#2e7d32",
                       label="RSU (alive)")
            ax.scatter(rp[~alive, 0], rp[~alive, 1], marker="x", s=50, color="k",
                       label="RSU (destroyed)")
        (ax0, ay0), (bx0, by0) = xy[hazard[0]], xy[hazard[1]]
        ax.scatter([(ax0 + bx0) / 2], [(ay0 + by0) / 2], s=160, marker="X", color="#c0392b",
                   zorder=5, label="blocked road")
    for name, n in G.graph.get("named", {}).items():
        ax.scatter([xy[n][0]], [xy[n][1]], s=30, color="k", zorder=6)
        ax.annotate(name, xy[n], xytext=(5, 5), textcoords="offset points", fontsize=9)
    jn = G.graph.get("junction_node")
    if jn is not None:
        ax.scatter([xy[jn][0]], [xy[jn][1]], s=120, facecolors="none", edgecolors="#c0392b",
                   lw=2, zorder=7, label="decision junction")
    ax.set_aspect("equal")
    ax.autoscale()
    ax.set_xlabel("east (m)"); ax.set_ylabel("north (m)")
    ax.set_title(f"N1 corridor -- {G.graph.get('source', '')}", fontsize=9)
    ax.legend(fontsize=7, loc="best")
    ax.grid(alpha=.2)
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, fname)
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_experiment(exp, outdir, fname="n1_corridor.png"):
    S, modes, scheds = exp["summary"], exp["info_modes"], exp["schedulings"]
    pal = ["#1f4e79", "#e6a020", "#2e7d32", "#c0392b"]
    fig, ax = plt.subplots(1, 3, figsize=(17, 4.5))
    x = np.arange(len(modes))
    wdt = 0.8 / max(len(scheds), 1)
    for j, s in enumerate(scheds):
        cis = [S[f"{m} | {s}"]["extra_min"] for m in modes]
        ax[0].bar(x + (j - (len(scheds) - 1) / 2) * wdt, [c[0] for c in cis], wdt,
                  yerr=[0 if not np.isfinite(c[1]) else c[1] for c in cis], capsize=3,
                  color=pal[j % 4], label=s)
        ax[1].bar(x + (j - (len(scheds) - 1) / 2) * wdt, [S[f"{m} | {s}"]["missed_pct"] for m in modes],
                  wdt, color=pal[j % 4], label=s)
    for a_ in ax[:2]:
        a_.set_xticks(x); a_.set_xticklabels(modes); a_.grid(alpha=.3, axis="y"); a_.legend(fontsize=8)
    ax[0].set_ylabel("ambulance delay vs. oracle (min)")
    ax[0].set_title("N1(d) extra arrival time from late warning")
    ax[1].set_ylabel("ambulance passed the junction uninformed (%)")
    ax[1].set_title("N1(e) missed the decision point")
    for i, m in enumerate(modes):
        rs = exp["results"][f"{m} | {scheds[0]}"]
        if not rs:
            continue
        L = min(len(r["cov_f"]) for r in rs)
        if L == 0:
            continue
        C = np.array([r["cov_f"][:L] for r in rs], dtype=float)
        tt = np.array(rs[0]["cov_t"][:L]) / 60
        ax[2].plot(tt, np.nanmean(C, 0) * 100, color=pal[i % 4], lw=2, label=m)
    ax[2].set_xlabel("minutes after the blockage")
    ax[2].set_ylabel("civilian vehicles informed (%)")
    ax[2].set_title(f"N1(f) warning coverage ({scheds[0]})")
    ax[2].grid(alpha=.3); ax[2].legend(fontsize=8)
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, fname)
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return path


def graph_to_json(G):
    keep = ("source", "origin", "junction", "dest", "named", "lat0", "lon0", "junction_node")
    return dict(graph={k: G.graph[k] for k in keep if k in G.graph},
                nodes=[[int(n), float(G.nodes[n]["x"]), float(G.nodes[n]["y"]),
                        G.nodes[n].get("name", "")] for n in G.nodes],
                edges=[[int(u), int(v), float(dd["length"]), float(dd["speed"]), dd.get("route", "")]
                       for u, v, dd in G.edges(data=True)])


def graph_from_json(js):
    G = nx.Graph()
    for n, x, y, name in js["nodes"]:
        G.add_node(int(n), x=x, y=y, name=name)
    for u, v, L, spd, route in js["edges"]:
        G.add_edge(int(u), int(v), length=L, speed=spd, tt=L / spd, route=route)
    G.graph.update(js["graph"])
    G.graph["named"] = {k: int(v) for k, v in G.graph.get("named", {}).items()}
    for k in ("origin", "junction", "dest", "junction_node"):
        if k in G.graph and G.graph[k] is not None:
            G.graph[k] = int(G.graph[k])
    analyse(G)
    return G


def describe(G, info):
    nm = G.graph.get("named", {})
    lines = [f"corridor graph : {info.get('chosen', '?')} -- {G.graph.get('source', '')}",
             f"why            : {info.get('reason', '')}",
             f"size           : {info['n_nodes']} nodes, {info['n_edges']} edges",
             f"open route     : {info['open_km']:.1f} km, {info['open_min']:.0f} min "
             f"(origin {G.nodes[G.graph['origin']].get('name', '')} -> "
             f"{G.nodes[G.graph['dest']].get('name', '')})"]
    if info.get("ok"):
        lines.append(f"detour         : exists for {info['frac_with_detour']:.0%} of tested hazard "
                     f"positions; median detour {info['detour_min']:.0f} min")
        lines.append(f"decision point : node {info['junction_node']} "
                     f"'{info.get('junction_name', '')}', {info['junction_km']:.1f} km from origin")
    if "snap_m" in G.graph:
        lines.append("place snapping : " + ", ".join(f"{k} {v:.0f} m" for k, v in G.graph["snap_m"].items()))
    lines.append("named places   : " + ", ".join(nm))
    return "\n".join(lines)
