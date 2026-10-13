"""app/routes.py -- HTTP surface. Endpoints never touch the filesystem by
user-supplied paths; all computation goes through the validated services."""
from __future__ import annotations

import json
import os
import time
import uuid

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse

from . import jobs
from .auth import auth_required
from .corridor_svc import HAZARDS, FLEET, run_compare, run_corridor
from .cell_svc import run_cell
from .outage_svc import run_outage
from .osm_svc import status as osm_status
from .schemas import CellRun, CompareRun, CorridorRun, OsmBuild, OutageRun
from .state import ASSETS, STATE

api = APIRouter(prefix="/api")


# ---------------------------------------------------------------- health / meta
@api.get("/health")
def health():
    cat = STATE.catalogue()
    ok = cat["graph_loaded"] and cat["reference_loaded"]
    return {"status": "ok" if ok else "degraded", "service": "eptask-api", **cat}


@api.get("/meta")
def meta():
    R = STATE.reference
    G = STATE.graph
    info = G.graph.get("analysis", {})
    onnx_checks = R.get("checks", {}).get("onnx_vs_torch_disagreements_of_500")
    return {
        "run": R.get("run"),
        "budget": R.get("budget"),
        "data": {"mode": R.get("data", {}).get("mode"),
                 "places": R.get("data", {}).get("places"),
                 "n_coolr": R.get("data", {}).get("n_coolr")},
        "corridor_graph": info,
        "training": {k: {kk: vv for kk, vv in v.items() if kk != "return_curve" and kk != "prot_miss_curve"}
                     for k, v in (R.get("training") or {}).items()},
        "checks": R.get("checks"),
        "hazards": {k: dict(label=v["label"], footprint_m=v["footprint_m"],
                            traffic_vph=v["traffic_vph"]) for k, v in HAZARDS.items()},
        "fleet": [dict(key=k, label=l, dispatch_s=t) for k, l, t in FLEET],
        "latency_arms": sorted(STATE.latency or {}),
        "onnx_checks": onnx_checks,
        "figures": sorted(p.name for p in (ASSETS / "figures").glob("*.png")),
        "service": STATE.catalogue(),
        "auth_required": auth_required(),
        "osm": osm_status(),
        "history": jobs.store_info(),
    }


