from classes.aggregators.base import Aggregator
from classes.models import BattleReport


class TotalGains(Aggregator):
    def update(self, report: BattleReport):
        prev = self.state.get("active_report")
        assert prev is None or prev == report.pk

        self.state.setdefault("active", dict())
        for k, v in report.data.items():
            self.state["active"][k] = v

    @classmethod
    def create(cls) -> "TotalGains":
        self = super(cls).create()
        self.state["battle_count"] = 0
        return self
