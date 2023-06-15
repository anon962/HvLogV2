import asyncio
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass
class PubSub(Generic[T]):
    event_data: T = None
    event = asyncio.Event()

    def publish(self, data: T) -> None:
        self.event_data = data
        self.event.set()
        self.event.clear()

    async def subscribe(self) -> T:
        await self.event.wait()
        return self.event_data
