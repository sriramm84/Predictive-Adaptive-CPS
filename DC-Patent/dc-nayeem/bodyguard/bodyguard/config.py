"""
Device-specific calibration parameters for the Bodyguard system.

All values correspond to parameters defined in the patent specification
(Section 3, Step 2 — Risk Score Computation). Default values are calibrated
for a Raspberry Pi 4 Model B with passive heatsink and stock 5V/2.5A USB PSU.

These parameters MUST be determined through device-specific profiling:
  - Subject the device to controlled thermal stress (sustained CPU load in
    a sealed enclosure) and record T_crit, s_max, and passive cooling rate.
  - Subject the device to controlled electrical stress (sudden load on a
    shared power rail) and record V_crit, dV_max, and sigma_max.
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class ThermalProfile:
    """Thermal calibration parameters from device stress profiling."""

    T_safe: float = 60.0
    """Safe operating temperature ceiling (°C). Below this, thermal proximity
    contributes zero risk."""

    T_crit: float = 80.0
    """OS thermal throttle trigger temperature (°C). At or above this,
    thermal proximity is maximal (1.0)."""

    s_safe: float = 1.0
    """Maximum sustainable thermal rise rate (°C/min) that passive cooling
    can dissipate indefinitely. Below this, thermal velocity contributes
    zero risk."""

    s_max: float = 5.0
    """Maximum observed thermal rise rate (°C/min) during device stress
    profiling. At or above this, thermal velocity is maximal (1.0)."""

    ambient_temp: float = 25.0
    """Expected ambient temperature (°C) for thermal simulation.
    Real deployments read this from DHT22 or similar."""

    passive_cooling_rate: float = 0.3
    """Passive cooling dissipation rate (°C/sec) — how fast the device
    cools toward ambient when idle. Measured during profiling."""

    thermal_mass: float = 15.0
    """Effective thermal mass coefficient. Higher = slower temperature
    change for given power input. Models heatsink + PCB thermal inertia."""


@dataclass
class PowerProfile:
    """Electrical calibration parameters from power stress profiling."""

    V_safe: float = 4.95
    """Nominal clean-power input voltage (V). Below this, voltage sag
    contributes risk."""

    V_crit: float = 4.63
    """Brownout / reboot voltage threshold (V). At or below this,
    voltage sag is maximal (1.0) and the device is at imminent risk."""

    V_nominal: float = 5.0
    """Nominal PSU output voltage (V) under no-load conditions."""

    dV_max: float = 0.5
    """Maximum expected voltage drop rate (V/sec) during power stress
    profiling (e.g., sudden motor-on on shared rail)."""

    sigma_max: float = 0.3
    """Maximum expected voltage standard deviation (V) — characterizes
    PSU quality. Cheap USB PSUs may have sigma > 0.1V."""

    psu_impedance: float = 0.15
    """Effective PSU output impedance (Ohms). Models voltage sag under
    load: V_drop = I_load × psu_impedance. Typical for cheap USB PSUs."""

    psu_noise_stddev: float = 0.02
    """Baseline PSU voltage noise standard deviation (V) under normal
    conditions. Models ripple and switching noise."""


@dataclass
class RiskWeights:
    """Weights for the six-term risk score. MUST sum to 1.0.

    The derivative/velocity terms (w2, w4) carry the highest weights because
    they are the PREDICTIVE core — they detect danger trajectories before
    absolute thresholds are crossed.
    """

    w1_thermal_proximity: float = 0.15
    """Weight for thermal proximity term (how close to T_crit)."""

    w2_thermal_velocity: float = 0.25
    """Weight for thermal velocity term (dT/dt). Primary predictive signal
    for thermal failure."""

    w3_voltage_sag: float = 0.15
    """Weight for voltage sag term (how far below V_safe)."""

    w4_voltage_drop_rate: float = 0.20
    """Weight for voltage drop rate term (dV/dt). Primary predictive signal
    for power failure."""

    w5_voltage_instability: float = 0.10
    """Weight for voltage instability term (sigma_V). Captures sustained
    PSU noise invisible to instantaneous derivatives."""

    w6_load_pressure: float = 0.15
    """Weight for load pressure term. Secondary signal — removing it
    degrades throughput but not core protective effect."""

    def as_list(self) -> List[float]:
        """Return weights as ordered list [w1, w2, w3, w4, w5, w6]."""
        return [
            self.w1_thermal_proximity,
            self.w2_thermal_velocity,
            self.w3_voltage_sag,
            self.w4_voltage_drop_rate,
            self.w5_voltage_instability,
            self.w6_load_pressure,
        ]

    def validate(self) -> None:
        """Verify weights sum to 1.0 (within floating-point tolerance)."""
        total = sum(self.as_list())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"Risk weights must sum to 1.0, got {total:.6f}. "
                f"Weights: {self.as_list()}"
            )


@dataclass
class BudgetConfig:
    """Safety budget parameters."""

    B_max: int = 10
    """Maximum safe task budget per window (calibrated per device during
    profiling). This is the upper bound on local tasks in any single window."""

    window_duration: float = 30.0
    """Fixed window duration (seconds) after which the budget resets and
    is recomputed from the current risk score."""

    R_replenish: float = 0.25
    """Replenishment threshold — budget replenishes at window boundary ONLY
    when R_t is below this value. Prevents premature replenishment during
    sustained stress. (Claim 10 in patent.)"""


@dataclass
class StateMachineConfig:
    """Dual-hysteresis state machine thresholds."""

    # SAFE → WARNING transition
    safe_to_warning: float = 0.30
    """Risk score threshold to enter WARNING from SAFE."""

    # WARNING → SAFE transition (hysteresis gap: 0.25–0.30)
    warning_to_safe: float = 0.25
    """Risk score threshold to return to SAFE from WARNING."""

    # WARNING → CRITICAL transition
    warning_to_critical: float = 0.65
    """Risk score threshold to enter CRITICAL from WARNING."""

    # CRITICAL → WARNING transition (hysteresis gap: 0.55–0.65)
    critical_to_warning: float = 0.55
    """Risk score threshold to return to WARNING from CRITICAL."""

    cold_start_min_samples: int = 5
    """Minimum number of sensor samples required before derivatives can
    be computed. During cold start, system defaults to WARNING state."""


@dataclass
class SamplingConfig:
    """Sensor sampling parameters."""

    interval: float = 2.0
    """Sampling interval in seconds. Sensors are read every this many seconds."""

    history_depth: int = 10
    """Circular buffer depth for history. Stores last N readings for
    derivative computation and sigma_V calculation."""

    derivative_span: int = 5
    """Number of samples to span for derivative computation.
    dT/dt = (T[-1] - T[-span]) / (span × interval)."""


@dataclass
class EmergencyConfig:
    """Emergency self-protection parameters."""

    sleep_ms: int = 500
    """Mandatory sleep interval (ms) between task executions in EMERGENCY
    state. Allows passive cooling and voltage recovery."""

    cloud_timeout: float = 5.0
    """Timeout (seconds) for cloud reachability check."""

    cloud_endpoint: str = "http://localhost:8080/tasks"
    """Cloud offload endpoint URL. In stub mode, this is a local endpoint."""


@dataclass
class BodyguardConfig:
    """Complete Bodyguard system configuration.

    Aggregates all sub-configurations. Default values are calibrated for
    Raspberry Pi 4 Model B, passive heatsink, stock 5V/2.5A USB PSU.
    """

    thermal: ThermalProfile = field(default_factory=ThermalProfile)
    power: PowerProfile = field(default_factory=PowerProfile)
    weights: RiskWeights = field(default_factory=RiskWeights)
    budget: BudgetConfig = field(default_factory=BudgetConfig)
    state_machine: StateMachineConfig = field(default_factory=StateMachineConfig)
    sampling: SamplingConfig = field(default_factory=SamplingConfig)
    emergency: EmergencyConfig = field(default_factory=EmergencyConfig)

    # System capacity for load normalization
    max_cpu_percent: float = 100.0
    """Maximum CPU utilization (always 100%)."""

    max_queue_depth: int = 20
    """Maximum expected task queue depth for normalization."""

    def validate(self) -> None:
        """Validate all configuration parameters."""
        self.weights.validate()

        assert self.thermal.T_safe < self.thermal.T_crit, \
            f"T_safe ({self.thermal.T_safe}) must be < T_crit ({self.thermal.T_crit})"
        assert self.thermal.s_safe < self.thermal.s_max, \
            f"s_safe ({self.thermal.s_safe}) must be < s_max ({self.thermal.s_max})"
        assert self.power.V_crit < self.power.V_safe, \
            f"V_crit ({self.power.V_crit}) must be < V_safe ({self.power.V_safe})"
        assert self.state_machine.warning_to_safe < self.state_machine.safe_to_warning, \
            "Hysteresis: warning_to_safe must be < safe_to_warning"
        assert self.state_machine.critical_to_warning < self.state_machine.warning_to_critical, \
            "Hysteresis: critical_to_warning must be < warning_to_critical"
        assert self.budget.B_max > 0, "B_max must be positive"
        assert self.budget.window_duration > 0, "Window duration must be positive"
