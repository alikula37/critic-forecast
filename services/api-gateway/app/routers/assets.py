import json

from fastapi import APIRouter, HTTPException

from .. import config
from ..data import provider
from ..jobs import get_redis

router = APIRouter(prefix="/api/assets", tags=["assets"])


@router.get("")
def list_assets():
    return provider.CATALOG


@router.get("/history")
def history(symbol: str, interval: str = config.DEFAULT_INTERVAL, limit: int = 500):
    try:
        points = provider.get_ohlcv(symbol, interval, limit=min(limit, config.MAX_BARS))
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(502, f"Veri sağlanamadı: {e}")
    return {"symbol": symbol, "interval": interval, "points": points}


@router.get("/job/{job_id}")
def job_status(job_id: str):
    r = get_redis()
    state = r.hgetall(f"jobstate:{job_id}")
    if not state:
        raise HTTPException(404, "Job bulunamadı")
    out = {"job_id": job_id, "state": state.get("state"), "stage": state.get("stage"), "progress": state.get("progress")}
    if state.get("result"):
        out["result"] = json.loads(state["result"])
    return out
