import asyncio
from typing import TypedDict


class TrackedTurn(TypedDict):
    index: int
    turn: dict


class TurnTracker:
    turns: dict[int, TrackedTurn] = dict()

    _sleep_period = 0.05
    next_idx = 0
    _max_turns = 100

    def insert_turn(self, turn: dict) -> None:
        # Append event
        self.turns[self.next_idx] = TrackedTurn(index=self.next_idx, turn=turn)

        # Update _next_index and remove old turns
        idx = self.next_idx - self._max_turns
        if idx in self.turns:
            del self.turns[idx]
        self.next_idx += 1

    async def get_turn(self, index: int) -> TrackedTurn:
        while self.next_idx <= index:
            await asyncio.sleep(self._sleep_period)
        return self.turns[index]
