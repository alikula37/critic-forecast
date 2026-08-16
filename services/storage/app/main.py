import json
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from .db import get_conn

app = FastAPI(title="Critic Forecast Storage", version="1.0.0")


class OHLCVPoint(BaseModel):
    t: str
    o: float
    h: float
    l: float
    c: float
    v: float


class OHLCVBatch(BaseModel):
    symbol: str
    interval: str
    points: list[OHLCVPoint]


class ForecastStore(BaseModel):
    job_id: str
    symbol: str
    interval: str
    horizon: int
    up_probability: float
    points: list[dict]
    critic: dict
    model_points: list[dict]
    last_close: float | None = None
    backfilled: bool = False


class ModelScore(BaseModel):
    symbol: str
    model_id: str
    score: float
    weight: float
    metrics: dict


class BacktestStore(BaseModel):
    job_id: str
    symbol: str
    summary: dict


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/data/ohlcv")
def upsert_ohlcv(batch: OHLCVBatch):
    conn = get_conn()
    rows = [
        (
            batch.symbol,
            datetime.fromisoformat(p.t.replace("Z", "+00:00")),
            batch.interval,
            p.o,
            p.h,
            p.l,
            p.c,
            p.v,
        )
        for p in batch.points
    ]
    conn.executemany(
        """
        INSERT INTO ohlcv (symbol, ts, interval, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (symbol, ts, interval) DO UPDATE SET
            open = excluded.open, high = excluded.high,
            low = excluded.low, close = excluded.close,
            volume = excluded.volume
        """,
        rows,
    )
    return {"inserted": len(rows)}


@app.get("/data/ohlcv")
def get_ohlcv(
    symbol: str,
    interval: str = "1d",
    start: str | None = None,
    end: str | None = None,
):
    conn = get_conn()
    sql = "SELECT ts, open, high, low, close, volume FROM ohlcv WHERE symbol = ? AND interval = ?"
    params: list = [symbol, interval]
    if start:
        sql += " AND ts >= ?"
        params.append(datetime.fromisoformat(start))
    if end:
        sql += " AND ts <= ?"
        params.append(datetime.fromisoformat(end))
    sql += " ORDER BY ts"
    rows = conn.execute(sql, params).fetchall()
    return [
        {"t": r[0].isoformat(), "o": r[1], "h": r[2], "l": r[3], "c": r[4], "v": r[5]}
        for r in rows
    ]


@app.get("/data/ohlcv/latest")
def get_latest(symbol: str, interval: str = "1d", limit: int = Query(500, le=5000)):
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT ts, open, high, low, close, volume FROM ohlcv
        WHERE symbol = ? AND interval = ?
        ORDER BY ts DESC LIMIT ?
        """,
        [symbol, interval, limit],
    ).fetchall()
    rows = rows[::-1]
    return [
        {"t": r[0].isoformat(), "o": r[1], "h": r[2], "l": r[3], "c": r[4], "v": r[5]}
        for r in rows
    ]


@app.post("/forecasts")
def store_forecast(fc: ForecastStore):
    conn = get_conn()
    last_close = fc.last_close
    if last_close is None and fc.points:
        first_date = datetime.fromisoformat(fc.points[0]["date"].replace("Z", "+00:00"))
        row = conn.execute(
            """
            SELECT close FROM ohlcv
            WHERE symbol = ? AND interval = ? AND ts < ?
            ORDER BY ts DESC LIMIT 1
            """,
            [fc.symbol, fc.interval, first_date],
        ).fetchone()
        last_close = row[0] if row else None
    conn.execute(
        """
        INSERT INTO ensemble_forecasts
            (job_id, symbol, interval, horizon, created_at, up_probability, points, critic, last_close, backfilled)
        VALUES (?, ?, ?, ?, current_timestamp, ?, ?, ?, ?, ?)
        ON CONFLICT (job_id) DO UPDATE SET
            up_probability = excluded.up_probability,
            points = excluded.points, critic = excluded.critic,
            last_close = excluded.last_close, backfilled = excluded.backfilled
        """,
        [
            fc.job_id,
            fc.symbol,
            fc.interval,
            fc.horizon,
            fc.up_probability,
            json.dumps(fc.points),
            json.dumps(fc.critic),
            last_close,
            fc.backfilled,
        ],
    )
    conn.execute("DELETE FROM forecast_points WHERE job_id = ?", [fc.job_id])
    for mp in fc.model_points:
        conn.executemany(
            """
            INSERT INTO forecast_points (job_id, model_id, ts, p10, p50, p90)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    fc.job_id,
                    mp["model_id"],
                    datetime.fromisoformat(p["date"].replace("Z", "+00:00")),
                    p.get("p10"),
                    p.get("p50"),
                    p.get("p90"),
                )
                for p in mp["points"]
            ],
        )
    return {"stored": fc.job_id}


