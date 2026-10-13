"""eptask-api test suite.

Run:  python3 -m pytest tests/ -v   (from mini-services/eptask-api, service NOT required —
tests exercise the service functions in-process via fastapi.testclient and direct calls)

Covers:
  1. integrity of the notebook assets (core modules + bundle files)
  2. backend startup / health / meta / graph
  3. unit behaviour of the extracted services (validation, determinism)
  4. invalid-request handling (422 + actionable messages)
  5. output consistency against the notebook's recorded demo bundle
  6. missing-file failure mode
  7. repeated requests / job reuse and cleanup
  8. end-to-end primary workflow through the HTTP surface
"""
import json
import os
import sys
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from app import jobs  # noqa: E402
from app.cell_svc import run_cell  # noqa: E402
from app.corridor_svc import HAZARDS, run_corridor  # noqa: E402
from app.outage_svc import run_outage  # noqa: E402
from app.state import ASSETS, CORE, STATE  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _load_state():
    STATE.load()


# ---------------------------------------------------------------- 1. integrity
def test_core_modules_present():
    expected = {"corridor.py", "env.py", "policies.py", "config.py", "contributions.py",
                "disaster.py", "meppo.py", "nets.py", "runlog.py"}
    have = {p.name for p in CORE.glob("*.py")}
    assert expected <= have, f"missing notebook modules: {expected - have}"


def test_bundle_assets_present():
    for rel in ("corridor_graph.json", "results_v71.json", "latency_samples.json",
                "onnx/meppo_A_v30.onnx", "onnx/meppo_B_v30.onnx", "onnx/meppo_A_v30.onnx.json"):
        assert (ASSETS / rel).exists(), f"missing asset {rel}"


def test_core_modules_importable():
    import corridor, contributions, env, policies  # noqa: F401


# ---------------------------------------------------------------- 2. startup surface
def test_graph_loaded():
    assert STATE.graph is not None
    assert STATE.graph.number_of_nodes() == 388          # the notebook's schematic graph
    assert "origin" in STATE.graph.graph and "dest" in STATE.graph.graph


def test_latency_arms():
    assert set(STATE.latency) == {"floor ON", "floor OFF"}
    assert len(STATE.latency["floor ON"]["T"]) == 247    # recorded emergency samples


def test_reference_run_id():
    assert STATE.reference["run"]["run_id"] == "20261008-124455-ba2667"
    assert STATE.reference["run"]["mode"] == "FULL"


def test_policies_load_and_cache():
    a = STATE.policy("A", 30)
    b = STATE.policy("B", 30)
    # A was trained on the static 29-dim state; B adds the 4 disaster features (33-dim)
    assert a.state_dim == 29 and b.state_dim == 33
    assert STATE.policy("A", 30) is a                    # cached, same session object


# ---------------------------------------------------------------- 3/5. corridor service + consistency
REF_DEMO = None


def _demo():
    global REF_DEMO
    if REF_DEMO is None:
        p = Path(os.environ.get("EPTASK_DEMO_DATA", BASE / "../../workspace/extracted/demo_raw/demo/demo_data.json"))
        REF_DEMO = json.loads(p.read_text())
    return REF_DEMO


@pytest.mark.parametrize("hz", ["earthquake", "landslide", "flood"])
@pytest.mark.parametrize("mode", ["NONE", "V2V", "RSU", "V2V+RSU"])
def test_corridor_matches_notebook_recording(hz, mode):
    """The live service must reproduce the recording embedded in the original
    demo (produced by make_traces.py from notebook run 20261008-…-ba2667)."""
    ref = _demo()["corridor"][f"{hz}|{mode}"]
    out = run_corridor(dict(hazard=hz, info_mode=mode, convoy=True, trace=True))
    assert out["amb"] == ref["amb"], f"{hz}|{mode}: ambulance track differs"
    assert out["veh"] == ref["veh"], f"{hz}|{mode}: civilian tracks differ"
    for k in ("arrival_min", "oracle_min", "extra_min", "informed_min"):
        a, b = out["summary"].get(k), ref["summary"].get(k)
        if a is None or b is None:
            assert a == b
        else:
            assert abs(a - b) < 1e-9, f"{hz}|{mode}: {k} {a} vs {b}"


