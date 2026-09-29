"""
Final Ablation Study — v5 (Post-Diagnostic Fix)
================================================

ROOT CAUSES IDENTIFIED BY DIAGNOSTIC TRACE:
1. x4 (dV/dt) spiking to 1.0 from PSU noise — NOT real voltage trends
2. x2 (dT/dt) spiking to 1.0 from random temp fluctuations
3. Temperature DECLINING (~39→33°C) because load is too low (~10% CPU)
4. Derivative-triggered WARNING only lasting 2-4 steps (noise, not trend)

FIXES:
- Increase derivative_span to 8 (16s window) → captures trends, not noise
- Reduce PSU noise (psu_noise_stddev 0.02→0.008) → less false x4 spikes
- Raise dV_max to 0.5 → normalize dV/dt less aggressively
- Increase task arrival significantly → CPU at 40-60% → sustained temp rise
- Lower thermal mass to 12 → temp responds to load in reasonable time
"""
import sys
import os
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bodyguard.config import BodyguardConfig
from bodyguard.controller import BodyguardController
from bodyguard.admission import Task, TaskPriority, RoutingDecision


def make_config():
    config = BodyguardConfig()

    # --- Thermal ---
    config.thermal.ambient_temp = 30.0
    config.thermal.T_safe = 44.0            # Reachable under moderate load
    config.thermal.T_crit = 50.0            # Tight margin — only 6°C headroom above T_safe
    config.thermal.passive_cooling_rate = 0.02
    config.thermal.thermal_mass = 10.0      # Responsive — temp changes compound faster
    config.thermal.s_safe = 0.3             # °C/min — gentle rise is OK
    config.thermal.s_max = 5.0              # °C/min — max for normalization

    # --- Power: clean PSU (low noise) so derivatives detect REAL trends ---
    config.power.V_nominal = 5.05
    config.power.V_safe = 4.85
    config.power.V_crit = 4.55
    config.power.psu_impedance = 0.25
    config.power.psu_noise_stddev = 0.008   # LOW noise — derivatives measure REAL trends
    config.power.dV_max = 0.50              # High denominator — only big drops score high
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
    config.state_machine.cold_start_min_samples = 9  # Wait for derivative span

    # --- Budget ---
    config.budget.B_max = 10
    config.budget.window_duration = 25.0     # Tighter windows → more budget decisions
    config.budget.R_replenish = 0.20

    # --- Sampling: LONGER derivative span to filter noise ---
    config.sampling.interval = 2.0
    config.sampling.history_depth = 12
    config.sampling.derivative_span = 8     # 16s window — trend, not noise

    config.validate()
    return config


def run_ablation_mode(label, config, duration_steps=600, seed=42, **kwargs):
    ctrl = BodyguardController(
        config=config, output_dir="evidence",
        log_prefix=label.lower().replace(" ", "_").replace("-", ""),
        seed=seed, **kwargs,
    )
    rng = random.Random(seed + 7)
    dt = config.sampling.interval
    active_load = 0.0
    base_idle = 3.0
    timeline = []

    for step in range(duration_steps):
        sim_time = step * dt
        active_load *= 0.93          # Slower decay → tasks linger longer thermally
        if active_load < 0.3:
            active_load = 0.0
        total = base_idle + active_load
        ctrl.set_load(min(99.0, total), queue_depth=max(0, int(active_load / 10)))
        bd = ctrl.sample(dt=dt)

        # Workload: ramps up to push temp toward T_crit boundary
        if step < 50:
            # Phase 1: Warm-up — light tasks to build derivative history
            num_tasks = 1 if rng.random() < 0.25 else 0
        elif step < 200:
            # Phase 2: Building load — temp rises toward T_safe (44°C)
            num_tasks = rng.choices([0, 1, 2], weights=[20, 45, 35])[0]
        elif step < 400:
            # Phase 3: Sustained heavy — this is the critical zone
            # Derivatives should detect rising trend here and offload
            # Without derivatives, extra local tasks push temp toward T_crit
            num_tasks = rng.choices([0, 1, 2, 3], weights=[10, 30, 35, 25])[0]
        else:
            # Phase 4: Sustained + heavy bursts
            if rng.random() < 0.25:
                num_tasks = rng.randint(3, 6)  # Bigger bursts
            else:
                num_tasks = rng.choices([1, 2, 3], weights=[30, 40, 30])[0]

        for i in range(num_tasks):
            weight = rng.uniform(0.15, 0.90)
            cpu_demand = weight * 20.0  # 3.0 – 18.0% per task
            pri = rng.choices(list(TaskPriority), weights=[25, 40, 25, 10])[0]
            task = Task(task_id=f"t{step}_{i}", weight=weight, priority=pri,
                        cpu_load=cpu_demand)
            result = ctrl.submit_task(task)
            if result.decision == RoutingDecision.LOCAL:
                active_load += cpu_demand
            elif result.decision == RoutingDecision.THROTTLE:
                active_load += cpu_demand * 0.4

        reading = ctrl._latest_reading
        if reading:
            timeline.append({
                "step": step, "time": sim_time,
                "temperature": reading.temperature,
                "voltage": reading.voltage,
                "cpu_percent": reading.cpu_percent,
                "risk_score": bd.risk_score,
                "state": ctrl.state.value,
                "budget": ctrl.budget_remaining,
                "active_load": active_load,
            })

    results = ctrl.get_experiment_results()
    results["timeline"] = timeline
    results["routing"] = ctrl.stats
    ctrl.close()
    return results


