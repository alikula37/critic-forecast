import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import config
from ..jobs import enqueue, find_cached, run_backtest, run_backfill, run_forecast

router = APIRouter(prefix="/api", tags=["forecast"])


class ForecastRequest(BaseModel):
    symbol: str
    interval: str = config.DEFAULT_INTERVAL
    horizon: int = config.DEFAULT_HORIZON
    force: bool = False


class BackfillRequest(BaseModel):
    symbol: str
    interval: str = config.DEFAULT_INTERVAL
    horizon: int = config.DEFAULT_HORIZON
    days: int = config.BACKFILL_DAYS
    end_offset: int = 0
    skip_wf: bool = True


@router.post("/forecast/backfill")
def create_backfill(req: BackfillRequest):
    if not 5 <= req.horizon <= 120:
        raise HTTPException(422, "Horizon 5-120 arası olmalı")
    if not 1 <= req.days <= 250:
        raise HTTPException(422, "Gün sayısı 1-250 arası olmalı")
    if not 0 <= req.end_offset <= 250:
        raise HTTPException(422, "end_offset 0-250 arası olmalı")
    job_id = enqueue(run_backfill, req.model_dump(), timeout=21600)
    return {"job_id": job_id, "cached": False}


@router.post("/forecast")
def create_forecast(req: ForecastRequest):
    if not 5 <= req.horizon <= 120:
        raise HTTPException(422, "Horizon 5-120 arası olmalı")
    if not req.force:
        cached = find_cached(req.symbol, req.interval, req.horizon)
        if cached is not None:
            return {"job_id": cached["job_id"], "cached": True, "result": cached["result"]}
    job_id = enqueue(run_forecast, req.model_dump(exclude={"force"}))
    return {"job_id": job_id, "cached": False}


@router.get("/forecast/latest")
def latest_forecast(symbol: str, horizon: int | None = None, interval: str = config.DEFAULT_INTERVAL):
    with httpx.Client(timeout=30) as client:
        resp = client.get(
            f"{config.STORAGE_URL}/results",
            params={"symbol": symbol, "interval": interval, "horizon": horizon, "limit": 1},
        )
        if resp.status_code != 200:
            raise HTTPException(502, "Depolama servisine ulaşılamadı")
        rows = resp.json()
    if not rows:
        raise HTTPException(404, "Bu sembol için kayıtlı tahmin yok")
    row = rows[0]
    row["payload"]["created_at"] = row["created_at"]
    return row["payload"]


@router.get("/forecast/history")
def forecast_history(symbol: str, limit: int = 20):
    with httpx.Client(timeout=30) as client:
        resp = client.get(
            f"{config.STORAGE_URL}/forecasts/history",
            params={"symbol": symbol, "limit": limit},
        )
        if resp.status_code != 200:
            raise HTTPException(502, "Depolama servisine ulaşılamadı")
    return resp.json()


@router.get("/forecast/{job_id}")
def get_forecast(job_id: str):
    from ..routers.assets import job_status

    try:
        return job_status(job_id)
    except HTTPException:
        pass
    with httpx.Client(timeout=30) as client:
        resp = client.get(f"{config.STORAGE_URL}/results/{job_id}")
        if resp.status_code == 200:
            row = resp.json()
            row["payload"]["created_at"] = row["created_at"]
            return {
                "job_id": job_id,
                "state": "finished",
                "stage": "tamamlandi",
                "progress": "100",
                "result": row["payload"],
            }
    raise HTTPException(404, "Job bulunamadı")


@router.post("/backtest/run")
def create_backtest(req: ForecastRequest):
    job_id = enqueue(run_backtest, req.model_dump())
    return {"job_id": job_id}
