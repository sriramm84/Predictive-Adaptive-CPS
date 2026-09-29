"""
Patent Evidence — Experiment 2: Time to First Critical Event
=============================================================

PURPOSE:
  Prove that derivative-based prediction (ΔT/Δt, ΔV/Δt) detects danger
  BEFORE static thresholds and enables earlier corrective routing.

MODES:
  1. Static Threshold — routing reacts ONLY when T ≥ T_safe (no rate info)
     (state machine ON, but derivatives disabled → risk from proximity only)
  2. Threshold + Derivatives — derivatives enabled → earlier risk detection
     → state machine transitions to WARNING sooner → earlier offloading
     (state machine ON, derivatives ON, no budget)
  3. Full Bodyguard — derivatives + budget + state machine
     → comprehensive protection

SCENARIO:
  Steadily ramping workload over 2 hours (simulating morning ramp-up in
  a smart building). Task arrival and intensity grow linearly.

  "Critical event" = first step where T ≥ T_crit (80°C)

PHYSICS:
  Using tight thermal margins:
    thermal_mass=5, cooling_rate=0.012 → T_eq at 100% = 35 + 6/(5×0.012) = 135°C
  This makes the device very responsive to load changes — small CPU increases
  cause rapid heating, so the derivative signal matters more.

RUN:
  python experiments/exp2_leadtime.py
"""
import sys
import os
import random
import csv

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from bodyguard.config import BodyguardConfig
from bodyguard.controller import BodyguardController
from bodyguard.admission import Task, TaskPriority, RoutingDecision


def make_config():
    """
    Config with tight thermal margins for clear derivative differentiation.

    T_eq = 35 + (load_frac × 6.0) / (5 × 0.012)
      30% CPU → 35 + 30.0 = 65°C  (hits T_safe)
      50% CPU → 35 + 50.0 = 85°C  (above T_crit!)
      40% CPU → 35 + 40.0 = 75°C  (close but safe)
    """
    config = BodyguardConfig()

    config.thermal.ambient_temp = 35.0
    config.thermal.T_safe = 65.0
    config.thermal.T_crit = 80.0
    config.thermal.passive_cooling_rate = 0.012
    config.thermal.thermal_mass = 5.0
    config.thermal.s_safe = 0.5
    config.thermal.s_max = 5.0

    config.power.V_nominal = 5.10
    config.power.V_safe = 4.85
    config.power.V_crit = 4.63
    config.power.psu_impedance = 0.30
    config.power.psu_noise_stddev = 0.012
    config.power.dV_max = 0.50
    config.power.sigma_max = 0.10

    config.weights.w1_thermal_proximity = 0.12
    config.weights.w2_thermal_velocity = 0.25
    config.weights.w3_voltage_sag = 0.13
    config.weights.w4_voltage_drop_rate = 0.20
    config.weights.w5_voltage_instability = 0.10
    config.weights.w6_load_pressure = 0.20

    config.state_machine.safe_to_warning = 0.25
    config.state_machine.warning_to_safe = 0.18
    config.state_machine.warning_to_critical = 0.55
    config.state_machine.critical_to_warning = 0.42
    config.state_machine.cold_start_min_samples = 9

    config.budget.B_max = 10
    config.budget.window_duration = 30.0
    config.budget.R_replenish = 0.20

    config.sampling.interval = 2.0
    config.sampling.history_depth = 12
    config.sampling.derivative_span = 8

    config.validate()
    return config