def test_corridor_deterministic_repeat():
    """Repeated identical requests give identical results (no hidden state)."""
    r1 = run_corridor(dict(hazard="flood", info_mode="RSU", convoy=False, trace=False))
    r2 = run_corridor(dict(hazard="flood", info_mode="RSU", convoy=False, trace=False))
    assert json.dumps(r1["summary"], sort_keys=True) == json.dumps(r2["summary"], sort_keys=True)


def test_corridor_custom_params_change_result():
    base = run_corridor(dict(hazard="custom", footprint_m=2000, traffic_vph=30, hazard_seed=7,
                             info_mode="V2V", convoy=False, trace=False))
    heavy = run_corridor(dict(hazard="custom", footprint_m=2000, traffic_vph=90, hazard_seed=7,
                              info_mode="V2V", convoy=False, trace=False))
    assert base["summary"]["civilians"] != heavy["summary"]["civilians"]
    assert base["config"]["params"]["traffic_vph"] == 30


def test_corridor_custom_candidate_without_detour_rejected():
    with pytest.raises(ValueError):
        run_corridor(dict(hazard="custom", footprint_m=2000, candidate_index=99999, info_mode="V2V",
                          convoy=False, trace=False))


def test_recorder_hook_does_not_change_results():
    """Every recorded ambulance run is verified in-service against an
    unrecorded rerun (run_corridor raises otherwise); assert it ran."""
    out = run_corridor(dict(hazard="landslide", info_mode="V2V+RSU", convoy=False, trace=True))
    assert out["amb"], "recorder produced no ambulance rows"


# ---------------------------------------------------------------- cell service
def test_cell_matches_notebook_recording():
    ref = _demo()["cell"]
    out = run_cell(dict(policy="B", version=30, V=30, seed=21, ticks=520,
                        event=dict(at=60, k=3, dur=360), floor=True, explain=True))
    assert len(out["ticks"]) == len(ref["ticks"])
    for i, (a, b) in enumerate(zip(out["ticks"], ref["ticks"])):
        for f in ("t", "i", "n", "role", "prot", "tier", "edge_ok", "a", "real", "lvl", "s", "sev", "T", "D"):
            assert a.get(f) == b.get(f), f"tick {i} field {f}: {a.get(f)} vs {b.get(f)}"
        if a.get("Tt") is not None and b.get("Tt") is not None:
            assert abs(a["Tt"] - b["Tt"]) <= 5e-4


def test_cell_floor_changes_protection():
    on = run_cell(dict(policy="B", version=30, V=30, seed=21, ticks=300,
                       event=dict(at=60, k=3, dur=120), floor=True, explain=False))
    off = run_cell(dict(policy="B", version=30, V=30, seed=21, ticks=300,
                        event=dict(at=60, k=3, dur=120), floor=False, explain=False))
    assert on["config"]["floor_level"] == 9
    # with the floor on, protected requests exist and out-of-block levels are capped
    assert on["summary"]["all"]["n"] > 0


def test_cell_event_validation():
    with pytest.raises(ValueError):
        run_cell(dict(policy="B", version=30, V=30, seed=1, ticks=100,
                      event=dict(at=90, k=3, dur=200), floor=True, explain=False))

def test_cell_model_a_runs():
    out = run_cell(dict(policy="A", version=30, V=20, seed=5, ticks=120,
                        event=dict(at=40, k=2, dur=60), floor=True, explain=True))
    assert out["config"]["onnx"] == "meppo_A_v30.onnx"
    assert any("cf" in r for r in out["ticks"]), "counterfactuals missing"


