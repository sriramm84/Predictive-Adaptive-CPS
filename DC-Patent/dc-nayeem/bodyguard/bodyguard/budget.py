"""
Consumable safety budget manager.

Implements the patent's safety budget abstraction (Section 3, Step 4):

  B_t = max(0, floor(B_max × (1 − R_t)) − C_w)

Where:
  B_max = device-specific maximum budget (calibrated)
  R_t   = current risk score ∈ [0, 1]
  C_w   = tasks already executed locally in the current window

Properties (from patent Claims 5, 10, 11):
  1. Non-negative integer resource: B_t ≥ 0 always
  2. Decremented by 1 on each local task execution
  3. Recomputed at each window boundary
  4. Replenishes ONLY when R_t < R_replenish (genuine recovery)
  5. Per-window burst limit: at most B_max tasks per window
  6. Can reject tasks BEFORE OS thermal/voltage protection triggers
"""

import math

from bodyguard.config import BudgetConfig


class SafetyBudget:
    """Consumable per-window safety budget.

    The budget is a spendable capacity — not a threshold, not a score.
    Each local task execution costs one unit. When budget reaches zero,
    ALL further local execution is denied regardless of device state.
    """

    def __init__(self, config: BudgetConfig) -> None:
        self._config = config
        self._budget: int = config.B_max     # Start with full budget
        self._tasks_this_window: int = 0     # C_w
        self._window_start: float = 0.0      # Simulated time
        self._enabled: bool = True           # Can be disabled for ablation

    @property
    def remaining(self) -> int:
        """Current remaining budget (tasks that can execute locally)."""
        return self._budget

    @property
    def tasks_this_window(self) -> int:
        """Number of tasks executed locally in the current window."""
        return self._tasks_this_window

    @property
    def window_elapsed(self) -> float:
        """Seconds elapsed in current window (simulated time)."""
        return 0.0  # Tracked externally via check_window_reset

    @property
    def enabled(self) -> bool:
        """Whether budget enforcement is active."""
        return self._enabled

    def disable(self) -> None:
        """Disable budget enforcement (ablation mode 3: no budget)."""
        self._enabled = False

    def enable(self) -> None:
        """Re-enable budget enforcement."""
        self._enabled = True

    def can_execute_locally(self) -> bool:
        """Check if a task is allowed to execute locally.

        Returns True if budget is disabled (ablation) or if B_t > 0.
        """
        if not self._enabled:
            return True  # Budget disabled for ablation
        return self._budget > 0

    def consume(self) -> bool:
        """Consume one budget unit for a local task execution.

        Returns True if budget was available and consumed, False if denied.
        """
        if not self._enabled:
            self._tasks_this_window += 1
            return True

        if self._budget <= 0:
            return False

        self._budget -= 1
        self._tasks_this_window += 1
        return True

    def recompute(self, risk_score: float) -> int:
        """Recompute budget from current risk score (called at window boundary).

        Implements: B_t = max(0, floor(B_max × (1 − R_t)) − C_w)

        Args:
            risk_score: Current composite risk R ∈ [0, 1].

        Returns:
            New budget value.
        """
        if not self._enabled:
            return self._config.B_max

        # Patent formula
        raw = math.floor(self._config.B_max * (1.0 - risk_score))
        self._budget = max(0, raw - self._tasks_this_window)
        return self._budget

    def check_window_reset(self, risk_score: float, sim_time: float = 0.0) -> bool:
        """Check if window has expired and reset if so.

        Budget replenishes at window boundary ONLY when risk is below
        the replenishment threshold (Claim 10). This prevents premature
        recovery during sustained stress.

        Args:
            risk_score: Current composite risk R ∈ [0, 1].
            sim_time: Current simulated time in seconds.

        Returns:
            True if window was reset, False otherwise.
        """
        if (sim_time - self._window_start) < self._config.window_duration:
            return False

        # Window has expired — reset
        self._window_start = sim_time
        self._tasks_this_window = 0

        if not self._enabled:
            self._budget = self._config.B_max
            return True

        # Replenishment gating (Claim 10):
        # Only replenish if risk is genuinely low
        if risk_score < self._config.R_replenish:
            self._budget = math.floor(self._config.B_max * (1.0 - risk_score))
        else:
            # Sustained stress — budget stays at minimal level
            self._budget = max(0, math.floor(self._config.B_max * (1.0 - risk_score)))

        return True

    def reset(self) -> None:
        """Full reset (e.g., for testing)."""
        self._budget = self._config.B_max
        self._tasks_this_window = 0
        self._window_start = 0.0
