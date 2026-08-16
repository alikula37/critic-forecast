import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .routers import assets, backtest, forecast, models, strategies
from .ws import stream_job_ws

app = FastAPI(title="Critic Forecast API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(assets.router)
app.include_router(forecast.router)
app.include_router(models.router)
app.include_router(backtest.router)
app.include_router(strategies.router)


@app.get("/api/health")
def health():
    status = {}
    for name, url in (
        ("storage", config.STORAGE_URL),
        ("deep_learning", config.DEEP_LEARNING_URL),
        ("quant", config.QUANT_URL),
    ):
        try:
            with httpx.Client(timeout=5) as client:
                resp = client.get(f"{url}/health")
                status[name] = "ok" if resp.status_code == 200 else "down"
        except Exception:
            status[name] = "down"
    try:
        import redis as redislib

        r = redislib.Redis.from_url(config.REDIS_URL)
        status["redis"] = "ok" if r.ping() else "down"
    except Exception:
        status["redis"] = "down"
    return {"status": "ok", "services": status}


@app.websocket("/ws/forecast/{job_id}")
async def ws_forecast(websocket: WebSocket, job_id: str):
    try:
        await stream_job_ws(websocket, job_id)
    except WebSocketDisconnect:
        pass
