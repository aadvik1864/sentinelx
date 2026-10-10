import asyncio
import json
import logging
from collections import defaultdict
from contextlib import suppress

import redis as sync_redis
import redis.asyncio as redis
from fastapi import APIRouter, WebSocket
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.security import authenticate_token, limiter

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()


class Broker:
    def __init__(self):
        self.clients = defaultdict(set)
        self.loop = None
        self.task = None
        self.redis = (
            sync_redis.Redis.from_url(
                settings.redis_url, socket_connect_timeout=2, socket_timeout=2
            )
            if settings.redis_url
            else None
        )

    async def start(self):
        self.loop = asyncio.get_running_loop()
        if self.redis:
            self.task = asyncio.create_task(self.listen())

    async def stop(self):
        if self.task:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
        self.clients.clear()
        self.loop = None

    async def listen(self):
        while True:
            try:
                async with redis.from_url(settings.redis_url) as client, client.pubsub() as pubsub:
                    await pubsub.subscribe("sentinelx:updates")
                    async for message in pubsub.listen():
                        if message["type"] == "message":
                            await self.dispatch(json.loads(message["data"]))
            except (redis.RedisError, OSError):
                logger.warning("Redis stream unavailable; reconnecting")
                await asyncio.sleep(2)

    async def dispatch(self, message):
        for queue in tuple(self.clients[message["channel"]]):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(message)

    def publish(self, channel: str, kind: str, data: dict):
        message = {"channel": channel, "type": kind, "data": data}
        if self.redis:
            try:
                self.redis.publish("sentinelx:updates", json.dumps(message))
                return
            except sync_redis.RedisError:
                logger.warning("Redis publication failed; clients should reconcile through REST")
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self.dispatch(message), self.loop)


broker = Broker()


def validate(token, channel):
    with SessionLocal() as db:
        user = authenticate_token(token, db)
        if channel == "events" and user.role == "VIEWER":
            raise ValueError("Not authorized")
        return user.id


@router.websocket("/ws/{channel}")
async def stream(socket: WebSocket, channel: str):
    if (
        channel not in {"events", "alerts", "incidents"}
        or socket.headers.get("origin") not in settings.origins
    ):
        await socket.close(code=1008)
        return
    queue = asyncio.Queue(maxsize=100)
    try:
        limiter.check("ws:" + (socket.client.host if socket.client else "unknown"), 30)
        await socket.accept()
        auth = await asyncio.wait_for(socket.receive_json(), timeout=10)
        token = auth.get("token", "")
        await run_in_threadpool(validate, token, channel)
        broker.clients[channel].add(queue)
        await socket.send_json({"type": "connected", "data": {"channel": channel}})
        while True:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=20)
            except TimeoutError:
                message = {"type": "heartbeat", "data": {}}
            # Recheck expiration, role changes, and logout for every update/heartbeat.
            await run_in_threadpool(validate, token, channel)
            await socket.send_json(message)
    except Exception:
        with suppress(Exception):
            await socket.close(code=1008)
    finally:
        broker.clients[channel].discard(queue)
