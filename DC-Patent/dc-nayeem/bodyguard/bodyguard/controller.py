"""
Bodyguard main controller — the central orchestration loop.

This is the 'daemon' described in the patent. It ties together:
  1. Sensor reading (physics-based simulation)
  2. History management & derivative computation
  3. Risk score computation
  4. State machine transitions
  5. Budget management
  6. Task admission decisions
  7. Telemetry logging

The controller runs in a loop at the configured sampling interval.
Tasks are submitted externally and routed through the admission controller.
"""

import time
from typing import Callable, Optional

from bodyguard.admission import AdmissionController, AdmissionResult, Task
from bodyguard.budget import SafetyBudget
from bodyguard.config import BodyguardConfig
from bodyguard.logger import TelemetryLogger
from bodyguard.risk_engine import RiskBreakdown, compute_risk_score
from bodyguard.sensors import PhysicsSimulator, SensorHistory, SensorReading
from bodyguard.state_machine import DeviceState, DualHysteresisFSM


class BodyguardController:
    """Main Bodyguard control loop.

    Usage:
        config = BodyguardConfig()
        ctrl = BodyguardController(config, output_dir="results")
        ctrl.start()

        # Submit tasks for routing
        result = ctrl.submit_task(task)

        # When done
        ctrl.stop()
    """

    def __init__(
        self,
        config: BodyguardConfig,
        output_dir: str = "results",
        log_prefix: str = "bodyguard",
        seed: Optional[int] = None,
        # Ablation flags
        disable_derivatives: bool = False,  # Ablation mode 2
        disable_budget: bool = False,       # Ablation mode 3
        disable_state_machine: bool = False,  # Threshold-only mode 4
        threshold_only_T: float = 75.0,     # For mode 4
        threshold_only_V: float = 4.8,      # For mode 4
        # Cloud stub
        cloud_handler: Optional[Callable[[Task], None]] = None,
    ) -> None:
        """Initialize the Bodyguard controller.

        Args:
            config: System configuration.
            output_dir: Directory for CSV output.
            log_prefix: Prefix for log filenames.
            seed: Random seed for reproducible simulations.
            disable_derivatives: Ablation mode 2 — zero out derivative terms.
            disable_budget: Ablation mode 3 — unlimited local tasks.
            disable_state_machine: Ablation mode 4 — threshold-only routing.
            threshold_only_T: Temperature threshold for mode 4 (°C).
            threshold_only_V: Voltage threshold for mode 4 (V).
            cloud_handler: Optional callback for cloud offloading.
        """
        config.validate()
        self._config = config

        # --- Ablation flags ---
        self._disable_derivatives = disable_derivatives
        self._disable_budget = disable_budget
        self._disable_state_machine = disable_state_machine
        self._threshold_only_T = threshold_only_T
        self._threshold_only_V = threshold_only_V

        # --- Core components ---
        self._simulator = PhysicsSimulator(config, seed=seed)
        self._history = SensorHistory(depth=config.sampling.history_depth)
        self._fsm = DualHysteresisFSM(config.state_machine)
        self._budget = SafetyBudget(config.budget)
        self._admission = AdmissionController(self._budget, cloud_available=True)
        self._logger = TelemetryLogger(output_dir=output_dir, prefix=log_prefix)

        # --- Cloud stub ---
        self._cloud_handler = cloud_handler or self._default_cloud_handler

        # --- Ablation setup ---
        if disable_budget:
            self._budget.disable()

        # --- State ---
        self._running = False
        self._latest_risk: Optional[RiskBreakdown] = None
        self._latest_reading: Optional[SensorReading] = None

        # --- Failure tracking (for experiments) ---
        self._failure_count = 0           # Distinct failure incidents (entering T_crit)
        self._failure_steps = 0           # Total steps spent in failure zone
        self._in_failure_state = False    # Currently in failure zone?
        self._first_failure_time: Optional[float] = None
        self._sim_time: float = 0.0      # Simulated time (seconds)
        self._peak_temperature = 0.0
        self._voltage_floor = 5.5

    # --- Public API ---

    @property
    def state(self) -> DeviceState:
        """Current device state."""
        return self._fsm.state

    @property
    def risk_score(self) -> float:
        """Current risk score."""
        return self._latest_risk.risk_score if self._latest_risk else 0.0

    @property
    def budget_remaining(self) -> int:
        """Remaining safety budget."""
        return self._budget.remaining

    @property
    def failure_count(self) -> int:
        """Number of simulated hardware failures (for experiments)."""
        return self._failure_count

    @property
    def peak_temperature(self) -> float:
        """Peak temperature recorded during run."""
        return self._peak_temperature

    @property
    def voltage_floor(self) -> float:
        """Minimum voltage recorded during run."""
        return self._voltage_floor

    @property
    def first_failure_time(self) -> Optional[float]:
        """Seconds from start to first failure, or None if no failure."""
        return self._first_failure_time

    @property
    def stats(self) -> dict:
        """Routing statistics."""
        return self._admission.stats

    @property
    def logger(self) -> TelemetryLogger:
        """Access to the telemetry logger."""
        return self._logger

    def sample(self, dt: Optional[float] = None) -> RiskBreakdown:
        """Perform one sample-compute-classify-budget cycle.

        This is the core iteration of the Bodyguard loop:
          1. Read sensors
          2. Push to history
          3. Compute derivatives
          4. Compute risk score
          5. Update state machine
          6. Check budget window
          7. Log telemetry

        Args:
            dt: Simulated time step (seconds). None = real-time.

        Returns:
            RiskBreakdown from this cycle.
        """
        # 1. Read sensors
        reading = self._simulator.step(dt=dt)
        self._latest_reading = reading

        # Track simulated time
        if dt is not None:
            self._sim_time += dt

        # Track extremes for experiments
        self._peak_temperature = max(self._peak_temperature, reading.temperature)
        self._voltage_floor = min(self._voltage_floor, reading.voltage)

        # 2. Push to history
        self._history.push(reading)

        # 3. Compute derivatives from history
        span = self._config.sampling.derivative_span
        dT_dt = self._history.compute_dT_dt(span=span)
        dV_dt = self._history.compute_dV_dt(span=span)
        sigma_V = self._history.compute_sigma_V()

        # 4. Compute risk score
        breakdown = compute_risk_score(
            temperature=reading.temperature,
            dT_dt=dT_dt,
            voltage=reading.voltage,
            dV_dt=dV_dt,
            sigma_V=sigma_V,
            cpu_percent=reading.cpu_percent,
            queue_depth=reading.queue_depth,
            config=self._config,
            disable_derivatives=self._disable_derivatives,
        )
        self._latest_risk = breakdown

        # 5. Update state machine
        if self._disable_state_machine:
            # Ablation mode 4: threshold-only
            state = self._threshold_only_check(reading)
        else:
            state = self._fsm.update(
                risk_score=breakdown.risk_score,
                cloud_reachable=self._admission.cloud_available,
                sample_count=self._history.count,
            )

        # 6. Check budget window (using simulated time)
        window_reset = self._budget.check_window_reset(
            breakdown.risk_score, sim_time=self._sim_time
        )
        event = ""
        if window_reset:
            event = f"window_reset|B={self._budget.remaining}"

        # 7. Check for simulated hardware failure
        failure_event = self._check_failure(reading)
        if failure_event:
            event = f"{event}|{failure_event}" if event else failure_event

        # 8. Log telemetry
        self._logger.log_reading(
            reading=reading,
            dT_dt=dT_dt,
            dV_dt=dV_dt,
            sigma_V=sigma_V,
            breakdown=breakdown,
            device_state=state,
            is_cold_start=self._fsm.is_cold_start,
            budget_remaining=self._budget.remaining,
            tasks_this_window=self._budget.tasks_this_window,
            event=event,
        )

        return breakdown

    def submit_task(self, task: Task) -> AdmissionResult:
        """Submit a task for admission and routing.

        Args:
            task: The task to route.

        Returns:
            AdmissionResult with decision and rationale.
        """
        risk = self._latest_risk.risk_score if self._latest_risk else 0.5

        result = self._admission.admit(
            task=task,
            device_state=self._fsm.state,
            risk_score=risk,
            disable_budget=self._disable_budget,
        )

        # Execute the decision
        self._execute_decision(result)

        # Log the decision
        self._logger.log_decision(result)

        return result

    def set_load(self, cpu_percent: float, queue_depth: int = 0) -> None:
        """Directly set CPU load (for scenario-driven simulation)."""
        self._simulator.set_load(cpu_percent, queue_depth)

    def set_cloud_available(self, available: bool) -> None:
        """Set cloud availability (for testing EMERGENCY state)."""
        self._admission.cloud_available = available

    def close(self) -> None:
        """Close the logger and clean up."""
        self._logger.close()

    def get_experiment_results(self) -> dict:
        """Get summary results for experiment analysis."""
        dt = self._config.sampling.interval
        return {
            "duration_sec": self._sim_time,
            "failure_incidents": self._failure_count,
            "failure_steps": self._failure_steps,
            "failure_seconds": self._failure_steps * dt,
            "first_failure_sec": self._first_failure_time,
            "peak_temperature_C": self._peak_temperature,
            "voltage_floor_V": self._voltage_floor,
            "routing": self._admission.stats,
            "csv_path": self._logger.filepath,
        }

    # --- Internal ---

    def _check_failure(self, reading: SensorReading) -> Optional[str]:
        """Check if conditions represent a hardware failure.

        Counts failure INCIDENTS (transitions into failure zone), not
        every step spent in the zone. This models real hardware:
          - T >= T_crit  -> OS thermal shutdown / reboot
          - V <= V_crit  -> brownout reboot
        Each incident = one reboot. Staying above T_crit after a
        reboot means the device immediately fails again on restart.
        """
        is_failing = (
            reading.temperature >= self._config.thermal.T_crit
            or reading.voltage <= self._config.power.V_crit
        )

        if is_failing:
            self._failure_steps += 1
            reasons = []
            if reading.temperature >= self._config.thermal.T_crit:
                reasons.append(f"THERMAL(T={reading.temperature:.1f}C)")
            if reading.voltage <= self._config.power.V_crit:
                reasons.append(f"BROWNOUT(V={reading.voltage:.3f}V)")

            if not self._in_failure_state:
                # New failure incident (transition INTO failure zone)
                self._failure_count += 1
                if self._first_failure_time is None:
                    self._first_failure_time = self._sim_time
                self._in_failure_state = True
                event = "FAILURE:" + "+".join(reasons)
                return event
            else:
                # Continuing in failure zone (not a new incident)
                return None
        else:
            # Recovered from failure zone
            self._in_failure_state = False
            return None

    def _threshold_only_check(self, reading: SensorReading) -> DeviceState:
        """Ablation mode 4: simple threshold-only routing.

        No risk score, no derivatives, no state machine.
        Just: T > threshold OR V < threshold → offload.
        """
        if (reading.temperature > self._threshold_only_T or
                reading.voltage < self._threshold_only_V):
            return DeviceState.CRITICAL
        return DeviceState.SAFE

    def _execute_decision(self, result: AdmissionResult) -> None:
        """Execute the routing decision (update simulator state)."""
        from bodyguard.admission import RoutingDecision

        if result.decision == RoutingDecision.LOCAL:
            self._simulator.add_load(result.task.cpu_load)
        elif result.decision == RoutingDecision.OFFLOAD:
            self._cloud_handler(result.task)
        elif result.decision == RoutingDecision.THROTTLE:
            # Execute locally but with sleep interleaving
            self._simulator.add_load(result.task.cpu_load * 0.5)  # Half load
        # REJECT: do nothing

    @staticmethod
    def _default_cloud_handler(task: Task) -> None:
        """Default cloud offload stub — just records it happened."""
        pass  # In real system: HTTP POST to cloud endpoint
