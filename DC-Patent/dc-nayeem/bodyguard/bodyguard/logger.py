"""
Telemetry logger for Bodyguard system.

Logs every sensor reading, risk score, state transition, and routing
decision to a CSV file for post-hoc analysis and patent evidence.

Output columns correspond directly to patent Figure 2 data flow:
  timestamp, temperature, voltage, current, cpu_percent, queue_depth,
  dT_dt, dV_dt, sigma_V, x1..x6, risk_score, device_state, budget,
  tasks_this_window, task_id, task_weight, task_priority, decision, reason
"""

import csv
import os
import time
from typing import Optional, TextIO

from bodyguard.admission import AdmissionResult
from bodyguard.risk_engine import RiskBreakdown
from bodyguard.sensors import SensorReading
from bodyguard.state_machine import DeviceState


class TelemetryLogger:
    """CSV telemetry logger.

    Creates a timestamped CSV file with every system event for
    post-experiment analysis and patent evidence generation.
    """

    COLUMNS = [
        "timestamp", "elapsed_sec",
        # Raw sensor readings
        "temperature", "voltage", "current", "cpu_percent", "queue_depth",
        # Computed derivatives
        "dT_dt", "dV_dt", "sigma_V",
        # Normalized risk terms
        "x1_thermal_prox", "x2_thermal_vel", "x3_voltage_sag",
        "x4_voltage_drop", "x5_voltage_instab", "x6_load_pressure",
        # Composite risk
        "risk_score",
        # State machine
        "device_state", "is_cold_start",
        # Budget
        "budget_remaining", "tasks_this_window",
        # Routing decision (optional — per-task rows)
        "task_id", "task_weight", "task_priority", "decision", "reason",
        # Events / markers
        "event",
    ]

    def __init__(self, output_dir: str = "results", prefix: str = "bodyguard") -> None:
        os.makedirs(output_dir, exist_ok=True)
        timestamp_str = time.strftime("%Y%m%d_%H%M%S")
        filename = f"{prefix}_{timestamp_str}.csv"
        self._filepath = os.path.join(output_dir, filename)
        self._start_time = time.time()

        self._file: TextIO = open(self._filepath, "w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=self.COLUMNS,
                                       extrasaction="ignore")
        self._writer.writeheader()
        self._file.flush()

    @property
    def filepath(self) -> str:
        """Path to the output CSV file."""
        return self._filepath

    def log_reading(
        self,
        reading: SensorReading,
        dT_dt: Optional[float],
        dV_dt: Optional[float],
        sigma_V: Optional[float],
        breakdown: RiskBreakdown,
        device_state: DeviceState,
        is_cold_start: bool,
        budget_remaining: int,
        tasks_this_window: int,
        event: str = "",
    ) -> None:
        """Log a sensor reading with computed risk and state."""
        row = {
            "timestamp": f"{reading.timestamp:.3f}",
            "elapsed_sec": f"{reading.timestamp - self._start_time:.1f}",
            "temperature": f"{reading.temperature:.2f}",
            "voltage": f"{reading.voltage:.4f}",
            "current": f"{reading.current:.3f}",
            "cpu_percent": f"{reading.cpu_percent:.1f}",
            "queue_depth": reading.queue_depth,
            "dT_dt": f"{dT_dt:.3f}" if dT_dt is not None else "",
            "dV_dt": f"{dV_dt:.5f}" if dV_dt is not None else "",
            "sigma_V": f"{sigma_V:.5f}" if sigma_V is not None else "",
            "x1_thermal_prox": f"{breakdown.x1_thermal_proximity:.4f}",
            "x2_thermal_vel": f"{breakdown.x2_thermal_velocity:.4f}",
            "x3_voltage_sag": f"{breakdown.x3_voltage_sag:.4f}",
            "x4_voltage_drop": f"{breakdown.x4_voltage_drop_rate:.4f}",
            "x5_voltage_instab": f"{breakdown.x5_voltage_instability:.4f}",
            "x6_load_pressure": f"{breakdown.x6_load_pressure:.4f}",
            "risk_score": f"{breakdown.risk_score:.4f}",
            "device_state": device_state.value,
            "is_cold_start": is_cold_start,
            "budget_remaining": budget_remaining,
            "tasks_this_window": tasks_this_window,
            "event": event,
        }
        self._writer.writerow(row)
        self._file.flush()

    def log_decision(self, result: AdmissionResult) -> None:
        """Log a task routing decision."""
        row = {
            "timestamp": f"{result.timestamp:.3f}",
            "elapsed_sec": f"{result.timestamp - self._start_time:.1f}",
            "risk_score": f"{result.risk_score:.4f}",
            "device_state": result.device_state.value,
            "budget_remaining": result.budget_remaining,
            "task_id": result.task.task_id,
            "task_weight": f"{result.task.weight:.2f}",
            "task_priority": result.task.priority.value,
            "decision": result.decision.value,
            "reason": result.reason,
        }
        self._writer.writerow(row)
        self._file.flush()

    def log_event(self, event: str, **kwargs) -> None:
        """Log a system event (window reset, state change, etc)."""
        row = {
            "timestamp": f"{time.time():.3f}",
            "elapsed_sec": f"{time.time() - self._start_time:.1f}",
            "event": event,
        }
        row.update(kwargs)
        self._writer.writerow(row)
        self._file.flush()

    def close(self) -> None:
        """Close the CSV file."""
        self._file.close()

    def __enter__(self) -> "TelemetryLogger":
        return self

    def __exit__(self, *args) -> None:
        self.close()
