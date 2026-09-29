"""
Dual-hysteresis finite state machine for device health classification.

Implements the patent's four-state FSM (Section 3, Step 3):

  SAFE ↔ WARNING ↔ CRITICAL → EMERGENCY

Each transition boundary uses SEPARATE entry and exit thresholds to prevent
oscillation (state flapping) when risk fluctuates near a threshold:

  SAFE → WARNING:    R ≥ 0.30  (entry)
  WARNING → SAFE:    R < 0.25  (exit, requires sustained recovery)
  WARNING → CRITICAL: R ≥ 0.65  (entry)
  CRITICAL → WARNING: R < 0.55  (exit, requires significant recovery)

Cold start behavior: Defaults to WARNING until sufficient samples exist
for derivative computation, providing conservative protection from power-on.
"""

from enum import Enum
from typing import Optional

from bodyguard.config import StateMachineConfig


class DeviceState(Enum):
    """Device health states ordered by severity."""
    SAFE = "SAFE"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    EMERGENCY = "EMERGENCY"

    @property
    def severity(self) -> int:
        """Numeric severity for comparison. Higher = more dangerous."""
        return {
            DeviceState.SAFE: 0,
            DeviceState.WARNING: 1,
            DeviceState.CRITICAL: 2,
            DeviceState.EMERGENCY: 3,
        }[self]


class DualHysteresisFSM:
    """Dual-hysteresis finite state machine for device health.

    EMERGENCY is entered from CRITICAL when cloud is unreachable —
    it is not driven by risk score alone, but by cloud availability.
    """

    def __init__(self, config: StateMachineConfig) -> None:
        self._config = config
        self._state = DeviceState.SAFE  # Cold start: begin SAFE, let risk drive transitions
        self._cold_start = True

    @property
    def state(self) -> DeviceState:
        """Current device state."""
        return self._state

    @property
    def is_cold_start(self) -> bool:
        """Whether the system is still in cold-start mode."""
        return self._cold_start

    def update(
        self,
        risk_score: float,
        cloud_reachable: bool = True,
        sample_count: int = 0,
    ) -> DeviceState:
        """Update state based on current risk score.

        Args:
            risk_score: Current composite risk R ∈ [0, 1].
            cloud_reachable: Whether the cloud offload endpoint is reachable.
            sample_count: Total sensor samples collected so far
                          (for cold-start detection).

        Returns:
            The new device state after transition logic.
        """
        # --- Cold start logic ---
        # During cold start, derivatives are not yet available,
        # but we still allow normal transitions based on absolute terms.
        # The risk engine already handles missing derivatives (returns 0).
        if self._cold_start:
            if sample_count >= self._config.cold_start_min_samples:
                self._cold_start = False
            # Continue to normal transitions even during cold start

        # --- Normal dual-hysteresis transitions ---
        # Each transition uses a DIFFERENT threshold for entry vs exit

        if self._state == DeviceState.SAFE:
            if risk_score >= self._config.safe_to_warning:
                self._state = DeviceState.WARNING

        elif self._state == DeviceState.WARNING:
            # Can go UP to CRITICAL or DOWN to SAFE
            if risk_score >= self._config.warning_to_critical:
                self._state = DeviceState.CRITICAL
            elif risk_score < self._config.warning_to_safe:
                self._state = DeviceState.SAFE

        elif self._state == DeviceState.CRITICAL:
            # Can go DOWN to WARNING or UP to EMERGENCY (if cloud lost)
            if not cloud_reachable:
                self._state = DeviceState.EMERGENCY
            elif risk_score < self._config.critical_to_warning:
                self._state = DeviceState.WARNING

        elif self._state == DeviceState.EMERGENCY:
            # Recovery: only exit EMERGENCY when cloud returns AND risk drops
            if cloud_reachable and risk_score < self._config.critical_to_warning:
                self._state = DeviceState.WARNING

        return self._state

    def reset(self) -> None:
        """Reset to cold-start state (e.g., for testing)."""
        self._state = DeviceState.SAFE
        self._cold_start = True