def run_mode(label, config, seed=42, **ctrl_kwargs):
    """
    2-hour simulation with ramping workload.
    Returns metrics and timeline.
    """
    dt = config.sampling.interval
    total_time = 2 * 3600           # 7200 sec
    total_steps = int(total_time / dt)  # 3600

    rng = random.Random(seed + 7)

    ctrl = BodyguardController(
        config=config, output_dir="experiments/output",
        log_prefix=f"exp2_{label[:8].lower().replace(' ', '_')}",
        seed=seed, **ctrl_kwargs,
    )

    active_load = 0.0
    base_idle = 3.0
    first_critical_step = None
    peak_temp = 0.0

    timeline = []
    SAMPLE_EVERY = 5   # every 10 seconds

    for step in range(total_steps):
        sim_time = step * dt

        # Decay
        active_load *= 0.93
        if active_load < 0.3:
            active_load = 0.0

        total = base_idle + active_load
        ctrl.set_load(min(99.0, total), queue_depth=max(0, int(active_load / 8)))
        bd = ctrl.sample(dt=dt)

        reading = ctrl._latest_reading
        if reading:
            if reading.temperature > peak_temp:
                peak_temp = reading.temperature
            if first_critical_step is None and reading.temperature >= config.thermal.T_crit:
                first_critical_step = step

        # --- RAMPING WORKLOAD ---
        progress = step / total_steps  # 0→1 over 2 hours

        # Arrival: 25% → 75%
        arrival_prob = 0.25 + 0.50 * progress

        # CPU per task: scales up
        cpu_mult = 6.0 + 10.0 * progress  # 6→16

        if rng.random() < arrival_prob:
            num_tasks = 1
            if rng.random() < 0.10 + 0.15 * progress:
                num_tasks = 2
        else:
            num_tasks = 0

        # Burst every ~8 min
        if step > 0 and step % 240 == 0:
            num_tasks += int(2 + 4 * progress)

        for i in range(num_tasks):
            weight = rng.uniform(0.20, 0.85)
            cpu_demand = weight * cpu_mult
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

        if step % SAMPLE_EVERY == 0 and reading:
            timeline.append({
                "time_min": sim_time / 60,
                "temperature": reading.temperature,
                "voltage": reading.voltage,
                "risk_score": bd.risk_score,
                "cpu_load": total,
                "state": ctrl.state.value,
            })

    stats = ctrl.stats
    ctrl.close()

    fc_min = (first_critical_step * dt / 60) if first_critical_step else None

    return {
        "label": label,
        "first_critical_min": fc_min,
        "peak_temp": peak_temp,
        "local": stats["local"],
        "offloaded": stats["offloaded"],
        "total_tasks": stats["total"],
        "timeline": timeline,
    }


def make_plots(results, config):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    modes = list(results.keys())
    colors = {
        "Static Threshold": "#c0392b",
        "Threshold+Deriv": "#e67e22",
        "Full Bodyguard": "#27ae60",
    }

    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    fig.suptitle("Experiment 2: Time to First Critical Event (2h Ramp)",
                 fontsize=14, fontweight="bold")

    # 1. Temperature
    ax = axes[0, 0]
    for name in modes:
        r = results[name]
        t = [d["time_min"] for d in r["timeline"]]
        temp = [d["temperature"] for d in r["timeline"]]
        ax.plot(t, temp, color=colors[name], label=name, lw=1.2, alpha=0.85)
        if r["first_critical_min"]:
            ax.axvline(x=r["first_critical_min"], color=colors[name],
                       ls=":", alpha=0.6, lw=2)
            ax.annotate(f'{r["first_critical_min"]:.0f} min',
                        xy=(r["first_critical_min"], config.thermal.T_crit),
                        fontsize=8, fontweight="bold", color=colors[name])
    ax.axhline(y=config.thermal.T_crit, color="red", ls="--", alpha=0.3, label="T_crit")
    ax.axhline(y=config.thermal.T_safe, color="orange", ls="--", alpha=0.3, label="T_safe")
    ax.set_xlabel("Time (min)"); ax.set_ylabel("Temperature (°C)")
    ax.set_title("Temperature Profile"); ax.legend(fontsize=7); ax.grid(True, alpha=0.3)
    ax.set_xlim(0, 120)

    # 2. Risk score
    ax = axes[0, 1]
    for name in modes:
        r = results[name]
        t = [d["time_min"] for d in r["timeline"]]
        risk = [d["risk_score"] for d in r["timeline"]]
        ax.plot(t, risk, color=colors[name], label=name, lw=1.2, alpha=0.85)
    ax.axhline(y=0.55, color="red", ls="--", alpha=0.3, label="CRITICAL")
    ax.axhline(y=0.25, color="orange", ls="--", alpha=0.3, label="WARNING")
    ax.set_xlabel("Time (min)"); ax.set_ylabel("Risk Score")
    ax.set_title("Risk Score Over Time"); ax.legend(fontsize=7)
    ax.set_ylim(-0.02, 1.02); ax.grid(True, alpha=0.3); ax.set_xlim(0, 120)

    # 3. Lead time bar chart
    ax = axes[1, 0]
    bar_names = []
    bar_vals = []
    bar_cols = []
    for name in modes:
        r = results[name]
        bar_names.append(name)
        bar_vals.append(r["first_critical_min"] if r["first_critical_min"] else 120)
        bar_cols.append(colors[name])
    bars = ax.bar(bar_names, bar_vals, color=bar_cols, edgecolor="white", lw=2, width=0.5)
    for bar, val, name in zip(bars, bar_vals, modes):
        r = results[name]
        if r["first_critical_min"]:
            lbl = f"{r['first_critical_min']:.1f} min"
        else:
            lbl = "No event\n(120 min)"
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2,
                lbl, ha="center", va="bottom", fontweight="bold", fontsize=11)
    ax.set_ylabel("Minutes to First Critical"); ax.set_title("Time to First Critical Event")
    ax.set_ylim(0, 145); ax.grid(True, axis="y", alpha=0.3)

    # 4. Task routing
    ax = axes[1, 1]
    lc = [results[n]["local"] for n in modes]
    oc = [results[n]["offloaded"] for n in modes]
    x = list(range(len(modes)))
    w = 0.30
    ax.bar([i-w/2 for i in x], lc, w, label="Local", color="#e74c3c", alpha=0.85)
    ax.bar([i+w/2 for i in x], oc, w, label="Offloaded", color="#2980b9", alpha=0.85)
    ax.set_ylabel("Tasks"); ax.set_title("Task Routing")
    ax.set_xticks(x); ax.set_xticklabels(modes, fontsize=9)
    ax.legend(fontsize=8); ax.grid(True, axis="y", alpha=0.3)

    plt.tight_layout()
    out = "experiments/output/exp2_leadtime.png"
    plt.savefig(out, dpi=150, bbox_inches="tight"); plt.close()
    print(f"  -> {out}")


