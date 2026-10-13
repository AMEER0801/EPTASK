"""app/osm_svc.py -- real OpenStreetMap road graph (v2).

v1 shipped only the notebook's schematic two-route graph (documented
limitation #1: the notebook's own v7.2 OSM/COOLR fetches failed offline).
v2 wires the ORIGINAL `corridor.build_corridor()` into the live service:

    1. collect the corridor places from the notebook's results bundle,
    2. fetch drivable highways for their bounding box from the Overpass API
       (two public mirrors, 30 s timeout each),
    3. cache the extract on disk so offline restarts can still use it,
    4. hand it to core/corridor.build_corridor(), which keeps the OSM graph
       ONLY if it is connected and a detour exists, and otherwise falls back
       to the synthetic schematic -- with the reason always reported.

The service graph is swapped atomically; in-flight simulations keep the
graph they started with, so a rebuild can never corrupt a running trial.
COOLR landslide points stay bundled (coolr_points.json); live COOLR fetch
is intentionally not attempted (the dataset requires an Earthdata login,
which a laptop deployment does not have by default).
"""
from __future__ import annotations

import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .state import ASSETS, STATE

CACHE_DIR = Path(os.environ.get("EPTASK_OSM_CACHE", ASSETS.parent / "osm_cache"))
CACHE_FILE = CACHE_DIR / "overpass_corridor.json"
META_FILE = CACHE_DIR / "overpass_corridor.meta.json"
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
# must cover exactly the highway types corridor.SPEED_KPH understands
_HW = "trunk|trunk_link|primary|primary_link|secondary|secondary_link|tertiary|" \
      "tertiary_link|unclassified|residential|road|track"


def places() -> dict:
    p = (STATE.reference or {}).get("data", {}).get("places")
    if not p:
        raise RuntimeError("notebook places not loaded -- cannot build a corridor")
    return p


def bbox(pad_km: float = 8.0) -> list[float]:
    """[south, west, north, east] around the notebook's places."""
    p = places()
    lats = [float(v["lat"]) for v in p.values()]
    lons = [float(v["lon"]) for v in p.values()]
    lat0 = (min(lats) + max(lats)) / 2
    dlat = (pad_km + 2.0) / 111.32
    dlon = (pad_km + 2.0) / (111.32 * max(0.2, math.cos(math.radians(lat0))))
    return [min(lats) - dlat, min(lons) - dlon, max(lats) + dlat, max(lons) + dlon]


def overpass_query(bb: list[float]) -> str:
    s, w, n, e = bb
    return (f'[out:json][timeout:25];(way["highway"~"^({_HW})$"]({s:.4f},{w:.4f},{n:.4f},{e:.4f}););'
            f"(._;>;);out body;")


def fetch_overpass(timeout_s: float = 30.0) -> tuple[dict, str]:
    """Query the public Overpass mirrors; returns (elements, url)."""
    q = overpass_query(bbox())
    errors = []
    for url in OVERPASS_URLS:
        try:
            req = urllib.request.Request(
                url, data=("data=" + urllib.parse.quote(q)).encode(),
                headers={"Content-Type": "application/x-www-form-urlencoded",
                         "User-Agent": "eptask-api/2.0 (EPtask research console)"})
            with urllib.request.urlopen(req, timeout=timeout_s) as r:
                raw = json.loads(r.read().decode("utf-8"))
            els = raw.get("elements", [])
            ways = sum(1 for el in els if el.get("type") == "way")
            if ways == 0:
                raise ValueError("Overpass returned no highway ways for the corridor bbox")
            return {"elements": els}, url
        except Exception as exc:  # noqa: BLE001 -- try the next mirror
            errors.append(f"{url.split('/')[2]}: {type(exc).__name__}: {exc}"[:220])
    raise RuntimeError("all Overpass mirrors failed -> " + " | ".join(errors))


def cache_meta() -> dict | None:
    if not META_FILE.exists():
        return None
    try:
        return json.loads(META_FILE.read_text())
    except Exception:  # noqa: BLE001
        return None


def read_cache() -> dict | None:
    if not CACHE_FILE.exists():
        return None
    try:
        return json.loads(CACHE_FILE.read_text())
    except Exception:  # noqa: BLE001
        return None


def _store_cache(osm: dict, url: str, bb: list[float], n_elements: int) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(osm))
    META_FILE.write_text(json.dumps(dict(
        fetched_at=time.strftime("%Y-%m-%d %H:%M:%S %Z", time.gmtime()),
        url=url, elements=n_elements, bbox=[round(v, 4) for v in bb])))


def rebuild(prefer_osm: bool = True, refresh: bool = False) -> dict:
    """Rebuild the service graph. Returns a status dict with the decision and
    its reason -- this is surfaced verbatim in the UI."""
    import corridor as CO  # original eptask module

    bb = bbox()
    osm, src = None, None
    info: dict = {"prefer_osm": bool(prefer_osm), "refresh": bool(refresh), "bbox": bb}

    if prefer_osm:
        use_cache = (not refresh) and CACHE_FILE.exists()
        if use_cache:
            osm, src = read_cache(), "cache"
            if osm is None:
                use_cache = False
        if osm is None:
            try:
                t0 = time.time()
                osm, url = fetch_overpass()
                ways = sum(1 for el in osm["elements"] if el.get("type") == "way")
                _store_cache(osm, url, bb, len(osm["elements"]))
                info["fetch"] = dict(ok=True, url=url, elements=len(osm["elements"]),
                                     ways=ways, seconds=round(time.time() - t0, 1))
                src = "fetched"
            except Exception as exc:  # noqa: BLE001 -- fall through to fallback
                info["fetch"] = dict(ok=False, error=str(exc)[:400])
                osm = None

    G, an = CO.build_corridor({"osm": osm, "places": places()},
                              prefer_osm=bool(prefer_osm and osm is not None))
    STATE.swap_graph(G)

    info.update(
        chosen=an.get("chosen"),
        reason=an.get("reason", ""),
        osm_payload=src,
        graph_source=G.graph.get("source", ""),
        nodes=G.number_of_nodes(), edges=G.number_of_edges(),
        analysis={k: an[k] for k in ("ok", "open_km", "open_min", "n_candidates",
                                     "frac_with_detour", "detour_min", "junction_name")
                  if k in an},
        named_snapped={k: dict(node=v, snap_m=round(G.graph.get("snap_m", {}).get(k, 0.0), 1))
                       for k, v in G.graph.get("named", {}).items()},
    )
    return info


def status() -> dict:
    meta = cache_meta()
    return dict(
        overpass_urls=OVERPASS_URLS,
        cache=dict(available=CACHE_FILE.exists(),
                   fetched_at=(meta or {}).get("fetched_at"),
                   url=(meta or {}).get("url"),
                   elements=(meta or {}).get("elements"),
                   size_kb=round(CACHE_FILE.stat().st_size / 1024) if CACHE_FILE.exists() else 0),
        graph_source=STATE.catalogue().get("graph_source", ""),
    )
