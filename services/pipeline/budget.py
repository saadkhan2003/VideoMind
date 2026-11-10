from __future__ import annotations


class BudgetExceeded(RuntimeError):
    def __init__(self, spent: float, limit: float) -> None:
        self.spent = spent
        self.limit = limit
        super().__init__(
            f"VLM caption budget reached: spent ${spent:.6f} of ${limit:.2f}. No further caption calls."
        )


class UsdBudget:
    """Running total of real model-reported USD. Cache hits are not added."""

    def __init__(self, max_usd: float) -> None:
        if max_usd <= 0:
            raise ValueError("--max-usd must be greater than 0")
        self.max_usd = float(max_usd)
        self.spent = 0.0

    @property
    def exhausted(self) -> bool:
        return self.spent >= self.max_usd

    def note(self, cost_usd: float) -> None:
        self.spent += max(0.0, float(cost_usd))

    def ensure_open(self) -> None:
        if self.exhausted:
            raise BudgetExceeded(self.spent, self.max_usd)
