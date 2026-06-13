import asyncio
from typing import Set

class EventBroker:
    def __init__(self):
        self.queues: Set[asyncio.Queue] = set()

    async def broadcast(self, message: str):
        for q in self.queues:
            await q.put(message)

    async def subscribe(self) -> asyncio.Queue:
        q = asyncio.Queue()
        self.queues.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        if q in self.queues:
            self.queues.remove(q)

# Global broker for the FastAPI instance
broker = EventBroker()
