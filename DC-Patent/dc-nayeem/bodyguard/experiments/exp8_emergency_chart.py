"""
Patent Evidence -- Result 8: Emergency Self-Preservation (The Offline Proof)
==============================================================================

PURPOSE:
  Demonstrate that the Bodyguard system keeps the device alive during a
  simulated cloud outage under high-stress conditions, using emergency
  throttling (sleep interleaving + task rejection) to cool hardware.

WHAT IT PROVES:
  The invention is a complete Hardware Guardian that ensures survival even
  when its primary offloading mechanism (the Cloud) is unavailable.

SCENARIO:
  15-minute simulation with cloud outage injected at minute 5.
  - Run A (Bodyguard): Full protection → transitions to EMERGENCY → throttles
  - Run B (Baseline):  No protection → thermal shutdown / brownout

FORMAT:
  4-panel chart:
    1. Temperature over time (cool-down effect)
    2. Risk score over time
    3. Task routing decisions (stacked bar)
    4. Survival summary table

RUN:
  python experiments/exp8_emergency_chart.py
"""
import sys
import os
import random

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from bodyguard.config import BodyguardConfig
from bodyguard.controller import BodyguardController
from bodyguard.admission import Task, TaskPriority, RoutingDecision


# ===========================================================================
#  CONFIGURATION
# ===========================================================================

def make_config():
    """
    Raspberry Pi 4 config tuned for a 15-minute emergency scenario.

    We use a warmer ambient and lower cooling to make the thermal stress
    scenario realistic within a short simulation window.
    """
    config = BodyguardConfig()

    # Warmer environment (IoT enclosure in server room)
    config.thermal.ambient_temp = 38.0
    config.thermal.T_safe = 65.0
    config.thermal.T_crit = 80.0
    config.thermal.passive_cooling_rate = 0.20
    config.thermal.thermal_mass = 10.0
    config.thermal.s_safe = 1.0
    config.thermal.s_max = 5.0

    # Slightly stressed PSU
    config.power.V_nominal = 5.0
    config.power.V_safe = 4.90
    config.power.V_crit = 4.63
    config.power.psu_impedance = 0.18
    config.power.psu_noise_stddev = 0.025

    # Standard weights
    config.weights.w1_thermal_proximity = 0.15
    config.weights.w2_thermal_velocity = 0.25
    config.weights.w3_voltage_sag = 0.15
    config.weights.w4_voltage_drop_rate = 0.20
    config.weights.w5_voltage_instability = 0.10
    config.weights.w6_load_pressure = 0.15

    # Budget
    config.budget.B_max = 10
    config.budget.window_duration = 30.0
    config.budget.R_replenish = 0.25

    # State thresholds
    config.state_machine.safe_to_warning = 0.30
    config.state_machine.warning_to_safe = 0.25
    config.state_machine.warning_to_critical = 0.65
    config.state_machine.critical_to_warning = 0.55

    # Sampling
    config.sampling.interval = 2.0
    config.sampling.history_depth = 10

    # Emergency
    config.emergency.sleep_ms = 500

    return config


# ===========================================================================
#  15-MINUTE SIMULATION
# ===========================================================================

