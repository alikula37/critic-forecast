import time

import httpx
import numpy as np
from scipy.optimize import linprog

from .. import config

_CACHE: dict[tuple[str, str], tuple[float, dict]] = {}
MIN_SAMPLES = 30


def solve_quantile_weights(X, y, alpha):
    """min_w sum pinball_alpha(y - Xw)  s.t. w >= 0, sum(w) = 1.

    X: (N, M) component predictions for one quantile (returns space)
    y: (N,) realized returns
    """
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    N, M = X.shape
    if N < MIN_SAMPLES or M < 2:
        return None
    c = np.concatenate([np.zeros(M), alpha * np.ones(N), (1.0 - alpha) * np.ones(N)])
    A_eq = np.hstack([X, np.eye(N), -np.eye(N)])
    b_eq = y
    A_eq = np.vstack([A_eq, np.concatenate([np.ones(M), np.zeros(2 * N)])[None, :]])
    b_eq = np.append(b_eq, 1.0)
    bounds = [(0.0, None)] * M + [(0.0, None)] * (2 * N)
    res = linprog(c, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")
    if not res.success:
        return None
    w = np.asarray(res.x[:M], dtype=float)
    if not np.isfinite(w).all() or w.sum() <= 1e-12:
        return None
    return w / w.sum()


def _job_date(job_id):
    parts = str(job_id).split("_")
    if len(parts) == 3 and parts[0] == "backfill":
        return parts[2]
    return None


def _fetch_realized(symbol, interval):
    with httpx.Client(timeout=60) as client:
        mp = client.get(
            f"{config.STORAGE_URL}/forecasts/model_points",
            params={"symbol": symbol, "limit": 50000},
        )
        ohlcv = client.get(
            f"{config.STORAGE_URL}/data/ohlcv",
            params={"symbol": symbol, "interval": interval},
        )
        if mp.status_code != 200 or ohlcv.status_code != 200:
            return {}
    closes = {p["t"][:10]: p["c"] for p in ohlcv.json()}
    last_close_by_job = {}
    by_date: dict[str, list[dict]] = {}
    for r in mp.json():
        if r.get("last_close"):
            last_close_by_job[r["job_id"]] = r["last_close"]
        by_date.setdefault(r["ts"][:10], []).append(r)
    out = {}
    for date, rows in by_date.items():
        actual = closes.get(date)
        if actual is None:
            continue
        best = None
        best_bf = ""
        for r in rows:
            bf = _job_date(r["job_id"]) or ""
            if bf and bf <= date and bf >= best_bf:
                best, best_bf = r["job_id"], bf
        if best is None:
            best = rows[-1]["job_id"]
        lc = last_close_by_job.get(best)
        if not lc or lc <= 0:
            continue
        preds = {}
        for r in rows:
            if r["job_id"] == best:
                preds[r["model_id"]] = {"p10": r["p10"], "p50": r["p50"], "p90": r["p90"]}
        if len(preds) < 2:
            continue
        out[date] = {"ret": actual / lc - 1.0, "preds": preds}
    return out


def build_qra_weights(symbol, interval, model_ids):
    cache_key = (symbol, interval)
    now = time.time()
    cached = _CACHE.get(cache_key)
    if cached and now - cached[0] < 3600:
        return cached[1]
    realized = _fetch_realized(symbol, interval)
    result = None
    dates = sorted(realized)
    if dates:
        rows = []
        for date in dates:
            preds = realized[date]["preds"]
            if all(m in preds for m in model_ids):
                rows.append((realized[date]["ret"], preds))
        if len(rows) >= MIN_SAMPLES:
            X10 = np.array([[r[m]["p10"] for m in model_ids] for _, r in rows], dtype=float)
            X50 = np.array([[r[m]["p50"] for m in model_ids] for _, r in rows], dtype=float)
            X90 = np.array([[r[m]["p90"] for m in model_ids] for _, r in rows], dtype=float)
            y = np.array([r[0] for r in rows], dtype=float)
            w10 = solve_quantile_weights(X10, y, 0.10)
            w50 = solve_quantile_weights(X50, y, 0.50)
            w90 = solve_quantile_weights(X90, y, 0.90)
            if w10 is not None and w50 is not None and w90 is not None:
                equal = np.ones(len(model_ids)) / len(model_ids)
                shrink = lambda w: 0.7 * np.asarray(w, dtype=float) + 0.3 * equal
                result = {
                    "weights": {
                        "p10": [float(v) for v in shrink(w10)],
                        "p50": [float(v) for v in shrink(w50)],
                        "p90": [float(v) for v in shrink(w90)],
                    },
                    "n": len(rows),
                }
    _CACHE[cache_key] = (now, result)
    return result


def isotonic_fix(p10, p50, p90):
    values = sorted([p10, p50, p90])
    return float(values[0]), float(values[1]), float(values[2])
