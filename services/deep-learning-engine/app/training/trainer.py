import numpy as np
import torch
from sklearn.preprocessing import RobustScaler
from torch.utils.data import DataLoader, TensorDataset

from .. import config
from ..models.bilstm_attention import BiLSTMAttentionModel, PinballLoss, count_parameters

METRIC_KEYS = ["rmse", "hit_rate", "pinball_10", "pinball_90", "sharpe", "max_drawdown"]


def fit_scaler(X_windows):
    flat = X_windows.reshape(-1, X_windows.shape[-1])
    scaler = RobustScaler(quantile_range=(5.0, 95.0))
    scaler.fit(flat)
    return scaler


def _train_loop(model, train_loader, val_X, val_Y, epochs, lr, patience):
    opt = torch.optim.AdamW(
        model.parameters(), lr=lr, weight_decay=config.WEIGHT_DECAY
    )
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    loss_fn = PinballLoss()
    best = float("inf")
    best_state = None
    bad = 0
    for epoch in range(epochs):
        model.train()
        for xb, yb in train_loader:
            opt.zero_grad()
            preds, _ = model(xb)
            loss = loss_fn(preds, yb)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
        sched.step()
        model.eval()
        with torch.no_grad():
            preds, _ = model(val_X)
            vloss = loss_fn(preds, val_Y).item()
        if vloss < best:
            best = vloss
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
            bad = 0
        else:
            bad += 1
            if bad >= patience:
                break
    if best_state is not None:
        model.load_state_dict(best_state)


def train_bilstm(X_train, Y_train, X_val, Y_val, X_last, epochs=None, seed=None):
    torch.manual_seed(seed if seed is not None else config.SEED)
    np.random.seed(seed if seed is not None else config.SEED)
    model = BiLSTMAttentionModel(input_size=X_train.shape[-1], horizon=Y_train.shape[1])
    dataset = TensorDataset(
        torch.tensor(X_train, dtype=torch.float32),
        torch.tensor(Y_train, dtype=torch.float32),
    )
    loader = DataLoader(dataset, batch_size=config.BATCH_SIZE, shuffle=True)
    val_t = torch.tensor(X_val, dtype=torch.float32)
    val_y = torch.tensor(Y_val, dtype=torch.float32)
    _train_loop(
        model,
        loader,
        val_t,
        val_y,
        epochs=epochs or config.EPOCHS,
        lr=config.LEARNING_RATE,
        patience=config.PATIENCE,
    )
    model.eval()
    last_t = torch.tensor(X_last[None, :, :], dtype=torch.float32)
    with torch.no_grad():
        preds, weights = model(last_t)
    out = {}
    for q, p in zip(config.QUANTILES, preds):
        out[f"q{int(q * 100)}"] = p[0].numpy()
    attn = weights[0].numpy().tolist()
    with torch.no_grad():
        val_preds, _ = model(val_t)
        val_out = {f"q{int(q * 100)}": p.numpy() for q, p in zip(config.QUANTILES, val_preds)}
    return model, out, val_out, attn


def evaluate_preds(actual_final, actual_path, pred50_final, pred50_path, pred10_path, pred90_path):
    if len(actual_final) == 0:
        return None
    rmse = float(np.sqrt(np.mean((pred50_final - actual_final) ** 2)))
    hit = float((np.sign(pred50_final) == np.sign(actual_final)).mean())
    pb10 = float(np.mean(np.maximum(0.1 * (actual_path - pred10_path), (0.1 - 1) * (actual_path - pred10_path))))
    pb90 = float(np.mean(np.maximum(0.9 * (actual_path - pred90_path), (0.9 - 1) * (actual_path - pred90_path))))
    strat = np.sign(pred50_final) * actual_final
    sharpe = float(strat.mean() / (strat.std() + 1e-12) * np.sqrt(252))
    equity = np.cumprod(1 + strat)
    peak = np.maximum.accumulate(equity)
    mdd = float((equity / peak - 1.0).min())
    pred_up = pred50_final > 0
    actual_up = actual_final > 0
    brier = float(np.mean((pred_up.astype(float) - actual_up.astype(float)) ** 2))
    calib = float(
        ((actual_final >= pred10_path[:, -1]) & (actual_final <= pred90_path[:, -1])).mean()
    )
    return {
        "rmse": rmse,
        "hit_rate": hit,
        "pinball_10": pb10,
        "pinball_90": pb90,
        "sharpe": sharpe,
        "max_drawdown": mdd,
        "brier": brier,
        "calibration": calib,
        "samples": int(len(actual_final)),
    }


