import numpy as np
import httpx

from .. import config


def _closes_by_date(points):
    out = {}
    for p in points:
        out[p["t"][:10]] = p["c"]
    return out


def compute_model_performance(symbol, interval="1d"):
    with httpx.Client(timeout=60) as client:
        mp_resp = client.get(
            f"{config.STORAGE_URL}/forecasts/model_points",
            params={"symbol": symbol, "limit": 50000},
        )
        ohlcv_resp = client.get(
            f"{config.STORAGE_URL}/data/ohlcv",
            params={"symbol": symbol, "interval": interval},
        )
        if mp_resp.status_code != 200 or ohlcv_resp.status_code != 200:
            return {"symbol": symbol, "models": []}
        mp_rows = mp_resp.json()
        closes = _closes_by_date(ohlcv_resp.json())

    by_model: dict[str, list[dict]] = {}
    by_job: dict[str, dict] = {}
    for r in mp_rows:
        job = by_job.setdefault(
            r["job_id"], {"job_id": r["job_id"], "points": {}, "last_close": r.get("last_close")}
        )
        job["points"][r["model_id"]] = {
            "ts": r["ts"][:10],
            "p10": r["p10"],
            "p50": r["p50"],
            "p90": r["p90"],
        }
        by_model.setdefault(r["model_id"], []).append(r)

    models = []
    for model_id in by_model:
        samples = []  # (pred_up, actual_up, p50, actual, p10, p90, last_close)
        per_job = {}
        for r in by_model[model_id]:
            pts = by_job[r["job_id"]]["points"][model_id]
            actual = closes.get(pts["ts"])
            last_close = by_job[r["job_id"]]["last_close"]
            if actual is None or not last_close or last_close <= 0:
                continue
            pred_up = bool(pts["p50"] > last_close)
            actual_up = bool(actual > last_close)
            samples.append(
                {
                    "job_id": r["job_id"],
                    "pred_up": pred_up,
                    "actual_up": actual_up,
                    "p50": pts["p50"],
                    "actual": actual,
                    "p10": pts["p10"],
                    "p90": pts["p90"],
                    "last_close": last_close,
                }
            )
            j = per_job.setdefault(
                r["job_id"],
                {"pred_up": [], "actual_up": [], "p50": [], "actual": [], "p10": [], "p90": [], "last_close": []},
            )
            j["pred_up"].append(pred_up)
            j["actual_up"].append(actual_up)
            j["p50"].append(pts["p50"])
            j["actual"].append(actual)
            j["p10"].append(pts["p10"])
            j["p90"].append(pts["p90"])
            j["last_close"].append(last_close)

        if len(samples) < 2:
            models.append({"model_id": model_id, "metrics": None, "series": []})
            continue

        pred = np.array([s["pred_up"] for s in samples], dtype=bool)
        act = np.array([s["actual_up"] for s in samples], dtype=bool)
        p50 = np.array([s["p50"] for s in samples], dtype=float)
        actual = np.array([s["actual"] for s in samples], dtype=float)
        p10 = np.array([s["p10"] for s in samples], dtype=float)
        p90 = np.array([s["p90"] for s in samples], dtype=float)
        last_close = np.array([s["last_close"] for s in samples], dtype=float)

        tp = int((pred & act).sum())
        fp = int((pred & ~act).sum())
        fn = int((~pred & act).sum())
        tn = int((~pred & ~act).sum())
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        accuracy = (tp + tn) / max(len(pred), 1)
        rmse = float(np.sqrt(np.mean((p50 - actual) ** 2)))
        mape = float(np.mean(np.abs((actual - p50) / (np.abs(actual) + 1e-12))))
        pb10 = float(np.mean(np.maximum(0.1 * (actual - p10), (0.1 - 1) * (actual - p10))))
        pb90 = float(np.mean(np.maximum(0.9 * (actual - p90), (0.9 - 1) * (actual - p90))))
        calibration = float(((actual >= p10) & (actual <= p90)).mean())
        ret = (actual - last_close) / (np.abs(last_close) + 1e-12)
        strat_ret = np.where(pred, ret, -ret)
        sharpe = float(strat_ret.mean() / (strat_ret.std() + 1e-12) * np.sqrt(252))
        brier = float(np.mean((pred.astype(float) - act.astype(float)) ** 2))

        series = []
        for jid, j in per_job.items():
            if len(j["actual"]) < 2:
                continue
            jp = np.array(j["pred_up"], dtype=bool)
            ja = np.array(j["actual_up"], dtype=bool)
            jtp = int((jp & ja).sum())
            jfp = int((jp & ~ja).sum())
            jfn = int((~jp & ja).sum())
            jprec = jtp / (jtp + jfp) if (jtp + jfp) else 0.0
            jrec = jtp / (jtp + jfn) if (jtp + jfn) else 0.0
            jf1 = 2 * jprec * jrec / (jprec + jrec) if (jprec + jrec) else 0.0
            jret = (np.array(j["actual"]) - np.array(j["last_close"])) / (
                np.abs(np.array(j["last_close"])) + 1e-12
            )
            jstrat = np.where(jp, jret, -jret)
            series.append(
                {
                    "job_id": jid,
                    "f1": round(jf1, 4),
                    "hit_rate": round((jp == ja).mean(), 4),
                    "rmse": round(float(np.sqrt(np.mean((np.array(j["p50"]) - np.array(j["actual"])) ** 2))), 4),
                    "sharpe": round(
                        float(jstrat.mean() / (jstrat.std() + 1e-12) * np.sqrt(252)), 4
                    ),
                }
            )
        series.sort(key=lambda x: x["job_id"])
        models.append(
            {
                "model_id": model_id,
                "metrics": {
                    "f1": round(f1, 4),
                    "precision": round(precision, 4),
                    "recall": round(recall, 4),
                    "accuracy": round(accuracy, 4),
                    "rmse": round(rmse, 4),
                    "mape": round(mape, 4),
                    "pinball_10": round(pb10, 4),
                    "pinball_90": round(pb90, 4),
                    "calibration": round(calibration, 4),
                    "sharpe": round(sharpe, 4),
                    "brier": round(brier, 4),
                    "samples": int(len(samples)),
                },
                "series": series,
            }
        )
    return {"symbol": symbol, "models": models}
