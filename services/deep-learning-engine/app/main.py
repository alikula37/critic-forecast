import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from scipy.stats import norm
from sklearn.preprocessing import RobustScaler

from . import config
from .models import lightgbm_line, xgboost_line
from .models.bilstm_attention import count_parameters
from .training import trainer
from .training.dataset import (
    build_targets,
    compute_features,
    make_sequence_windows,
    make_tabular_windows,
    regime_label,
)

app = FastAPI(title="Deep Learning Engine", version="1.0.0")


class Point(BaseModel):
    t: str
    o: float
    h: float
    l: float
    c: float
    v: float


class PredictRequest(BaseModel):
    symbol: str
    interval: str = "1d"
    horizon: int = 30
    points: list[Point]
    regime_probs: list[list[float]] | None = None
    skip_wf: bool = False


@app.get("/health")
def health():
    return {"status": "ok"}


def _to_price_paths(last_close, cumlog):
    return last_close * np.exp(cumlog)


def _up_from_cone(p50_final, p10_final, p90_final):
    sigma = (p90_final - p10_final) / 2.56
    if sigma <= 1e-12:
        return 1.0 if p50_final > 0 else 0.0
    z = p50_final / sigma
    return float(norm.cdf(z))


def _future_dates(points, horizon):
    import datetime as dt

    last = dt.date.fromisoformat(points[-1].t[:10])
    out = []
    cur = last
    while len(out) < horizon:
        cur = cur + dt.timedelta(days=1)
        if cur.weekday() < 5:
            out.append(cur.isoformat())
    return out


