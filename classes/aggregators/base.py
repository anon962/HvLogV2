from dataclasses import dataclass
from typing import Any, Optional

from classes.models import BattleReport, Summary
from classes.pubsub import PubSub


@dataclass
class Aggregator(PubSub[Summary]):
    """
    Assumptions:
        - update() is called after a battle report is updated
        - finalize() is called after a battle ends
        - all update()s and the following finalize() call are all for the same report
        - BattleReports are supplied in chronological order

        @todo update() should auto-call finalize if report is different
    """

    def update(self, report: BattleReport):
        pass

    def finalize(self) -> None:
        self.save()

    @classmethod
    def create(cls) -> "Aggregator":
        pass

    @classmethod
    def get(cls) -> Optional["Aggregator"]:
        pass

    def save(self) -> None:
        self.event_data.save()

    @property
    def state(self) -> dict[str, Any]:
        return self.event_data.state

    @property
    def data(self) -> dict[str, Any]:
        return self.event_data.data
