import json

import redis.asyncio as aioredis

from . import config


async def stream_job_ws(websocket, job_id):
    await websocket.accept()
    client = aioredis.from_url(config.REDIS_URL, decode_responses=True)
    pubsub = client.pubsub()
    await pubsub.subscribe(f"job:{job_id}")
    state = await client.hgetall(f"jobstate:{job_id}")
    if state and state.get("state") == "finished":
        await websocket.send_text(
            json.dumps({"stage": "tamamlandi", "progress": 100, "message": "Tahmin tamamlandı", "payload": json.loads(state.get("result", "null"))})
        )
        await websocket.close()
        await pubsub.unsubscribe()
        await client.aclose()
        return
    try:
        async for msg in pubsub.listen():
            if msg["type"] != "message":
                continue
            await websocket.send_text(msg["data"])
    except Exception:
        pass
    finally:
        await pubsub.unsubscribe()
        await client.aclose()
