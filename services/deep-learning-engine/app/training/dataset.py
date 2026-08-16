import numpy as np
import pandas as pd

EPS = 1e-10

FEATURE_NAMES = [
    "log_return",
    "rsi14",
    "macd",
    "macd_signal",
    "bb_pos",
    "atr14",
    "mom5",
    "mom10",
    "vol_z20",
    "ma10_pos",
    "ma20_pos",
    "ma60_pos",
    "range_pos20",
    "dow_sin",
    "dow_cos",
    "dom_sin",
    "dom_cos",
    "ewma_vol",
    "hl_range",
    "vol_chg",
    "ret_lag1",
    "ret_lag2",
    "ret_lag3",
    "ret_lag5",
    "ret_lag10",
    "regime_0",
    "regime_1",
    "regime_2",
]

REGIME_IDX = [25, 26, 27]


def _rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / (loss + EPS)
    return 100.0 - 100.0 / (1.0 + rs)


def compute_features(closes, highs, lows, volumes, dates, regime_probs=None):
    close = pd.Series(closes, dtype=float)
    high = pd.Series(highs, dtype=float)
    low = pd.Series(lows, dtype=float)
    vol = pd.Series(volumes, dtype=float)
    ret = np.log(close).diff()
    df = pd.DataFrame(index=close.index)
    df["log_return"] = ret.fillna(0.0)
    df["rsi14"] = _rsi(close).fillna(50.0)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    df["macd"] = macd.fillna(0.0)
    df["macd_signal"] = (macd.ewm(span=9, adjust=False).mean()).fillna(0.0)
    ma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    bb_upper = ma20 + 2 * std20
    bb_lower = ma20 - 2 * std20
    df["bb_pos"] = ((close - bb_lower) / (bb_upper - bb_lower + EPS)).fillna(0.5)
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    df["atr14"] = (tr.ewm(alpha=1 / 14, adjust=False).mean()).fillna(0.0)
    df["mom5"] = ret.rolling(5).sum().fillna(0.0)
    df["mom10"] = ret.rolling(10).sum().fillna(0.0)
    vol_ma = vol.rolling(20).mean()
    vol_std = vol.rolling(20).std()
    df["vol_z20"] = ((vol - vol_ma) / (vol_std + EPS)).fillna(0.0)
    for n in (10, 20, 60):
        ma = close.rolling(n).mean()
        df[f"ma{n}_pos"] = ((close - ma) / (ma + EPS)).fillna(0.0)
    high20 = high.rolling(20).max()
    low20 = low.rolling(20).min()
    df["range_pos20"] = ((close - low20) / (high20 - low20 + EPS)).fillna(0.5)
    dt_index = pd.to_datetime(pd.Series(dates))
    dow = dt_index.dt.dayofweek.astype(float)
    dom = dt_index.dt.day.astype(float)
    df["dow_sin"] = np.sin(2 * np.pi * dow / 7)
    df["dow_cos"] = np.cos(2 * np.pi * dow / 7)
    df["dom_sin"] = np.sin(2 * np.pi * dom / 30)
    df["dom_cos"] = np.cos(2 * np.pi * dom / 30)
    df["ewma_vol"] = (np.abs(ret).ewm(span=10, adjust=False).mean()).fillna(0.0)
    df["hl_range"] = ((high - low) / (close + EPS)).fillna(0.0)
    df["vol_chg"] = vol.pct_change().fillna(0.0)
    for lag in (1, 2, 3, 5, 10):
        df[f"ret_lag{lag}"] = ret.shift(lag).fillna(0.0)
    if regime_probs is not None:
        arr = np.asarray(regime_probs, dtype=float)
        if arr.ndim == 2 and arr.shape[0] == len(close):
            for k in range(3):
                df[f"regime_{k}"] = arr[:, k]
        else:
            for k in range(3):
                df[f"regime_{k}"] = 0.0
    else:
        for k in range(3):
            df[f"regime_{k}"] = 0.0
    return df[FEATURE_NAMES].fillna(0.0)


def build_targets(ret, horizon):
    cum = np.cumsum(np.asarray(ret, dtype=float))
    n = len(cum)
    out = np.full((n, horizon), np.nan)
    for k in range(1, horizon + 1):
        y = np.full(n, np.nan)
        y[: n - k] = cum[k:] - cum[: n - k]
        out[:, k - 1] = y
    return out


def make_sequence_windows(features, targets, seq_len):
    n = len(features)
    X, Y = [], []
    for t in range(seq_len - 1, n):
        x = features[t - seq_len + 1 : t + 1]
        y = targets[t]
        if not np.isnan(y).any():
            X.append(x)
            Y.append(y)
    return np.asarray(X, dtype=np.float32), np.asarray(Y, dtype=np.float32)


def make_tabular_windows(features, targets):
    n = len(features)
    X, Y = [], []
    for t in range(n - 1):
        y = targets[t]
        if not np.isnan(y).any():
            X.append(features[t])
            Y.append(y)
    return np.asarray(X, dtype=np.float32), np.asarray(Y, dtype=np.float32)


def regime_label(features_row):
    probs = features_row[REGIME_IDX]
    if not np.isfinite(probs).any() or np.max(probs) <= 0:
        return None
    return int(np.argmax(probs))
