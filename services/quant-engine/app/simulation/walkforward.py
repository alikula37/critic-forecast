import numpy as np

from .. import config
from ..seasonality import ets, stl
from ..simulation import montecarlo
from ..volatility.garch import fit_garch


def _evaluate(actual_final, actual_path, pred50_final, pred10_path, pred50_path, pred90_path):
    if len(actual_final) == 0:
        return None
    rmse = float(np.sqrt(np.mean((pred50_final - actual_final) ** 2)))
    hit = float((np.sign(pred50_final) == np.sign(actual_final)).mean())
    pb10 = float(
        np.mean(np.maximum(0.10 * (actual_path - pred10_path), -0.90 * (actual_path - pred10_path)))
    )
    pb90 = float(
        np.mean(np.maximum(0.90 * (actual_path - pred90_path), -0.10 * (actual_path - pred90_path)))
    )
    strat = np.sign(pred50_final) * actual_final
    sharpe = float(strat.mean() / (strat.std() + 1e-12) * np.sqrt(252))
    equity = np.cumprod(1 + strat)
    peak = np.maximum.accumulate(equity)
    mdd = float((equity / peak - 1.0).min())
    calibration = float(
        ((actual_final >= pred10_path[:, -1]) & (actual_final <= pred90_path[:, -1])).mean()
    )
    pred_up = pred50_final > 0
    actual_up = actual_final > 0
    brier = float(np.mean((pred_up.astype(float) - actual_up.astype(float)) ** 2))
    return {
        "rmse": rmse,
        "hit_rate": hit,
        "pinball_10": pb10,
        "pinball_90": pb90,
        "sharpe": sharpe,
        "max_drawdown": mdd,
        "calibration": calibration,
        "brier": brier,
        "samples": int(len(actual_final)),
    }


def walkforward_perf(closes, dates, horizon, kind):
    closes = np.asarray(closes, dtype=float)
    n = len(closes)
    if n < 260 or horizon >= n - 130:
        return None
    start = max(120, n - 240)
    finals = {"final": [], "path": []}
    buckets = {}
    step = config.WF_STRIDE
    for t in range(start, n - horizon - 1, step):
        hist = closes[: t + 1]
        hist_dates = dates[: t + 1]
        try:
            if kind == "monte_carlo":
                g = fit_garch(hist, horizon)
                res = montecarlo.simulate(hist, horizon, hist_dates, g, n_paths=config.MC_N_PATHS_WF)
                p10, p50, p90 = res["p10"], res["p50"], res["p90"]
            elif kind == "stl":
                res = stl.stl_decompose(hist, horizon)
                p10, p50, p90 = res["p10"], res["p50"], res["p90"]
            else:
                res = ets.ets_forecast(hist, horizon)
                p10, p50, p90 = res["p10"], res["p50"], res["p90"]
        except Exception:
            continue
        s0 = closes[t]
        if s0 <= 0:
            continue
        pred10 = np.asarray(p10, dtype=float) / s0 - 1.0
        pred50 = np.asarray(p50, dtype=float) / s0 - 1.0
        pred90 = np.asarray(p90, dtype=float) / s0 - 1.0
        act_path = closes[t + 1 : t + 1 + horizon] / s0 - 1.0
        if len(act_path) < horizon:
            continue
        finals["final"].append((float(pred50[-1]), float(act_path[-1])))
        finals["path"].append((pred10, pred50, pred90, act_path))
        ma20 = float(np.mean(closes[max(0, t - 19) : t + 1]))
        ma60 = float(np.mean(closes[max(0, t - 59) : t + 1]))
        key = "trend_up" if ma20 > ma60 else "trend_down"
        b = buckets.setdefault(
            key, {"actual_final": [], "pred50_final": [], "actual_path": [], "p10": [], "p50": [], "p90": []}
        )
        b["actual_final"].append(float(act_path[-1]))
        b["pred50_final"].append(float(pred50[-1]))
        b["actual_path"].append(act_path)
        b["p10"].append(pred10)
        b["p50"].append(pred50)
        b["p90"].append(pred90)

    if len(finals["final"]) < 5:
        return None
    actual_f = np.array([s[1] for s in finals["final"]])
    pred50_f = np.array([s[0] for s in finals["final"]])
    actual_p = np.vstack([s[3] for s in finals["path"]])
    p10_p = np.vstack([s[0] for s in finals["path"]])
    p50_p = np.vstack([s[1] for s in finals["path"]])
    p90_p = np.vstack([s[2] for s in finals["path"]])
    base = _evaluate(actual_f, actual_p, pred50_f, p10_p, p50_p, p90_p)
    regime_errors = {}
    for key, b in buckets.items():
        if len(b["actual_final"]) >= 3:
            regime_errors[key] = _evaluate(
                np.array(b["actual_final"]),
                np.vstack(b["actual_path"]),
                np.array(b["pred50_final"]),
                np.vstack(b["p10"]),
                np.vstack(b["p50"]),
                np.vstack(b["p90"]),
            )
    base["regime_errors"] = regime_errors
    return base