def walkforward_backtest(features, targets, closes, horizon, kind, epochs=None):
    n = len(features)
    if n < 200:
        return None
    import time

    t0 = time.time()
    fold_epochs = epochs or config.WF_EPOCHS
    samples = {"final": [], "path": [], "buckets": []}
    bounds = [int(n * f) for f in (0.7, 0.8, 0.9)]
    print(f"[wf:{kind}] başladı, folds={len(bounds)}", flush=True)
    for b in bounds:
        if b - config.SEQUENCE_LEN < 60:
            continue
        if b >= n - horizon - 2:
            continue
        import time as _t

        tf0 = _t.time()
        print(f"[wf:{kind}] fold @{b}", flush=True)
        train_f = features[:b]
        train_t = targets[:b]
        scaler = fit_scaler(train_f)
        train_f_s = scaler.transform(train_f.reshape(-1, train_f.shape[-1])).reshape(train_f.shape)
        if kind == "bilstm":
            Xw, Yw = make_windows(train_f_s, train_t)
        else:
            Xw, Yw = make_tabular(train_f_s, train_t)
        split = int(len(Xw) * 0.9)
        model = None
        for t in range(b, n - horizon, config.WF_STRIDE):
            if kind == "bilstm":
                window = scaler.transform(features[t - config.SEQUENCE_LEN + 1 : t + 1].reshape(-1, features.shape[-1])).reshape(
                    config.SEQUENCE_LEN, features.shape[-1]
                )
            else:
                window = scaler.transform(features[t : t + 1])[0]
            if kind == "bilstm":
                if model is None:
                    model, _, _, _ = train_bilstm(
                        Xw[:split], Yw[:split], Xw[split:], Yw[split:], window, epochs=fold_epochs
                    )
                x = torch.tensor(window[None, :, :], dtype=torch.float32)
                with torch.no_grad():
                    preds, _ = model(x)
                p50 = preds[1][0].numpy()
                p10 = preds[0][0].numpy()
                p90 = preds[2][0].numpy()
            else:
                if model is None:
                    if kind == "lightgbm":
                        model = train_lgb_models(Xw[:split], Yw[:split], config.WF_TREE_ESTIMATORS)
                    else:
                        model = train_xgb_models(Xw[:split], Yw[:split], config.WF_TREE_ESTIMATORS)
                p50 = model["p50"].predict(window[None, :])[0]
                p10 = model["p10"].predict(window[None, :])[0]
                p90 = model["p90"].predict(window[None, :])[0]
            actual = targets[t]
            if np.isnan(actual).any():
                continue
            samples["final"].append((p50[-1], actual[-1]))
            samples["path"].append((p10, p50, p90, actual))
            ma20 = float(np.mean(closes[max(0, t - 19) : t + 1]))
            ma60 = float(np.mean(closes[max(0, t - 59) : t + 1]))
            samples["buckets"].append(
                (
                    p50[-1],
                    actual[-1],
                    p10,
                    p50,
                    p90,
                    actual,
                    ma20,
                    ma60,
                )
            )
    if len(samples["final"]) < 5:
        print(f"[wf:{kind}] yetersiz örnek", flush=True)
        return None
    import time as _t

    print(f"[wf:{kind}] tamam ({_t.time() - t0:.0f}s, {len(samples['final'])} örnek)", flush=True)
    actual_f = np.array([s[1] for s in samples["final"]])
    pred50_f = np.array([s[0] for s in samples["final"]])
    actual_p = np.vstack([s[3] for s in samples["path"]])
    p10_p = np.vstack([s[0] for s in samples["path"]])
    p50_p = np.vstack([s[1] for s in samples["path"]])
    p90_p = np.vstack([s[2] for s in samples["path"]])
    base = evaluate_preds(actual_f, actual_p, pred50_f, p50_p, p10_p, p90_p)
    buckets = {}
    for (p50_f, actual_f_item, p10_i, p50_i, p90_i, actual_i, ma20, ma60) in samples["buckets"]:
        key = "trend_up" if ma20 > ma60 else "trend_down"
        b = buckets.setdefault(
            key,
            {"actual_final": [], "pred50_final": [], "actual_path": [], "p10": [], "p50": [], "p90": []},
        )
        b["actual_final"].append(actual_f_item)
        b["pred50_final"].append(p50_f)
        b["actual_path"].append(actual_i)
        b["p10"].append(p10_i)
        b["p50"].append(p50_i)
        b["p90"].append(p90_i)
    regime_errors = {}
    for key, b in buckets.items():
        if len(b["actual_final"]) >= 3:
            regime_errors[key] = evaluate_preds(
                np.array(b["actual_final"]),
                np.vstack(b["actual_path"]),
                np.array(b["pred50_final"]),
                np.vstack(b["p50"]),
                np.vstack(b["p10"]),
                np.vstack(b["p90"]),
            )
    base["regime_errors"] = regime_errors
    return base


def make_windows(features, targets):
    from .dataset import make_sequence_windows

    return make_sequence_windows(features, targets, config.SEQUENCE_LEN)


def make_tabular(features, targets):
    from .dataset import make_tabular_windows

    return make_tabular_windows(features, targets)


def train_xgb_models(Xw, Yw, n_estimators=None):
    from ..models.xgboost_line import train_xgboost_core

    return train_xgboost_core(Xw, Yw, n_estimators=n_estimators or config.XGB_ESTIMATORS)


def train_lgb_models(Xw, Yw, n_estimators=None):
    from ..models.lightgbm_line import train_lightgbm_core

    return train_lightgbm_core(Xw, Yw, n_estimators=n_estimators or config.LGB_ESTIMATORS)


def train_regime_models(Xw, Yw, labels, kind, min_samples=60):
    """Per-regime quantile models (0/1/2). Returns dict regime -> {p10,p50,p90}."""
    out = {}
    labels = np.asarray(labels, dtype=int)
    for reg in (0, 1, 2):
        mask = labels == reg
        if int(mask.sum()) < min_samples:
            continue
        Xr = np.asarray(Xw)[mask]
        Yr = np.asarray(Yw)[mask]
        if kind == "lightgbm":
            out[reg] = train_lgb_models(Xr, Yr, config.WF_TREE_ESTIMATORS)
        else:
            out[reg] = train_xgb_models(Xr, Yr, config.WF_TREE_ESTIMATORS)
    return out


def predict_regime_models(models_by_regime, x, regime):
    m = models_by_regime.get(regime) or models_by_regime.get(None)
    if m is None:
        return None
    p50 = m["p50"].predict(x)[0]
    p10 = m["p10"].predict(x)[0]
    p90 = m["p90"].predict(x)[0]
    return p10, p50, p90
