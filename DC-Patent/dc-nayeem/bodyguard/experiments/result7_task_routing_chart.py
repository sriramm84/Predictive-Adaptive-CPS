"""
Patent Evidence -- Result 7: Task Routing Bar Chart
=====================================================

PURPOSE:
  Generate a bar chart showing Local vs Cloud task distribution
  across the three operational states (SAFE, WARNING, CRITICAL).

  This visually proves the "Proportional Protection" novelty:
    - SAFE:     All bars are Blue (Local)
    - WARNING:  Mixed Blue/Orange (lightweight local, heavy cloud)
    - CRITICAL: Mostly Orange (Cloud), only mission-critical local

RUN:
  First generate the CSV:  python experiments/result7_task_routing_data.py
  Then generate the chart: python experiments/result7_task_routing_chart.py
"""

import csv
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def make_result7_chart():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patheffects as pe

    # =====================================================================
    #  LOAD CSV
    # =====================================================================
    csv_path = os.path.join("experiments", "output", "result7_task_routing.csv")
    if not os.path.exists(csv_path):
        print(f"  ERROR: CSV not found at {csv_path}")
        print(f"  Run: python experiments/result7_task_routing_data.py first")
        return None

    rows = []
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    # =====================================================================
    #  AGGREGATE DATA BY STATE
    # =====================================================================
    states_order = ["SAFE", "WARNING", "CRITICAL"]
    state_local = {s: 0 for s in states_order}
    state_cloud = {s: 0 for s in states_order}
    state_throttle = {s: 0 for s in states_order}
    state_reject = {s: 0 for s in states_order}

    for r in rows:
        s = r["State"]
        d = r["Decision"]
        if s not in state_local:
            continue  # skip EMERGENCY if present
        if d == "LOCAL":
            state_local[s] += 1
        elif d == "OFFLOAD":
            state_cloud[s] += 1
        elif d == "THROTTLE":
            state_throttle[s] += 1
        elif d == "REJECT":
            state_reject[s] += 1

    local_counts = [state_local[s] for s in states_order]
    cloud_counts = [state_cloud[s] for s in states_order]

    # =====================================================================
    #  FIGURE
    # =====================================================================
    fig, (ax_bar, ax_detail) = plt.subplots(
        1, 2, figsize=(16, 8), width_ratios=[1.2, 1],
        facecolor="#FAFAFA"
    )

    # =====================================================================
    #  PANEL 1: STACKED BAR CHART
    # =====================================================================
    ax = ax_bar
    ax.set_facecolor("#FAFAFA")

    x = np.arange(len(states_order))
    bar_width = 0.35

    # Bar colors
    color_local = "#2E86C1"
    color_cloud = "#E67E22"

    bars_local = ax.bar(x - bar_width/2, local_counts, bar_width,
                         label="Local Execution", color=color_local,
                         edgecolor="white", linewidth=1.5, zorder=3)
    bars_cloud = ax.bar(x + bar_width/2, cloud_counts, bar_width,
                         label="Cloud Offload", color=color_cloud,
                         edgecolor="white", linewidth=1.5, zorder=3)

    # Add count labels on bars
    for bar in bars_local:
        height = bar.get_height()
        if height > 0:
            ax.text(bar.get_x() + bar.get_width()/2., height + 0.15,
                    f"{int(height)}", ha="center", va="bottom",
                    fontsize=13, fontweight="bold", color=color_local)

    for bar in bars_cloud:
        height = bar.get_height()
        if height > 0:
            ax.text(bar.get_x() + bar.get_width()/2., height + 0.15,
                    f"{int(height)}", ha="center", va="bottom",
                    fontsize=13, fontweight="bold", color=color_cloud)

    # State-colored background
    state_colors = ["#27AE6020", "#F39C1220", "#E74C3C20"]
    for i, (s, c) in enumerate(zip(states_order, state_colors)):
        ax.axvspan(i - 0.5, i + 0.5, color=c, zorder=1)

    # Styling
    ax.set_xlabel("System State", fontsize=14, fontweight="bold", labelpad=10)
    ax.set_ylabel("Number of Tasks", fontsize=14, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(states_order, fontsize=13, fontweight="bold")
    ax.set_title(
        "Result 7: Task Routing — Local vs Cloud Offload\n"
        "(Dual-Gate Admission Proportional Protection)",
        fontsize=14, fontweight="bold", color="#2C3E50", pad=15
    )
    ax.legend(fontsize=12, loc="upper right", framealpha=0.9,
              edgecolor="#BDC3C7")
    ax.grid(axis="y", alpha=0.2)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # Set y-axis to integer only
    ax.set_ylim(0, max(max(local_counts), max(cloud_counts)) + 3)
    ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))

    # =====================================================================
    #  PANEL 2: DETAILED DECISION TABLE + ANALYSIS
    # =====================================================================
    ax2 = ax_detail
    ax2.set_facecolor("#FAFAFA")
    ax2.axis("off")

    # Decision table
    col_labels = ["State", "Local", "Cloud", "Total", "Local %"]
    table_data = []
    for s in states_order:
        total = state_local[s] + state_cloud[s]
        pct = (state_local[s] / total * 100) if total > 0 else 0
        table_data.append([
            s,
            str(state_local[s]),
            str(state_cloud[s]),
            str(total),
            f"{pct:.0f}%"
        ])

    # Add totals row
    total_local = sum(local_counts)
    total_cloud = sum(cloud_counts)
    total_all = total_local + total_cloud
    table_data.append([
        "TOTAL",
        str(total_local),
        str(total_cloud),
        str(total_all),
        f"{total_local/total_all*100:.0f}%"
    ])

    tbl = ax2.table(
        cellText=table_data, colLabels=col_labels,
        cellLoc="center", loc="upper center",
        colWidths=[0.20, 0.15, 0.15, 0.15, 0.15],
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(11)
    tbl.scale(1.0, 1.8)

    # Style header
    for j in range(len(col_labels)):
        cell = tbl[0, j]
        cell.set_facecolor("#2C3E50")
        cell.set_text_props(color="white", fontweight="bold")

    # Style data rows
    state_bg = {"SAFE": "#E8F8F5", "WARNING": "#FEF9E7", "CRITICAL": "#FDEDEC"}
    for i in range(1, len(table_data) + 1):
        for j in range(len(col_labels)):
            cell = tbl[i, j]
            if i <= len(states_order):
                cell.set_facecolor(state_bg.get(states_order[i-1], "#FDFEFE"))
            else:
                cell.set_facecolor("#D5DBDB")
                cell.set_text_props(fontweight="bold")
            cell.set_edgecolor("#BDC3C7")

    ax2.set_title("Admission Decision Summary",
                  fontsize=13, fontweight="bold", color="#2C3E50", pad=15)

    # Analysis text box
    # Compute reactive comparison (all-or-nothing throttling)
    reactive_local = state_local.get("SAFE", 0)
    improvement = ((total_local - reactive_local) / reactive_local * 100) if reactive_local > 0 else 0

    analysis = (
        "Proportional Protection Analysis\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Bodyguard (this system):\n"
        f"  {total_local} of {total_all} tasks executed locally\n\n"
        f"Standard Reactive Throttling:\n"
        f"  {reactive_local} of {total_all} tasks executed locally\n"
        f"  (blocks ALL tasks in WARNING/CRITICAL)\n\n"
        f"Improvement: {improvement:.0f}% more local availability\n\n"
        "Key insight: Lightweight tasks CONTINUE\n"
        "running locally even in WARNING state,\n"
        "preserving device functionality while\n"
        "protecting hardware by offloading\n"
        "heavy workloads to the cloud."
    )
    props = dict(boxstyle="round,pad=0.6", facecolor="#EBF5FB",
                 edgecolor="#2E86C1", alpha=0.9)
    ax2.text(0.5, 0.12, analysis, transform=ax2.transAxes,
             fontsize=9.5, va="bottom", ha="center", bbox=props,
             family="monospace", color="#2C3E50")

    # =====================================================================
    #  SAVE
    # =====================================================================
    plt.tight_layout()
    out_path = os.path.join("experiments", "output", "result7_task_routing.png")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    plt.savefig(out_path, dpi=200, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close()
    print(f"  -> Saved: {out_path}")
    return out_path


if __name__ == "__main__":
    print("=" * 65)
    print("  RESULT 7: Task Routing Bar Chart")
    print("=" * 65)
    path = make_result7_chart()
    if path:
        print(f"\n  Done! Output: {path}")
    else:
        print("\n  Failed! Generate CSV data first.")
