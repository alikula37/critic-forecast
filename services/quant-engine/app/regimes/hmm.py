import numpy as np
from hmmlearn import hmm

from .. import config


def _label_states(means, stds):
    n = len(means)
    order = np.argsort(means)
    labels = {}
    for rank, s in enumerate(order):
        if rank == n - 1 and means[s] > 0:
            labels[s] = "boğa"
        elif rank == 0 and means[s] < 0:
            labels[s] = "ayı"
        else:
            labels[s] = "yatay"
    return labels


def detect_regimes(closes, dates):
    closes = np.asarray(closes, dtype=float)
    rets_all = np.diff(np.log(closes))
    vol_all = np.abs(rets_all)
    rets = rets_all[-config.HMM_LOOKBACK:]
    vol = vol_all[-config.HMM_LOOKBACK:]
    features = np.column_stack([rets, vol])
    model = hmm.GaussianHMM(
        n_components=config.HMM_STATES,
        covariance_type="diag",
        n_iter=300,
        random_state=42,
        tol=1e-4,
    )
    model.fit(features)
    states = model.predict(features)
    probs = model.predict_proba(features)
    means = {s: float(rets[states == s].mean()) for s in range(config.HMM_STATES)}
    stds = {s: float(rets[states == s].std()) for s in range(config.HMM_STATES)}
    labels = _label_states(list(means.values()), list(stds.values()))

    offset = len(closes) - len(states)
    state_series = np.full(len(closes), states[0], dtype=int)
    prob_series = np.tile(probs[0], (len(closes), 1))
    state_series[offset:] = states
    prob_series[offset:] = probs

    out = []
    for i in range(len(closes)):
        s = int(state_series[i])
        out.append(
            {
                "date": dates[i],
                "state": labels[s],
                "prob": float(prob_series[i][s]),
                "state_id": s,
            }
        )
    current_s = int(state_series[-1])
    return {
        "states": out,
        "current": {"label": labels[current_s], "state_id": current_s},
        "state_probs": {labels[s]: float(prob_series[-1][s]) for s in range(config.HMM_STATES)},
        "state_means": {labels[s]: means[s] for s in range(config.HMM_STATES)},
        "state_stds": {labels[s]: stds[s] for s in range(config.HMM_STATES)},
    }


def causal_regime_series(closes, dates, anchor_step=60):
    """Regime probabilities per date fitted causally: each date uses the HMM
    fit on data up to the latest anchor <= t. Avoids lookahead in features."""
    closes = np.asarray(closes, dtype=float)
    n = len(closes)
    if n < 120:
        return []
    anchors = list(range(anchor_step, n - 1, anchor_step))
    if not anchors:
        anchors = [n - 1]
    fits = []
    for a in anchors:
        rets = np.diff(np.log(closes[: a + 1]))
        vol = np.abs(rets)
        features = np.column_stack([rets[-config.HMM_LOOKBACK:], vol[-config.HMM_LOOKBACK:]])
        if len(features) < 60:
            continue
        try:
            m = hmm.GaussianHMM(
                n_components=config.HMM_STATES,
                covariance_type="diag",
                n_iter=100,
                random_state=42,
                tol=1e-3,
            )
            m.fit(features)
            fits.append((a, m))
        except Exception:
            continue
    if not fits:
        return []
    out = [None] * n
    for t in range(n):
        a, m = fits[0]
        for (a2, m2) in fits:
            if a2 <= t:
                a, m = a2, m2
            else:
                break
        if t == 0:
            probs = [1.0 / config.HMM_STATES] * config.HMM_STATES
        else:
            pt = np.asarray([np.diff(np.log(closes[: t + 1]))[-1], abs(np.diff(np.log(closes[: t + 1]))[-1])], dtype=float)
            try:
                probs = m.predict_proba(pt[None, :])[0].tolist()
            except Exception:
                probs = [1.0 / config.HMM_STATES] * config.HMM_STATES
        out[t] = {"date": dates[t], "probs": probs}
    return out


def quick_backtest(closes, horizon_days=1):
    closes = np.asarray(closes, dtype=float)
    rets = np.diff(np.log(closes))
    n = len(closes)
    start = max(1, n - config.BACKTEST_WINDOW)
    signals = []
    for t in range(start, n):
        hist = closes[:t]
        r = np.diff(np.log(hist))
        mu = r.mean()
        sig = 1 if mu > 0 else -1
        fwd = rets[t] if t + horizon_days <= len(rets) else None
        if fwd is not None:
            signals.append((sig, fwd))
    if len(signals) < 20:
        return None
    sig_arr = np.array([s for s, _ in signals])
    fwd_arr = np.array([f for _, f in signals])
    hit = float((np.sign(sig_arr) == np.sign(fwd_arr)).mean())
    strat_ret = sig_arr * fwd_arr
    sharpe = float(strat_ret.mean() / (strat_ret.std() + 1e-12) * np.sqrt(252))
    mdd = _max_drawdown(np.cumprod(1 + strat_ret))
    return {"hit_rate": hit, "sharpe": sharpe, "max_drawdown": mdd, "samples": len(signals)}


def _max_drawdown(equity):
    peak = np.maximum.accumulate(equity)
    dd = equity / peak - 1.0
    return float(dd.min())
