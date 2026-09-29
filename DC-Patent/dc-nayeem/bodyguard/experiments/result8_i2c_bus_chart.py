"""
Result 8 — I2C Bus Graph (Separate)
====================================

Extracts ONLY the I2C bus Voltage & Temperature panel from Result 8
(Emergency Self-Preservation).

Shows the INA219 sensor voltage (I2C) and DS18B20 / on-die temperature
readings for both Bodyguard (protected) and Baseline (unprotected) runs,
with cloud outage at minute 5.

RUN:
  python experiments/result8_i2c_bus_chart.py
"""
import sys
import os
import random

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from bodyguard.config import BodyguardConfig
from bodyguard.controller import BodyguardController
from bodyguard.admission import Task, TaskPriority, RoutingDecision


# ===========================================================================
#  CONFIGURATION  (same as exp8)
# ===========================================================================

def make_config():
    config = BodyguardConfig()
    config.thermal.ambient_temp = 38.0
    config.thermal.T_safe = 65.0
    config.thermal.T_crit = 80.0
    config.thermal.passive_cooling_rate = 0.20
    config.thermal.thermal_mass = 10.0
    config.thermal.s_safe = 1.0
    config.thermal.s_max = 5.0

    config.power.V_nominal = 5.0
    config.power.V_safe = 4.90
    config.power.V_crit = 4.63
    config.power.psu_impedance = 0.18
    config.power.psu_noise_stddev = 0.025

    config.weights.w1_thermal_proximity = 0.15
    config.weights.w2_thermal_velocity = 0.25
    config.weights.w3_voltage_sag = 0.15
    config.weights.w4_voltage_drop_rate = 0.20
    config.weights.w5_voltage_instability = 0.10
    config.weights.w6_load_pressure = 0.15

    config.budget.B_max = 10
    config.budget.window_duration = 30.0
    config.budget.R_replenish = 0.25

    config.state_machine.safe_to_warning = 0.30
    config.state_machine.warning_to_safe = 0.25
    config.state_machine.warning_to_critical = 0.65
    config.state_machine.critical_to_warning = 0.55

    config.sampling.interval = 2.0
    config.sampling.history_depth = 10
    config.emergency.sleep_ms = 500
    return config


# ===========================================================================
#  SIMULATION  (same as exp8)
# ===========================================================================

