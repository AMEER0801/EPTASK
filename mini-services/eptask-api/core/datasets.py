"""
datasets.py -- ZERO-TOUCH data access for V7.1.

No uploads, no manual downloads, no logins, no API keys, no prompts. Standard
library only (urllib), so an agent needs nothing extra installed. Every
dataset resolves in this order:

  1. cache on disk (RESULTS/data/<name>.json + <name>.prov.json)   -> reproducible re-runs
  2. live HTTP fetch, with mirrors and retries                     -> cached with provenance
  3. None + the reason                                             -> caller runs SYNTHETIC
                                                                      and stamps DATA_MODE

Sources (both public, no key):
  * OpenStreetMap roads and place names, via the Overpass API (POST).
    Licence: ODbL 1.0, (c) OpenStreetMap contributors -- cite it.
  * NASA COOLR landslide event points, via the Earthdata GIS ArcGIS REST
    "query" operation (GET, Esri JSON, paginated; MaxRecordCount 2000).
    Cite: Juang, Stanley & Kirschbaum (2019) PLOS ONE 14(7): e0218657, and the
    per-event citations in the layer's "citation" field.
    NOTE: the mirror at maps.nccs.nasa.gov disallows automated access in its
    robots.txt, so it is deliberately NOT used.

What is NOT fetched, and why: casualty figures (NDRRMA / BIPAD) are report
context, not model inputs -- quote them in the report with the access date.
"""
import hashlib
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "EPtask-V7.1-student-research/1.0 (non-interactive notebook; contact via repository)"
OVERPASS_ENDPOINTS = ("https://overpass-api.de/api/interpreter",
                      "https://overpass.kumi.systems/api/interpreter")
COOLR_SERVICE = ("https://gis.earthdata.nasa.gov/gis05/rest/services/Landslides/"
                 "COOLR_Events_Points/FeatureServer")

# Bidur -> Betrawati -> {Mailung (NH42 valley) | Dhunche (NH18 hill)} -> Syaphrubesi
BBOX = (27.85, 85.08, 28.22, 85.45)          # south, west, north, east (WGS84)
DRIVE_HIGHWAYS = ("trunk", "trunk_link", "primary", "primary_link", "secondary",
                  "secondary_link", "tertiary", "tertiary_link", "unclassified",
                  "residential", "road", "track")

# Fallback coordinates. Bidur and Dhunche are verified (Wikipedia). The others
# are APPROXIMATE (+-2 km) and are replaced by OSM's own place nodes whenever
# the Overpass fetch succeeds -- see resolve_places().
PLACES_FALLBACK = {
    "Bidur": (27.89000, 85.15972, "Wikipedia (verified)"),
    "Betrawati": (27.967, 85.188, "approximate"),
    "Mailung": (28.040, 85.250, "approximate"),
    "Dhunche": (28.11167, 85.29778, "Wikipedia (verified)"),
    "Syaphrubesi": (28.160, 85.343, "approximate"),
}
PLACE_ALIASES = {
    "Bidur": ("bidur", "trishuli bazar", "trishuli bazaar", "trisuli bazar"),
    "Betrawati": ("betrawati", "betravati", "bettrawati"),
    "Mailung": ("mailung",),
    "Dhunche": ("dhunche", "dhunchhe", "dhunche bazar"),
    "Syaphrubesi": ("syaphrubesi", "syabrubesi", "syafrubesi", "syabru besi",
                    "syaphru besi", "syabrubensi"),
}