def main():
    os.makedirs("evidence", exist_ok=True)
    config = make_config()

    modes = [
        ("1-Full-System", {}),
        ("2-No-Derivatives", {"disable_derivatives": True}),
        ("3-No-Budget", {"disable_budget": True}),
        ("4-Threshold-Only", {"disable_state_machine": True, "disable_budget": True}),
    ]

    all_results = {}
    for label, kwargs in modes:
        print(f"Running {label}...")
        res = run_ablation_mode(label, config, duration_steps=800, **kwargs)
        all_results[label] = res
        ff = res["first_failure_sec"]
        ff_str = "None" if ff is None else f"{ff:.1f}s"
        s = res["routing"]
        print(f"  FailSec={res['failure_seconds']:>6.0f}s  Incidents={res['failure_incidents']:>3}  "
              f"PeakT={res['peak_temperature_C']:.1f}C  "
              f"Vfloor={res['voltage_floor_V']:.3f}V")
        print(f"  Local={s['local']:>4}  Offload={s['offloaded']:>4}  "
              f"Reject={s['rejected']:>3}  Total={s['total']}")

    print("\n" + "=" * 80)
    print("  ABLATION STUDY RESULTS")
    print("=" * 80)
    hdr = "{:<22} {:>9} {:>10} {:>8} {:>8} {:>7} {:>7} {:>7}"
    print(hdr.format("Mode", "FailSec", "Incidents", "PeakT", "Vfloor",
                     "Local", "Offld", "Total"))
    print("-" * 85)
    for label, r in all_results.items():
        s = r["routing"]
        print(hdr.format(label, f"{r['failure_seconds']:.0f}s",
                         r["failure_incidents"],
                         f"{r['peak_temperature_C']:.1f}C",
                         f"{r['voltage_floor_V']:.3f}V",
                         s["local"], s["offloaded"], s["total"]))
    print("-" * 85)

    print("\nGenerating plots...")
    try:
        generate_plots(all_results, config)
        print("Plots saved to evidence/")
    except ImportError:
        print("matplotlib not available")

    return all_results


