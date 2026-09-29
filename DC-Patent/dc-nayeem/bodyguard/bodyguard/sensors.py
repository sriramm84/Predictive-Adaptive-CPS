"""
Physics-based mock sensor simulation for Bodyguard development.

This module simulates realistic hardware sensor readings WITHOUT fabricating
data. Instead, it models the actual physics:

  - **Thermal model**: Newton's Law of Cooling + Joule heating from CPU load.
    Temperature rises under load proportional to power dissipation, and falls
    toward ambient proportional to (T_current - T_ambient). Thermal inertia
    from heatsink + PCB mass prevents instant changes.

  - **Voltage model**: PSU output sag under load via V = V_nominal - I*R_internal.
    Includes realistic switching noise (Gaussian jitter), load transient spikes,
    and gradual recovery when load drops.

  - **Load model**: Simulates CPU utilization from a task queue. Each task
    contributes CPU load proportional to its weight.

All values stay within physically realistic ranges for a Raspberry Pi 4:
  - Temperature: 25°C (ambient) to 85°C (max junction)
  - Voltage: 4.5V (heavy sag) to 5.1V (light load overshoot)
  - CPU load: 0–100%
"""

import math
import random
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional

from bodyguard.config import BodyguardConfig


@dataclass
class SensorReading:
    """A single timestamped sensor snapshot."""

    timestamp: float
    """Unix timestamp of the reading."""

    temperature: float
    """Processor/enclosure temperature in °C."""

    voltage: float
    """Input supply voltage in V."""

    current: float
    """Current draw in A."""

    cpu_percent: float
    """CPU utilization as a percentage (0–100)."""

    queue_depth: int
    """Number of tasks currently in the execution queue."""


class SensorHistory:
    """Circular buffer of sensor readings for derivative computation.

    Stores the last `depth` readings. Provides methods to compute
    derivatives (ΔT/Δt, ΔV/Δt) and voltage stability (σ_V) from
    the buffered history.
    """

    def __init__(self, depth: int = 10) -> None:
        self._depth = depth
        self._buffer: Deque[SensorReading] = deque(maxlen=depth)

    @property
    def count(self) -> int:
        """Number of readings currently in the buffer."""
        return len(self._buffer)

    @property
    def is_full(self) -> bool:
        """Whether the buffer has reached its configured depth."""
        return self.count >= self._depth

    def push(self, reading: SensorReading) -> None:
        """Add a sensor reading to the history buffer."""
        self._buffer.append(reading)

    @property
    def latest(self) -> Optional[SensorReading]:
        """Most recent reading, or None if empty."""
        return self._buffer[-1] if self._buffer else None

    def compute_dT_dt(self, span: int = 5) -> Optional[float]:
        """Compute rate of thermal rise (°C/min) over `span` samples.

        Returns None if insufficient history exists.
        Uses: dT/dt = (T[-1] - T[-span]) / elapsed_time * 60
        """
        if self.count < span + 1:
            return None
        newest = self._buffer[-1]
        older = self._buffer[-span - 1] if span < self.count else self._buffer[0]
        elapsed = newest.timestamp - older.timestamp
        if elapsed <= 0:
            return None
        return (newest.temperature - older.temperature) / elapsed * 60.0  # °C/min

    def compute_dV_dt(self, span: int = 5) -> Optional[float]:
        """Compute rate of voltage change (V/sec) over `span` samples.

        Returns None if insufficient history exists.
        Negative values indicate voltage drop (danger); positive = recovery.
        """
        if self.count < span + 1:
            return None
        newest = self._buffer[-1]
        older = self._buffer[-span - 1] if span < self.count else self._buffer[0]
        elapsed = newest.timestamp - older.timestamp
        if elapsed <= 0:
            return None
        return (newest.voltage - older.voltage) / elapsed  # V/sec

    def compute_sigma_V(self) -> Optional[float]:
        """Compute voltage standard deviation over all buffered readings.

        Returns None if fewer than 2 readings exist.
        Higher values indicate PSU instability / noise.
        """
        if self.count < 2:
            return None
        voltages = [r.voltage for r in self._buffer]
        mean_v = sum(voltages) / len(voltages)
        variance = sum((v - mean_v) ** 2 for v in voltages) / len(voltages)
        return math.sqrt(variance)


# ---------------------------------------------------------------------------
#  Physics-Based Hardware Simulator
# ---------------------------------------------------------------------------

