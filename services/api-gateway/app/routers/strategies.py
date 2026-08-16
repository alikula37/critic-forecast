import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import config
from ..jobs import enqueue, run_strategy_backtest

router = APIRouter(prefix="/api/strategies", tags=["strategies"])

PARAM_DEFS = {
    "signal_source": {
        "label": "Sinyal Kaynağı",
        "type": "select",
        "options": [
            "ensemble",
            "bilstm_attention",
            "xgboost_quantile",
            "lightgbm_quantile",
            "monte_carlo",
            "ets_baseline",
            "stl_seasonality",
        ],
        "default": "ensemble",
    },
    "fees": {"label": "Komisyon (%)", "default": 0.001, "min": 0.0, "max": 0.01, "step": 0.0005},
    "fee_mode": {"label": "Komisyon Modu", "type": "select", "options": ["flat", "per_trade"], "default": "flat"},
    "fixed_fee": {"label": "Sabit İşlem Ücreti", "default": 0.0, "min": 0.0, "max": 50.0, "step": 0.5},
    "slippage_bps": {"label": "Slippage (baz puan)", "default": 0, "min": 0, "max": 200, "step": 5},
    "max_position": {"label": "Max Pozisyon (sermaye oranı)", "default": 1.0, "min": 0.1, "max": 1.0, "step": 0.05},
    "max_trades_per_month": {"label": "Aylık Max İşlem (0=sınırsız)", "default": 0, "min": 0, "max": 30, "step": 1},
}

CATALOG = [
    {
        "strategy_id": "cone_trend",
        "name": "Koni Trend Takibi",
        "description": "P50 tahmininin fiyatın üzerinde olduğu günlerde pozisyonda kalır (tahmin konisi trendine yatırım).",
        "params": PARAM_DEFS,
    },
    {
        "strategy_id": "cone_breakout",
        "name": "Koni Kırılımı",
        "description": "Fiyat P90'ı yukarı kırınca girer, P10'un altına düşünce çıkar (belirsizlik bandı dışında momentum).",
        "params": PARAM_DEFS,
    },
    {
        "strategy_id": "regime_switch",
        "name": "Rejim Anahtarı",
        "description": "HMM rejimi 'yükseliş' olan tahmin pencerelerinde pozisyonda kalır; düşüş/yatayda çıkar.",
        "params": PARAM_DEFS,
    },
]


class StrategyBacktestRequest(BaseModel):
    symbol: str
    interval: str = config.DEFAULT_INTERVAL
    strategy_id: str
    params: dict = {}


@router.get("")
def catalog():
    return CATALOG


@router.post("/backtest")
def create_strategy_backtest(req: StrategyBacktestRequest):
    if req.strategy_id not in {s["strategy_id"] for s in CATALOG}:
        raise HTTPException(422, "Bilinmeyen strateji")
    job_id = enqueue(run_strategy_backtest, req.model_dump())
    return {"job_id": job_id, "cached": False}


@router.get("/backtests")
def strategy_backtests(symbol: str, interval: str = config.DEFAULT_INTERVAL):
    with httpx.Client(timeout=30) as client:
        resp = client.get(
            f"{config.STORAGE_URL}/strategies/backtests",
            params={"symbol": symbol, "interval": interval, "limit": 50},
        )
        if resp.status_code != 200:
            raise HTTPException(502, "Depolama servisine ulaşılamadı")
    return resp.json()


@router.get("/backtests/{job_id}")
def strategy_backtest(job_id: str):
    with httpx.Client(timeout=30) as client:
        resp = client.get(f"{config.STORAGE_URL}/strategies/backtests/{job_id}")
        if resp.status_code == 200:
            return resp.json()
    raise HTTPException(404, "Backtest bulunamadı")
