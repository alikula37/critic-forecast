import datetime as dt

from .. import config
from ..regimes import hmm
from ..seasonality import ets, stl
from ..simulation import montecarlo
from ..simulation.walkforward import walkforward_perf
from ..volatility import garch


def _future_dates(dates, horizon):
    last = dt.date.fromisoformat(dates[-1][:10])
    out = []
    cur = last
    while len(out) < horizon:
        cur = cur + dt.timedelta(days=1)
        if cur.weekday() < 5:
            out.append(cur.isoformat())
    return out


def _points(dates, p10, p50, p90):
    return [
        {"date": d, "p10": p10[i], "p50": p50[i], "p90": p90[i]}
        for i, d in enumerate(dates)
    ]


def build_result(symbol, interval, horizon, points):
    dates = [p.t for p in points]
    closes = [p.c for p in points]

    regime = hmm.detect_regimes(closes, dates)
    regime_series = hmm.causal_regime_series(closes, dates)
    garch_res = garch.fit_garch(closes, horizon)
    mc = montecarlo.simulate(closes, horizon, dates, garch_res)
    stl_res = stl.stl_decompose(closes, horizon)

    future = _future_dates(dates, horizon)
    mc_perf = walkforward_perf(closes, dates, horizon, "monte_carlo")
    stl_perf = walkforward_perf(closes, dates, horizon, "stl")
    ets_res = ets.ets_forecast(closes, horizon)
    ets_perf = walkforward_perf(closes, dates, horizon, "ets")

    models = [
        {
            "model_id": "monte_carlo",
            "model_name": "Monte Carlo + HMM/GARCH",
            "line": "istatistik",
            "points": _points(future, mc["p10"], mc["p50"], mc["p90"]),
            "up_probability": mc["up_probability"],
            "performance": mc_perf,
            "details": {
                "mu_drift": mc["mu_drift"],
                "annualized_vol": garch_res["annualized_vol"],
                "n_paths": config.MC_N_PATHS,
            },
        },
        {
            "model_id": "stl_seasonality",
            "model_name": "STL Döngüsellik",
            "line": "döngüsellik",
            "points": _points(future, stl_res["p10"], stl_res["p50"], stl_res["p90"]),
            "up_probability": stl_res["up_probability"],
            "performance": stl_perf,
            "details": {
                "cycles": stl_res["cycles"],
                "period": stl_res["period"],
                "resid_std": stl_res["resid_std"],
            },
        },
        {
            "model_id": "ets_baseline",
            "model_name": "ETS Trend (Baseline)",
            "line": "istatistik",
            "points": _points(future, ets_res["p10"], ets_res["p50"], ets_res["p90"]),
            "up_probability": ets_res["up_probability"],
            "performance": ets_perf,
            "details": {
                "slope": ets_res["slope"],
                "resid_std": ets_res["resid_std"],
                "window": 300,
            },
        },
    ]

    return {
        "symbol": symbol,
        "interval": interval,
        "horizon": horizon,
        "regimes": regime,
        "regime_series": regime_series,
        "garch": {
            "sigma_daily": garch_res["sigma_daily"],
            "params": garch_res["params"],
            "annualized_vol": garch_res["annualized_vol"],
        },
        "seasonality": {
            "components": stl_res["components"],
            "cycles": stl_res["cycles"],
        },
        "mc": {
            "distribution": mc["distribution"],
            "stats": mc["stats"],
            "up_probability": mc["up_probability"],
        },
        "models": models,
    }
