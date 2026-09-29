"""
Experiment 1 — Uptime & Crash Count (24-hour simulation)
=========================================================

Patent Evidence: Compares Baseline (no protection) vs Bodyguard (full system)
over a simulated 24-hour period with realistic IoT workload.

Reboot Model:
  When device hits T_crit or V_crit → hardware shutdown + reboot.
  Reboot takes ~60 seconds (device cools to ambient, load clears).
  After reboot, workload resumes and device heats up again.
  Each cycle = 1 reboot counted.

Expected Result:
  Baseline:  Multiple reboots (device repeatedly overheats)
  Bodyguard: 0 reboots (predictive offloading keeps temp safe)
"""
import sys
import os
import random
import csv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bodyguard.config import BodyguardConfig
from bodyguard.controller import BodyguardController
from bodyguard.admission import Task, TaskPriority, RoutingDecision


def make_config():
    """Production-tuned config for Raspberry Pi 4 simulation."""
    config = BodyguardConfig()

    # --- Thermal: realistic Pi 4 parameters ---
    config.thermal.ambient_temp = 35.0       # Warm enclosure (IoT deployment)
    config.thermal.T_safe = 65.0             # Arm throttle threshold
    config.thermal.T_crit = 80.0             # Shutdown threshold (real Pi 4 = 85°C)
    config.thermal.passive_cooling_rate = 0.03
    config.thermal.thermal_mass = 20.0       # Heatsink-equipped Pi 4
    config.thermal.s_safe = 0.5              # °C/min acceptable rise
    config.thermal.s_max = 5.0

    # --- Power: realistic 5V USB-C supply ---
    config.power.V_nominal = 5.10
    config.power.V_safe = 4.85
    config.power.V_crit = 4.63              # Pi undervoltage threshold
    config.power.psu_impedance = 0.35        # Moderate PSU with some drop under load
    config.power.psu_noise_stddev = 0.012
    config.power.dV_max = 0.50
    config.power.sigma_max = 0.10

    # --- Weights ---
    config.weights.w1_thermal_proximity = 0.12
    config.weights.w2_thermal_velocity = 0.25
    config.weights.w3_voltage_sag = 0.13
    config.weights.w4_voltage_drop_rate = 0.20
    config.weights.w5_voltage_instability = 0.10
    config.weights.w6_load_pressure = 0.20

    # --- State machine ---
    config.state_machine.safe_to_warning = 0.25
    config.state_machine.warning_to_safe = 0.18
    config.state_machine.warning_to_critical = 0.55
    config.state_machine.critical_to_warning = 0.42
    config.state_machine.cold_start_min_samples = 9

    # --- Budget ---
    config.budget.B_max = 10
    config.budget.window_duration = 30.0
    config.budget.R_replenish = 0.20

    # --- Sampling ---
    config.sampling.interval = 2.0
    config.sampling.history_depth = 12
    config.sampling.derivative_span = 8

    config.validate()
    return config