def main():
    os.makedirs("experiments/output", exist_ok=True)
    config = make_config()

    # Calibration check
    mass = config.thermal.thermal_mass
    rate = config.thermal.passive_cooling_rate
    amb = config.thermal.ambient_temp
    print("THERMAL CALIBRATION:")
    for pct in [20, 30, 40, 50, 70]:
        teq = amb + (pct / 100 * 6.0) / (mass * rate)
        tag = "SAFE" if teq < config.thermal.T_crit else "DANGER"
        print(f"  {pct:3d}% CPU -> T_eq = {teq:.0f}C [{tag}]")
    print()

    print("=" * 65)
    print("  EXPERIMENT 2: Time to First Critical Event")
    print("=" * 65)

    # Mode 1: no derivatives, state machine uses proximity-only risk
    print("\n[1] Static Threshold (no derivatives)")
    r1 = run_mode("Static Threshold", config, seed=42,
                  disable_derivatives=True, disable_budget=True)

    # Mode 2: derivatives ON → risk rises earlier → state machine acts sooner
    print("[2] Threshold + Derivatives (no budget)")
    r2 = run_mode("Threshold+Deriv", config, seed=42,
                  disable_derivatives=False, disable_budget=True)

    # Mode 3: full system
    print("[3] Full Bodyguard")
    r3 = run_mode("Full Bodyguard", config, seed=42)

    results = {"Static Threshold": r1, "Threshold+Deriv": r2, "Full Bodyguard": r3}

    print("\n" + "=" * 65)
    print("  RESULT 2: Time to First Critical Event")
    print("=" * 65)
    print(f"  {'Mode':<22} {'1st Critical':>14} {'PeakT':>8} {'Local':>7} {'Offload':>8}")
    print("-" * 65)
    for name, r in results.items():
        crit = f"{r['first_critical_min']:.1f} min" if r['first_critical_min'] else "No event"
        print(f"  {name:<22} {crit:>14} {r['peak_temp']:>7.1f}C "
              f"{r['local']:>7} {r['offloaded']:>8}")
    print("-" * 65)

    csv_path = "experiments/output/exp2_results.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["mode", "first_critical_min", "peak_temp_C",
                     "tasks_local", "tasks_offloaded"])
        for name, r in results.items():
            cm = f"{r['first_critical_min']:.1f}" if r['first_critical_min'] else "none"
            w.writerow([name, cm, f"{r['peak_temp']:.1f}",
                        r["local"], r["offloaded"]])
    print(f"\n  -> {csv_path}")

    print("\nGenerating plots...")
    try:
        make_plots(results, config)
    except ImportError:
        print("  matplotlib not available")


if __name__ == "__main__":
    main()
