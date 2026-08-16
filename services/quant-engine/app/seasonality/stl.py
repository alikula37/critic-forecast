import numpy as np
from scipy.signal import find_peaks
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.seasonal import STL

from .. import config


def _detect_cycles(x, max_cycles=3):
    x = x - np.nanmean(x)
    n = len(x)
    if n < 8:
        return []
    fft = np.fft.rfft(x * np.hanning(n))
    power = np.abs(fft) ** 2
    freqs = np.fft.rfftfreq(n, 1)
    freqs = freqs[1:]
    power = power[1:]
    valid = freqs > 0
    periods = (1.0 / freqs[valid]).astype(int)
    power = power[valid]
    mask = periods <= n // 2
    periods, power = periods[mask], power[mask]
    if len(periods) == 0:
        return []
    peaks, _ = find_peaks(power)
    if len(peaks) == 0:
        peaks = [int(np.argmax(power))]
    order = peaks[np.argsort(power[peaks])[::-1]][:max_cycles]
    total = power.sum() + 1e-12
    return [
        {"period": int(periods[p]), "power": float(power[p] / total)}
        for p in order
    ]


def _forecast_trend(trend, horizon, recent_window=180):
    x = trend[~np.isnan(trend)]
    if len(x) < 20:
        return np.full(horizon, float(np.nanmean(x)))
    x = x[-recent_window:]
    try:
        model = ExponentialSmoothing(
            x, trend="add", damped_trend=True, seasonal=None
        ).fit(optimized=True)
        fc = model.forecast(horizon)
        return np.asarray(fc, dtype=float)
    except Exception:
        k = len(x)
        x_fit = np.arange(k)
        poly = np.polyfit(x_fit, x, 1)
        t_future = np.arange(k, k + horizon)
        return poly[0] * t_future + poly[1]


def stl_decompose(closes, horizon):
    closes = np.asarray(closes, dtype=float)
    dates_future = None
    logp = np.log(closes)
    period = config.STL_PERIOD_WEEK
    seasonal = np.zeros(len(logp))
    trend = logp
    resid = np.zeros(len(logp))
    cycles = []
    try:
        stl = STL(logp, period=period, robust=True)
        res = stl.fit()
        trend = res.trend
        seasonal = res.seasonal
        resid = res.resid
        cycles = _detect_cycles(logp - trend)
    except Exception:
        pass

    trend_fc = _forecast_trend(trend, horizon)
    seasonal_ext = _extend_seasonal(seasonal, period, horizon)
    resid_std = float(np.nanstd(resid)) if len(resid) > 5 else 0.0

    p50 = np.exp(trend_fc + seasonal_ext)
    spread = resid_std * 1.28 * np.sqrt(np.arange(1, horizon + 1))
    p10 = p50 * np.exp(-spread)
    p90 = p50 * np.exp(spread)

    last_trend = trend_fc[-1] - trend_fc[0] if horizon > 1 else trend_fc[0] - trend[-1]
    up_probability = float(1.0 / (1.0 + np.exp(-last_trend / (np.maximum(resid_std, 1e-9) * 2))))

    hist = {
        "trend": np.exp(trend).tolist(),
        "seasonal": np.exp(seasonal).tolist(),
        "resid": np.exp(resid).tolist(),
    }
    return {
        "components": hist,
        "cycles": cycles,
        "period": period,
        "resid_std": resid_std,
        "up_probability": up_probability,
        "p50": p50.tolist(),
        "p10": p10.tolist(),
        "p90": p90.tolist(),
    }


def _extend_seasonal(seasonal, period, horizon):
    n = len(seasonal)
    if n < period * 2:
        return np.zeros(horizon)
    last = seasonal[-(period * 2):]
    last = last[~np.isnan(last)]
    if len(last) < period:
        return np.zeros(horizon)
    pattern = last[-period:]
    reps = int(np.ceil(horizon / period))
    ext = np.tile(pattern, reps)[:horizon]
    return ext