@app.get("/forecasts/history")
def forecast_history(symbol: str, limit: int = Query(20, le=200)):
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT job_id, symbol, interval, horizon, created_at, up_probability, points, critic
        FROM ensemble_forecasts WHERE symbol = ? AND (backfilled IS NULL OR backfilled = FALSE)
        ORDER BY created_at DESC LIMIT ?
        """,
        [symbol, limit],
    ).fetchall()
    out = []
    for r in rows:
        realized = []
        for p in json.loads(r[6] or "[]"):
            hit = conn.execute(
                "SELECT close FROM ohlcv WHERE symbol = ? AND interval = ? AND ts = ?",
                [symbol, r[2], datetime.fromisoformat(p["date"].replace("Z", "+00:00"))],
            ).fetchone()
            realized.append(
                {"date": p["date"], "p50": p["p50"], "actual": hit[0] if hit else None}
            )
        out.append(
            {
                "job_id": r[0],
                "symbol": r[1],
                "interval": r[2],
                "horizon": r[3],
                "created_at": r[4].isoformat(),
                "up_probability": r[5],
                "realized": realized,
            }
        )
    return out


@app.post("/forecasts/backfill_last_close")
def backfill_last_close(symbol: str | None = None, interval: str | None = None):
    conn = get_conn()
    sql = "SELECT job_id, symbol, interval, points FROM ensemble_forecasts WHERE last_close IS NULL"
    params: list = []
    if symbol:
        sql += " AND symbol = ?"
        params.append(symbol)
    if interval:
        sql += " AND interval = ?"
        params.append(interval)
    rows = conn.execute(sql, params).fetchall()
    updated = 0
    for r in rows:
        jid, sym, iv, points = r
        pts = json.loads(points or "[]")
        if not pts:
            continue
        first_date = datetime.fromisoformat(pts[0]["date"].replace("Z", "+00:00"))
        row = conn.execute(
            """
            SELECT close FROM ohlcv
            WHERE symbol = ? AND interval = ? AND ts < ?
            ORDER BY ts DESC LIMIT 1
            """,
            [sym, iv, first_date],
        ).fetchone()
        if row is None:
            continue
        conn.execute(
            "UPDATE ensemble_forecasts SET last_close = ? WHERE job_id = ?",
            [row[0], jid],
        )
        updated += 1
    return {"updated": updated, "scanned": len(rows)}


@app.get("/forecasts/model_points")
def model_points(symbol: str, limit: int = Query(500, le=50000)):
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT fp.job_id, fp.model_id, fp.ts, fp.p10, fp.p50, fp.p90, ef.last_close
        FROM forecast_points fp
        JOIN ensemble_forecasts ef ON fp.job_id = ef.job_id
        WHERE ef.symbol = ? ORDER BY fp.ts DESC LIMIT ?
        """,
        [symbol, limit],
    ).fetchall()
    return [
        {
            "job_id": r[0],
            "model_id": r[1],
            "ts": r[2].isoformat(),
            "p10": r[3],
            "p50": r[4],
            "p90": r[5],
            "last_close": r[6],
        }
        for r in rows
    ]


@app.post("/model-scores")
def store_scores(scores: list[ModelScore]):
    conn = get_conn()
    conn.executemany(
        """
        INSERT INTO model_scores (symbol, model_id, as_of, score, weight, metrics)
        VALUES (?, ?, current_timestamp, ?, ?, ?)
        """,
        [(s.symbol, s.model_id, s.score, s.weight, json.dumps(s.metrics)) for s in scores],
    )
    return {"stored": len(scores)}


@app.get("/model-scores")
def get_scores(symbol: str, limit: int = Query(200, le=1000)):
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT model_id, as_of, score, weight, metrics FROM model_scores
        WHERE symbol = ? ORDER BY as_of DESC LIMIT ?
        """,
        [symbol, limit],
    ).fetchall()
    return [
        {
            "model_id": r[0],
            "as_of": r[1].isoformat(),
            "score": r[2],
            "weight": r[3],
            "metrics": json.loads(r[4] or "{}"),
        }
        for r in rows
    ]


@app.post("/backtests")
def store_backtest(bt: BacktestStore):
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO backtests (job_id, symbol, created_at, summary)
        VALUES (?, ?, current_timestamp, ?)
        """,
        [bt.job_id, bt.symbol, json.dumps(bt.summary)],
    )
    return {"stored": bt.job_id}


