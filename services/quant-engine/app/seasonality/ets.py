import numpy as np
from statsmodels.tsa.holtwinters import ExponentialSmoothing


def _trend_model(x, horizon):
    try:
        model = ExponentialSmoothing(
            x, trend="add", damped_trend=True, seasonal=None
        ).fit(optimized=True)
        return np.asarray(model.forecast(horizon), dtype=float)
    except Exception:
        k = len(x)
        poly = np.polyfit(np.arange(k), x, 1)
        return poly[0] * np.arange(k, k + horizon) + poly[1]


def ets_forecast(closes, horizon, recent_window=300):
    closes = np.asarray(closes, dtype=float)
    logp = np.log(closes)
    x = logp[~np.isnan(logp)][-recent_window:]
    fc_log = _trend_model(x, horizon)
    resid = x - np.mean(x)
    resid_std = float(np.std(resid)) if len(resid) > 5 else 0.0

    p50 = np.exp(fc_log)
    spread = resid_std * 1.28 * np.sqrt(np.arange(1, horizon + 1))
    p10 = p50 * np.exp(-spread)
    p90 = p50 * np.exp(spread)

    slope = fc_log[-1] - fc_log[0] if horizon > 1 else fc_log[0] - x[-1]
    up_probability = float(1.0 / (1.0 + np.exp(-slope / (max(resid_std, 1e-9) * 2))))

    return {
        "p10": p10.tolist(),
        "p50": p50.tolist(),
        "p90": p90.tolist(),
        "up_probability": up_probability,
        "resid_std": resid_std,
        "slope": float(slope),
    }
