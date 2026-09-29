"""
Task admission controller with dual-gate routing.

Implements the patent's per-task admission logic (Section 3, Step 5; Claim 9):

  DUAL-GATE ADMISSION:
    Gate 1 (STATE): Device state determines WHICH tasks are eligible
      - SAFE:      all tasks
      - WARNING:   only lightweight tasks (weight < threshold)
      - CRITICAL:  only mission-critical tasks
      - EMERGENCY: no local tasks; self-throttle with sleep

    Gate 2 (BUDGET): Remaining budget determines WHETHER the eligible task
      actually runs locally:
      - B_t > 0:  local execution permitted
      - B_t = 0:  offload or reject, regardless of state

  The state gate controls WHICH tasks; the budget gate controls HOW MANY.
"""

import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from bodyguard.budget import SafetyBudget
from bodyguard.state_machine import DeviceState


class TaskPriority(Enum):
    """Task priority classification."""
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"  # Mission-critical, must attempt local if possible


class RoutingDecision(Enum):
    """Where a task should be executed."""
    LOCAL = "LOCAL"          # Execute on this device
    OFFLOAD = "OFFLOAD"     # Send to cloud compute
    THROTTLE = "THROTTLE"   # Execute locally with sleep interleaving
    REJECT = "REJECT"       # Cannot process (cloud down + emergency)


@dataclass
class Task:
    """A computational task submitted for admission."""

    task_id: str
    """Unique identifier for this task."""

    weight: float
    """Computational weight (0.0 = trivial, 1.0 = heavy).
    Determines CPU load contribution and state-gate eligibility."""

    priority: TaskPriority
    """Priority classification for state-gate filtering."""

    cpu_load: float = 0.0
    """Estimated CPU load increase (%) when executing. Derived from weight."""

    estimated_duration: float = 5.0
    """Estimated execution duration in seconds."""

    def __post_init__(self) -> None:
        # Auto-estimate CPU load from weight if not specified
        if self.cpu_load <= 0:
            self.cpu_load = self.weight * 40.0  # 0.0→0%, 1.0→40% per task


@dataclass
class AdmissionResult:
    """Complete admission decision with rationale."""

    task: Task
    decision: RoutingDecision
    device_state: DeviceState
    risk_score: float
    budget_remaining: int
    reason: str
    timestamp: float


