import numpy as np

from .. import config


def _clip01(x):
    return float(np.clip(x, 0.0, 1.0))


def skill_from_performance(perf, price_scale, ret_scale):
    if not perf or perf.get("samples", 0) == 0:
        return 0.5
    hit = _clip01(perf.get("hit_rate", 0.5))
    if "rmse" in perf:
        rmse_norm = 1.0 / (1.0 + abs(perf["rmse"]) / max(price_scale, 1e-12))
    else:
        rmse_norm = 0.0
    if "pinball_10" in perf and "pinball_90" in perf:
        pb = (abs(perf["pinball_10"]) + abs(perf["pinball_90"])) / 2.0
        pinball_norm = 1.0 / (1.0 + pb / max(ret_scale, 1e-12))
    else:
        pinball_norm = 0.0
    sharpe = _clip01(0.5 + perf.get("sharpe", 0.0) / 4.0)
    skill = 0.40 * hit + 0.30 * rmse_norm + 0.15 * pinball_norm + 0.15 * sharpe
    return _clip01(skill)


def live_score_from_history(history):
    if not history:
        return None
    entries = history[:12]
    total_w = 0.0
    acc = 0.0
    w = 1.0
    for e in entries:
        acc += w * e.get("score", 0.5)
        total_w += w
        w *= config.LIVE_DECAY
    return _clip01(acc / max(total_w, 1e-9))


def combine(live, skill):
    if live is None:
        return _clip01(0.8 * skill + 0.1)
    return _clip01(config.LIVE_WEIGHT * live + config.BACKTEST_WEIGHT * skill)


def regime_factor(perf, current_regime):
    if not perf:
        return 1.0
    errs = perf.get("regime_errors") or {}
    bucket = {"boğa": "trend_up", "ayı": "trend_down"}.get(current_regime)
    if bucket is None or bucket not in errs:
        return 1.0
    rmse_all = abs(perf.get("rmse", 0.0)) + 1e-12
    rmse_reg = abs(errs[bucket].get("rmse", 0.0)) + 1e-12
    if rmse_reg <= rmse_all:
        return 1.15
    return 0.85


def confidence(score, consensus):
    return _clip01(0.5 * score + 0.5 * consensus)
