"""
Patent Evidence — Experiment 1: 24-Hour Uptime & Crash Count
=============================================================

PURPOSE:
  Compare Baseline (no Bodyguard protection) vs Bodyguard (full system)
  over a simulated 24-hour period. This is the HEADLINE result for the patent:
  "Baseline: X reboots → Bodyguard: 0 reboots."

PHYSICS CALIBRATION:
  The thermal equilibrium equation from our PhysicsSimulator is:
    T_eq = T_ambient + P_cpu / (thermal_mass × cooling_rate)

  We calibrate so that:
    100% CPU → T_eq = 85°C  (above T_crit=80°C → reboots)
     60% CPU → T_eq = 65°C  (comfortably below T_crit → safe)
     40% CPU → T_eq = 55°C  (well below T_crit → very safe)

  This means the device CAN handle moderate load, but sustained high load
  causes overheating. The Bodyguard offloads excess tasks to keep load at
  ~50-60%, while Baseline runs everything locally at ~80-100%.

REBOOT MODEL:
  When T ≥ T_crit (80°C), the device reboots:
    - Temperature resets toward ambient (fast cool during shutdown)
    - All running tasks are lost (active_load = 0)
    - 60-second boot time (device offline)
    - After boot, workload generator resumes pushing tasks
    - Without protection → overheats again → cyclical reboots

RUN:
  python experiments/exp1_uptime.py
"""
import sys
import os
import random
import csv
import math

# Add parent directory for bodyguard imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from bodyguard.config import BodyguardConfig
from bodyguard.controller import BodyguardController
from bodyguard.admission import Task, TaskPriority, RoutingDecision


# ===========================================================================
#  CONFIGURATION
# ===========================================================================

def make_config():
    """
    Realistic Raspberry Pi 4 in a warm IoT enclosure.

    CALIBRATION MATH:
      T_eq = T_ambient + (load_fraction × max_thermal_power) / (thermal_mass × cooling_rate)
      With thermal_mass=8, cooling_rate=0.015:
        100% CPU: 35 + (1.0 × 6.0) / (8 × 0.015) = 35 + 50.0 = 85°C → ABOVE T_crit
         70% CPU: 35 + (0.7 × 6.0) / (8 × 0.015) = 35 + 35.0 = 70°C → Below T_crit
         50% CPU: 35 + (0.5 × 6.0) / (8 × 0.015) = 35 + 25.0 = 60°C → Safe
         30% CPU: 35 + (0.3 × 6.0) / (8 × 0.015) = 35 + 15.0 = 50°C → Very safe
    """
    config = BodyguardConfig()

    # --- Thermal: calibrated to overheat at sustained high load ---
    config.thermal.ambient_temp = 35.0       # Warm enclosure (typical IoT)
    config.thermal.T_safe = 65.0             # ARM throttle point
    config.thermal.T_crit = 80.0             # Hard shutdown (real Pi 4 = 85°C)
    config.thermal.passive_cooling_rate = 0.015  # Calibrated for T_eq math above
    config.thermal.thermal_mass = 8.0        # Small passive heatsink
    config.thermal.s_safe = 0.5
    config.thermal.s_max = 5.0

    # --- Power: realistic 5V USB-C ---
    config.power.V_nominal = 5.10
    config.power.V_safe = 4.85
    config.power.V_crit = 4.63               # Pi undervoltage detection
    config.power.psu_impedance = 0.30
    config.power.psu_noise_stddev = 0.012
    config.power.dV_max = 0.50
    config.power.sigma_max = 0.10

    # --- Risk weights ---
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


# ===========================================================================
#  WORKLOAD GENERATOR
# ===========================================================================

def get_workload_intensity(sim_time):
    """
    Day/night cycle for a smart-building IoT gateway.

    Returns a multiplier [0.0, 1.0]:
      08:00-18:00  →  1.0  (business hours: inference, dashboards, alerts)
      18:00-23:00  →  0.5  (evening: reduced but active)
      23:00-08:00  →  0.2  (night: batch analytics, health checks)
    """
    hour = (sim_time / 3600) % 24
    if 8 <= hour < 18:
        return 1.0
    elif 18 <= hour < 23:
        return 0.5
    else:
        return 0.2