def simulate_24h(label, config, seed=42, protected=True):
    """
    Simulate 24 hours of IoT workload with reboot modeling.

    Args:
        label: Test label
        config: BodyguardConfig
        seed: Random seed
        protected: True = Bodyguard enabled, False = Baseline (no protection)

    Returns:
        dict with reboot_count, total_downtime_sec, timeline, etc.
    """
    dt = config.sampling.interval  # 2 seconds per step
    total_sim_time = 24 * 3600      # 24 hours = 86400 seconds
    total_steps = int(total_sim_time / dt)  # 43200 steps

    rng = random.Random(seed + 7)

    # Controller kwargs
    ctrl_kwargs = {}
    if not protected:
        # Baseline: disable all protection → everything runs locally
        ctrl_kwargs = {
            "disable_state_machine": True,
            "disable_budget": True,
        }

    ctrl = BodyguardController(
        config=config, output_dir="evidence",
        log_prefix=f"exp1_{label.lower().replace(' ', '_')}",
        seed=seed, **ctrl_kwargs,
    )

    active_load = 0.0
    base_idle = 3.0  # Minimal background processes

    # Reboot tracking
    reboot_count = 0
    reboot_cooldown = 0  # Steps remaining in reboot cooldown
    reboot_duration_steps = 30  # 60 seconds reboot time (30 × 2s)
    total_downtime_sec = 0.0

    # Timeline for plotting (sample every 5 minutes = 150 steps)
    timeline = []
    sample_interval = 150

    # Hour-by-hour summary
    hourly_reboots = [0] * 24

    # Workload pattern: realistic IoT with day/night cycle
    def get_workload_intensity(sim_time):
        """Returns workload multiplier based on time of day."""
        hour = (sim_time / 3600) % 24
        # Business hours (8am-6pm): high load
        # Evening (6pm-11pm): moderate
        # Night (11pm-8am): low but not zero (analytics, backups)
        if 8 <= hour < 18:
            return 1.0    # Full load
        elif 18 <= hour < 23:
            return 0.6    # Evening
        else:
            return 0.25   # Night (still running batch jobs)

    print(f"  Simulating {label}... ({total_steps} steps = 24h)")

    for step in range(total_steps):
        sim_time = step * dt

        # --- Reboot cooldown ---
        if reboot_cooldown > 0:
            reboot_cooldown -= 1
            total_downtime_sec += dt
            # During reboot: device is OFF, temp drops toward ambient
            ctrl._simulator._temperature = max(
                config.thermal.ambient_temp,
                ctrl._simulator._temperature - 2.0  # Fast cool during shutdown
            )
            ctrl.set_load(0.0, queue_depth=0)
            ctrl.sample(dt=dt)
            if step % sample_interval == 0:
                reading = ctrl._latest_reading
                if reading:
                    timeline.append({
                        "time": sim_time, "temperature": reading.temperature,
                        "voltage": reading.voltage, "state": "REBOOTING",
                        "active_load": 0.0,
                    })
            continue

        # --- Normal operation ---
        # Load decay (tasks complete over time)
        active_load *= 0.90  # Tasks complete/decay
        if active_load < 0.5:
            active_load = 0.0

        total = base_idle + active_load
        ctrl.set_load(min(99.0, total), queue_depth=max(0, int(active_load / 8)))
        bd = ctrl.sample(dt=dt)

        # Check for thermal/voltage failure
        reading = ctrl._latest_reading
        if reading:
            hit_thermal = reading.temperature >= config.thermal.T_crit
            hit_voltage = reading.voltage <= config.power.V_crit

            if hit_thermal or hit_voltage:
                # REBOOT: device crashes and restarts
                reboot_count += 1
                hour_idx = min(int(sim_time / 3600), 23)
                hourly_reboots[hour_idx] += 1
                reboot_cooldown = reboot_duration_steps
                active_load = 0.0  # All tasks lost
                # Reset controller state for fresh start
                ctrl._in_failure_state = False
                continue

        # --- Generate workload ---
        intensity = get_workload_intensity(sim_time)

        # Task arrival rate scales with intensity
        if rng.random() < 0.45 * intensity:
            num_tasks = 1
        else:
            num_tasks = 0

        # Occasional burst (simulates user request or analytics job)
        if rng.random() < 0.015 * intensity:
            num_tasks += rng.randint(1, 3)

        for i in range(num_tasks):
            weight = rng.uniform(0.20, 0.80)
            cpu_demand = weight * 10.0  # 2.0% – 8.0% per task
            pri = rng.choices(list(TaskPriority), weights=[25, 40, 25, 10])[0]
            task = Task(
                task_id=f"t{step}_{i}", weight=weight,
                priority=pri, cpu_load=cpu_demand,
            )
            result = ctrl.submit_task(task)
            if result.decision == RoutingDecision.LOCAL:
                active_load += cpu_demand
            elif result.decision == RoutingDecision.THROTTLE:
                active_load += cpu_demand * 0.4

        # Record timeline
        if step % sample_interval == 0 and reading:
            timeline.append({
                "time": sim_time, "temperature": reading.temperature,
                "voltage": reading.voltage, "state": ctrl.state.value,
                "active_load": active_load,
            })

        # Progress every 6 hours
        if step > 0 and step % (total_steps // 4) == 0:
            hour = sim_time / 3600
            print(f"    [{hour:.0f}h] T={reading.temperature:.1f}°C  "
                  f"V={reading.voltage:.3f}V  reboots={reboot_count}")

    stats = ctrl.stats
    ctrl.close()

    uptime_pct = ((total_sim_time - total_downtime_sec) / total_sim_time) * 100

    return {
        "label": label,
        "reboot_count": reboot_count,
        "total_downtime_sec": total_downtime_sec,
        "uptime_percent": uptime_pct,
        "hourly_reboots": hourly_reboots,
        "timeline": timeline,
        "routing": stats,
        "protected": protected,
    }


def generate_exp1_plot(baseline, bodyguard, config):
    """Generate Experiment 1 evidence plot."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    fig.suptitle("Experiment 1: 24-Hour Uptime & Crash Count",
                 fontsize=14, fontweight="bold")

    # --- Temperature over 24h ---
    ax = axes[0, 0]
    for res, color, ls in [(baseline, "#c0392b", "-"), (bodyguard, "#27ae60", "-")]:
        t = [d["time"] / 3600 for d in res["timeline"]]
        temp = [d["temperature"] for d in res["timeline"]]
        ax.plot(t, temp, color=color, label=res["label"], lw=1.0, alpha=0.85, ls=ls)
    ax.axhline(y=config.thermal.T_crit, color="#c0392b", ls="--", alpha=0.4,
               label=f"T_crit ({config.thermal.T_crit}°C)")
    ax.axhline(y=config.thermal.T_safe, color="#e67e22", ls="--", alpha=0.4,
               label=f"T_safe ({config.thermal.T_safe}°C)")
    ax.set_xlabel("Time (hours)")
    ax.set_ylabel("Temperature (°C)")
    ax.set_title("Temperature Over 24 Hours")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, 24)

    # --- Voltage over 24h ---
    ax = axes[0, 1]
    for res, color in [(baseline, "#c0392b"), (bodyguard, "#27ae60")]:
        t = [d["time"] / 3600 for d in res["timeline"]]
        volt = [d["voltage"] for d in res["timeline"]]
        ax.plot(t, volt, color=color, label=res["label"], lw=1.0, alpha=0.85)
    ax.axhline(y=config.power.V_crit, color="#c0392b", ls="--", alpha=0.4,
               label=f"V_crit ({config.power.V_crit}V)")
    ax.set_xlabel("Time (hours)")
    ax.set_ylabel("Voltage (V)")
    ax.set_title("Supply Voltage Over 24 Hours")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, 24)

    # --- Reboot comparison bar chart ---
    ax = axes[1, 0]
    names = [baseline["label"], bodyguard["label"]]
    reboots = [baseline["reboot_count"], bodyguard["reboot_count"]]
    colors = ["#c0392b", "#27ae60"]
    bars = ax.bar(names, reboots, color=colors, edgecolor="white", lw=1.5)
    ax.set_ylabel("Reboot Count")
    ax.set_title("Total Reboots in 24 Hours")
    ax.grid(True, axis="y", alpha=0.3)
    for bar, val in zip(bars, reboots):
        ax.text(bar.get_x() + bar.get_width() / 2,
                bar.get_height() + max(max(reboots), 1) * 0.03,
                str(val), ha="center", va="bottom", fontweight="bold", fontsize=14)

    # --- Hourly reboot heatmap ---
    ax = axes[1, 1]
    hours = list(range(24))
    ax.bar([h - 0.2 for h in hours], baseline["hourly_reboots"],
           0.4, label=baseline["label"], color="#c0392b", alpha=0.8)
    ax.bar([h + 0.2 for h in hours], bodyguard["hourly_reboots"],
           0.4, label=bodyguard["label"], color="#27ae60", alpha=0.8)
    ax.set_xlabel("Hour of Day")
    ax.set_ylabel("Reboots")
    ax.set_title("Reboots by Hour")
    ax.legend(fontsize=8)
    ax.grid(True, axis="y", alpha=0.3)
    ax.set_xticks([0, 4, 8, 12, 16, 20])
    ax.set_xticklabels(["00:00", "04:00", "08:00", "12:00", "16:00", "20:00"])

    plt.tight_layout()
    plt.savefig("evidence/exp1_uptime.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  -> evidence/exp1_uptime.png")


def main():
    os.makedirs("evidence", exist_ok=True)
    config = make_config()

    print("=" * 60)
    print("  EXPERIMENT 1: 24-Hour Uptime & Crash Count")
    print("=" * 60)

    # --- Baseline: No protection ---
    baseline = simulate_24h("Baseline (No Protection)", config,
                            seed=42, protected=False)

    # --- Bodyguard: Full system ---
    bodyguard = simulate_24h("Bodyguard (Full System)", config,
                             seed=42, protected=True)

    # --- Results ---
    print("\n" + "=" * 60)
    print("  RESULT 1: Uptime & Crash Count")
    print("=" * 60)
    print(f"  {'Metric':<25} {'Baseline':>15} {'Bodyguard':>15}")
    print("-" * 60)
    print(f"  {'Reboots in 24h':<25} {baseline['reboot_count']:>15} "
          f"{bodyguard['reboot_count']:>15}")
    print(f"  {'Downtime (min)':<25} "
          f"{baseline['total_downtime_sec']/60:>15.1f} "
          f"{bodyguard['total_downtime_sec']/60:>15.1f}")
    print(f"  {'Uptime %':<25} {baseline['uptime_percent']:>14.1f}% "
          f"{bodyguard['uptime_percent']:>14.1f}%")

    b_stats = baseline["routing"]
    g_stats = bodyguard["routing"]
    print(f"  {'Tasks Local':<25} {b_stats['local']:>15} {g_stats['local']:>15}")
    print(f"  {'Tasks Offloaded':<25} {b_stats['offloaded']:>15} "
          f"{g_stats['offloaded']:>15}")
    print("-" * 60)

    # Generate plot
    print("\nGenerating plot...")
    try:
        generate_exp1_plot(baseline, bodyguard, config)
    except ImportError:
        print("  matplotlib not available")

    # Save results as CSV
    with open("evidence/exp1_results.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metric", "baseline", "bodyguard"])
        w.writerow(["reboots_24h", baseline["reboot_count"],
                     bodyguard["reboot_count"]])
        w.writerow(["downtime_minutes",
                     f"{baseline['total_downtime_sec']/60:.1f}",
                     f"{bodyguard['total_downtime_sec']/60:.1f}"])
        w.writerow(["uptime_percent",
                     f"{baseline['uptime_percent']:.1f}",
                     f"{bodyguard['uptime_percent']:.1f}"])
        w.writerow(["tasks_local", b_stats["local"], g_stats["local"]])
        w.writerow(["tasks_offloaded", b_stats["offloaded"],
                     g_stats["offloaded"]])
    print("  -> evidence/exp1_results.csv")


if __name__ == "__main__":
    main()