@app.get("/backtests")
def get_backtests(symbol: str, limit: int = Query(20, le=200)):
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT job_id, created_at, summary FROM backtests
        WHERE symbol = ? ORDER BY created_at DESC LIMIT ?
        """,
        [symbol, limit],
    ).fetchall()
    return [
        {
            "job_id": r[0],
            "created_at": r[1].isoformat(),
            "summary": json.loads(r[2] or "{}"),
        }
        for r in rows
    ]


class ResultStore(BaseModel):
    job_id: str
    symbol: str
    interval: str
    horizon: int
    payload: dict
    backfilled: bool = False


@app.post("/results")
def store_result(rs: ResultStore):
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO results (job_id, symbol, interval, horizon, created_at, payload, backfilled)
        VALUES (?, ?, ?, ?, current_timestamp, ?, ?)
        ON CONFLICT (job_id) DO UPDATE SET
            symbol = excluded.symbol, interval = excluded.interval,
            horizon = excluded.horizon, payload = excluded.payload,
            backfilled = excluded.backfilled
        """,
        [rs.job_id, rs.symbol, rs.interval, rs.horizon, json.dumps(rs.payload, default=str), rs.backfilled],
    )
    return {"stored": rs.job_id}


@app.get("/results")
def get_results(
    symbol: str,
    interval: str = "1d",
    horizon: int | None = None,
    limit: int = Query(1, le=500),
    include_backfilled: bool = False,
):
    conn = get_conn()
    sql = "SELECT job_id, created_at, payload FROM results WHERE symbol = ? AND interval = ?"
    params: list = [symbol, interval]
    if horizon:
        sql += " AND horizon = ?"
        params.append(horizon)
    if not include_backfilled:
        sql += " AND (backfilled IS NULL OR backfilled = FALSE)"
    sql += " ORDER BY created_at DESC, job_id DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [
        {"job_id": r[0], "created_at": r[1].isoformat(), "payload": json.loads(r[2] or "{}")}
        for r in rows
    ]


@app.get("/results/{job_id}")
def get_result(job_id: str):
    conn = get_conn()
    row = conn.execute(
        "SELECT job_id, created_at, payload FROM results WHERE job_id = ?",
        [job_id],
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Sonuç bulunamadı")
    return {"job_id": row[0], "created_at": row[1].isoformat(), "payload": json.loads(row[2] or "{}")}


class StrategyBacktestStore(BaseModel):
    job_id: str
    symbol: str
    interval: str
    strategy_id: str
    params: dict
    metrics: dict
    equity: list[dict]
    trades: list[dict]
    benchmark: list[dict] = []


@app.post("/strategies/backtests")
def store_strategy_backtest(sb: StrategyBacktestStore):
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO strategy_backtests
            (job_id, symbol, interval, strategy_id, created_at, params, metrics, equity, trades, benchmark)
        VALUES (?, ?, ?, ?, current_timestamp, ?, ?, ?, ?, ?)
        ON CONFLICT (job_id) DO UPDATE SET
            symbol = excluded.symbol, interval = excluded.interval,
            strategy_id = excluded.strategy_id, params = excluded.params,
            metrics = excluded.metrics, equity = excluded.equity,
            trades = excluded.trades, benchmark = excluded.benchmark
        """,
        [
            sb.job_id,
            sb.symbol,
            sb.interval,
            sb.strategy_id,
            json.dumps(sb.params, default=str),
            json.dumps(sb.metrics, default=str),
            json.dumps(sb.equity, default=str),
            json.dumps(sb.trades, default=str),
            json.dumps(sb.benchmark, default=str),
        ],
    )
    return {"stored": sb.job_id}


@app.get("/strategies/backtests")
def get_strategy_backtests(symbol: str, interval: str = "1d", limit: int = Query(20, le=100)):
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT job_id, strategy_id, created_at, params, metrics, equity, trades, benchmark
        FROM strategy_backtests
        WHERE symbol = ? AND interval = ?
        ORDER BY created_at DESC LIMIT ?
        """,
        [symbol, interval, limit],
    ).fetchall()
    return [
        {
            "job_id": r[0],
            "strategy_id": r[1],
            "created_at": r[2].isoformat(),
            "params": json.loads(r[3] or "{}"),
            "metrics": json.loads(r[4] or "{}"),
            "equity": json.loads(r[5] or "[]"),
            "trades": json.loads(r[6] or "[]"),
            "benchmark": json.loads(r[7] or "[]"),
        }
        for r in rows
    ]


@app.get("/strategies/backtests/{job_id}")
def get_strategy_backtest(job_id: str):
    conn = get_conn()
    row = conn.execute(
        """
        SELECT job_id, strategy_id, created_at, params, metrics, equity, trades, benchmark
        FROM strategy_backtests WHERE job_id = ?
        """,
        [job_id],
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Backtest bulunamadı")
    return {
        "job_id": row[0],
        "strategy_id": row[1],
        "created_at": row[2].isoformat(),
        "params": json.loads(row[3] or "{}"),
        "metrics": json.loads(row[4] or "{}"),
        "equity": json.loads(row[5] or "[]"),
        "trades": json.loads(row[6] or "[]"),
        "benchmark": json.loads(row[7] or "[]"),
    }