def generate_plots(all_results, config):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = {"1-Full-System": "#27ae60", "2-No-Derivatives": "#e67e22",
              "3-No-Budget": "#c0392b", "4-Threshold-Only": "#2980b9"}
    labels = {"1-Full-System": "Full System", "2-No-Derivatives": "No Derivatives",
              "3-No-Budget": "No Budget", "4-Threshold-Only": "Threshold Only"}

    fig, axes = plt.subplots(3, 2, figsize=(16, 14))
    fig.suptitle("Bodyguard Ablation Study — Patent Evidence", fontsize=14, fontweight="bold")

    # --- Timeseries: Temperature, Voltage, Risk ---
    plot_defs = [
        (axes[0,0], "temperature", "Temp (C)", "Temperature",
         [(config.thermal.T_safe, "T_safe"), (config.thermal.T_crit, "T_crit")]),
        (axes[0,1], "voltage", "Voltage (V)", "Supply Voltage",
         [(config.power.V_safe, "V_safe"), (config.power.V_crit, "V_crit")]),
        (axes[1,0], "risk_score", "Risk R", "Risk Score",
         [(config.state_machine.safe_to_warning, "SAFE>WARN"),
          (config.state_machine.warning_to_critical, "WARN>CRIT")]),
    ]
    for ax, key, ylabel, title, hlines in plot_defs:
        for mode, res in all_results.items():
            tl = res["timeline"]
            t = [d["time"]/60 for d in tl]
            v = [d[key] for d in tl]
            ax.plot(t, v, color=colors[mode], label=labels[mode], lw=1.2, alpha=0.85)
        for val, name in hlines:
            ax.axhline(y=val, color="#888", ls="--", alpha=0.4, label=name)
        ax.set_ylabel(ylabel)
        ax.set_xlabel("Time (min)")
        ax.set_title(title)
        ax.legend(fontsize=7)
        ax.grid(True, alpha=0.3)
        if key == "risk_score":
            ax.set_ylim(-0.02, 1.02)

    # --- Failure Seconds: ALL modes (log scale) ---
    ax = axes[1, 1]
    mode_names = [labels[m] for m in all_results]
    fails = [r["failure_seconds"] for r in all_results.values()]
    bc = [colors[m] for m in all_results]
    display_fails = [max(f, 0.5) for f in fails]
    bars = ax.bar(mode_names, display_fails, color=bc, edgecolor="white", lw=1.5)
    ax.set_yscale("log")
    ax.set_ylabel("Time in Danger Zone (seconds, log)")
    ax.set_title("Failure Duration - All Modes")
    ax.grid(True, axis="y", alpha=0.3)
    ax.set_ylim(0.3, max(max(fails), 1) * 3)
    for bar, val in zip(bars, fails):
        y_pos = max(val, 0.5) * 1.5
        ax.text(bar.get_x() + bar.get_width()/2, y_pos,
                f"{val:.0f}s", ha="center", va="bottom", fontweight="bold", fontsize=11)

    # --- Failure Seconds: ZOOMED on modes 1-3 only ---
    ax = axes[2, 0]
    zoom_modes = [m for m in all_results if m != "4-Threshold-Only"]
    zoom_names = [labels[m] for m in zoom_modes]
    zoom_fails = [all_results[m]["failure_seconds"] for m in zoom_modes]
    zoom_colors = [colors[m] for m in zoom_modes]
    bars = ax.bar(zoom_names, zoom_fails, color=zoom_colors, edgecolor="white", lw=1.5)
    ax.set_ylabel("Time in Danger Zone (seconds)")
    ax.set_title("Failure Duration - Protected Modes (Zoomed)")
    ax.grid(True, axis="y", alpha=0.3)
    y_max = max(max(zoom_fails) * 1.4, 5)
    ax.set_ylim(0, y_max)
    for bar, val in zip(bars, zoom_fails):
        ax.text(bar.get_x() + bar.get_width()/2,
                bar.get_height() + y_max * 0.03,
                f"{val:.0f}s", ha="center", va="bottom", fontweight="bold", fontsize=12)

    # --- Task Routing Distribution ---
    ax = axes[2, 1]
    mode_names_all = [labels[m] for m in all_results]
    local_c = [r["routing"]["local"] for r in all_results.values()]
    offload_c = [r["routing"]["offloaded"] for r in all_results.values()]
    x = list(range(len(mode_names_all)))
    w = 0.3
    bars1 = ax.bar([i-w/2 for i in x], local_c, w, label="Local", color="#e74c3c", alpha=0.85)
    bars2 = ax.bar([i+w/2 for i in x], offload_c, w, label="Offloaded", color="#2980b9", alpha=0.85)
    ax.set_ylabel("Task Count")
    ax.set_title("Task Routing Distribution")
    ax.set_xticks(x)
    ax.set_xticklabels(mode_names_all, fontsize=9)
    ax.legend()
    ax.grid(True, axis="y", alpha=0.3)
    for bar, val in zip(bars1, local_c):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 10,
                str(val), ha="center", va="bottom", fontsize=7, fontweight="bold")
    for bar, val in zip(bars2, offload_c):
        if val > 0:
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 10,
                    str(val), ha="center", va="bottom", fontsize=7, fontweight="bold")

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig("evidence/ablation_study.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  -> evidence/ablation_study.png")

    fig, ax = plt.subplots(figsize=(9, 5))
    mode_names = [labels[m] for m in all_results]
    local_c = [r["routing"]["local"] for r in all_results.values()]
    offload_c = [r["routing"]["offloaded"] for r in all_results.values()]
    x = list(range(len(mode_names)))
    w = 0.3
    ax.bar([i-w/2 for i in x], local_c, w, label="Local", color="#27ae60")
    ax.bar([i+w/2 for i in x], offload_c, w, label="Offloaded", color="#2980b9")
    ax.set_ylabel("Task Count")
    ax.set_title("Task Routing Distribution")
    ax.set_xticks(x)
    ax.set_xticklabels(mode_names, fontsize=9)
    ax.legend()
    ax.grid(True, axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig("evidence/routing_distribution.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  -> evidence/routing_distribution.png")


if __name__ == "__main__":
    main()
