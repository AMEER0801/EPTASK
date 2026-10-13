"""
runlog.py -- provenance and logging helpers (V7.1).

Standing rule since v5: every summary number must be recomputable from raw
records. These helpers stamp a results file with a run id, the full Config
snapshot, a digest of the exact module sources and the runtime, compute
mean +- 95% confidence intervals over seeds, and write JSON atomically so an
interrupted run never leaves a half-written file.
"""
import hashlib
import json
import math
import os
import platform
import time
import uuid

import numpy as np

_T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
         8: 2.306, 9: 2.262, 10: 2.228, 12: 2.179, 15: 2.131, 20: 2.086,
         25: 2.060, 30: 2.042}


def t975(df):
    """Two-sided 95% Student-t critical value (table + linear interpolation)."""
    if df <= 0:
        return float("nan")
    if df in _T975:
        return _T975[df]
    keys = sorted(_T975)
    if df > keys[-1]:
        return 1.96
    lo = max(k for k in keys if k < df)
    hi = min(k for k in keys if k > df)
    return _T975[lo] + (_T975[hi] - _T975[lo]) * (df - lo) / (hi - lo)


def mean_ci(x):
    """(mean, 95% CI half-width, n) over the finite values of x. With n == 1
    the half-width is NaN -- one seed gives no uncertainty estimate."""
    a = np.asarray([v for v in x if v is not None and np.isfinite(v)], dtype=float)
    if a.size == 0:
        return (float("nan"), float("nan"), 0)
    if a.size == 1:
        return (float(a[0]), float("nan"), 1)
    return (float(a.mean()), float(t975(a.size - 1) * a.std(ddof=1) / math.sqrt(a.size)),
            int(a.size))


def fmt_ci(ci, digits=2, unit=""):
    m, h, n = ci
    if not np.isfinite(m):
        return "n/a"
    if n < 2 or not np.isfinite(h):
        return f"{m:.{digits}f}{unit} (n={n})"
    return f"{m:.{digits}f} +- {h:.{digits}f}{unit} (n={n})"


def to_jsonable(o):
    if isinstance(o, dict):
        return {str(k): to_jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [to_jsonable(v) for v in o]
    if isinstance(o, np.ndarray):
        return to_jsonable(o.tolist())
    if isinstance(o, (np.bool_, bool)):
        return bool(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return f if math.isfinite(f) else None
    if isinstance(o, (str, int)) or o is None:
        return o
    return repr(o)


def save_json(obj, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(to_jsonable(obj), fh, indent=1)
    os.replace(tmp, path)
    return path


def cfg_snapshot(cfg):
    """Every UPPER_CASE Config field (inputs and derived values)."""
    return {k: to_jsonable(v) for k, v in vars(cfg).items() if k.isupper()}


def sources_digest(pkg_dir):
    h = hashlib.sha256()
    for name in sorted(os.listdir(pkg_dir)):
        if name.endswith(".py"):
            h.update(name.encode())
            with open(os.path.join(pkg_dir, name), "rb") as fh:
                h.update(fh.read())
    return h.hexdigest()[:16]


def new_run(mode, pkg_dir, extra=None):
    info = dict(run_id=time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6],
                mode=mode, started=time.strftime("%Y-%m-%d %H:%M:%S"),
                python=platform.python_version(), platform=platform.platform(),
                code_digest=sources_digest(pkg_dir))
    info.update(extra or {})
    return info
