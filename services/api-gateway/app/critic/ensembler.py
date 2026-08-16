import numpy as np

from . import scorer
from .divergence import consensus_from_divergence, divergence_matrix
from .qra import isotonic_fix


def softmax_weights(scores, temperature):
    s = np.asarray(scores, dtype=float) / max(temperature, 1e-6)
    s = s - s.max()
    e = np.exp(s)
    return e / e.sum()


def meta_adjust(weights, rmse_norms):
    arr = np.asarray(rmse_norms, dtype=float)
    mean = arr.mean()
    if mean <= 1e-12:
        return weights
    factor = np.clip(1.0 - 0.5 * (arr - mean) / mean, 0.7, 1.3)
    out = weights * factor
    return out / out.sum()


def blend_quantiles(models_meta, weights, qra_weights=None):
    dates = [p["date"] for p in models_meta[0]["points"]]
    qra = None
    if qra_weights and len(qra_weights["weights"]) == 3:
        n_m = len(models_meta)
        qra = {
            q: np.asarray(qra_weights["weights"][q], dtype=float)
            for q in ("p10", "p50", "p90")
        }
        if all(len(v) == n_m for v in qra.values()):
            for q in qra:
                s = qra[q].sum()
                if s > 1e-12:
                    qra[q] = qra[q] / s
        else:
            qra = None
    out = []
    for i, d in enumerate(dates):
        if qra is not None:
            p10 = sum(qra["p10"][j] * m["points"][i]["p10"] for j, m in enumerate(models_meta))
            p50 = sum(qra["p50"][j] * m["points"][i]["p50"] for j, m in enumerate(models_meta))
            p90 = sum(qra["p90"][j] * m["points"][i]["p90"] for j, m in enumerate(models_meta))
        else:
            p10 = sum(w * m["points"][i]["p10"] for w, m in zip(weights, models_meta))
            p50 = sum(w * m["points"][i]["p50"] for w, m in zip(weights, models_meta))
            p90 = sum(w * m["points"][i]["p90"] for w, m in zip(weights, models_meta))
        p10, p50, p90 = isotonic_fix(p10, p50, p90)
        out.append({"date": d, "p10": p10, "p50": p50, "p90": p90})
    up = sum(w * m["up_probability"] for w, m in zip(weights, models_meta))
    return out, float(np.clip(up, 0.01, 0.99))


def build_critic_state(model_inputs, price_scale, ret_scale, current_regime, live_histories, temperature, qra_weights=None, realized_perf=None):
    scores, skills, confs, factors, divs, rmse_norms = [], [], [], [], [], []
    for i, m in enumerate(model_inputs):
        skill = scorer.skill_from_performance(m["performance"], price_scale, ret_scale)
        realized = None
        if realized_perf is not None:
            for rp in realized_perf.get("models", []):
                if rp["model_id"] == m["model_id"] and rp["metrics"] and rp["metrics"]["samples"] >= 5:
                    realized = rp["metrics"]
                    break
        live = scorer.live_score_from_history(live_histories.get(m["model_id"], []))
        if realized is not None:
            live = scorer.combine(live, scorer.skill_from_performance(realized, price_scale, ret_scale))
        score = scorer.combine(live, skill)
        factor = scorer.regime_factor(m["performance"], current_regime)
        rmse_norms.append(abs((m["performance"] or {}).get("rmse", 0.0)) / max(price_scale, 1e-12))
        skills.append(skill)
        scores.append(score)
        factors.append(factor)
    p50_curves = [np.asarray([p["p50"] for p in m["points"]], dtype=float) for m in model_inputs]
    divs, mean_div = divergence_matrix(p50_curves, price_scale)
    consensus = consensus_from_divergence(mean_div)

    raw_weights = softmax_weights(scores, temperature)
    adjusted = meta_adjust(raw_weights, rmse_norms)
    adjusted = adjusted * np.asarray(factors)
    weights = adjusted / adjusted.sum()
    confs = [scorer.confidence(s, consensus) for s in scores]

    ensemble_points, ensemble_up = blend_quantiles(model_inputs, weights, qra_weights)
    ensemble_confidence = float(np.clip(0.5 * float(np.mean(scores)) + 0.5 * consensus, 0.05, 0.98))

    model_states = []
    for i, m in enumerate(model_inputs):
        model_states.append(
            {
                "model_id": m["model_id"],
                "model_name": m["model_name"],
                "line": m["line"],
                "score": float(scores[i]),
                "weight": float(weights[i]),
                "confidence": float(confs[i]),
                "divergence": float(divs[i]),
                "regime_factor": float(factors[i]),
                "up_probability": float(m["up_probability"]),
                "performance": m["performance"],
            }
        )
    model_states.sort(key=lambda x: x["weight"], reverse=True)

    return {
        "models": model_states,
        "ensemble": {
            "points": ensemble_points,
            "up_probability": ensemble_up,
            "confidence": ensemble_confidence,
        },
        "consensus": float(consensus),
        "mean_divergence": float(mean_div),
        "current_regime": current_regime,
        "temperature": temperature,
        "qra": {
            "used": qra_weights is not None,
            "n": qra_weights.get("n", 0) if qra_weights else 0,
        },
        "live_weight": 0.6,
        "backtest_weight": 0.4,
    }