# ----------------------------------------------------------------------
def _http(url, data=None, timeout=90):
    req = urllib.request.Request(url, data=data, headers={
        "User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _paths(cache_dir, name):
    return (os.path.join(cache_dir, name + ".json"),
            os.path.join(cache_dir, name + ".prov.json"))


def _load_cache(cache_dir, name):
    p, q = _paths(cache_dir, name)
    if os.path.exists(p) and os.path.exists(q):
        with open(p) as fh:
            payload = json.load(fh)
        with open(q) as fh:
            prov = json.load(fh)
        return payload, prov
    return None


def _store(cache_dir, name, payload, prov):
    os.makedirs(cache_dir, exist_ok=True)
    p, q = _paths(cache_dir, name)
    raw = json.dumps(payload).encode()
    prov = dict(prov, sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
    with open(p + ".tmp", "wb") as fh:
        fh.write(raw)
    os.replace(p + ".tmp", p)
    with open(q, "w") as fh:
        json.dump(prov, fh, indent=1)
    return prov


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())


# ----------------------------------------------------------------------
# OpenStreetMap via Overpass
# ----------------------------------------------------------------------
def overpass_query(bbox=BBOX):
    s, w, n, e = bbox
    hw = "|".join(DRIVE_HIGHWAYS)
    return (f'[out:json][timeout:180];'
            f'(way["highway"~"^({hw})$"]({s},{w},{n},{e}););'
            f'(._;>;);out body;'
            f'node["place"]({s},{w},{n},{e});out body;')


def fetch_osm_roads(cache_dir, bbox=BBOX, live=True, timeout=240, retries=2):
    hit = _load_cache(cache_dir, "osm_roads")
    if hit is not None:
        return hit[0], dict(hit[1], status="cache")
    if not live:
        return None, dict(status="disabled", source="OpenStreetMap")
    q = overpass_query(bbox)
    errors = []
    for ep in OVERPASS_ENDPOINTS:
        for attempt in range(retries):
            try:
                raw = _http(ep, data=urllib.parse.urlencode({"data": q}).encode(),
                            timeout=timeout)
                js = json.loads(raw)
                els = js.get("elements", [])
                n_ways = sum(1 for x in els if x.get("type") == "way")
                if n_ways == 0:
                    raise ValueError("Overpass returned no drivable ways for the bbox")
                prov = dict(source="OpenStreetMap via Overpass API",
                            license="ODbL 1.0, (c) OpenStreetMap contributors",
                            endpoint=ep, query=q, bbox=list(bbox), fetched=_now(),
                            n_elements=len(els), n_ways=n_ways,
                            osm_base=js.get("osm3s", {}).get("timestamp_osm_base"))
                prov = _store(cache_dir, "osm_roads", js, prov)
                return js, dict(prov, status="live")
            except Exception as exc:                       # network, HTTP, JSON
                errors.append(f"{ep} attempt {attempt + 1}: {exc!r}"[:300])
                time.sleep(3 * (attempt + 1))
    return None, dict(status="failed", source="OpenStreetMap", errors=errors[-4:])


def resolve_places(osm_js):
    """Canonical place -> (lat, lon, source). Uses OSM place nodes when the
    fetch succeeded (nearest same-named node to the fallback guess, which
    disambiguates duplicates); otherwise the fallback table."""
    out = {k: dict(lat=v[0], lon=v[1], source=v[2]) for k, v in PLACES_FALLBACK.items()}
    if not osm_js:
        return out
    cands = {k: [] for k in PLACE_ALIASES}
    for el in osm_js.get("elements", []):
        tags = el.get("tags") or {}
        if el.get("type") != "node" or "place" not in tags:
            continue
        names = " | ".join(str(tags.get(t, "")).lower()
                           for t in ("name", "name:en", "alt_name", "old_name"))
        for canon, aliases in PLACE_ALIASES.items():
            if any(a in names for a in aliases):
                cands[canon].append(el)
    for canon, els in cands.items():
        if not els:
            continue
        la0, lo0, _ = PLACES_FALLBACK[canon]
        best = min(els, key=lambda x: (x["lat"] - la0) ** 2 + (x["lon"] - lo0) ** 2)
        if (best["lat"] - la0) ** 2 + (best["lon"] - lo0) ** 2 < 0.15 ** 2:   # ~15 km sanity
            out[canon] = dict(lat=best["lat"], lon=best["lon"],
                              source=f"OSM node {best['id']} ({best.get('tags', {}).get('name', '')})")
    return out


# ----------------------------------------------------------------------
# NASA COOLR via Earthdata GIS (ArcGIS REST)
# ----------------------------------------------------------------------
def _coolr_layer_id(timeout):
    try:
        meta = json.loads(_http(COOLR_SERVICE + "?f=json", timeout=timeout))
        for lyr in meta.get("layers", []):
            if "point" in str(lyr.get("geometryType", "")).lower() or "point" in lyr.get("name", "").lower():
                return int(lyr["id"])
        if meta.get("layers"):
            return int(meta["layers"][0]["id"])
    except Exception:
        pass
    return 0


def fetch_coolr(cache_dir, bbox=BBOX, live=True, timeout=90, page=1000, max_pages=20):
    hit = _load_cache(cache_dir, "coolr_points")
    if hit is not None:
        return hit[0], dict(hit[1], status="cache")
    if not live:
        return None, dict(status="disabled", source="NASA COOLR")
    s, w, n, e = bbox
    errors = []
    for attempt in range(2):
        try:
            lid = _coolr_layer_id(timeout)
            feats, offset = [], 0
            for _ in range(max_pages):
                params = dict(where="1=1", geometry=f"{w},{s},{e},{n}",
                              geometryType="esriGeometryEnvelope", inSR="4326",
                              spatialRel="esriSpatialRelIntersects", outFields="*",
                              outSR="4326", returnGeometry="true", f="json",
                              resultOffset=offset, resultRecordCount=page)
                url = f"{COOLR_SERVICE}/{lid}/query?" + urllib.parse.urlencode(params)
                js = json.loads(_http(url, timeout=timeout))
                if "error" in js:
                    raise RuntimeError(str(js["error"])[:200])
                batch = js.get("features", [])
                feats.extend(batch)
                if not js.get("exceededTransferLimit") or len(batch) == 0:
                    break
                offset += len(batch)
            payload = dict(features=feats, layer_id=lid)
            prov = dict(source="NASA COOLR event points via Earthdata GIS ArcGIS REST",
                        citation="Juang, Stanley & Kirschbaum (2019) PLOS ONE 14(7): e0218657; "
                                 "plus per-event citations in the 'citation' field",
                        endpoint=f"{COOLR_SERVICE}/{lid}/query", bbox=list(bbox),
                        fetched=_now(), n_features=len(feats))
            prov = _store(cache_dir, "coolr_points", payload, prov)
            return payload, dict(prov, status="live")
        except Exception as exc:
            errors.append(f"attempt {attempt + 1}: {exc!r}"[:300])
            time.sleep(3 * (attempt + 1))
    return None, dict(status="failed", source="NASA COOLR", errors=errors)


def _pick(attrs, *names):
    low = {str(k).lower(): v for k, v in attrs.items()}
    for nm in names:
        if nm in low and low[nm] not in (None, ""):
            return low[nm]
    return None


def parse_coolr(payload):
    """Esri JSON features -> [{lat, lon, date, kind, title, source}]. Tolerant
    of schema differences: only the geometry is required."""
    out = []
    for f in (payload or {}).get("features", []):
        g, a = f.get("geometry") or {}, f.get("attributes") or {}
        if "x" in g and "y" in g:
            lon, lat = float(g["x"]), float(g["y"])
        elif g.get("points"):
            lon, lat = float(g["points"][0][0]), float(g["points"][0][1])
        else:
            continue
        if not (math.isfinite(lat) and math.isfinite(lon)):
            continue
        d = _pick(a, "event_date", "ev_date", "date", "eventdate")
        if isinstance(d, (int, float)) and d > 1e11:            # ArcGIS epoch ms
            d = time.strftime("%Y-%m-%d", time.gmtime(d / 1000.0))
        out.append(dict(lat=lat, lon=lon, date=d,
                        kind=_pick(a, "ls_type", "landslide_category", "category", "type"),
                        title=_pick(a, "title", "event_title", "name"),
                        source=_pick(a, "event_import_source", "source", "method")))
    return out


# ----------------------------------------------------------------------
def load_corridor_data(results_dir, fetch=True, bbox=BBOX):
    cache_dir = os.path.join(results_dir, "data")
    osm, p_osm = fetch_osm_roads(cache_dir, bbox=bbox, live=fetch)
    coolr, p_cool = fetch_coolr(cache_dir, bbox=bbox, live=fetch)
    pts = parse_coolr(coolr) if coolr else []
    places = resolve_places(osm)
    mode = (f"roads={'OSM-' + p_osm['status'] if osm else 'SYNTHETIC'} | "
            f"hazard prior={'COOLR-' + p_cool['status'] + f' ({len(pts)} pts)' if coolr else 'UNIFORM'}")
    return dict(mode=mode, osm=osm, coolr_points=pts, places=places, bbox=list(bbox),
                provenance=dict(osm=p_osm, coolr=p_cool))
