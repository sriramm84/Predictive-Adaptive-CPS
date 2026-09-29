"""
Patent Evidence -- Result 6: Hysteresis Line Graph
====================================================

PURPOSE:
  Generate a line graph from the Result 6 CSV data showing:
    - Risk Score R(t) plotted over time
    - SAFE→WARNING trigger line at R=0.30
    - WARNING→SAFE recovery line at R=0.25
    - Annotated "Stability Zone" between 0.25 and 0.30
    - State transition markers

RUN:
  First generate the CSV:  python experiments/result6_hysteresis_data.py
  Then generate the graph: python experiments/result6_hysteresis_graph.py
"""

import csv
import os
import sys
import numpy as np

# Add parent for bodyguard imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def make_result6_hysteresis_graph():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patheffects as pe
    from matplotlib.patches import FancyBboxPatch

    # =====================================================================
    #  LOAD CSV DATA
    # =====================================================================
    csv_path = os.path.join("experiments", "output", "result6_hysteresis_telemetry.csv")
    if not os.path.exists(csv_path):
        print(f"  ERROR: CSV not found at {csv_path}")
        print(f"  Run: python experiments/result6_hysteresis_data.py first")
        return None

    rows = []
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    samples = [int(r["Sample"]) for r in rows]
    times = [(int(r["Sample"]) - 1) * 2 for r in rows]  # 2s intervals
    risk_scores = [float(r["Risk_Score_R"]) for r in rows]
    states = [r["State"] for r in rows]
    voltages = [float(r["Voltage_V"]) for r in rows]
    temperatures = [float(r["Temperature_C"]) for r in rows]

    # =====================================================================
    #  FIGURE
    # =====================================================================
    fig, (ax_main, ax_sensors) = plt.subplots(
        2, 1, figsize=(14, 10), height_ratios=[1.3, 1],
        sharex=True, facecolor="#FAFAFA"
    )

    # =====================================================================
    #  PANEL 1: RISK SCORE WITH HYSTERESIS ZONES
    # =====================================================================
    ax = ax_main
    ax.set_facecolor("#FAFAFA")

    # Fill the hysteresis stability zone (0.25 to 0.30)
    ax.axhspan(0.25, 0.30, alpha=0.12, color="#F39C12", zorder=1,
               label="Stability Zone (Hysteresis Band)")

    # Threshold lines
    ax.axhline(y=0.30, color="#E74C3C", ls="--", lw=2, alpha=0.8, zorder=2)
    ax.axhline(y=0.25, color="#27AE60", ls="--", lw=2, alpha=0.8, zorder=2)

    # Threshold labels
    ax.text(times[-1] + 0.5, 0.305, "SAFE → WARNING Trigger (R = 0.30)",
            fontsize=9.5, color="#E74C3C", va="bottom", ha="right",
            fontweight="bold", fontstyle="italic",
            path_effects=[pe.withStroke(linewidth=3, foreground="white")])
    ax.text(times[-1] + 0.5, 0.245, "WARNING → SAFE Recovery (R = 0.25)",
            fontsize=9.5, color="#27AE60", va="top", ha="right",
            fontweight="bold", fontstyle="italic",
            path_effects=[pe.withStroke(linewidth=3, foreground="white")])

    # Plot the risk score line
    ax.plot(times, risk_scores, color="#8E44AD", lw=2.5, marker="o",
            markersize=6, zorder=5, label="Risk Score R(t)")

    # Color markers by state
    for i, (t, r, s) in enumerate(zip(times, risk_scores, states)):
        if s == "SAFE":
            c = "#27AE60"
        elif s == "WARNING":
            c = "#E67E22"
        elif s == "CRITICAL":
            c = "#E74C3C"
        else:
            c = "#8E44AD"
        ax.plot(t, r, "o", color=c, markersize=8, zorder=6,
                markeredgecolor="white", markeredgewidth=1.5)

    # Annotate state transitions
    for i in range(1, len(states)):
        if states[i] != states[i-1]:
            transition = f"{states[i-1]} → {states[i]}"
            y_offset = 0.03 if risk_scores[i] > risk_scores[i-1] else -0.03
            ax.annotate(
                transition,
                xy=(times[i], risk_scores[i]),
                xytext=(times[i] + 1.5, risk_scores[i] + y_offset),
                fontsize=9, fontweight="bold", color="#2C3E50",
                arrowprops=dict(arrowstyle="->", color="#2C3E50", lw=1.5),
                bbox=dict(boxstyle="round,pad=0.3", facecolor="#FADBD8",
                          edgecolor="#E74C3C", alpha=0.9),
                zorder=10,
            )

    # Annotate hysteresis proof rows (where R is between 0.25 and 0.30 in WARNING)
    for i, (t, r, s) in enumerate(zip(times, risk_scores, states)):
        if s == "WARNING" and 0.25 <= r < 0.30:
            ax.annotate(
                f"R={r:.3f}\nStays WARNING\n(Hysteresis)",
                xy=(t, r), xytext=(t - 3, r - 0.06),
                fontsize=8, fontweight="bold", color="#D35400",
                arrowprops=dict(arrowstyle="->", color="#D35400", lw=1.5),
                bbox=dict(boxstyle="round,pad=0.3", facecolor="#FEF9E7",
                          edgecolor="#F39C12", alpha=0.9),
                ha="center", zorder=10,
            )
            break  # Only annotate the first one to avoid clutter

    # Styling
    ax.set_ylabel("Risk Score R(t)", fontsize=13, fontweight="bold", color="#2C3E50")
    ax.set_ylim(0, max(risk_scores) + 0.10)
    ax.legend(fontsize=10, loc="upper left", framealpha=0.9)
    ax.grid(True, alpha=0.2)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # Title
    ax.set_title(
        "Result 6: State Transitions & Dual-Hysteresis Stability Proof",
        fontsize=15, fontweight="bold", color="#2C3E50", pad=12
    )

    # State color bar along the top
    for i, (t, s) in enumerate(zip(times, states)):
        width = 2 if i < len(times) - 1 else 1
        color = "#27AE60" if s == "SAFE" else "#E67E22" if s == "WARNING" else "#E74C3C"
        ax.axvspan(t - 1, t + 1, ymin=0.95, ymax=1.0, color=color, alpha=0.7)

    # State legend at top
    legend_y = max(risk_scores) + 0.07
    ax.plot([], [], "s", color="#27AE60", markersize=10, label="SAFE State")
    ax.plot([], [], "s", color="#E67E22", markersize=10, label="WARNING State")
    legend = ax.legend(fontsize=9, loc="upper left", framealpha=0.9, ncol=3)

    # =====================================================================
    #  PANEL 2: VOLTAGE & TEMPERATURE SENSOR TRACES
    # =====================================================================
    ax2 = ax_sensors
    ax2.set_facecolor("#FAFAFA")

    color_v = "#2E86C1"
    color_t = "#E67E22"

    ax2.plot(times, voltages, color=color_v, lw=2, marker="s", markersize=4,
             alpha=0.85, label="Voltage V (V)", zorder=3)
    ax2.set_ylabel("Voltage (V)", fontsize=12, fontweight="bold", color=color_v)
    ax2.tick_params(axis="y", labelcolor=color_v)

    ax2_twin = ax2.twinx()
    ax2_twin.plot(times, temperatures, color=color_t, lw=2, marker="^",
                  markersize=4, alpha=0.85, label="Temperature T (°C)", zorder=3)
    ax2_twin.set_ylabel("Temperature (°C)", fontsize=12, fontweight="bold",
                        color=color_t)
    ax2_twin.tick_params(axis="y", labelcolor=color_t)

    ax2.set_xlabel("Time (seconds)", fontsize=13, fontweight="bold")
    ax2.set_title("Supporting Sensor Traces (INA219 Voltage + SoC Temperature)",
                  fontsize=12, fontweight="bold", color="#2C3E50", pad=10)

    # Combined legend
    lines1, labels1 = ax2.get_legend_handles_labels()
    lines2, labels2 = ax2_twin.get_legend_handles_labels()
    ax2.legend(lines1 + lines2, labels1 + labels2, fontsize=9,
               loc="lower left", framealpha=0.9)

    ax2.grid(True, alpha=0.2)
    ax2.spines["top"].set_visible(False)

    # Reference lines
    ax2.axhline(y=4.95, color=color_v, ls=":", lw=1, alpha=0.4)
    ax2.text(0.5, 4.955, "V_safe=4.95V", fontsize=7, color=color_v,
             fontstyle="italic", alpha=0.6)

    # =====================================================================
    #  INFO BOX
    # =====================================================================
    info_text = (
        "Evidence Summary:\n"
        "• SAFE → WARNING at R ≥ 0.30\n"
        "• R dips to ~0.27: state stays WARNING\n"
        "  (Hysteresis prevents flickering)\n"
        "• WARNING → SAFE at R < 0.25\n"
        "• Gap = 0.05 (Dual-Hysteresis Band)"
    )
    props = dict(boxstyle="round,pad=0.5", facecolor="#EBF5FB",
                 edgecolor="#2E86C1", alpha=0.9)
    ax.text(0.98, 0.45, info_text, transform=ax.transAxes,
            fontsize=8.5, va="top", ha="right", bbox=props,
            family="monospace", color="#2C3E50")

    # =====================================================================
    #  SAVE
    # =====================================================================
    plt.tight_layout()
    out_path = os.path.join("experiments", "output", "result6_hysteresis_graph.png")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    plt.savefig(out_path, dpi=200, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close()
    print(f"  -> Saved: {out_path}")
    return out_path


if __name__ == "__main__":
    print("=" * 65)
    print("  RESULT 6: Hysteresis Line Graph")
    print("=" * 65)
    path = make_result6_hysteresis_graph()
    if path:
        print(f"\n  Done! Output: {path}")
    else:
        print("\n  Failed! Generate CSV data first.")