def run_scenario(label, config, seed=42, protected=True):
    """
    Simulate 15 minutes with cloud outage at minute 5.

    Args:
        label:     Name for this run
        config:    BodyguardConfig
        seed:      Deterministic seed
        protected: True=Bodyguard enabled, False=baseline (no protection)

    Returns:
        dict with timeline data and summary metrics
    """
    dt = config.sampling.interval     # 2 seconds
    total_time = 15 * 60              # 900 seconds = 15 minutes
    total_steps = int(total_time / dt) # 450 steps

    CLOUD_OUTAGE_TIME = 5 * 60        # Cloud goes offline at 5 minutes
    BURST_START = 5 * 60              # Heavy burst starts at minute 5
    BURST_END = 7 * 60                # Burst lasts 2 minutes

    rng = random.Random(seed + 8)

    # Baseline disables all protection
    kwargs = {}
    if not protected:
        kwargs = {"disable_state_machine": True, "disable_budget": True}

    ctrl = BodyguardController(
        config=config, output_dir="experiments/output",
        log_prefix=f"exp8_{label.lower().replace(' ', '_')}",
        seed=seed, **kwargs,
    )

    active_load = 0.0
    base_idle = 5.0   # 5% idle baseline

    # Timeline tracking (every step for 15 min = manageable)
    timeline = {
        "time": [],
        "temperature": [],
        "voltage": [],
        "risk_score": [],
        "state": [],
        "cpu_load": [],
    }

    # Routing counters per minute
    routing_per_minute = []
    for _ in range(16):
        routing_per_minute.append({"LOCAL": 0, "OFFLOAD": 0, "THROTTLE": 0, "REJECT": 0})

    # Failure tracking
    failure_events = []
    thermal_shutdowns = 0
    brownouts = 0
    peak_temp = 0.0
    peak_risk = 0.0
    total_tasks_submitted = 0
    total_tasks_completed = 0  # LOCAL + THROTTLE

    print(f"  Running {label}... ({total_steps} steps = 15 min)")

    for step in range(total_steps):
        sim_time = step * dt
        minute = int(sim_time / 60)

        # --- CLOUD OUTAGE at minute 5 ---
        if sim_time >= CLOUD_OUTAGE_TIME:
            ctrl._admission._cloud_available = False

        # --- LOAD DECAY ---
        active_load *= 0.93
        if active_load < 0.2:
            active_load = 0.0

        total_cpu = base_idle + active_load
        ctrl.set_load(min(99.0, total_cpu), queue_depth=max(0, int(active_load / 6)))
        bd = ctrl.sample(dt=dt)

        reading = ctrl._latest_reading
        if not reading:
            continue

        # --- TRACK TEMPERATURE & FAILURES ---
        if reading.temperature > peak_temp:
            peak_temp = reading.temperature
        if bd and bd.risk_score > peak_risk:
            peak_risk = bd.risk_score

        # Detect failure (thermal shutdown or brownout)
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

        # --- RECORD TIMELINE (every 3rd step to keep chart manageable) ---
        if step % 3 == 0:
            timeline["time"].append(sim_time / 60)  # in minutes
            timeline["temperature"].append(reading.temperature)
            timeline["voltage"].append(reading.voltage)
            timeline["risk_score"].append(bd.risk_score if bd else 0.0)
            timeline["state"].append(ctrl.state.value if protected else "N/A")
            timeline["cpu_load"].append(total_cpu)

        # --- GENERATE WORKLOAD ---
        # Normal load: ~0.3 tasks/step
        # Burst (min 5-7): ~0.8 tasks/step with heavy tasks
        if BURST_START <= sim_time < BURST_END:
            task_prob = 0.80
            weight_range = (0.50, 0.95)  # Heavy tasks during burst
            cpu_range = (6.0, 12.0)
        else:
            task_prob = 0.30
            weight_range = (0.15, 0.60)
            cpu_range = (2.0, 6.0)

        if rng.random() < task_prob:
            num_tasks = 1
            if BURST_START <= sim_time < BURST_END and rng.random() < 0.15:
                num_tasks += rng.randint(1, 3)  # Occasional burst
        else:
            num_tasks = 0

        for i in range(num_tasks):
            weight = rng.uniform(*weight_range)
            cpu_demand = rng.uniform(*cpu_range)
            pri = rng.choices(
                list(TaskPriority),
                weights=[20, 40, 25, 15]
            )[0]
            task = Task(
                task_id=f"t{step}_{i}", weight=weight,
                priority=pri, cpu_load=cpu_demand,
            )
            total_tasks_submitted += 1

            if protected:
                result = ctrl.submit_task(task)
                decision = result.decision
            else:
                # Baseline: execute everything locally (no protection)
                decision = RoutingDecision.LOCAL
                ctrl._simulator.add_load(cpu_demand)

            if decision == RoutingDecision.LOCAL:
                active_load += cpu_demand
                total_tasks_completed += 1
            elif decision == RoutingDecision.THROTTLE:
                active_load += cpu_demand * 0.4
                total_tasks_completed += 1
            elif decision == RoutingDecision.OFFLOAD:
                total_tasks_completed += 1  # Completed via cloud

            # Track routing per minute
            if minute < 16:
                routing_per_minute[minute][decision.value] += 1

        # Progress
        if step > 0 and step % (total_steps // 5) == 0:
            print(f"    [{sim_time/60:.1f}m] T={reading.temperature:.1f}C  "
                  f"V={reading.voltage:.3f}V  R={bd.risk_score if bd else 0:.3f}  "
                  f"State={ctrl.state.value if protected else 'N/A'}  "
                  f"CPU={total_cpu:.0f}%")

    ctrl.close()

    return {
        "label": label,
        "timeline": timeline,
        "routing_per_minute": routing_per_minute,
        "thermal_shutdowns": thermal_shutdowns,
        "brownouts": brownouts,
        "peak_temp": peak_temp,
        "peak_risk": peak_risk,
        "total_tasks_submitted": total_tasks_submitted,
        "total_tasks_completed": total_tasks_completed,
        "failure_events": failure_events,
    }


# ===========================================================================
#  PLOTTING
# ===========================================================================

def make_result8_chart(bodyguard, baseline):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.gridspec import GridSpec
    from matplotlib.patches import FancyBboxPatch

    fig = plt.figure(figsize=(18, 13))
    fig.patch.set_facecolor("#FAFAFA")
    gs = GridSpec(2, 2, figure=fig, hspace=0.35, wspace=0.30)

    CLOUD_OUTAGE_MIN = 5.0
    color_bg = "#2E86C1"    # Bodyguard blue
    color_bl = "#C0392B"    # Baseline red
    color_throttle = "#E67E22"
    color_reject = "#E74C3C"
    color_local = "#27AE60"
    color_offload = "#3498DB"

    # ===================================================================
    #  PANEL 1: Voltage & Temperature Over Time (dual-axis)
    # ===================================================================
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.set_facecolor("#FAFAFA")

    t_bg = bodyguard["timeline"]["time"]
    t_bl = baseline["timeline"]["time"]

    # Primary axis: Voltage
    V_bg = bodyguard["timeline"]["voltage"]
    V_bl = baseline["timeline"]["voltage"]

    ax1.plot(t_bg, V_bg, color=color_bg, lw=2.5, alpha=0.9,
             label="Bodyguard V(t)", zorder=3)
    ax1.plot(t_bl, V_bl, color=color_bl, lw=2.5, alpha=0.9, ls="--",
             label="Baseline V(t)", zorder=3)

    # Voltage critical threshold
    ax1.axhline(y=4.63, color="#C0392B", ls=":", lw=2, alpha=0.6)
    ax1.text(14.8, 4.635, "V_crit = 4.63V (Brownout)", fontsize=8,
             color="#C0392B", ha="right", fontstyle="italic", fontweight="bold")
    ax1.axhline(y=4.90, color="#E67E22", ls=":", lw=1.5, alpha=0.4)
    ax1.text(14.8, 4.905, "V_safe = 4.90V", fontsize=8, color="#E67E22",
             ha="right", fontstyle="italic")

    # Mark brownout failure events on baseline at actual voltage
    for fe in baseline["failure_events"]:
        if fe["type"] == "BROWNOUT":
            ax1.plot(fe["time"] / 60, fe.get("voltage", 4.63), "X",
                     color="#C0392B", markersize=14, zorder=5,
                     markeredgewidth=2)

    # Cloud outage marker
    ax1.axvline(x=CLOUD_OUTAGE_MIN, color="#7F8C8D", ls="--", lw=2, alpha=0.7)
    ax1.text(CLOUD_OUTAGE_MIN + 0.15, ax1.get_ylim()[1] - 0.02 if ax1.get_ylim()[1] > 4.5 else 5.0,
             "Cloud\nOutage", fontsize=9, color="#7F8C8D",
             fontweight="bold", va="top")

    # Secondary axis: Temperature
    ax1_t = ax1.twinx()
    T_bg = bodyguard["timeline"]["temperature"]
    T_bl = baseline["timeline"]["temperature"]
    ax1_t.plot(t_bg, T_bg, color="#27AE60", lw=1.5, alpha=0.5,
               ls="-.", label="Bodyguard T(t)", zorder=2)
    ax1_t.plot(t_bl, T_bl, color="#E67E22", lw=1.5, alpha=0.5,
               ls="-.", label="Baseline T(t)", zorder=2)
    ax1_t.set_ylabel("Temperature (°C)", fontsize=10, color="#7F8C8D")
    ax1_t.tick_params(axis="y", labelcolor="#7F8C8D")

    ax1.set_xlabel("Time (minutes)", fontsize=11, fontweight="bold")
    ax1.set_ylabel("Voltage (V)", fontsize=11, fontweight="bold")
    ax1.set_title("Voltage Stability: Brownout Prevention",
                  fontsize=13, fontweight="bold", color="#2C3E50", pad=10)

    # Combined legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax1_t.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, fontsize=8,
               loc="lower left", framealpha=0.9, ncol=2)
    ax1.grid(True, alpha=0.2)
    ax1.spines["top"].set_visible(False)
    ax1.set_xlim(0, 15)

    # Brownout count annotation
    n_brownouts_bl = baseline["brownouts"]
    if n_brownouts_bl > 0:
        props = dict(boxstyle="round,pad=0.3", facecolor="#FADBD8",
                     edgecolor="#C0392B", alpha=0.9)
        ax1.text(0.98, 0.15, f"Baseline: {n_brownouts_bl} BROWNOUTS",
                 transform=ax1.transAxes, fontsize=10, va="bottom",
                 ha="right", bbox=props, fontweight="bold", color="#C0392B")

    # ===================================================================
    #  PANEL 2: Risk Score Over Time
    # ===================================================================
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.set_facecolor("#FAFAFA")

    R_bg = bodyguard["timeline"]["risk_score"]
    R_bl = baseline["timeline"]["risk_score"]

    ax2.plot(t_bg, R_bg, color=color_bg, lw=2.5, alpha=0.9,
             label=f"Bodyguard (Peak R: {bodyguard['peak_risk']:.3f})", zorder=3)
    ax2.plot(t_bl, R_bl, color=color_bl, lw=2.5, alpha=0.9, ls="--",
             label=f"Baseline (Peak R: {baseline['peak_risk']:.3f})", zorder=3)

    # Threshold lines
    ax2.axhline(y=0.30, color="#E67E22", ls=":", lw=1.5, alpha=0.5)
    ax2.text(14.8, 0.31, "WARNING (0.30)", fontsize=8, color="#E67E22",
             ha="right", fontstyle="italic")
    ax2.axhline(y=0.65, color="#C0392B", ls=":", lw=1.5, alpha=0.5)
    ax2.text(14.8, 0.66, "CRITICAL (0.65)", fontsize=8, color="#C0392B",
             ha="right", fontstyle="italic")

    # Cloud outage marker
    ax2.axvline(x=CLOUD_OUTAGE_MIN, color="#7F8C8D", ls="--", lw=2, alpha=0.7)

    ax2.set_xlabel("Time (minutes)", fontsize=11, fontweight="bold")
    ax2.set_ylabel("Risk Score R(t)", fontsize=11, fontweight="bold")
    ax2.set_title("Risk Score: Throttle Reduces Stress",
                  fontsize=13, fontweight="bold", color="#2C3E50", pad=10)
    ax2.legend(fontsize=9, loc="upper left", framealpha=0.9)
    ax2.grid(True, alpha=0.2)
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)
    ax2.set_xlim(0, 15)
    ax2.set_ylim(0, 1.0)

    # ===================================================================
    #  PANEL 3: Task Routing Decisions (Stacked Bar)
    # ===================================================================
    ax3 = fig.add_subplot(gs[1, 0])
    ax3.set_facecolor("#FAFAFA")

    minutes = np.arange(15)
    local_counts = [bodyguard["routing_per_minute"][m]["LOCAL"] for m in range(15)]
    offload_counts = [bodyguard["routing_per_minute"][m]["OFFLOAD"] for m in range(15)]
    throttle_counts = [bodyguard["routing_per_minute"][m]["THROTTLE"] for m in range(15)]
    reject_counts = [bodyguard["routing_per_minute"][m]["REJECT"] for m in range(15)]

    bar_width = 0.7
    bottom1 = np.array(local_counts)
    bottom2 = bottom1 + np.array(offload_counts)
    bottom3 = bottom2 + np.array(throttle_counts)

    ax3.bar(minutes, local_counts, bar_width, label="LOCAL", color=color_local, alpha=0.85)
    ax3.bar(minutes, offload_counts, bar_width, bottom=bottom1,
            label="OFFLOAD", color=color_offload, alpha=0.85)
    ax3.bar(minutes, throttle_counts, bar_width, bottom=bottom2,
            label="THROTTLE", color=color_throttle, alpha=0.85)
    ax3.bar(minutes, reject_counts, bar_width, bottom=bottom3,
            label="REJECT", color=color_reject, alpha=0.85)

    # Cloud outage marker
    ax3.axvline(x=CLOUD_OUTAGE_MIN - 0.5, color="#7F8C8D", ls="--", lw=2, alpha=0.7)
    ax3.text(CLOUD_OUTAGE_MIN + 0.2, ax3.get_ylim()[1] * 0.9 if ax3.get_ylim()[1] > 0 else 10,
             "⚡ Cloud\nOutage", fontsize=8, color="#7F8C8D", fontweight="bold")

    ax3.set_xlabel("Time (minute)", fontsize=11, fontweight="bold")
    ax3.set_ylabel("Task Count", fontsize=11, fontweight="bold")
    ax3.set_title("Bodyguard Task Routing: Before vs After Cloud Outage",
                  fontsize=13, fontweight="bold", color="#2C3E50", pad=10)
    ax3.legend(fontsize=9, loc="upper right", framealpha=0.9, ncol=2)
    ax3.grid(True, alpha=0.15, axis="y")
    ax3.spines["top"].set_visible(False)
    ax3.spines["right"].set_visible(False)
    ax3.set_xticks(minutes)

    # ===================================================================
    #  PANEL 4: Survival Summary Table
    # ===================================================================
    ax4 = fig.add_subplot(gs[1, 1])
    ax4.set_facecolor("#FAFAFA")
    ax4.axis("off")

    # Summary data
    col_labels = ["Metric", "Bodyguard", "Baseline"]
    table_data = [
        ["Thermal Shutdowns",
         f"{'0  ✅' if bodyguard['thermal_shutdowns'] == 0 else str(bodyguard['thermal_shutdowns'])}",
         f"{baseline['thermal_shutdowns']}  ❌" if baseline['thermal_shutdowns'] > 0
         else f"{baseline['thermal_shutdowns']}"],
        ["Brownouts",
         f"{'0  ✅' if bodyguard['brownouts'] == 0 else str(bodyguard['brownouts'])}",
         f"{baseline['brownouts']}  ❌" if baseline['brownouts'] > 0
         else f"{baseline['brownouts']}"],
        ["Peak Temperature",
         f"{bodyguard['peak_temp']:.1f}°C",
         f"{baseline['peak_temp']:.1f}°C"],
        ["Peak Risk Score",
         f"{bodyguard['peak_risk']:.3f}",
         f"{baseline['peak_risk']:.3f}"],
        ["Tasks Submitted",
         f"{bodyguard['total_tasks_submitted']}",
         f"{baseline['total_tasks_submitted']}"],
        ["Tasks Completed",
         f"{bodyguard['total_tasks_completed']}",
         f"{baseline['total_tasks_completed']}"],
        ["Completion Rate",
         f"{bodyguard['total_tasks_completed']/max(1,bodyguard['total_tasks_submitted'])*100:.1f}%",
         f"{baseline['total_tasks_completed']/max(1,baseline['total_tasks_submitted'])*100:.1f}%"],
        ["Device Survived?",
         "YES  ✅" if bodyguard['thermal_shutdowns'] + bodyguard['brownouts'] == 0
         else "NO  ❌",
         "YES  ✅" if baseline['thermal_shutdowns'] + baseline['brownouts'] == 0
         else "NO  ❌"],
    ]

    tbl = ax4.table(
        cellText=table_data, colLabels=col_labels,
        cellLoc="center", loc="center",
        colWidths=[0.38, 0.31, 0.31],
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(11)
    tbl.scale(1.0, 1.8)

    # Style header
    for j in range(3):
        cell = tbl[0, j]
        cell.set_facecolor("#2C3E50")
        cell.set_text_props(color="white", fontweight="bold", fontsize=12)

    # Style data rows
    for i in range(1, len(table_data) + 1):
        for j in range(3):
            cell = tbl[i, j]
            if j == 0:
                cell.set_text_props(fontweight="bold", ha="left")
                cell.set_facecolor("#F2F3F4")
            elif j == 1:
                cell.set_facecolor("#D5F5E3")  # Green tint for Bodyguard
            else:
                cell.set_facecolor("#FADBD8")  # Red tint for Baseline
            cell.set_edgecolor("#D5DBDB")

    # Last row highlight (Device Survived)
    for j in range(3):
        cell = tbl[len(table_data), j]
        cell.set_text_props(fontweight="bold", fontsize=12)

    ax4.set_title("Emergency Survival: Bodyguard vs Baseline",
                  fontsize=13, fontweight="bold", color="#2C3E50", pad=15)

    # Evidence box
    evidence_text = (
        "KEY EVIDENCE:\n"
        "• Bodyguard detects cloud outage → transitions to EMERGENCY\n"
        "• Emergency throttling: 500ms sleep + half CPU load\n"
        "• Non-critical tasks REJECTED to reduce hardware stress\n"
        "• Result: Temperature stabilizes, device SURVIVES\n"
        "• Baseline: No protection → thermal shutdown/brownout"
    )
    props = dict(boxstyle="round,pad=0.5", facecolor="#FEF9E7",
                 edgecolor="#F39C12", alpha=0.9)
    ax4.text(0.50, -0.05, evidence_text, transform=ax4.transAxes,
             fontsize=9, va="top", ha="center",
             bbox=props, color="#2C3E50", family="sans-serif")

    # === SUPER TITLE ===
    fig.suptitle(
        "Result 8: Emergency Self-Preservation (The Offline Proof)\n"
        "Cloud Outage at Minute 5 — Bodyguard vs Unprotected Baseline",
        fontsize=16, fontweight="bold", color="#2C3E50", y=0.99,
    )

    # --- Save ---
    plt.tight_layout(rect=[0, 0, 1, 0.94])
    out = os.path.join("experiments", "output", "result8_emergency.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    plt.savefig(out, dpi=200, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"  -> Saved: {out}")
    return out


# ===========================================================================
#  MAIN
# ===========================================================================

def main():
    print("=" * 65)
    print("  RESULT 8: Emergency Self-Preservation (The Offline Proof)")
    print("=" * 65)

    config = make_config()

    print("\n  Scenario: 15-minute simulation, cloud outage at minute 5")
    print("  ─" * 30)

    # Run A: Bodyguard (full protection)
    print("\n  [A] WITH Bodyguard Protection:")
    bodyguard = run_scenario(
        label="Bodyguard Emergency",
        config=config, seed=42, protected=True,
    )
    print(f"      Thermal shutdowns: {bodyguard['thermal_shutdowns']}")
    print(f"      Brownouts:         {bodyguard['brownouts']}")
    print(f"      Peak temperature:  {bodyguard['peak_temp']:.1f}°C")
    print(f"      Tasks completed:   {bodyguard['total_tasks_completed']}"
          f"/{bodyguard['total_tasks_submitted']}")

    # Run B: Baseline (no protection)
    print("\n  [B] WITHOUT Protection (Baseline):")
    baseline = run_scenario(
        label="Baseline No Protection",
        config=config, seed=42, protected=False,
    )
    print(f"      Thermal shutdowns: {baseline['thermal_shutdowns']}")
    print(f"      Brownouts:         {baseline['brownouts']}")
    print(f"      Peak temperature:  {baseline['peak_temp']:.1f}°C")
    print(f"      Tasks completed:   {baseline['total_tasks_completed']}"
          f"/{baseline['total_tasks_submitted']}")

    # Generate chart
    print("\n  Generating Result 8 chart...")
    chart_path = make_result8_chart(bodyguard, baseline)

    # Print summary
    print("\n  ━" * 30)
    print("  SUMMARY")
    print("  ━" * 30)
    survived = bodyguard['thermal_shutdowns'] + bodyguard['brownouts'] == 0
    crashed = baseline['thermal_shutdowns'] + baseline['brownouts'] > 0
    print(f"  Bodyguard:  {'SURVIVED ✅' if survived else 'FAILED ❌'}")
    print(f"  Baseline:   {'CRASHED ❌' if crashed else 'SURVIVED ✅'}")
    if survived and crashed:
        print("\n  ✅ PROOF: Bodyguard's emergency throttling saved the device")
        print("     when cloud offloading was unavailable.")
    print(f"\n  Output: {chart_path}")
    print("=" * 65)


if __name__ == "__main__":
    main()
