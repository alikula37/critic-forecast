import numpy as np

from .. import config
from ..volatility.garch import fit_garch


def simulate(closes, horizon, dates, garch_res=None, n_paths=None):
    n_paths = n_paths or config.MC_N_PATHS
    tail_df = config.MC_TAIL_DF
    rng = np.random.default_rng(42)
    closes = np.asarray(closes, dtype=float)
    rets = np.diff(np.log(closes))
    rets = rets[~np.isnan(rets)]

    from ..regimes.hmm import detect_regimes

    regime = detect_regimes(closes, dates)
    mu_d = 0.0
    for k, prob in regime["state_probs"].items():
        mu_d += prob * regime["state_means"].get(k, 0.0)
    mu_d = float(np.clip(mu_d, -0.05, 0.05))

    if garch_res is None:
        garch_res = fit_garch(closes, horizon)
    sigma = np.asarray(garch_res["sigma_daily"], dtype=float)
    sigma = np.clip(sigma, 1e-5, None)

    z = rng.standard_t(tail_df, size=(n_paths, horizon))
    z /= np.sqrt(tail_df / (tail_df - 2.0))

    s0 = closes[-1]
    drift = mu_d - 0.5 * sigma**2
    log_increments = drift[None, :] + sigma[None, :] * z
    log_paths = np.cumsum(log_increments, axis=1)
    paths = s0 * np.exp(log_paths)

    p10, p50, p90 = [], [], []
    for t in range(horizon):
        col = paths[:, t]
        p10.append(float(np.quantile(col, 0.10)))
        p50.append(float(np.quantile(col, 0.50)))
        p90.append(float(np.quantile(col, 0.90)))

    finals = paths[:, -1]
    up_probability = float((finals > s0).mean())
    bins, edges = np.histogram(finals, bins=50)
    q5 = np.quantile(finals, 0.05)
    return {
        "p10": p10,
        "p50": p50,
        "p90": p90,
        "up_probability": up_probability,
        "distribution": {"edges": edges.tolist(), "counts": [int(x) for x in bins]},
        "stats": {
            "mean_final": float(finals.mean()),
            "median_final": float(np.median(finals)),
            "std_final": float(finals.std()),
            "var_1": float(np.quantile(finals, 0.01)),
            "var_5": float(q5),
            "cvar_5": float(finals[finals <= q5].mean()) if (finals <= q5).any() else float(q5),
        },
        "mu_drift": mu_d,
    }