class AdmissionController:
    """Dual-gate task admission controller.

    Combines state-based eligibility (Gate 1) with budget-based capacity
    (Gate 2) to produce per-task routing decisions.
    """

    # Tasks with weight below this threshold are considered "lightweight"
    LIGHTWEIGHT_THRESHOLD: float = 0.3

    def __init__(
        self,
        budget: SafetyBudget,
        cloud_available: bool = True,
    ) -> None:
        self._budget = budget
        self._cloud_available = cloud_available
        self._total_local = 0
        self._total_offloaded = 0
        self._total_throttled = 0
        self._total_rejected = 0

    @property
    def cloud_available(self) -> bool:
        return self._cloud_available

    @cloud_available.setter
    def cloud_available(self, value: bool) -> None:
        self._cloud_available = value

    @property
    def stats(self) -> dict:
        """Routing statistics."""
        total = (self._total_local + self._total_offloaded +
                 self._total_throttled + self._total_rejected)
        return {
            "total": total,
            "local": self._total_local,
            "offloaded": self._total_offloaded,
            "throttled": self._total_throttled,
            "rejected": self._total_rejected,
            "offload_ratio": self._total_offloaded / total if total > 0 else 0.0,
        }

    def admit(
        self,
        task: Task,
        device_state: DeviceState,
        risk_score: float,
        disable_budget: bool = False,  # For ablation mode 3
    ) -> AdmissionResult:
        """Determine routing for an incoming task.

        Args:
            task: The task requesting admission.
            device_state: Current device health state.
            risk_score: Current composite risk score R ∈ [0, 1].
            disable_budget: If True, skip budget gate (ablation mode).

        Returns:
            AdmissionResult with decision and rationale.
        """

        # --- EMERGENCY: self-throttle, no normal local execution ---
        if device_state == DeviceState.EMERGENCY:
            decision, reason = self._handle_emergency(task)

        # --- GATE 1: State gate (which tasks are eligible) ---
        elif device_state == DeviceState.CRITICAL:
            decision, reason = self._gate_critical(task)

        elif device_state == DeviceState.WARNING:
            decision, reason = self._gate_warning(task)

        else:  # SAFE
            decision, reason = self._gate_safe(task)

        # --- GATE 2: Budget gate (how many tasks can run locally) ---
        # Only applies if Gate 1 approved local execution
        if decision == RoutingDecision.LOCAL and not disable_budget:
            if not self._budget.can_execute_locally():
                # Budget exhausted — override to offload
                if self._cloud_available:
                    decision = RoutingDecision.OFFLOAD
                    reason = f"Budget exhausted (B=0), offloading. Original: {reason}"
                else:
                    decision = RoutingDecision.REJECT
                    reason = f"Budget exhausted (B=0), cloud unavailable. Original: {reason}"
            else:
                # Consume budget unit
                self._budget.consume()

        # --- Track statistics ---
        self._track(decision)

        return AdmissionResult(
            task=task,
            decision=decision,
            device_state=device_state,
            risk_score=risk_score,
            budget_remaining=self._budget.remaining,
            reason=reason,
            timestamp=time.time(),
        )

    def _gate_safe(self, task: Task) -> tuple:
        """SAFE state: all tasks eligible for local execution."""
        return RoutingDecision.LOCAL, f"SAFE: all tasks permitted (weight={task.weight:.2f})"

    def _gate_warning(self, task: Task) -> tuple:
        """WARNING state: only lightweight tasks run locally."""
        if task.weight < self.LIGHTWEIGHT_THRESHOLD:
            return RoutingDecision.LOCAL, (
                f"WARNING: lightweight task permitted "
                f"(weight={task.weight:.2f} < {self.LIGHTWEIGHT_THRESHOLD})"
            )
        elif self._cloud_available:
            return RoutingDecision.OFFLOAD, (
                f"WARNING: heavy task offloaded "
                f"(weight={task.weight:.2f} >= {self.LIGHTWEIGHT_THRESHOLD})"
            )
        else:
            # No cloud, but WARNING — can still run locally with caution
            return RoutingDecision.LOCAL, (
                f"WARNING: heavy task forced local (no cloud), "
                f"weight={task.weight:.2f}"
            )

    def _gate_critical(self, task: Task) -> tuple:
        """CRITICAL state: only mission-critical tasks run locally."""
        if task.priority == TaskPriority.CRITICAL:
            return RoutingDecision.LOCAL, (
                f"CRITICAL: mission-critical task permitted locally "
                f"(priority={task.priority.value})"
            )
        elif self._cloud_available:
            return RoutingDecision.OFFLOAD, (
                f"CRITICAL: non-critical task offloaded "
                f"(priority={task.priority.value})"
            )
        else:
            return RoutingDecision.REJECT, (
                f"CRITICAL: non-critical task rejected (no cloud), "
                f"priority={task.priority.value}"
            )

    def _handle_emergency(self, task: Task) -> tuple:
        """EMERGENCY: self-throttle mode."""
        if task.priority == TaskPriority.CRITICAL:
            return RoutingDecision.THROTTLE, (
                "EMERGENCY: mission-critical task throttled with sleep interleaving"
            )
        else:
            return RoutingDecision.REJECT, (
                f"EMERGENCY: task rejected (priority={task.priority.value})"
            )

    def _track(self, decision: RoutingDecision) -> None:
        """Update routing statistics."""
        if decision == RoutingDecision.LOCAL:
            self._total_local += 1
        elif decision == RoutingDecision.OFFLOAD:
            self._total_offloaded += 1
        elif decision == RoutingDecision.THROTTLE:
            self._total_throttled += 1
        elif decision == RoutingDecision.REJECT:
            self._total_rejected += 1
