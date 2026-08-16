import numpy as np
import pandas as pd

from .. import config

_MAX_SIZE_SAFE = 0.999


def _series(points):
    idx = pd.to_datetime([p["t"][:10] for p in points])
    return pd.Series([p["c"] for p in points], index=idx, dtype=float)


def _entries_exits_from_position(position):
    held = position > 0
    entries = held & ~held.shift(1, fill_value=False)
    exits = ~held & held.shift(1, fill_value=False)
    return entries.fillna(False), exits.fillna(False)


def _position_from_signals(close, cone_df, strategy_id):
    position = pd.Series(0.0, index=close.index, dtype=float)
    if strategy_id == "cone_trend":
        sig = (cone_df["p50"] > close).astype(float)
        position = sig.fillna(0.0)
    elif strategy_id == "regime_switch":
        reg = cone_df["regime"]
        position = reg.isin(["yükseliş", "boğa"]).astype(float).fillna(0.0)
    return position


def _apply_monthly_trade_limit(entries, exits, max_trades):
    if not max_trades or max_trades <= 0:
        return entries, exits
    per_month = entries.groupby(entries.index.to_period("M")).cumsum()
    exceed = (per_month > max_trades) & entries
    exit_dates = exits.index[exits]
    for d in exceed.index[exceed]:
        later = exit_dates[exit_dates > d]
        if len(later):
            exits.loc[later[0]] = False
        entries.loc[d] = False
    return entries, exits


def _fee_params(params):
    mode = str(params.get("fee_mode", "flat"))
    if mode == "per_trade":
        return {"fees": 0.0, "fixed_fees": float(params.get("fixed_fee", 0.0))}
    return {"fees": float(params.get("fees", config.STRATEGY_FEES)), "fixed_fees": 0.0}


def _slippage_price(close, entries, exits, slippage):
    if not slippage or slippage <= 0:
        return close
    adj = close.copy()
    adj = adj.where(~entries, adj * (1 + slippage))
    adj = adj.where(~exits, adj * (1 - slippage))
    return adj


def _alpha_beta(equity, close):
    try:
        r = equity.pct_change().dropna()
        b = close.pct_change().dropna()
        r, b = r.align(b, join="inner")
        r = r[r > -1]
        b = b.reindex(r.index)
        var_b = float(np.var(b.values))
        if var_b <= 0 or len(r) < 10:
            return None, None
        beta = float(np.cov(r.values, b.values)[0, 1] / var_b)
        alpha = (float(np.mean(r.values)) - beta * float(np.mean(b.values))) * 252
        return round(alpha, 4), round(beta, 4)
    except Exception:
        return None, None


def _summarize(pf, close, position, params, entries, exits):
    trades = pf.trades
    n = int(_scalar(trades.count()))
    hold = close.iloc[-1] / close.iloc[0] - 1
    alpha, beta = _alpha_beta(pf.value(), close)
    metrics = {
        "total_return": _f(pf.total_return()),
        "benchmark_return": _f(hold),
        "sharpe": _f(pf.sharpe_ratio()),
        "sortino": _f(pf.sortino_ratio()),
        "calmar": _f(pf.calmar_ratio()),
        "max_drawdown": _f(pf.max_drawdown()),
        "win_rate": _f(_scalar(trades.win_rate())) if n else None,
        "profit_factor": _f(_scalar(trades.profit_factor())) if n else None,
        "expectancy": _f(_scalar(trades.expectancy())) if n else None,
        "n_trades": n,
        "coverage": _f(float((position > 0).mean())) if len(position) else None,
        "fees": params.get("fees", config.STRATEGY_FEES),
        "fee_mode": params.get("fee_mode", "flat"),
        "slippage_bps": params.get("slippage_bps", 0),
        "max_position": params.get("max_position", 1.0),
        "alpha": alpha,
        "beta": beta,
    }
    equity = [{"date": str(d.date()), "value": round(float(v), 4)} for d, v in pf.value().items()]
    bench_eq = [
        {"date": str(d.date()), "value": round(float(100 * c / close.iloc[0]), 4)}
        for d, c in close.items()
    ]
    trade_rows = []
    if n:
        try:
            rec = trades.records_readable
            for r in rec.tail(60).to_dict("records"):
                entry = r.get("Entry Timestamp") or r.get("Entry Time") or r.get("entry_time")
                exit_t = r.get("Exit Timestamp") or r.get("Exit Time") or r.get("exit_time")
                ret = r.get("Return") or r.get("return")
                trade_rows.append(
                    {
                        "entry": _date(entry),
                        "exit": _date(exit_t),
                        "return": _f(ret),
                    }
                )
        except Exception:
            trade_rows = []
    return {"metrics": metrics, "equity": equity, "benchmark": bench_eq, "trades": trade_rows}


def _date(v):
    if v is None:
        return None
    try:
        return str(v.date())
    except Exception:
        return str(v)


def _scalar(v):
    try:
        if hasattr(v, "__len__") and len(v) > 0:
            return v[0]
    except Exception:
        pass
    return v


def _f(v):
    try:
        f = float(v)
        if f != f or f == float("inf") or f == float("-inf"):
            return None
        return round(f, 4)
    except Exception:
        return None


def run_backtest(symbol, interval, strategy_id, params, points, cones, regimes):
    close = _series(points)
    cone_df = pd.DataFrame(cones)
    if len(cone_df) == 0:
        return {"symbol": symbol, "strategy_id": strategy_id, "metrics": None, "equity": [], "benchmark": [], "trades": [], "reason": "Kayıtlı tahmin konisi yok"}
    cone_df["date"] = pd.to_datetime(cone_df["date"])
    cone_df = cone_df.set_index("date").sort_index()
    cone_df = cone_df[~cone_df.index.duplicated(keep="first")]
    cone_df = cone_df.reindex(close.index)
    cone_df["regime"] = [regimes.get(d.strftime("%Y-%m-%d")) for d in cone_df.index]

    if strategy_id == "cone_breakout":
        entries = (close > cone_df["p90"]) & cone_df["p90"].notna()
        exits = (close < cone_df["p10"]) & cone_df["p10"].notna()
        position = pd.Series(0.0, index=close.index, dtype=float)
    else:
        position = _position_from_signals(close, cone_df, strategy_id)
        entries, exits = _entries_exits_from_position(position)

    max_position = min(float(params.get("max_position", 1.0)), _MAX_SIZE_SAFE)
    entries = entries.fillna(False)
    exits = exits.fillna(False)
    entries, exits = _apply_monthly_trade_limit(entries, exits, int(params.get("max_trades_per_month", 0) or 0))
    fee_params = _fee_params(params)
    slippage = float(params.get("slippage_bps", 0) or 0) / 10000.0
    exec_price = _slippage_price(close, entries, exits, slippage)

    pf = _vbt().Portfolio.from_signals(
        close,
        entries,
        exits,
        size=max_position,
        size_type="percent",
        price=exec_price,
        fees=fee_params["fees"],
        fixed_fees=fee_params["fixed_fees"],
        freq="1D",
        direction="longonly",
    )
    return {**_summarize(pf, close, position, params, entries, exits), "symbol": symbol, "strategy_id": strategy_id}


_vbt_mod = None


def _vbt():
    global _vbt_mod
    if _vbt_mod is None:
        import vectorbt as vbt

        _vbt_mod = vbt
    return _vbt_mod
