"""app/state.py -- shared service state: the loaded notebook world.

Everything here is loaded ONCE at startup (graph, latency samples, reference
results, ONNX policies) so that live requests never pay the initialisation
cost again. The eptask modules in core/ are the ORIGINAL notebook files,
imported unmodified.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent.parent          # mini-services/eptask-api
CORE = Path(os.environ.get("EPTASK_CORE", BASE / "core"))
ASSETS = Path(os.environ.get("EPTASK_ASSETS", BASE / "assets" / "demo_bundle"))

# core/ holds the original eptask modules; they use flat imports
# (`from env import VECEnv`), so the directory itself goes on sys.path.
sys.path.insert(0, str(CORE))


class ServiceState:
    """Singleton holding every expensive resource."""

    def __init__(self) -> None:
        self.started_at = time.time()
        self.lock = threading.Lock()
        self.graph = None               # networkx corridor graph
        self.latency = None             # {"floor ON": {"T":…, "D":…}, "floor OFF": …}
        self.reference = None           # results_v71.json (static reference artifact)
        self._policies: dict = {}       # "A_v30" -> OnnxPolicy
        self.bundle_meta = {
            "bundle": "demo_bundle (results run 20261008-124455-ba2667)",
            "core_modules": sorted(p.name for p in CORE.glob("*.py")),
        }

    # ------------------------------------------------------------------
    def load(self) -> None:
        """Load graph + reference data. Called once at startup; fails loudly
        if the notebook assets are missing (the app cannot pretend to work)."""
        import corridor as CO  # original eptask module

        gpath = ASSETS / "corridor_graph.json"
        rpath = ASSETS / "results_v71.json"
        lpath = ASSETS / "latency_samples.json"
        for p in (gpath, rpath, lpath):
            if not p.exists():
                raise FileNotFoundError(f"required notebook asset missing: {p}")
        with self.lock:
            self.graph = CO.graph_from_json(json.loads(gpath.read_text()))
            self.reference = json.loads(rpath.read_text())
            lat_raw = json.loads(lpath.read_text())
            self.latency = {
                k: dict(T=np.asarray(v["T"], float), D=np.asarray(v["D"], float))
                for k, v in lat_raw.items()
            }

    # ------------------------------------------------------------------
    def swap_graph(self, G) -> None:
        """Atomically replace the corridor graph (v2: OSM rebuilds).
        In-flight runs keep the graph object they already hold."""
        with self.lock:
            self.graph = G

    def latency_arm(self, arm: str):
        if arm not in self.latency:
            raise KeyError(f"unknown latency arm {arm!r}; have {sorted(self.latency)}")
        return self.latency[arm]

    def default_latency_arm(self) -> str:
        return "floor ON" if "floor ON" in self.latency else sorted(self.latency)[0]

    # ------------------------------------------------------------------
    def policy(self, model: str, version: int):
        """Cached OnnxPolicy for a shipped model export (A/B x v10/v30/v50)."""
        key = f"{model}_v{version}"
        with self.lock:
            if key in self._policies:
                return self._policies[key]
        from policies import OnnxPolicy  # original eptask module

        path = ASSETS / "onnx" / f"meppo_{model}_v{version}.onnx"
        if not path.exists():
            raise FileNotFoundError(f"model export not shipped: {path.name}")
        pol = OnnxPolicy(str(path))
        with self.lock:
            self._policies.setdefault(key, pol)
        return pol

    def catalogue(self) -> dict:
        """What is loaded and ready, for /health and the UI."""
        onnx_dir = ASSETS / "onnx"
        onnx_files = sorted(p.name for p in onnx_dir.glob("*.onnx")) if onnx_dir.exists() else []
        return {
            "graph_loaded": self.graph is not None,
            "graph_nodes": self.graph.number_of_nodes() if self.graph is not None else 0,
            "graph_source": (self.graph.graph.get("source", "") if self.graph is not None else ""),
            "latency_arms": sorted(self.latency) if self.latency else [],
            "reference_loaded": self.reference is not None,
            "policies_cached": sorted(self._policies),
            "onnx_exports": onnx_files,
            "uptime_s": round(time.time() - self.started_at, 1),
        }


STATE = ServiceState()