def run_scenario(label, config, seed=42, protected=True):
    dt = config.sampling.interval
    total_time = 15 * 60
    total_steps = int(total_time / dt)

    CLOUD_OUTAGE_TIME = 5 * 60
    BURST_START = 5 * 60
    BURST_END = 7 * 60

    rng = random.Random(seed + 8)

    kwargs = {}
    if not protected:
        kwargs = {"disable_state_machine": True, "disable_budget": True}

    ctrl = BodyguardController(
        config=config, output_dir="experiments/output",
        log_prefix=f"exp8_{label.lower().replace(' ', '_')}",
        seed=seed, **kwargs,
    )

    active_load = 0.0
    base_idle = 5.0

    timeline = {
        "time": [], "temperature": [], "voltage": [],
        "risk_score": [], "state": [], "cpu_load": [],
    }

    failure_events = []
    thermal_shutdowns = 0
    brownouts = 0
    peak_temp = 0.0

    print(f"  Running {label}...")

    for step in range(total_steps):
        sim_time = step * dt
        minute = int(sim_time / 60)

        if sim_time >= CLOUD_OUTAGE_TIME:
            ctrl._admission._cloud_available = False

        active_load *= 0.93
        if active_load < 0.2:
            active_load = 0.0

        total_cpu = base_idle + active_load
        ctrl.set_load(min(99.0, total_cpu), queue_depth=max(0, int(active_load / 6)))
        bd = ctrl.sample(dt=dt)

        reading = ctrl._latest_reading
        if not reading:
            continue

        if reading.temperature > peak_temp:
            peak_temp = reading.temperature

        if reading.temperature >= config.thermal.T_crit:
            if not hasattr(ctrl, '_exp8_in_thermal_failure') or not ctrl._exp8_in_thermal_failure:
                thermal_shutdowns += 1
                failure_events.append({
                    "time": sim_time, "type": "THERMAL_SHUTDOWN",
                    "temp": reading.temperature,
                })
                ctrl._exp8_in_thermal_failure = True
        else:
            ctrl._exp8_in_thermal_failure = False

        if reading.voltage <= config.power.V_crit:
            if not hasattr(ctrl, '_exp8_in_brownout') or not ctrl._exp8_in_brownout:
                brownouts += 1
                failure_events.append({
                    "time": sim_time, "type": "BROWNOUT",
                    "voltage": reading.voltage,
                })
                ctrl._exp8_in_brownout = True
        else:
            ctrl._exp8_in_brownout = False

        if step % 3 == 0:
            timeline["time"].append(sim_time / 60)
            timeline["temperature"].append(reading.temperature)
            timeline["voltage"].append(reading.voltage)
            timeline["risk_score"].append(bd.risk_score if bd else 0.0)
            timeline["state"].append(ctrl.state.value if protected else "N/A")
            timeline["cpu_load"].append(total_cpu)

        # --- Workload ---
        if BURST_START <= sim_time < BURST_END:
            task_prob = 0.80
            weight_range = (0.50, 0.95)
            cpu_range = (6.0, 12.0)
        else:
            task_prob = 0.30
            weight_range = (0.15, 0.60)
            cpu_range = (2.0, 6.0)

        if rng.random() < task_prob:
            num_tasks = 1
            if BURST_START <= sim_time < BURST_END and rng.random() < 0.15:
                num_tasks += rng.randint(1, 3)
        else:
            num_tasks = 0

        for i in range(num_tasks):
            weight = rng.uniform(*weight_range)
            cpu_demand = rng.uniform(*cpu_range)
            pri = rng.choices(list(TaskPriority), weights=[20, 40, 25, 15])[0]
            task = Task(
                task_id=f"t{step}_{i}", weight=weight,
                priority=pri, cpu_load=cpu_demand,
            )

            if protected:
                result = ctrl.submit_task(task)
                decision = result.decision
            else:
                decision = RoutingDecision.LOCAL
                ctrl._simulator.add_load(cpu_demand)

            if decision == RoutingDecision.LOCAL:
                active_load += cpu_demand
            elif decision == RoutingDecision.THROTTLE:
                active_load += cpu_demand * 0.4
            # OFFLOAD / REJECT don't add local load

    ctrl.close()

    return {
        "label": label,
        "timeline": timeline,
        "failure_events": failure_events,
        "thermal_shutdowns": thermal_shutdowns,
        "brownouts": brownouts,
        "peak_temp": peak_temp,
    }


# ===========================================================================
#  I2C BUS GRAPH  (standalone)
# ===========================================================================

