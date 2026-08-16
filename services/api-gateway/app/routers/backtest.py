import httpx
from fastapi import APIRouter, HTTPException

from .. import config

router = APIRouter(prefix="/api", tags=["backtest"])


@router.get("/backtest")
def backtests(symbol: str):
    with httpx.Client(timeout=30) as client:
        resp = client.get(
            f"{config.STORAGE_URL}/backtests",
            params={"symbol": symbol, "limit": 20},
        )
        if resp.status_code != 200:
            raise HTTPException(502, "Depolama servisine ulaşılamadı")
    return resp.json()
