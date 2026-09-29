"""
Six-term predictive risk score computation.

Implements the core risk function from the patent (Section 3, Step 2):

  R = Σ(w_i × x_i)  for i = 1..6

Where each x_i is normalized to [0, 1] using device-specific ranges:
  x1 = thermal proximity   → (T - T_safe) / (T_crit - T_safe)
  x2 = thermal velocity     → (dT/dt - s_safe) / (s_max - s_safe)
  x3 = voltage sag          → (V_safe - V) / (V_safe - V_crit)
  x4 = voltage drop rate    → |dV/dt| / dV_max     (only negative dV/dt counts)
  x5 = voltage instability  → σ_V / σ_max
  x6 = load pressure        → (cpu% × 0.7 + queue_ratio × 0.3)

DESIGN PROPERTY — Bounded and Normalized Risk:
  Because every x_i is clipped to [0, 1] and weights sum to 1.0,
  R is GUARANTEED to lie in [0, 1] under all operating conditions.
"""

from dataclasses import dataclass
from typing import List, Optional

from bodyguard.config import BodyguardConfig


@dataclass
class RiskBreakdown:
    """Detailed breakdown of each risk score component.

    Stored with each decision for telemetry and ablation analysis.
    """
    x1_thermal_proximity: float
    x2_thermal_velocity: float
    x3_voltage_sag: float
    x4_voltage_drop_rate: float
    x5_voltage_instability: float
    x6_load_pressure: float

    risk_score: float

    def as_list(self) -> List[float]:
        return [
            self.x1_thermal_proximity,
            self.x2_thermal_velocity,
            self.x3_voltage_sag,
            self.x4_voltage_drop_rate,
            self.x5_voltage_instability,
            self.x6_load_pressure,
        ]


def _clip01(value: float) -> float:
    """Clip a value to [0, 1]."""
    return max(0.0, min(1.0, value))


def compute_risk_score(
    temperature: float,
    dT_dt: Optional[float],           # °C/min (None during cold start)
    voltage: float,
    dV_dt: Optional[float],           # V/sec (None during cold start)
    sigma_V: Optional[float],         # V (None if < 2 samples)
    cpu_percent: float,
    queue_depth: int,
    config: BodyguardConfig,
    disable_derivatives: bool = False,  # For ablation mode 2
) -> RiskBreakdown:
    """Compute the six-term predictive risk score.

    Args:
        temperature: Current processor temperature (°C).
        dT_dt: Rate of thermal rise (°C/min), or None during cold start.
        voltage: Current input voltage (V).
        dV_dt: Rate of voltage change (V/sec), or None during cold start.
        sigma_V: Voltage standard deviation (V), or None if < 2 readings.
        cpu_percent: CPU utilization percentage (0–100).
        queue_depth: Current task queue depth.
        config: System configuration with normalization parameters.
        disable_derivatives: If True, x2 and x4 are forced to 0.0 (ablation mode).

    Returns:
        RiskBreakdown with individual terms and composite score.
    """
    thermal = config.thermal
    power = config.power
    weights = config.weights.as_list()

    # --- x1: Thermal proximity ---
    # How close are we to OS thermal throttle temperature?
    thermal_range = thermal.T_crit - thermal.T_safe
    x1 = _clip01((temperature - thermal.T_safe) / thermal_range) if thermal_range > 0 else 0.0

    # --- x2: Thermal velocity (derivative) ---
    # How fast is temperature rising? (°C/min)
    if disable_derivatives or dT_dt is None:
        x2 = 0.0
    else:
        slope_range = thermal.s_max - thermal.s_safe
        x2 = _clip01((dT_dt - thermal.s_safe) / slope_range) if slope_range > 0 else 0.0

    # --- x3: Voltage sag ---
    # How far has voltage dropped below safe threshold?
    # Note: inverted — lower voltage = higher risk
    voltage_range = power.V_safe - power.V_crit
    x3 = _clip01((power.V_safe - voltage) / voltage_range) if voltage_range > 0 else 0.0

    # --- x4: Voltage drop rate (derivative) ---
    # How fast is voltage dropping? Only negative dV/dt counts as risk.
    if disable_derivatives or dV_dt is None:
        x4 = 0.0
    else:
        # Negative dV/dt means voltage is falling (dangerous)
        drop_rate = max(0.0, -dV_dt)  # Absolute drop rate
        x4 = _clip01(drop_rate / power.dV_max) if power.dV_max > 0 else 0.0

    # --- x5: Voltage instability (σ_V) ---
    if sigma_V is None:
        x5 = 0.0
    else:
        x5 = _clip01(sigma_V / power.sigma_max) if power.sigma_max > 0 else 0.0

    # --- x6: Load pressure ---
    # Composite of CPU utilization and queue saturation
    cpu_norm = _clip01(cpu_percent / config.max_cpu_percent)
    queue_norm = _clip01(queue_depth / config.max_queue_depth) if config.max_queue_depth > 0 else 0.0
    x6 = _clip01(cpu_norm * 0.7 + queue_norm * 0.3)

    # --- Weighted sum ---
    terms = [x1, x2, x3, x4, x5, x6]
    R = sum(w * x for w, x in zip(weights, terms))

    # Guaranteed bounded by construction, but clamp for safety
    R = _clip01(R)

    return RiskBreakdown(
        x1_thermal_proximity=x1,
        x2_thermal_velocity=x2,
        x3_voltage_sag=x3,
        x4_voltage_drop_rate=x4,
        x5_voltage_instability=x5,
        x6_load_pressure=x6,
        risk_score=R,
    )