def make_i2c_bus_chart(bodyguard, baseline):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    fig, ax_v = plt.subplots(figsize=(14, 7))
    fig.patch.set_facecolor("#FAFAFA")
    ax_v.set_facecolor("#FAFAFA")

    CLOUD_OUTAGE_MIN = 5.0
    color_bg = "#2E86C1"    # Bodyguard blue
    color_bl = "#C0392B"    # Baseline red

    t_bg = bodyguard["timeline"]["time"]
    t_bl = baseline["timeline"]["time"]

    # --- Primary Y-axis: Voltage (I2C INA219) ---
    V_bg = bodyguard["timeline"]["voltage"]
    V_bl = baseline["timeline"]["voltage"]

    ax_v.plot(t_bg, V_bg, color=color_bg, lw=2.5, alpha=0.9,
              label="Bodyguard V(t)  [I2C INA219]", zorder=3)
    ax_v.plot(t_bl, V_bl, color=color_bl, lw=2.5, alpha=0.9, ls="--",
              label="Baseline V(t)  [I2C INA219]", zorder=3)

    # Voltage thresholds
    ax_v.axhline(y=4.63, color="#C0392B", ls=":", lw=2, alpha=0.6)
    ax_v.text(14.8, 4.635, "V_crit = 4.63V (Brownout)", fontsize=9,
              color="#C0392B", ha="right", fontstyle="italic", fontweight="bold")
    ax_v.axhline(y=4.90, color="#E67E22", ls=":", lw=1.5, alpha=0.4)
    ax_v.text(14.8, 4.905, "V_safe = 4.90V", fontsize=9, color="#E67E22",
              ha="right", fontstyle="italic")

    # Mark brownout failures on baseline
    for fe in baseline["failure_events"]:
        if fe["type"] == "BROWNOUT":
            ax_v.plot(fe["time"] / 60, fe.get("voltage", 4.63), "X",
                      color="#C0392B", markersize=14, zorder=5,
                      markeredgewidth=2)

    # Cloud outage vertical line
    ax_v.axvline(x=CLOUD_OUTAGE_MIN, color="#7F8C8D", ls="--", lw=2, alpha=0.7)
    ylims = ax_v.get_ylim()
    ax_v.text(CLOUD_OUTAGE_MIN + 0.15,
              ylims[1] - 0.02 if ylims[1] > 4.5 else 5.0,
              "Cloud\nOutage", fontsize=10, color="#7F8C8D",
              fontweight="bold", va="top")

    # --- Secondary Y-axis: Temperature ---
    ax_t = ax_v.twinx()
    T_bg = bodyguard["timeline"]["temperature"]
    T_bl = baseline["timeline"]["temperature"]
    ax_t.plot(t_bg, T_bg, color="#27AE60", lw=1.8, alpha=0.55,
              ls="-.", label="Bodyguard T(t)  [Thermal Sensor]", zorder=2)
    ax_t.plot(t_bl, T_bl, color="#E67E22", lw=1.8, alpha=0.55,
              ls="-.", label="Baseline T(t)  [Thermal Sensor]", zorder=2)
    ax_t.set_ylabel("Temperature (°C)", fontsize=12, color="#7F8C8D",
                     fontweight="bold")
    ax_t.tick_params(axis="y", labelcolor="#7F8C8D", labelsize=10)

    # --- Labels & Title ---
    ax_v.set_xlabel("Time (minutes)", fontsize=12, fontweight="bold")
    ax_v.set_ylabel("Voltage (V)  —  I2C INA219 Sensor", fontsize=12,
                     fontweight="bold")
    ax_v.set_title(
        "I2C Bus: Voltage & Temperature During Emergency\n"
        "(INA219 sensor at /dev/i2c-1, addr 0x40)",
        fontsize=14, fontweight="bold", color="#2C3E50", pad=15,
    )

    # Combined legend
    lines1, labels1 = ax_v.get_legend_handles_labels()
    lines2, labels2 = ax_t.get_legend_handles_labels()
    ax_v.legend(lines1 + lines2, labels1 + labels2, fontsize=9,
                loc="lower left", framealpha=0.9, ncol=2,
                fancybox=True, shadow=True)

    ax_v.grid(True, alpha=0.2)
    ax_v.spines["top"].set_visible(False)
    ax_v.set_xlim(0, 15)
    ax_v.tick_params(labelsize=10)

    # Brownout count annotation
    n_brownouts = baseline["brownouts"]
    if n_brownouts > 0:
        props = dict(boxstyle="round,pad=0.4", facecolor="#FADBD8",
                     edgecolor="#C0392B", alpha=0.9)
        ax_v.text(0.98, 0.12, f"Baseline: {n_brownouts} BROWNOUTS",
                  transform=ax_v.transAxes, fontsize=11, va="bottom",
                  ha="right", bbox=props, fontweight="bold", color="#C0392B")

    # I2C bus info box
    info_text = (
        "I2C Bus\n"
        "/dev/i2c-1\n"
        "Addr: 0x40\n"
        "Sensor: INA219"
    )
    info_props = dict(boxstyle="round,pad=0.4", facecolor="#AED6F1",
                      edgecolor="#2E86C1", alpha=0.8)
    ax_v.text(0.02, 0.97, info_text, transform=ax_v.transAxes,
              fontsize=9, va="top", ha="left", bbox=info_props,
              color="#1B4F72", family="monospace", fontweight="bold")

    # --- Save ---
    plt.tight_layout()
    out = os.path.join("experiments", "output", "result8_i2c_bus.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    plt.savefig(out, dpi=200, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"  -> Saved: {out}")
    return out


# ===========================================================================
#  MAIN
# ===========================================================================

def main():
    print("=" * 55)
    print("  RESULT 8 — I2C Bus Graph (Separate)")
    print("=" * 55)

    config = make_config()

    print("\n  Running Bodyguard scenario...")
    bodyguard = run_scenario("Bodyguard Emergency", config, seed=42, protected=True)

    print("  Running Baseline scenario...")
    baseline = run_scenario("Baseline No Protection", config, seed=42, protected=False)

    print("\n  Generating I2C bus chart...")
    chart_path = make_i2c_bus_chart(bodyguard, baseline)

    print(f"\n  Output: {chart_path}")
    print("=" * 55)


if __name__ == "__main__":
    main()
