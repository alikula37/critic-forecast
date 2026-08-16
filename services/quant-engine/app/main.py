from fastapi import FastAPI
from pydantic import BaseModel

from .simulation import scenarios
from .strategies import backtester

app = FastAPI(title="Quant Engine", version="1.0.0")


class Point(BaseModel):
    t: str
    o: float
    h: float
    l: float
    c: float
    v: float


class AnalyzeRequest(BaseModel):
    symbol: str
    interval: str = "1d"
    horizon: int = 30
    points: list[Point]


class ConePoint(BaseModel):
    date: str
    p10: float | None = None
    p50: float | None = None
    p90: float | None = None


class BacktestRequest(BaseModel):
    symbol: str
    interval: str = "1d"
    strategy_id: str
    params: dict = {}
    points: list[Point]
    cones: list[ConePoint] = []
    regimes: dict = {}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    result = scenarios.build_result(req.symbol, req.interval, req.horizon, req.points)
    return result


@app.post("/backtest")
def backtest(req: BacktestRequest):
    return backtester.run_backtest(
        req.symbol,
        req.interval,
        req.strategy_id,
        req.params,
        [p.model_dump() for p in req.points],
        [c.model_dump() for c in req.cones],
        req.regimes,
    )
