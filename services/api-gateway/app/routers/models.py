import httpx
from fastapi import APIRouter, HTTPException

from .. import config
from ..metrics.historical import compute_model_performance

router = APIRouter(prefix="/api", tags=["models"])

REGISTRY = [
    {
        "model_id": "bilstm_attention",
        "model_name": "Bi-LSTM + Attention",
        "line": "derin_ogrenme",
        "description": "Çift yönlü LSTM + additive attention, P10/P50/P90 quantile kafaları, pinball loss.",
        "framework": "PyTorch",
    },
    {
        "model_id": "xgboost_quantile",
        "model_name": "XGBoost (Yön + Quantile)",
        "line": "gradient_boosting",
        "description": "Teknik indikatörler üzerinde yön sınıflandırıcısı ve çok-ufuklu quantile regresörleri.",
        "framework": "XGBoost",
    },
    {
        "model_id": "lightgbm_quantile",
        "model_name": "LightGBM (Yön + Quantile)",
        "line": "gradient_boosting",
        "description": "LightGBM ile yön sınıflandırıcısı ve çok-ufuklu quantile regresörleri; ağaç havuzunu çeşitlendirir.",
        "framework": "LightGBM",
    },
    {
        "model_id": "monte_carlo",
        "model_name": "Monte Carlo + HMM/GARCH",
        "line": "istatistik",
        "description": "HMM rejim drifti + GARCH koşullu volatilite ile 10.000 senaryo simülasyonu.",
        "framework": "hmmlearn / arch",
    },
    {
        "model_id": "ets_baseline",
        "model_name": "ETS Trend (Baseline)",
        "line": "istatistik",
        "description": "Üstel düzleştirme trend modeli; model karşılaştırması için altın standart.",
        "framework": "statsmodels",
    },
    {
        "model_id": "stl_seasonality",
        "model_name": "STL Döngüsellik",
        "line": "döngüsellik",
        "description": "STL ayrıştırması + FFT döngü tespiti; trend ve sezonluk devamlılığı.",
        "framework": "statsmodels",
    },
]


@router.get("/models/registry")
def registry():
    return REGISTRY


@router.get("/models/scores")
def scores(symbol: str):
    with httpx.Client(timeout=30) as client:
        resp = client.get(
            f"{config.STORAGE_URL}/model-scores",
            params={"symbol": symbol, "limit": 200},
        )
        if resp.status_code != 200:
            raise HTTPException(502, "Depolama servisine ulaşılamadı")
        rows = resp.json()
    latest = {}
    for r in rows:
        mid = r["model_id"]
        if mid not in latest:
            latest[mid] = r
    return {"history": rows, "latest": latest}


@router.get("/models/performance")
def performance(symbol: str, interval: str = config.DEFAULT_INTERVAL):
    return compute_model_performance(symbol, interval)
