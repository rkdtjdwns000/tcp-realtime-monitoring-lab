"""Serve the dashboard and forward Redis events to WebSocket clients."""

import asyncio
import os
from pathlib import Path

import redis.asyncio as redis
from redis.exceptions import RedisError
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse


REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
INSTANCE_NAME = os.getenv("INSTANCE_NAME", "web")
EVENT_CHANNEL = "tcp-probe-events"
INDEX_FILE = Path(__file__).parent / "static" / "index.html"

app = FastAPI(title="TCP Realtime Monitoring Lab")


@app.get("/")
async def index():
    return FileResponse(INDEX_FILE)


@app.get("/health")
async def health():
    client = redis.from_url(REDIS_URL)
    try:
        await client.ping()
    except RedisError as error:
        raise HTTPException(status_code=503, detail="Redis unavailable") from error
    finally:
        await client.aclose()
    return {"status": "ok"}


@app.websocket("/ws")
async def websocket_events(websocket: WebSocket):
    await websocket.accept()
    print(f"[WEB {INSTANCE_NAME}] WebSocket connected", flush=True)
    client = redis.from_url(REDIS_URL, decode_responses=True)
    pubsub = client.pubsub()
    tasks = []

    async def forward_events():
        async for message in pubsub.listen():
            if message["type"] == "message":
                await websocket.send_text(message["data"])
                print(f"[WEB {INSTANCE_NAME}] Event forwarded: {message['data']}", flush=True)

    async def watch_disconnect():
        # 메시지가 없는 동안에도 브라우저 종료를 감지한다.
        while True:
            await websocket.receive_text()

    try:
        # 각 브라우저가 구독한다. 두 앱 인스턴스 모두 같은 채널을 볼 수 있다.
        await pubsub.subscribe(EVENT_CHANNEL)
        tasks = [
            asyncio.create_task(forward_events()),
            asyncio.create_task(watch_disconnect()),
        ]
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    except WebSocketDisconnect:
        pass
    except RedisError:
        try:
            await websocket.close(code=1011, reason="Redis unavailable")
        except (WebSocketDisconnect, RuntimeError):
            pass
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        try:
            await pubsub.unsubscribe(EVENT_CHANNEL)
        except RedisError:
            pass
        finally:
            await pubsub.aclose()
            await client.aclose()
        print(f"[WEB {INSTANCE_NAME}] WebSocket closed", flush=True)