@app.post("/predict")
def predict(req: PredictRequest):
    import time as _t

    _t0 = _t.time()
    n = len(req.points)
    if n < 220:
        raise HTTPException(422, "Yetersiz veri: en az 220 bar gerekiyor")
    horizon = min(req.horizon, n - config.SEQUENCE_LEN - 30)

    closes = np.asarray([p.c for p in req.points], dtype=float)
    highs = np.asarray([p.h for p in req.points], dtype=float)
    lows = np.asarray([p.l for p in req.points], dtype=float)
    volumes = np.asarray([p.v for p in req.points], dtype=float)
    dates = [p.t for p in req.points]

    ret = np.log(pd.Series(closes)).diff().fillna(0.0).to_numpy()
    targets = build_targets(ret, horizon)
    regime_probs = None
    if req.regime_probs and len(req.regime_probs) == n:
        regime_probs = req.regime_probs
    features = compute_features(
        closes, highs, lows, volumes, dates, regime_probs=regime_probs
    ).to_numpy(dtype=float)

    future = _future_dates(req.points, horizon)

    results = []

    X_seq, Y_seq = make_sequence_windows(features, targets, config.SEQUENCE_LEN)
    split = int(len(X_seq) * 0.85)
    scaler = trainer.fit_scaler(X_seq[:split])
    X_tr = scaler.transform(X_seq[:split].reshape(-1, X_seq.shape[-1])).reshape(X_seq[:split].shape)
    X_va = scaler.transform(X_seq[split:].reshape(-1, X_seq.shape[-1])).reshape(X_seq[split:].shape)
    X_last = scaler.transform(features[-config.SEQUENCE_LEN :])
    print(f"[dle] {_t.time() - _t0:.0f}s — bilstm eğitimi başlıyor", flush=True)

    model, preds, val_preds, attn = trainer.train_bilstm(
        X_tr, Y_seq[:split], X_va, Y_seq[split:], X_last,
        epochs=config.WF_EPOCHS if req.skip_wf else None,
    )
    last_close = closes[-1]
    paths = {q: _to_price_paths(last_close, preds[q]) for q in preds}
    p50_f, p10_f, p90_f = paths["q50"][-1], paths["q10"][-1], paths["q90"][-1]
    up = _up_from_cone(p50_f - last_close, p10_f - last_close, p90_f - last_close)
    if req.skip_wf:
        perf = None
    else:
        perf = trainer.walkforward_backtest(features, targets, closes, horizon, "bilstm")
    if perf is None:
        val_out = {
            f"q{int(q * 100)}": p for q, p in zip(config.QUANTILES, val_preds)
        }
        perf = _val_performance(val_out, Y_seq[split:], last_close)
    results.append(
        {
            "model_id": "bilstm_attention",
            "model_name": "Bi-LSTM + Attention (Quantile)",
            "line": "derin_ogrenme",
            "points": [
                {"date": d, "p10": float(paths["q10"][i]), "p50": float(paths["q50"][i]), "p90": float(paths["q90"][i])}
                for i, d in enumerate(future)
            ],
            "up_probability": up,
            "performance": perf,
            "details": {
                "hidden_size": config.HIDDEN_SIZE,
                "layers": config.NUM_LAYERS,
                "epochs": config.EPOCHS,
                "attention_peak_index": int(np.argmax(attn)),
                "train_windows": len(X_tr),
                "param_count": count_parameters(model),
            },
        }
    )

    X_tab, Y_tab = make_tabular_windows(features, targets)
    split_t = int(len(X_tab) * 0.85)
    scaler_t = RobustScaler(quantile_range=(5.0, 95.0))
    scaler_t.fit(X_tab[:split_t])
    X_tr_t = scaler_t.transform(X_tab[:split_t])
    X_va_t = scaler_t.transform(X_tab[split_t:])
    X_last_t = scaler_t.transform(features[-1:])

    xgb_est = config.WF_TREE_ESTIMATORS if req.skip_wf else None
    models = trainer.train_xgb_models(X_tr_t, Y_tab[:split_t], xgb_est)
    labels = [regime_label(features[t]) for t in range(len(X_tr_t))]
    xgb_regime = None
    if not req.skip_wf:
        xgb_regime = trainer.train_regime_models(X_tr_t, Y_tab[:split_t], labels, "xgboost")
    clf = xgboost_line.train_direction_classifier(X_tr_t, Y_tab[:split_t][:, -1])
    cur_regime = regime_label(features[-1])
    xgb_rp = trainer.predict_regime_models(xgb_regime, X_last_t, cur_regime) if xgb_regime else None
    if xgb_rp is not None:
        p10, p50, p90 = xgb_rp
    else:
        p50 = models["p50"].predict(X_last_t)[0]
        p10 = models["p10"].predict(X_last_t)[0]
        p90 = models["p90"].predict(X_last_t)[0]
    up_xgb = float(clf.predict_proba(X_last_t)[0][1])
    xgb_paths = {
        "q10": _to_price_paths(last_close, p10),
        "q50": _to_price_paths(last_close, p50),
        "q90": _to_price_paths(last_close, p90),
    }
    if req.skip_wf:
        xgb_perf = None
    else:
        xgb_perf = trainer.walkforward_backtest(features, targets, closes, horizon, "xgboost")
    if not req.skip_wf and xgb_perf is None:
        xgb_perf = _val_performance(
            {"q10": p10, "q50": p50, "q90": p90}, Y_tab[split_t:], last_close
        )
    results.append(
        {
            "model_id": "xgboost_quantile",
            "model_name": "XGBoost (Direction + Quantile)",
            "line": "gradient_boosting",
            "points": [
                {"date": d, "p10": float(xgb_paths["q10"][i]), "p50": float(xgb_paths["q50"][i]), "p90": float(xgb_paths["q90"][i])}
                for i, d in enumerate(future)
            ],
            "up_probability": up_xgb,
            "performance": xgb_perf,
            "details": {
                "top_features": xgboost_line.feature_importances(models),
                "train_samples": len(X_tr_t),
            },
        }
    )

    lgb_models = trainer.train_lgb_models(X_tr_t, Y_tab[:split_t], xgb_est)
    lgb_regime = None
    if not req.skip_wf:
        lgb_regime = trainer.train_regime_models(X_tr_t, Y_tab[:split_t], labels, "lightgbm")
    lgb_clf = lightgbm_line.train_direction_classifier(X_tr_t, Y_tab[:split_t][:, -1])
    lgb_rp = trainer.predict_regime_models(lgb_regime, X_last_t, cur_regime) if lgb_regime else None
    if lgb_rp is not None:
        lgb_p10, lgb_p50, lgb_p90 = lgb_rp
    else:
        lgb_p50 = lgb_models["p50"].predict(X_last_t)[0]
        lgb_p10 = lgb_models["p10"].predict(X_last_t)[0]
        lgb_p90 = lgb_models["p90"].predict(X_last_t)[0]
    up_lgb = float(lgb_clf.predict_proba(X_last_t)[0][1])
    lgb_paths = {
        "q10": _to_price_paths(last_close, lgb_p10),
        "q50": _to_price_paths(last_close, lgb_p50),
        "q90": _to_price_paths(last_close, lgb_p90),
    }
    if req.skip_wf:
        lgb_perf = None
    else:
        lgb_perf = trainer.walkforward_backtest(features, targets, closes, horizon, "lightgbm")
    if not req.skip_wf and lgb_perf is None:
        lgb_perf = _val_performance(
            {"q10": lgb_p10, "q50": lgb_p50, "q90": lgb_p90}, Y_tab[split_t:], last_close
        )
    results.append(
        {
            "model_id": "lightgbm_quantile",
            "model_name": "LightGBM (Direction + Quantile)",
            "line": "gradient_boosting",
            "points": [
                {"date": d, "p10": float(lgb_paths["q10"][i]), "p50": float(lgb_paths["q50"][i]), "p90": float(lgb_paths["q90"][i])}
                for i, d in enumerate(future)
            ],
            "up_probability": up_lgb,
            "performance": lgb_perf,
            "details": {
                "top_features": lightgbm_line.feature_importances(lgb_models),
                "train_samples": len(X_tr_t),
            },
        }
    )

    return {"symbol": req.symbol, "interval": req.interval, "horizon": horizon, "models": results}


