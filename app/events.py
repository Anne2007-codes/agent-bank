"""In-process pub/sub for live dashboards. Swap for Redis pub/sub when running >1 worker."""
import asyncio
import time
from collections import defaultdict

from fastapi import WebSocket, WebSocketDisconnect


class Bus:
    def __init__(self):
        self.subs = defaultdict(set)
        self.loop = None

    def publish(self, channel: str, event: dict):
        if self.loop is None:
            return
        event = {"ts": time.time(), **event}
        for q in list(self.subs[channel]):
            self.loop.call_soon_threadsafe(q.put_nowait, event)  # safe from worker threads

    def subscribe(self, channel: str) -> asyncio.Queue:
        q = asyncio.Queue()
        self.subs[channel].add(q)
        return q

    def unsubscribe(self, channel: str, q):
        self.subs[channel].discard(q)


bus = Bus()


async def stream_ws(ws: WebSocket, channel: str, replay=None):
    await ws.accept()
    q = bus.subscribe(channel)
    try:
        for ev in replay or []:
            await ws.send_json(ev)
        while True:
            await ws.send_json(await q.get())
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(channel, q)
