"""
Patent Evidence — Result 2: Time to First Critical Event (Early Warning Proof)
===============================================================================

PURPOSE:
  Generate a comparison bar chart showing "Survival Time" — the duration
  (in minutes) before the device hits a critical thermal (80°C) or
  voltage (4.63V) threshold under each protection mode.

VALUES (from Experiment 2 calibrated simulation):
  - Static Threshold:        12 minutes  (reacts only on absolute T >= T_safe)
  - Threshold + Derivatives: 28 minutes  (ΔT/Δt and ΔV/Δt provide earlier warning)
  - Full Bodyguard:          No event    (test concluded at 120 minutes)

WHAT IT PROVES:
  Using Thermal Velocity (ΔT/Δt) and Voltage Drop Rate (ΔV/Δt) provides
  an early warning that absolute thresholds miss entirely.

FORMAT:
  Comparison bar chart showing "Survival Time".

RUN:
  python experiments/exp2_result2_chart.py
"""
import os
import numpy as np

def make_result2_chart():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patheffects as pe

    # ── DATA ──────────────────────────────────────────────────────────────
    modes         = ["Static\nThreshold", "Threshold +\nDerivatives", "PAHPS\n(Full System)"]
    survival_min  = [12, 28, 120]           # minutes before first critical event
    is_no_event   = [False, False, True]    # Full Bodyguard never hits critical
    bar_colors    = ["#E74C3C", "#F39C12", "#27AE60"]
    edge_colors   = ["#C0392B", "#D68910", "#1E8449"]

    # Thresholds
    T_CRIT  = 80    # °C
    V_CRIT  = 4.63  # V
    TEST_END = 120  # minutes (test concluded)

    # ── FIGURE SETUP ──────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(10, 7))
    fig.patch.set_facecolor("#FAFAFA")
    ax.set_facecolor("#FAFAFA")

    # ── BAR CHART ─────────────────────────────────────────────────────────
    x = np.arange(len(modes))
    bar_width = 0.52

    bars = ax.bar(
        x, survival_min,
        width=bar_width,
        color=bar_colors,
        edgecolor=edge_colors,
        linewidth=2.0,
        zorder=3,
    )

    # Add gradient effect via overlay
    for i, bar in enumerate(bars):
        bar.set_alpha(0.92)

    # ── ANNOTATIONS ON BARS ───────────────────────────────────────────────
    for i, (bar, val, no_ev) in enumerate(zip(bars, survival_min, is_no_event)):
        bx = bar.get_x() + bar.get_width() / 2
        by = bar.get_height()

        if no_ev:
            # Full Bodyguard: no event label
            label_main = "No Critical Event"
            label_sub  = f"Test concluded at {TEST_END} min"
            ax.text(bx, by + 6, label_main,
                    ha="center", va="bottom", fontsize=13,
                    fontweight="bold", color="#1E8449",
                    path_effects=[pe.withStroke(linewidth=3, foreground="white")])
        else:
            # Show exact minutes
            ax.text(bx, by + 2.5, f"{val} min",
                    ha="center", va="bottom", fontsize=15,
                    fontweight="bold", color=edge_colors[i],
                    path_effects=[pe.withStroke(linewidth=3, foreground="white")])

    # ── REFERENCE LINES ──────────────────────────────────────────────────
    ax.axhline(y=TEST_END, color="#2C3E50", ls="--", lw=1.2, alpha=0.35, zorder=2)
    ax.text(len(modes) - 0.72, TEST_END + 1.5,
            f"Test Duration = {TEST_END} min",
            fontsize=8.5, color="#2C3E50", fontstyle="italic",
            ha="right", va="bottom")

    # ── AXIS FORMATTING ──────────────────────────────────────────────────
    ax.set_xticks(x)
    ax.set_xticklabels(modes, fontsize=12, fontweight="bold")
    ax.set_ylabel("Survival Time (minutes)", fontsize=13, fontweight="bold",
                  labelpad=10)
    ax.set_ylim(0, 145)
    ax.set_xlim(-0.6, len(modes) - 0.4)

    # Y-axis fine grid
    ax.yaxis.set_major_locator(plt.MultipleLocator(20))
    ax.yaxis.set_minor_locator(plt.MultipleLocator(10))
    ax.grid(True, axis="y", which="major", alpha=0.25, color="#888888", zorder=1)
    ax.grid(True, axis="y", which="minor", alpha=0.10, color="#AAAAAA",
            ls=":", zorder=1)
    ax.tick_params(axis="y", labelsize=11)

    # Remove top/right spines
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#CCCCCC")
    ax.spines["bottom"].set_color("#CCCCCC")

    # ── TITLE & SUBTITLE ─────────────────────────────────────────────────
    ax.set_title(
        "Time to First Critical Event\n(Early Warning Proof)",
        fontsize=16, fontweight="bold", pad=18, color="#2C3E50",
    )

    # ── ANNOTATION BOX ───────────────────────────────────────────────────
    info_text = (
        f"Critical Thresholds:  T ≥ {T_CRIT}°C  or  V ≤ {V_CRIT}V\n"
        f"Derivatives used:  Thermal Velocity (ΔT/Δt)  •  Voltage Drop Rate (ΔV/Δt)"
    )
    props = dict(boxstyle="round,pad=0.5", facecolor="#EBF5FB",
                 edgecolor="#5DADE2", alpha=0.85)
    ax.text(0.02, 0.97, info_text, transform=ax.transAxes,
            fontsize=9, verticalalignment="top",
            bbox=props, family="monospace", color="#2C3E50")

    # ── IMPROVEMENT ARROWS ───────────────────────────────────────────────
    # Arrow from Static → Threshold+Deriv  (×2.3 improvement)
    ax.annotate(
        "", xy=(1, 28), xytext=(0, 12),
        arrowprops=dict(arrowstyle="-|>", color="#7F8C8D", lw=1.8,
                        connectionstyle="arc3,rad=-0.25"),
        zorder=4,
    )
    ax.text(0.5, 22, "×2.3 longer", fontsize=9, fontweight="bold",
            ha="center", va="center", color="#7F8C8D", rotation=20,
            path_effects=[pe.withStroke(linewidth=2, foreground="white")])

    # Arrow from Threshold+Deriv → PAHPS (Full System)  (no event)
    ax.annotate(
        "", xy=(2, 120), xytext=(1, 28),
        arrowprops=dict(arrowstyle="-|>", color="#7F8C8D", lw=1.8,
                        connectionstyle="arc3,rad=-0.25"),
        zorder=4,
    )
    ax.text(1.5, 80, "∞ (no event)", fontsize=9, fontweight="bold",
            ha="center", va="center", color="#27AE60", rotation=35,
            path_effects=[pe.withStroke(linewidth=2, foreground="white")])

    # ── SAVE ──────────────────────────────────────────────────────────────
    plt.tight_layout()
    out = os.path.join("experiments", "output", "result2_survival_time.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    plt.savefig(out, dpi=200, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"  -> Saved: {out}")
    return out


if __name__ == "__main__":
    print("=" * 65)
    print("  RESULT 2: Time to First Critical Event (Early Warning Proof)")
    print("=" * 65)

    print("\n  Values:")
    print("    Static Threshold:        12 min  (absolute T/V thresholds only)")
    print("    Threshold + Derivatives: 28 min  (dT/dt + dV/dt early warning)")
    print("    Full Bodyguard:          No event (120 min test concluded)")

    print("\n  Generating chart...")
    path = make_result2_chart()
    print(f"\n  Done! Output: {path}")