def _val_performance(val_preds, Y_val, last_close):
    y = np.asarray(Y_val)
    p10 = np.asarray(val_preds["q10"])
    p50 = np.asarray(val_preds["q50"])
    p90 = np.asarray(val_preds["q90"])
    if y.shape[0] == 0 or p10.ndim < 2:
        return None
    actual = y[:, -1]
    pred50 = p50[:, -1]
    rmse = float(np.sqrt(np.mean((pred50 - actual) ** 2)))
    hit = float((np.sign(pred50) == np.sign(actual)).mean())
    pb10 = float(np.mean(np.maximum(0.1 * (y - p10), (0.1 - 1) * (y - p10))))
    pb90 = float(np.mean(np.maximum(0.9 * (y - p90), (0.9 - 1) * (y - p90))))
    strat = np.sign(pred50) * actual
    sharpe = float(strat.mean() / (strat.std() + 1e-12) * np.sqrt(252))
    equity = np.cumprod(1 + strat)
    peak = np.maximum.accumulate(equity)
    mdd = float((equity / peak - 1.0).min())
    pred_up = pred50 > 0
    actual_up = actual > 0
    brier = float(np.mean((pred_up.astype(float) - actual_up.astype(float)) ** 2))
    calib = float(((actual >= p10[:, -1]) & (actual <= p90[:, -1])).mean())
    return {
        "rmse": rmse,
        "hit_rate": hit,
        "pinball_10": pb10,
        "pinball_90": pb90,
        "sharpe": sharpe,
        "max_drawdown": mdd,
        "brier": brier,
        "calibration": calib,
        "samples": int(len(actual)),
        "regime_errors": {},
    }
