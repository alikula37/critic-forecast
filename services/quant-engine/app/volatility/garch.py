import numpy as np
from arch import arch_model


def fit_garch(closes, horizon):
    closes = np.asarray(closes, dtype=float)
    rets = np.diff(np.log(closes))
    rets = rets[~np.isnan(rets)]
    if len(rets) < 60:
        rets = rets[-400:]
    try:
        model = arch_model(
            rets * 100.0, vol="GARCH", p=1, q=1, dist="studentst", rescale=False
        )
        res = model.fit(disp="off", show_warning=False)
        fc = res.forecast(horizon=horizon, reindex=False)
        var_path = fc.variance.values[-1] / 100.0**2
        params = {
            "omega": float(res.params.get("omega", 0.0)),
            "alpha": float(res.params.get("alpha[1]", 0.0)),
            "beta": float(res.params.get("beta[1]", 0.0)),
            "nu": float(res.params.get("nu", 6.0)),
        }
        return {
            "sigma_daily": np.sqrt(var_path).tolist(),
            "params": params,
            "annualized_vol": float(np.sqrt(np.mean(var_path)) * np.sqrt(252)),
        }
    except Exception:
        sigma = np.full(horizon, float(np.std(rets)) + 1e-10)
        return {
            "sigma_daily": sigma.tolist(),
            "params": {"omega": 0.0, "alpha": 0.0, "beta": 0.0, "nu": 6.0},
            "annualized_vol": float(np.std(rets) * np.sqrt(252)),
        }