class PhysicsSimulator:
    """Simulates realistic Raspberry Pi 4 hardware behavior.

    This is NOT a random number generator — it models actual physics:

    THERMAL MODEL (Newton's Law of Cooling + Joule heating):
      dT/dt = (P_cpu / thermal_mass) - cooling_rate × (T - T_ambient)

      Where:
        P_cpu = cpu_load × P_max  (Joule heating proportional to load)
        cooling_rate models passive heatsink convection
        thermal_mass models PCB + heatsink thermal inertia

    VOLTAGE MODEL (Ohm's Law on PSU output impedance):
      V = V_nominal - I_load × R_internal + noise

      Where:
        I_load is proportional to CPU load (Pi 4: ~0.6A idle, ~2.0A full load)
        R_internal is the effective PSU + cable impedance
        noise models switching ripple (Gaussian with device-specific sigma)
    """

    def __init__(self, config: BodyguardConfig, seed: Optional[int] = None) -> None:
        self._config = config
        self._rng = random.Random(seed)

        # --- Internal thermal state ---
        self._temperature = config.thermal.ambient_temp  # Start cold
        self._last_time = time.time()

        # --- Internal electrical state ---
        self._voltage = config.power.V_nominal

        # --- Load state ---
        self._cpu_percent = 5.0  # Idle baseline (OS processes)
        self._queue_depth = 0

        # --- Pi 4 electrical profile ---
        self._idle_current = 0.6   # Amps at idle
        self._max_current = 2.0    # Amps at full CPU load
        self._max_thermal_power = 6.0  # Watts max CPU dissipation (Pi 4 SoC)

    def set_load(self, cpu_percent: float, queue_depth: int = 0) -> None:
        """Set the current CPU load and queue depth.

        Called by the task admission system when tasks start/finish.
        """
        self._cpu_percent = max(0.0, min(100.0, cpu_percent))
        self._queue_depth = max(0, queue_depth)

    def add_load(self, cpu_delta: float) -> None:
        """Add incremental CPU load (from a new task starting)."""
        self._cpu_percent = max(0.0, min(100.0, self._cpu_percent + cpu_delta))

    def remove_load(self, cpu_delta: float) -> None:
        """Remove CPU load (task completed)."""
        self._cpu_percent = max(5.0, self._cpu_percent - cpu_delta)  # Never below idle

    def set_queue_depth(self, depth: int) -> None:
        """Update task queue depth."""
        self._queue_depth = max(0, depth)

    def step(self, dt: Optional[float] = None) -> SensorReading:
        """Advance the physics simulation by dt seconds and return a reading.

        If dt is None, uses wall-clock elapsed time since last step.
        """
        now = time.time()
        if dt is None:
            dt = now - self._last_time
        dt = max(0.001, dt)  # Guard against zero
        self._last_time = now

        # --- Thermal physics ---
        load_fraction = self._cpu_percent / 100.0
        thermal = self._config.thermal

        # Joule heating: power dissipated by CPU
        P_cpu = load_fraction * self._max_thermal_power  # Watts

        # Newton's Law of Cooling: heat loss to environment
        temp_diff = self._temperature - thermal.ambient_temp
        cooling_power = thermal.passive_cooling_rate * temp_diff  # °C/sec × °C ≈ heat flow

        # Temperature change: heating - cooling, scaled by thermal mass
        dT = (P_cpu / thermal.thermal_mass - cooling_power) * dt

        # Add small sensor noise (real sensors have ±0.5°C resolution)
        sensor_noise_T = self._rng.gauss(0, 0.3)

        self._temperature += dT
        # Clamp to physical limits
        self._temperature = max(thermal.ambient_temp, min(90.0, self._temperature))

        # --- Voltage physics (Ohm's Law) ---
        power = self._config.power
        current_draw = self._idle_current + (self._max_current - self._idle_current) * load_fraction

        # PSU sag: V = V_nominal - I × R_internal
        voltage_sag = current_draw * power.psu_impedance

        # PSU noise: switching ripple + random fluctuations
        # Noise increases under load (more switching transients)
        noise_amplitude = power.psu_noise_stddev * (1.0 + load_fraction * 2.0)
        voltage_noise = self._rng.gauss(0, noise_amplitude)

        # Occasional transient spikes (inrush from motor/relay on shared rail)
        if self._rng.random() < 0.005:  # 0.5% chance per sample
            voltage_noise -= self._rng.uniform(0.05, 0.15)  # Negative spike

        target_voltage = power.V_nominal - voltage_sag + voltage_noise

        # Voltage doesn't change instantly — capacitor smoothing
        # Exponential moving average simulates cap charge/discharge
        smoothing = 1.0 - math.exp(-dt / 0.5)  # ~0.5s time constant
        self._voltage += (target_voltage - self._voltage) * smoothing

        # Clamp to physical limits
        self._voltage = max(4.0, min(5.3, self._voltage))

        return SensorReading(
            timestamp=now,
            temperature=self._temperature + sensor_noise_T,
            voltage=self._voltage,
            current=current_draw,
            cpu_percent=self._cpu_percent,
            queue_depth=self._queue_depth,
        )