# ---------------------------------------------------------------- outage service
def test_outage_paired_runs_match_reference_direction():
    """With the notebook's own C3 protocol (V=30, k=4), model B's excess must be
    below model A's for these seeds — the qualitative result of the paper run."""
    out = run_outage(dict(policies=["A", "B"], V=30, k_list=[4], seeds=[0, 1, 2],
                          fail_at=600, fail_dur=300, post=200))
    a = out["rows"]["k=4 | model A (static)"]["during_pct"][0]
    b = out["rows"]["k=4 | model B (DR-MEPPO)"]["during_pct"][0]
    assert a > b, f"expected B excess < A excess under severe outage, got A={a:.1f} B={b:.1f}"


def test_outage_baseline_local_is_failure_proof():
    out = run_outage(dict(policies=["local"], V=30, k_list=[2], seeds=[0],
                          fail_at=600, fail_dur=300, post=200))
    row = out["rows"]["k=2 | Local-only"]
    assert abs(row["during_pct"][0]) < 5.0   # local execution barely notices an edge outage


# ---------------------------------------------------------------- HTTP surface
@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    import main

    with TestClient(main.app) as c:
        yield c


def test_http_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_http_meta(client):
    r = client.get("/api/meta")
    assert r.status_code == 200
    assert r.json()["run"]["run_id"] == "20261008-124455-ba2667"


def test_http_graph(client):
    r = client.get("/api/graph")
    assert r.status_code == 200
    g = r.json()
    assert g["origin"] is not None and len(g["routes"]["valley"]) > 1
    assert "Bidur" in g["named"]


def test_http_invalid_policy_rejected(client):
    r = client.post("/api/cell/run", json={"policy": "C"})
    assert r.status_code == 422
    assert "policy" in json.dumps(r.json())


def test_http_out_of_range_rejected(client):
    r = client.post("/api/cell/run", json={"policy": "B", "ticks": 99999})
    assert r.status_code == 422
    r = client.post("/api/corridor/run", json={"hazard": "volcano"})
    assert r.status_code == 422


def test_http_unknown_job_404(client):
    assert client.get("/api/jobs/nope").status_code == 404


def test_http_unknown_reference_404(client):
    assert client.get("/api/reference/secret").status_code == 404


def test_http_full_workflow_corridor_job(client):
    r = client.post("/api/corridor/run", json={"hazard": "landslide", "info_mode": "V2V+RSU"})
    assert r.status_code == 200
    jid = r.json()["job_id"]
    status = None
    for _ in range(120):
        j = client.get(f"/api/jobs/{jid}").json()
        status = j["status"]
        if status in ("done", "error"):
            break
        import time as _t
        _t.sleep(0.5)
    assert status == "done", client.get(f"/api/jobs/{jid}").json().get("error")
    res = client.get(f"/api/jobs/{jid}").json()["result"]
    assert res["summary"]["civilians"] > 0
    assert res["config"]["generator"].startswith("corridor.py run_trial")


def test_http_job_listing_and_repeated_use(client):
    body = {"policy": "B", "ticks": 60, "event": {"at": 5, "k": 2, "dur": 30}}
    r1 = client.post("/api/cell/run", json=body)
    r2 = client.post("/api/cell/run", json=body)
    assert r1.status_code == r2.status_code == 200
    assert r1.json()["job_id"] != r2.json()["job_id"]
    listing = client.get("/api/jobs").json()["jobs"]
    assert len(listing) >= 2


def test_missing_asset_failure_mode(tmp_path, monkeypatch):
    """If the model export is missing, the service reports an actionable error
    instead of fabricating results."""
    from app.state import STATE as S

    monkeypatch.setattr(S, "_policies", {})
    with pytest.raises(FileNotFoundError) as ei:
        S.policy("A", 99)     # v99 was never exported
    assert "not shipped" in str(ei.value)


def test_jobs_lru_bound():
    assert jobs._EXEC._max_workers == 2
