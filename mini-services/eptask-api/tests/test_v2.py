"""eptask-api v2 test suite -- the four upgrades.

Run:  python3 -m pytest tests/test_v2.py -v   (from mini-services/eptask-api)

Covers:
  V2.1  persistent job history (SQLite store, restart survival, pruning)
  V2.2  auth layer (off by default, 401 when enabled, header + query param,
        open health/docs, meta reporting)
  V2.3  compare endpoint (two modes side by side, deltas, validation)
  V2.4  OSM graph pipeline (offline fallback with honest reason, real
        Overpass-element ingestion via a synthetic extract, schematic reload)
"""
import json
import os
import sys
import time
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from app import jobs, osm_svc  # noqa: E402
from app.jobstore import JobStore  # noqa: E402
from app.state import STATE  # noqa: E402


def _wait_job(client, jid, timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/jobs/{jid}").json()
        if j["status"] in ("done", "error"):
            return j
        time.sleep(0.4)
    raise TimeoutError(f"job {jid} did not finish in {timeout}s")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    import main  # noqa: F401 -- ensures startup ran

    with TestClient(main.app) as c:
        yield c


# ================================================================ V2.1 persistence
def test_jobstore_roundtrip_and_restart(tmp_path):
    db = tmp_path / "h.db"
    s1 = JobStore(db)
    s1.insert(dict(id="jX", kind="corridor", params={"hazard": "landslide"}, status="queued",
                   progress=0, stage="queued", error=None, created=1.0, started=None,
                   finished=None))
    s1.update("jX", status="done", progress=1.0, stage="done", finished=2.0)
    s1.store_result("jX", {"summary": {"arrival_min": 42.5}, "veh": [[1] * 500]})
    row = s1.get("jX")
    assert row["status"] == "done" and row["result"]["summary"]["arrival_min"] == 42.5
    # simulate a restart: a fresh instance on the same file
    s2 = JobStore(db)
    row2 = s2.get("jX")
    assert row2["result"]["summary"]["arrival_min"] == 42.5
    assert s2.listing()[0]["result"] is None          # listing never ships payloads
    assert s2.listing()[0]["id"] == "jX"


def test_jobstore_prune_keeps_max_rows(tmp_path):
    s = JobStore(tmp_path / "p.db", max_rows=5)
    for i in range(12):
        s.insert(dict(id=f"j{i:03d}", kind="t", params=None, status="done", progress=1.0,
                      stage="done", error=None, created=float(i), started=None, finished=None))
    assert s.count() == 5
    assert {r["id"] for r in s.listing()} == {f"j{i:03d}" for i in range(7, 12)}


def test_finished_job_is_persisted_with_result(client, monkeypatch, tmp_path):
    store = JobStore(tmp_path / "live.db")
    monkeypatch.setattr(jobs, "STORE", store)
    r = client.post("/api/corridor/run", json={
        "hazard": "landslide", "info_mode": "NONE", "convoy": False, "trace": False})
    j = _wait_job(client, r.json()["job_id"])
    assert j["status"] == "done"
    row = store.get(j["id"])
    assert row is not None and row["status"] == "done"
    assert row["result"]["summary"]["unreachable"] is not None


def test_job_listing_has_no_payloads(client):
    r = client.get("/api/jobs")
    assert r.status_code == 200
    for row in r.json()["jobs"]:
        assert "result" not in row or row.get("result") is None


# ================================================================ V2.2 auth
def test_auth_disabled_by_default(client, monkeypatch):
    monkeypatch.delenv("EPTASK_API_KEY", raising=False)
    assert client.get("/api/meta").status_code == 200
    meta = client.get("/api/meta").json()
    assert meta["auth_required"] is False


def test_auth_enabled_rejects_missing_and_wrong_key(client, monkeypatch):
    monkeypatch.setenv("EPTASK_API_KEY", "sekrit-42")
    assert client.get("/api/meta").status_code == 401
    assert client.get("/api/meta", headers={"X-API-Key": "wrong"}).status_code == 401
    # /health stays open for orchestrators
    assert client.get("/health").status_code == 200
    assert client.get("/api/health", headers={"X-API-Key": "sekrit-42"}).status_code == 200


def test_auth_accepts_header_and_query_param(client, monkeypatch):
    monkeypatch.setenv("EPTASK_API_KEY", "sekrit-42")
    ok_header = client.get("/api/meta", headers={"X-API-Key": "sekrit-42"})
    assert ok_header.status_code == 200 and ok_header.json()["auth_required"] is True
    ok_query = client.get("/api/meta?api_key=sekrit-42")
    assert ok_query.status_code == 200
    # figures are consumed via <img>, the query-param path must cover them
    assert client.get("/api/figures/corridor_map.png?api_key=sekrit-42").status_code == 200


def test_auth_blocks_runs_too(client, monkeypatch):
    monkeypatch.setenv("EPTASK_API_KEY", "sekrit-42")
    assert client.post("/api/corridor/run", json={"hazard": "landslide"}).status_code == 401


# ================================================================ V2.3 compare
def test_compare_runs_two_modes_and_reports_delta(client):
    r = client.post("/api/corridor/compare", json={
        "modes": ["NONE", "V2V+RSU"], "hazard": "landslide", "convoy": False})
    j = _wait_job(client, r.json()["job_id"], timeout=240)
    assert j["status"] == "done", j.get("error")
    res = j["result"]
    assert [run["config"]["info_mode"] for run in res["runs"]] == ["NONE", "V2V+RSU"]
    assert res["runs"][0]["config"]["convoy"] is False
    for run in res["runs"]:
        assert run["summary"]["arrival_min"] > 0
        assert run["hazard_edge"] and run["rsu"]["xy"]
        assert run["coverage"]
    # delta = B - A for every metric key
    d = res["delta"]
    a, b = res["runs"][0]["summary"], res["runs"][1]["summary"]
    assert d["arrival_min"] == round(b["arrival_min"] - a["arrival_min"], 2)
    # the notebook's core finding must reproduce live: warnings shorten the trip
    assert b["arrival_min"] <= a["arrival_min"]


def test_compare_custom_hazard_preset(client):
    r = client.post("/api/corridor/compare", json={
        "modes": ["V2V", "RSU"], "hazard": "custom",
        "footprint_m": 8000, "traffic_vph": 12, "hazard_seed": 99})
    j = _wait_job(client, r.json()["job_id"], timeout=240)
    assert j["status"] == "done", j.get("error")
    cfg = j["result"]["runs"][0]["config"]["params"]
    assert cfg["footprint_m"] == 8000 and cfg["traffic_vph"] == 12


def test_compare_validation(client):
    # three modes -> 422
    assert client.post("/api/corridor/compare", json={
        "modes": ["NONE", "V2V", "RSU"]}).status_code == 422
    # unknown mode -> 422
    assert client.post("/api/corridor/compare", json={
        "modes": ["NONE", "radio"]}).status_code == 422
    # custom hazard without any geometry -> 422
    assert client.post("/api/corridor/compare", json={
        "modes": ["NONE", "V2V"], "hazard": "custom"}).status_code == 422


# ================================================================ V2.4 OSM graph
def _fake_overpass_elements():
    """A tiny but valid OSM extract: two routes Bidur->Syaphrubesi meeting the
    notebook's place coordinates, so snapping, connectivity and the detour
    check all behave like a real extract."""
    segs = [
        ("valley", [(27.890, 85.160), (27.930, 85.172), (27.967, 85.188),
                    (28.040, 85.250), (28.160, 85.343)]),
        ("hill",   [(27.967, 85.188), (28.060, 85.230), (28.112, 85.298),
                    (28.160, 85.343)]),
        ("access", [(27.890, 85.160), (27.920, 85.170), (27.967, 85.188)]),
    ]
    nodes, ways, nid = [], [], 1000
    for _, pts in segs:
        nds = []
        for k, (la, lo) in enumerate(pts[:-1]):
            nid += 1
            nodes.append(dict(type="node", id=nid, lat=la, lon=lo))
            nds.append(nid)
        nid += 1
        nodes.append(dict(type="node", id=nid, lat=pts[-1][0], lon=pts[-1][1]))
        nds.append(nid)
        ways.append(dict(type="way", id=nid + 5000, nodes=nds,
                         tags={"highway": "primary", "name": "NH test"}))
        nid += 6000
    # de-duplicate shared nodes by reusing ids: rebuild with a shared node map
    seen = {}
    nodes, ways = [], []
    nid = 1000
    for _, pts in segs:
        nds = []
        for la, lo in pts:
            key = (round(la, 4), round(lo, 4))
            if key not in seen:
                nid += 1
                seen[key] = nid
                nodes.append(dict(type="node", id=nid, lat=la, lon=lo))
            nds.append(seen[key])
        ways.append(dict(type="way", id=nid + 5000, nodes=nds,
                         tags={"highway": "primary", "name": "NH test"}))
    return nodes + ways


@pytest.fixture()
def _osm_cache_to_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(osm_svc, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(osm_svc, "CACHE_FILE", tmp_path / "overpass_corridor.json")
    monkeypatch.setattr(osm_svc, "META_FILE", tmp_path / "overpass_corridor.meta.json")
    yield tmp_path


def test_osm_offline_falls_back_with_honest_reason(client, monkeypatch, _osm_cache_to_tmp):
    def boom(timeout_s=30.0):
        raise RuntimeError("all Overpass mirrors failed -> simulated offline")
    monkeypatch.setattr(osm_svc, "fetch_overpass", boom)
    r = client.post("/api/graph/osm", json={"prefer_osm": True, "refresh": True})
    j = _wait_job(client, r.json()["job_id"])
    assert j["status"] == "done", j.get("error")
    info = j["result"]
    assert info["fetch"]["ok"] is False
    assert info["chosen"] == "synthetic"
    assert "Overpass" in info["reason"] or "offline" in info["reason"] or "failed" in info["reason"]
    # the service keeps serving the schematic and stays healthy
    assert client.get("/api/graph").status_code == 200
    assert client.get("/api/health").json()["graph_source"].startswith("synthetic")


def test_osm_ingestion_builds_real_graph_from_elements(client, monkeypatch, _osm_cache_to_tmp):
    monkeypatch.setattr(osm_svc, "fetch_overpass",
                        lambda timeout_s=30.0: ({"elements": _fake_overpass_elements()},
                                                "test://fake-overpass"))
    r = client.post("/api/graph/osm", json={"prefer_osm": True, "refresh": True})
    j = _wait_job(client, r.json()["job_id"])
    assert j["status"] == "done", j.get("error")
    info = j["result"]
    assert info["fetch"]["ok"] is True
    assert info["chosen"] == "osm", info["reason"]
    assert info["graph_source"] == "OpenStreetMap"
    assert info["analysis"]["ok"] is True and info["nodes"] > 0
    # the live graph really changed and everything downstream still works
    src = client.get("/api/graph/source").json()
    assert src["graph_source"] == "OpenStreetMap"
    assert src["cache"]["available"] is True          # extract was cached
    g = client.get("/api/graph").json()
    assert g["source"] == "OpenStreetMap" and len(g["nodes"]) > 5
    # a corridor run on the OSM graph completes and reports the OSM graph
    r2 = client.post("/api/corridor/run", json={
        "hazard": "landslide", "info_mode": "NONE", "convoy": False, "trace": False})
    j2 = _wait_job(client, r2.json()["job_id"])
    assert j2["status"] == "done", j2.get("error")


def test_schematic_reload_restores_notebook_graph(client, monkeypatch, _osm_cache_to_tmp):
    r = client.post("/api/graph/osm", json={"prefer_osm": False})
    j = _wait_job(client, r.json()["job_id"])
    assert j["status"] == "done", j.get("error")
    assert j["result"]["chosen"] == "synthetic"
    g = client.get("/api/graph").json()
    assert g["source"].startswith("synthetic")
    assert STATE.graph.number_of_nodes() == 388       # the notebook's schematic


def test_meta_reports_osm_and_history(client, monkeypatch):
    monkeypatch.delenv("EPTASK_API_KEY", raising=False)
    meta = client.get("/api/meta").json()
    assert set(meta["osm"]) >= {"overpass_urls", "cache", "graph_source"}
    assert "jobs_stored" in meta["history"]
    assert meta["auth_required"] is False
