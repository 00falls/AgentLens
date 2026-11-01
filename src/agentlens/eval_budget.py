"""An explicit evaluation campaign budget, inactive for ordinary application calls."""

import json
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from agentlens.config import ROOT


class BudgetStop(RuntimeError):
    pass


@dataclass
class EvaluationBudget:
    limit: Decimal
    spent: Decimal = Decimal(0)
    calls: int = 0
    unknown_usage: bool = False

    def before_call(self, messages, tool_catalog, max_output_tokens):
        pricing = json.loads((ROOT / "configs/observability/pricing.json").read_text())
        now = datetime.now(UTC)
        if not (
            datetime.fromisoformat(pricing["valid_from"])
            <= now
            < datetime.fromisoformat(pricing["valid_until"])
        ):
            raise BudgetStop("Pricing is outside its verified time window")
        if self.unknown_usage:
            raise BudgetStop("Previous model usage or pricing is unknown")
        # UTF-8 byte count plus per-message framing is a conservative estimate, not a bill cap.
        payload = {"messages": [m.model_dump(mode="json") for m in messages], "tools": tool_catalog}
        upper_input = len(json.dumps(payload, ensure_ascii=False).encode()) + 512 * len(messages)
        rates = pricing["models"]["deepseek-flash"]
        reserve = (
            Decimal(upper_input) * Decimal(str(rates["cache_miss"]))
            + Decimal(max_output_tokens) * Decimal(str(rates["output"]))
        ) / 1_000_000
        if self.spent + reserve > self.limit:
            raise BudgetStop("Next model call exceeds the batch's conservative budget reserve")

    def observe(self, billing):
        self.calls += 1
        if billing["cost"] is None:
            self.unknown_usage = True
            raise BudgetStop("Completed call has unknown usage or pricing; stopping further calls")
        self.spent += Decimal(billing["cost"])


active_budget: ContextVar[EvaluationBudget | None] = ContextVar("evaluation_budget", default=None)