@api.get("/graph")
def graph():
    """The corridor graph in the demo's rendering format (make_traces.py).
    v2: on real OpenStreetMap graphs the raw extract is far too large for a
    browser, so non-major ways farther than ~1.2 km from the open path are
    dropped; the detour preview uses a candidate that actually has a detour."""
    import corridor as CO  # original eptask module
    import numpy as np

    G = STATE.graph
    o, d = G.graph["origin"], G.graph["dest"]
    jn = G.graph.get("junction_node", G.graph["junction"])
    p = G.graph["open_path"]
    cands = G.graph["cands"]

    # detour preview: the schematic's middle candidate may have no detour on
    # real road networks (the notebook's own frac_with_detour can be < 1);
    # walk outwards from the middle until a usable candidate is found.
    mid = len(cands) // 2
    order = [mid]
    for k in range(1, len(cands)):
        order.append(mid + k if mid + k < len(cands) else mid - k)
    pb, db, blocked = None, None, cands[mid]
    for i in order:
        pb_t, db_t = CO.tree(G, d, blocked=cands[i])
        if o in db_t:
            pb, db, blocked = pb_t, db_t, cands[i]
            break
    if pb is None:                       # extreme case: no detour anywhere
        pb, db = CO.tree(G, d)
    q = CO.path_from(pb, o, d)
    xy = lambda n: [round(G.nodes[n]["x"], 1), round(G.nodes[n]["y"], 1)]
    ji = p.index(jn) if jn in p else 0
    qi = q.index(jn) if jn in q else 0
    edges = [[int(u), int(v), dd.get("route", "")] for u, v, dd in G.edges(data=True)]

    # keep the payload browser-safe on large OSM extracts
    MAJOR = {"trunk", "trunk_link", "primary", "primary_link",
             "secondary", "secondary_link", "tertiary", "tertiary_link"}
    if len(edges) > 20000:
        step = max(1, len(p) // 400)          # 400 path samples are plenty for 1.2 km proximity
        pxy = np.array([[G.nodes[n]["x"], G.nodes[n]["y"]] for n in p][::step])
        mx = np.array([(G.nodes[u]["x"] + G.nodes[v]["x"]) / 2 for u, v, _ in edges])
        my = np.array([(G.nodes[u]["y"] + G.nodes[v]["y"]) / 2 for u, v, _ in edges])
        near = np.zeros(len(edges), dtype=bool)
        CHUNK, R2 = 4000, 1200.0 ** 2
        for s in range(0, len(edges), CHUNK):
            dx = mx[s:s + CHUNK, None] - pxy[None, :, 0]
            dy = my[s:s + CHUNK, None] - pxy[None, :, 1]
            near[s:s + CHUNK] = ((dx * dx + dy * dy).min(axis=1) <= R2)
        edges = [e for e, n_ in zip(edges, near) if n_ or e[2] in MAJOR]

    used = {e[0] for e in edges} | {e[1] for e in edges} | set(G.graph.get("named", {}).values())
    allx = [G.nodes[n]["x"] for n in used]
    ally = [G.nodes[n]["y"] for n in used]
    pts = STATE.reference.get("data", {}).get("places", {})
    coolr_pts = []
    cp = ASSETS / "coolr_points.json"
    if cp.exists():
        coolr_pts = json.loads(cp.read_text()).get("points", []) or []
    coolr = CO.coolr_xy(G, coolr_pts)
    return dict(
        source=G.graph.get("source", ""),
        nodes=[[int(n)] + xy(n) + [G.nodes[n].get("name", "")] for n in G if n in used],
        edges=edges, origin=int(o), dest=int(d), junction=int(jn),
        named={k: int(v) for k, v in G.graph.get("named", {}).items()},
        routes=dict(access=[xy(n) for n in p[:ji + 1]], valley=[xy(n) for n in p[ji:]],
                    hill=[xy(n) for n in q[qi:]]),
        bbox=[min(allx), min(ally), max(allx), max(ally)] if used else G.graph.get("_bbox", [0, 0, 1, 1]),
        coolr=[[round(float(a_), 1), round(float(b_), 1)] for a_, b_ in coolr],
        places=pts,
        cands=[[int(a_), int(b_)] for a_, b_ in cands],
    )


# ---------------------------------------------------------------- runs (async jobs)
@api.post("/corridor/run")
def corridor_run(req: CorridorRun):
    params = req.model_dump()
    jid = jobs.submit("corridor", params, lambda cb: run_corridor(params, cb))
    return {"job_id": jid, "poll": f"/api/jobs/{jid}"}


@api.post("/cell/run")
def cell_run(req: CellRun):
    params = req.model_dump()
    jid = jobs.submit("cell", params, lambda cb: run_cell(params, cb))
    return {"job_id": jid, "poll": f"/api/jobs/{jid}"}


@api.post("/outage/run")
def outage_run(req: OutageRun):
    params = req.model_dump()
    jid = jobs.submit("outage", params, lambda cb: run_outage(params, cb))
    return {"job_id": jid, "poll": f"/api/jobs/{jid}"}


@api.post("/corridor/compare")
def corridor_compare(req: CompareRun):
    """v2: one hazard scenario, two information modes, side by side."""
    params = req.model_dump()
    jid = jobs.submit("compare", params, lambda cb: run_compare(params, cb))
    return {"job_id": jid, "poll": f"/api/jobs/{jid}"}


@api.post("/graph/osm")
def graph_osm(req: OsmBuild):
    """v2: rebuild the corridor graph from real OpenStreetMap roads (or fall
    back to the schematic with the reason). Runs as a job: the Overpass fetch
    can take tens of seconds."""
    from .osm_svc import rebuild

    params = req.model_dump()
    jid = jobs.submit("osm", params, lambda cb: rebuild(params["prefer_osm"], params["refresh"]))
    return {"job_id": jid, "poll": f"/api/jobs/{jid}"}


@api.get("/graph/source")
def graph_source():
    """v2: which road graph is live, why, and what OSM state exists."""
    G = STATE.graph
    return {**osm_status(), "analysis": G.graph.get("analysis", {}) if G is not None else {}}


@api.get("/jobs")
def jobs_list():
    return {"jobs": jobs.listing()}


@api.get("/jobs/{jid}")
def job_get(jid: str):
    j = jobs.get(jid)
    if j is None:
        raise HTTPException(404, f"unknown job {jid}")
    return j


# ---------------------------------------------------------------- reference artifacts
_SECTIONS = {"run", "budget", "checks", "corridor_graph", "data", "training", "c1", "c2",
             "c3", "n1", "n2", "latency", "corridor", "onnx", "cfg", "figures"}


@api.get("/reference/{section}")
def reference(section: str):
    if section not in _SECTIONS:
        raise HTTPException(404, f"unknown section; have {sorted(_SECTIONS)}")
    R = STATE.reference
    if section == "figures":
        return {"figures": R.get("figures", [])}
    return {"section": section, "static": True, "note":
            "Reference artifact recorded by notebook run 20261008-124455-ba2667 "
            "(not recomputed live).", "data": R.get(section)}


@api.get("/figures/{name}")
def figure(name: str):
    safe = os.path.basename(name)
    p = ASSETS / "figures" / safe
    if not p.exists() or p.suffix != ".png":
        raise HTTPException(404, "figure not found")
    return FileResponse(p, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})