# ===========================================================================
#  24-HOUR SIMULATION
# ===========================================================================

def run_24h(label, config, seed=42, protected=True):
    """
    Simulate 24 hours with reboot modeling.

    Args:
        label: Name for this run
        config: BodyguardConfig
        seed: Deterministic seed
        protected: True=Bodyguard enabled, False=no protection (baseline)

    Returns:
        dict with all metrics
    """
    dt = config.sampling.interval   # 2 seconds
    total_time = 24 * 3600          # 86400 seconds
    total_steps = int(total_time / dt)  # 43200 steps

    rng = random.Random(seed + 7)

    # Baseline disables all protection
    kwargs = {}
    if not protected:
        kwargs = {"disable_state_machine": True, "disable_budget": True}

    ctrl = BodyguardController(
        config=config, output_dir="experiments/output",
        log_prefix=f"exp1_{label.lower().replace(' ', '_')}",
        seed=seed, **kwargs,
    )

    active_load = 0.0
    base_idle = 3.0

    # Reboot tracking
    reboot_count = 0
    reboot_cooldown = 0
    REBOOT_STEPS = 30            # 60 seconds to reboot
    total_downtime = 0.0
    hourly_reboots = [0] * 24

    # Timeline (sample every 5 min = 150 steps for plotting)
    timeline = []
    TIMELINE_INTERVAL = 150

    print(f"  Running {label}... ({total_steps} steps = 24h)")

    for step in range(total_steps):
        sim_time = step * dt

        # --- REBOOT COOLDOWN ---
        if reboot_cooldown > 0:
            reboot_cooldown -= 1
            total_downtime += dt
            # Device is OFF: temperature drops toward ambient
            ctrl._simulator._temperature = max(
                config.thermal.ambient_temp,
                ctrl._simulator._temperature - 1.5  # Cool ~45°C over 60s reboot
            )
            ctrl.set_load(0.0, queue_depth=0)
            ctrl.sample(dt=dt)

            if step % TIMELINE_INTERVAL == 0:
                r = ctrl._latest_reading
                if r:
                    timeline.append({
                        "time": sim_time, "temp": r.temperature,
                        "voltage": r.voltage, "state": "REBOOT",
                        "load": 0.0,
                    })
            continue

        # --- NORMAL OPERATION ---
        # Tasks decay as they complete
        active_load *= 0.92
        if active_load < 0.3:
            active_load = 0.0

        total = base_idle + active_load
        ctrl.set_load(min(99.0, total), queue_depth=max(0, int(active_load / 8)))
        bd = ctrl.sample(dt=dt)

        # Check for reboot condition
        reading = ctrl._latest_reading
        if reading and (reading.temperature >= config.thermal.T_crit
                        or reading.voltage <= config.power.V_crit):
            reboot_count += 1
            hour_idx = min(int(sim_time / 3600), 23)
            hourly_reboots[hour_idx] += 1
            reboot_cooldown = REBOOT_STEPS
            active_load = 0.0          # All tasks lost on crash
            ctrl._in_failure_state = False
            continue

        # --- GENERATE WORKLOAD ---
        intensity = get_workload_intensity(sim_time)

        # Task generation: ~0.4 tasks/step at full intensity
        # Each task: 2-8% CPU. Steady-state with 0.92 decay:
        #   ~0.4 tasks/step × 5% avg = 2% per step added
        #   Equilibrium at ~25% from tasks + 3% idle = ~28% CPU (safe)
        # BUT during bursts or sustained periods → can reach 70%+ → danger
        if rng.random() < 0.40 * intensity:
            num_tasks = 1
        else:
            num_tasks = 0

        # Periodic heavy bursts (3% chance during business hours)
        # These push load to 60-80% for short periods
        if rng.random() < 0.03 * intensity:
            num_tasks += rng.randint(2, 4)

        for i in range(num_tasks):
            weight = rng.uniform(0.20, 0.80)
            cpu_demand = weight * 10.0   # 2% – 8% per task
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
        if step % TIMELINE_INTERVAL == 0 and reading:
            timeline.append({
                "time": sim_time, "temp": reading.temperature,
                "voltage": reading.voltage, "state": ctrl.state.value,
                "load": total,
            })

        # Progress every 6 hours
        if step > 0 and step % (total_steps // 4) == 0:
            h = sim_time / 3600
            print(f"    [{h:.0f}h] T={reading.temperature:.1f}C  "
                  f"V={reading.voltage:.3f}V  reboots={reboot_count}  "
                  f"CPU={total:.0f}%")

    stats = ctrl.stats
    csv_path = ctrl._logger._filepath
    ctrl.close()

    uptime_pct = ((total_time - total_downtime) / total_time) * 100

    return {
        "label": label,
        "reboots": reboot_count,
        "downtime_sec": total_downtime,
        "uptime_pct": uptime_pct,
        "hourly_reboots": hourly_reboots,
        "timeline": timeline,
        "local": stats["local"],
        "offloaded": stats["offloaded"],
        "total_tasks": stats["total"],
        "csv_path": csv_path,
    }


# ===========================================================================
#  PLOTTING
# ===========================================================================

def make_plots(baseline, bodyguard, config):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    fig.suptitle("24-Hour Uptime & Crash Count",
                 fontsize=14, fontweight="bold")

    # 1. Temperature over 24h
    ax = axes[0, 0]
    for res, color, lbl in [(baseline, "#c0392b", "Baseline (No Protection)"), (bodyguard, "#27ae60", "PAHPS (Full System)")]:
        t = [d["time"] / 3600 for d in res["timeline"]]
        temp = [d["temp"] for d in res["timeline"]]
        ax.plot(t, temp, color=color, label=lbl, lw=1.0, alpha=0.85)
    ax.axhline(y=config.thermal.T_crit, color="#c0392b", ls="--", alpha=0.4,
               label="T_crit (80C)")
    ax.axhline(y=config.thermal.T_safe, color="#e67e22", ls="--", alpha=0.4,
               label="T_safe (65C)")
    ax.set_xlabel("Time (hours)")
    ax.set_ylabel("Temperature (C)")
    ax.set_title("Temperature Over 24 Hours")
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, 24)

    # 2. Voltage over 24h
    ax = axes[0, 1]
    for res, color, lbl in [(baseline, "#c0392b", "Baseline (No Protection)"), (bodyguard, "#27ae60", "PAHPS (Full System)")]:
        t = [d["time"] / 3600 for d in res["timeline"]]
        v = [d["voltage"] for d in res["timeline"]]
        ax.plot(t, v, color=color, label=lbl, lw=1.0, alpha=0.85)
    ax.axhline(y=config.power.V_crit, color="#c0392b", ls="--", alpha=0.4,
               label="V_crit (4.63V)")
    ax.set_xlabel("Time (hours)")
    ax.set_ylabel("Voltage (V)")
    ax.set_title("Supply Voltage Over 24 Hours")
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, 24)

    # 3. Reboot comparison
    ax = axes[1, 0]
    names = ["Baseline\n(No Protection)", "PAHPS\n(Full System)"]
    vals = [baseline["reboots"], bodyguard["reboots"]]
    colors = ["#c0392b", "#27ae60"]
    bars = ax.bar(names, vals, color=colors, edgecolor="white", lw=2, width=0.5)
    for bar, val in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2,
                bar.get_height() + max(max(vals), 1) * 0.04,
                str(val), ha="center", va="bottom", fontweight="bold", fontsize=16)
    ax.set_ylabel("Reboot Count")
    ax.set_title("Total Reboots in 24 Hours")
    ax.grid(True, axis="y", alpha=0.3)

    # 4. Hourly reboot distribution
    ax = axes[1, 1]
    hours = list(range(24))
    w = 0.35
    ax.bar([h - w/2 for h in hours], baseline["hourly_reboots"],
           w, label="Baseline", color="#c0392b", alpha=0.8)
    ax.bar([h + w/2 for h in hours], bodyguard["hourly_reboots"],
           w, label="PAHPS", color="#27ae60", alpha=0.8)
    ax.set_xlabel("Hour of Day")
    ax.set_ylabel("Reboots per Hour")
    ax.set_title("Reboot Distribution by Hour")
    ax.legend(fontsize=8)
    ax.grid(True, axis="y", alpha=0.3)
    ax.set_xticks([0, 4, 8, 12, 16, 20])
    ax.set_xticklabels(["00:00", "04:00", "08:00", "12:00", "16:00", "20:00"])

    plt.tight_layout()
    outpath = "experiments/output/exp1_uptime.png"
    plt.savefig(outpath, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  -> {outpath}")


# ===========================================================================
#  MAIN
# ===========================================================================

def main():
    os.makedirs("experiments/output", exist_ok=True)
    config = make_config()

    # Verify calibration
    mass = config.thermal.thermal_mass
    rate = config.thermal.passive_cooling_rate
    amb = config.thermal.ambient_temp
    pmax = 6.0  # max_thermal_power from PhysicsSimulator
    print("THERMAL CALIBRATION CHECK:")
    for load_pct in [30, 50, 70, 100]:
        teq = amb + (load_pct / 100 * pmax) / (mass * rate)
        safe = "SAFE" if teq < config.thermal.T_crit else "OVERHEATS"
        print(f"  {load_pct:3d}% CPU -> T_eq = {teq:.1f}C  [{safe}]")
    print()

    print("=" * 65)
    print("  EXPERIMENT 1: 24-Hour Uptime & Crash Count")
    print("=" * 65)

    baseline = run_24h("Baseline (No Protection)", config, seed=42, protected=False)
    bodyguard = run_24h("Bodyguard (Full System)", config, seed=42, protected=True)

    # --- RESULT TABLE ---
    print("\n" + "=" * 65)
    print("  RESULT 1: Uptime & Crash Count (Patent Evidence)")
    print("=" * 65)
    print(f"  {'Metric':<28} {'Baseline':>15} {'Bodyguard':>15}")
    print("-" * 65)
    print(f"  {'Reboots in 24h':<28} {baseline['reboots']:>15} "
          f"{bodyguard['reboots']:>15}")
    print(f"  {'Total Downtime (min)':<28} "
          f"{baseline['downtime_sec']/60:>15.1f} "
          f"{bodyguard['downtime_sec']/60:>15.1f}")
    print(f"  {'Uptime (%)':<28} {baseline['uptime_pct']:>14.1f}% "
          f"{bodyguard['uptime_pct']:>14.1f}%")
    print(f"  {'Tasks Executed Locally':<28} {baseline['local']:>15} "
          f"{bodyguard['local']:>15}")
    print(f"  {'Tasks Offloaded to Cloud':<28} {baseline['offloaded']:>15} "
          f"{bodyguard['offloaded']:>15}")
    print(f"  {'Total Tasks Submitted':<28} {baseline['total_tasks']:>15} "
          f"{bodyguard['total_tasks']:>15}")
    print("-" * 65)

    # Save CSV
    csv_path = "experiments/output/exp1_results.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metric", "baseline", "bodyguard"])
        w.writerow(["reboots_24h", baseline["reboots"], bodyguard["reboots"]])
        w.writerow(["downtime_min",
                     f"{baseline['downtime_sec']/60:.1f}",
                     f"{bodyguard['downtime_sec']/60:.1f}"])
        w.writerow(["uptime_pct",
                     f"{baseline['uptime_pct']:.1f}",
                     f"{bodyguard['uptime_pct']:.1f}"])
        w.writerow(["tasks_local", baseline["local"], bodyguard["local"]])
        w.writerow(["tasks_offloaded", baseline["offloaded"], bodyguard["offloaded"]])
    print(f"\n  -> {csv_path}")

    # Generate plot
    print("\nGenerating plots...")
    try:
        make_plots(baseline, bodyguard, config)
    except ImportError:
        print("  matplotlib not available, skipping plots")


if __name__ == "__main__":
    main()
