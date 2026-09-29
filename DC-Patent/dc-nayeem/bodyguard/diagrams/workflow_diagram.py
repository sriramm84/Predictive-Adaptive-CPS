"""
Bodyguard Patent -- System Workflow Diagram (Grayscale, Patent-Grade)
=====================================================================

Generates a professional grayscale block-diagram matching the visual style
of academic/patent workflow figures: rectangular boxes, numbered stages,
sub-components stacked vertically, clean directional arrows, and hatched
output blocks.

RUN:
  python diagrams/workflow_diagram.py

OUTPUT:
  diagrams/bodyguard_workflow_diagram.png
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle
from matplotlib.lines import Line2D
import matplotlib.patches as mpatches
import numpy as np


def make_workflow_diagram():
    # =====================================================================
    #  CANVAS SETUP
    # =====================================================================
    fig, ax = plt.subplots(figsize=(24, 11))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.set_xlim(-0.5, 24.5)
    ax.set_ylim(-0.5, 11)
    ax.set_aspect("equal")
    ax.axis("off")

    # =====================================================================
    #  COLOR PALETTE (Grayscale / Patent style)
    # =====================================================================
    # Stage header backgrounds (muted olive-gray like reference)
    STAGE_BG       = "#C8C8B0"   # olive-gray for stage headers
    STAGE_BG_ALT   = "#B8B8A0"   # slightly darker alternate
    SUB_BOX_BG     = "#E8E8DC"   # light gray-cream for sub-boxes
    SUB_BOX_BG2    = "#D8D8CC"   # medium gray for sub-boxes
    INPUT_BG       = "#F0F0E8"   # very light for input labels
    OUTPUT_BG      = "#E0E0D4"   # for output blocks
    BORDER         = "#404040"   # dark gray borders
    BORDER_LIGHT   = "#606060"   # medium borders
    TEXT_COLOR     = "#1A1A1A"   # near-black text
    ARROW_COLOR    = "#303030"   # dark arrows
    HATCH_COLOR    = "#808080"   # hatching

    # =====================================================================
    #  HELPER FUNCTIONS
    # =====================================================================
    def draw_box(x, y, w, h, text, bg=SUB_BOX_BG, ec=BORDER, lw=1.5,
                 fontsize=9, bold=False, ha="center", va="center",
                 hatch=None, text_color=TEXT_COLOR, zorder=3):
        """Draw a rectangular box with centered text."""
        rect = Rectangle((x, y), w, h, facecolor=bg, edgecolor=ec,
                          linewidth=lw, zorder=zorder, hatch=hatch)
        ax.add_patch(rect)
        fw = "bold" if bold else "normal"
        ax.text(x + w/2, y + h/2, text, ha=ha, va=va, fontsize=fontsize,
                fontweight=fw, color=text_color, zorder=zorder+1,
                linespacing=1.35, family="serif")

    def draw_stage_header(x, y, w, h, text, bg=STAGE_BG):
        """Draw a stage header box with bold title."""
        draw_box(x, y, w, h, text, bg=bg, ec=BORDER, lw=2.0,
                 fontsize=10.5, bold=True, zorder=4)

    def draw_arrow_h(x1, y1, x2, y2, lw=2.0):
        """Horizontal arrow."""
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                     arrowprops=dict(arrowstyle="-|>", color=ARROW_COLOR,
                                     lw=lw, mutation_scale=18),
                     zorder=5)

    def draw_arrow_custom(x1, y1, x2, y2, lw=1.5, color=ARROW_COLOR):
        """Custom directional arrow."""
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                     arrowprops=dict(arrowstyle="-|>", color=color,
                                     lw=lw, mutation_scale=15),
                     zorder=5)

    def draw_line(x1, y1, x2, y2, lw=1.5, color=ARROW_COLOR, ls="-"):
        """Simple line without arrowhead."""
        ax.plot([x1, x2], [y1, y2], color=color, lw=lw, ls=ls, zorder=5)

    def draw_input_label(x, y, text, fontsize=9):
        """Draw an input label (left side)."""
        ax.text(x, y, text, ha="right", va="center", fontsize=fontsize,
                fontweight="normal", color=TEXT_COLOR,
                family="serif", zorder=5)

    # =====================================================================
    #  TITLE
    # =====================================================================
    fig.text(0.5, 0.96,
             "FIGURE 1: Workflow of Bodyguard -- Hardware-Aware Predictive Task Routing System",
             ha="center", va="top", fontsize=11, fontweight="normal",
             color=TEXT_COLOR, family="serif")
    fig.text(0.5, 0.93,
             "Workflow of Bodyguard\u2013Predictive Task Routing System",
             ha="center", va="top", fontsize=16, fontweight="bold",
             color=TEXT_COLOR, family="serif")

    # =====================================================================
    #  LAYOUT CONSTANTS
    # =====================================================================
    # Column X positions for the 6 stages
    col = [2.3, 5.8, 9.3, 12.8, 16.2, 20.0]
    stage_w = 2.8
    stage_top = 9.5
    header_h = 0.9

    # =====================================================================
    #  INPUT SOURCES (far left)
    # =====================================================================
    # I2C Bus input
    draw_box(0.0, 7.6, 1.8, 1.5,
             "I2C Bus\n(INA219\nSensor)",
             bg=INPUT_BG, fontsize=9)
    draw_input_label(-0.15, 8.35, "Hardware\nSensor", fontsize=8)

    # GPIO Bus input
    draw_box(0.0, 5.6, 1.8, 1.5,
             "GPIO Bus\n(thermal_\nzone0)",
             bg=INPUT_BG, fontsize=9)

    # OS Kernel input
    draw_box(0.0, 3.6, 1.8, 1.5,
             "OS /proc\nKernel\nInterface",
             bg=INPUT_BG, fontsize=9)
    draw_input_label(-0.15, 4.35, "Software\nMetrics", fontsize=8)

    # Input arrows driving into stage 1
    draw_arrow_h(1.8, 8.35, col[0], 8.35)
    draw_arrow_h(1.8, 6.35, col[0], 6.35)
    draw_arrow_h(1.8, 4.35, col[0], 5.2)

    # Input labels on arrows
    ax.text(2.05, 8.55, "Voltage (V)\nCurrent (I)", fontsize=7,
            color=TEXT_COLOR, family="serif", va="bottom")
    ax.text(2.05, 6.55, "Temperature\n(T)", fontsize=7,
            color=TEXT_COLOR, family="serif", va="bottom")
    ax.text(2.05, 5.05, "CPU (%)\nQueue Depth", fontsize=7,
            color=TEXT_COLOR, family="serif", va="bottom")

    # Task Queue input (bottom left)
    draw_box(0.0, 1.2, 1.8, 1.8,
             "Incoming\nTask\nQueue",
             bg=INPUT_BG, fontsize=9, bold=True)
    draw_input_label(-0.15, 2.1, "Input", fontsize=9)

    # =====================================================================
    #  STAGE 1: Data Acquisition Module
    # =====================================================================
    x1 = col[0]
    # Stage outline
    draw_box(x1, 3.5, stage_w, 6.8, "", bg="#E0E0D0", ec=BORDER, lw=2.0,
             fontsize=1, zorder=2)
    # Header
    draw_stage_header(x1, stage_top, stage_w, header_h,
                      "1. Data\nAcquisition Module")
    # Sub-boxes
    draw_box(x1+0.15, 8.0, stage_w-0.3, 1.1,
             "PhysicsSimulator\n/ HW Reader",
             bg=SUB_BOX_BG2, fontsize=9)
    draw_box(x1+0.15, 6.6, stage_w-0.3, 1.1,
             "SensorReading\n(T, V, I, CPU%, Q)",
             bg=SUB_BOX_BG, fontsize=9)
    draw_box(x1+0.15, 5.1, stage_w-0.3, 1.1,
             "SensorHistory\n(Circular Buffer\nDepth = 10)",
             bg=SUB_BOX_BG, fontsize=9)
    draw_box(x1+0.15, 3.7, stage_w-0.3, 1.1,
             "Normalization\n& Calibration",
             bg=SUB_BOX_BG2, fontsize=9)

    # Internal arrows
    draw_arrow_custom(x1+stage_w/2, 8.0, x1+stage_w/2, 7.75, lw=1.2)
    draw_arrow_custom(x1+stage_w/2, 6.6, x1+stage_w/2, 6.35, lw=1.2)
    draw_arrow_custom(x1+stage_w/2, 5.1, x1+stage_w/2, 4.85, lw=1.2)

    # =====================================================================
    #  STAGE 2: Derivative Computation
    # =====================================================================
    x2 = col[1]
    draw_box(x2, 3.5, stage_w, 6.8, "", bg="#D8D8CC", ec=BORDER, lw=2.0,
             fontsize=1, zorder=2)
    draw_stage_header(x2, stage_top, stage_w, header_h,
                      "2. Derivative\nComputation", bg=STAGE_BG_ALT)
    draw_box(x2+0.15, 8.0, stage_w-0.3, 1.1,
             "dT/dt\nThermal Velocity\n(deg C/min)",
             bg=SUB_BOX_BG, fontsize=9)
    draw_box(x2+0.15, 6.6, stage_w-0.3, 1.1,
             "dV/dt\nVoltage Drop\nRate (V/sec)",
             bg=SUB_BOX_BG, fontsize=9)
    draw_box(x2+0.15, 5.1, stage_w-0.3, 1.1,
             "sigma_V\nVoltage Noise\n(Std Dev)",
             bg=SUB_BOX_BG, fontsize=9)
    draw_box(x2+0.15, 3.7, stage_w-0.3, 1.1,
             "L_press\nLoad Pressure\n(CPU + Queue)",
             bg=SUB_BOX_BG2, fontsize=9)

    # Arrow: stage 1 -> stage 2
    draw_arrow_h(x1+stage_w, 7.0, x2, 7.0)

    # =====================================================================
    #  STAGE 3: Risk Score Engine
    # =====================================================================
    x3 = col[2]
    draw_box(x3, 3.5, stage_w, 6.8, "", bg="#D0D0C4", ec=BORDER, lw=2.0,
             fontsize=1, zorder=2)
    draw_stage_header(x3, stage_top, stage_w, header_h,
                      "3. Risk Score\nEngine", bg=STAGE_BG)
    draw_box(x3+0.15, 8.0, stage_w-0.3, 1.1,
             "Six-Term\nWeighted Sum\nR = Sum(w_i * x_i)",
             bg=SUB_BOX_BG2, fontsize=9, bold=True)
    draw_box(x3+0.15, 6.6, stage_w-0.3, 1.1,
             "i) x1: T_proximity\nii) x2: dT/dt velocity\niii) x3: V_sag",
             bg=SUB_BOX_BG, fontsize=8)
    draw_box(x3+0.15, 5.1, stage_w-0.3, 1.1,
             "iv) x4: dV/dt rate\nv) x5: sigma_V\nvi) x6: Load_pressure",
             bg=SUB_BOX_BG, fontsize=8)
    draw_box(x3+0.15, 3.7, stage_w-0.3, 1.1,
             "Bounded Output\nR in [0, 1]\n(Clip & Normalize)",
             bg=SUB_BOX_BG2, fontsize=9)

    # Internal arrows
    draw_arrow_custom(x3+stage_w/2, 8.0, x3+stage_w/2, 7.75, lw=1.2)
    draw_arrow_custom(x3+stage_w/2, 6.6, x3+stage_w/2, 6.35, lw=1.2)
    draw_arrow_custom(x3+stage_w/2, 5.1, x3+stage_w/2, 4.85, lw=1.2)

    # Arrow: stage 2 -> stage 3
    draw_arrow_h(x2+stage_w, 7.0, x3, 7.0)

    # =====================================================================
    #  STAGE 4: State Classification (FSM)
    # =====================================================================
    x4 = col[3]
    draw_box(x4, 3.5, stage_w, 6.8, "", bg="#C8C8BC", ec=BORDER, lw=2.0,
             fontsize=1, zorder=2)
    draw_stage_header(x4, stage_top, stage_w, header_h,
                      "4. State\nClassification", bg=STAGE_BG_ALT)

    draw_box(x4+0.15, 8.0, stage_w-0.3, 1.1,
             "Dual-Hysteresis\nFinite State\nMachine (FSM)",
             bg=SUB_BOX_BG2, fontsize=9, bold=True)

    # Four state boxes arranged as 2x2
    sw = (stage_w - 0.5) / 2
    sh = 1.0
    draw_box(x4+0.15, 6.7, sw, sh, "SAFE", bg="#E8E8E0", fontsize=10, bold=True)
    draw_box(x4+0.15+sw+0.2, 6.7, sw, sh, "WARNING", bg="#D0D0C8", fontsize=10, bold=True)
    draw_box(x4+0.15, 5.4, sw, sh, "CRITICAL", bg="#B8B8B0", fontsize=10, bold=True)
    draw_box(x4+0.15+sw+0.2, 5.4, sw, sh, "EMERG\nENCY", bg="#A0A098", fontsize=9, bold=True)

    # Arrows between states
    draw_arrow_custom(x4+0.15+sw, 7.2, x4+0.15+sw+0.2, 7.2, lw=1.0)
    draw_arrow_custom(x4+0.15+sw+0.2, 7.0, x4+0.15+sw, 7.0, lw=1.0)
    draw_arrow_custom(x4+0.15+sw, 5.9, x4+0.15+sw+0.2, 5.9, lw=1.0)
    draw_arrow_custom(x4+stage_w/2+0.1, 6.7, x4+stage_w/2+0.1, 6.45, lw=1.0)

    draw_box(x4+0.15, 3.7, stage_w-0.3, 1.4,
             "Hysteresis Bands:\nSAFE->WARN: R>=0.30\nWARN->SAFE: R<0.25\nWARN->CRIT: R>=0.65\nCRIT->WARN: R<0.55",
             bg=SUB_BOX_BG, fontsize=7)

    # Arrow: stage 3 -> stage 4
    draw_arrow_h(x3+stage_w, 7.0, x4, 7.0)
    ax.text(x3+stage_w+0.15, 7.2, "R(t)", fontsize=9,
            fontweight="bold", color=TEXT_COLOR, family="serif")

    # =====================================================================
    #  STAGE 5: Task Admission Controller
    # =====================================================================
    x5 = col[4]
    draw_box(x5, 1.0, stage_w+0.4, 9.2, "", bg="#C0C0B4", ec=BORDER, lw=2.0,
             fontsize=1, zorder=2)
    draw_stage_header(x5, stage_top, stage_w+0.4, header_h,
                      "5. Task Admission\nController", bg=STAGE_BG)

    draw_box(x5+0.15, 8.0, stage_w+0.1, 1.1,
             "Gate 1: STATE\nDevice State\nDetermines Eligibility",
             bg=SUB_BOX_BG2, fontsize=9, bold=True)

    draw_box(x5+0.15, 6.5, stage_w+0.1, 1.1,
             "Gate 2: BUDGET\nSafety Budget B(t)\nCapacity Check",
             bg=SUB_BOX_BG2, fontsize=9, bold=True)

    draw_box(x5+0.15, 5.0, stage_w+0.1, 1.1,
             "Budget Formula:\nB_t = floor(\nB_max*(1-R) - C_w)",
             bg=SUB_BOX_BG, fontsize=8)

    draw_box(x5+0.15, 3.5, stage_w+0.1, 1.1,
             "Window: 30 sec\nB_max = 10 tasks\nReplenish: R < 0.25",
             bg=SUB_BOX_BG, fontsize=8)

    draw_box(x5+0.15, 1.8, stage_w+0.1, 1.4,
             "Routing Decision:\ni)   LOCAL\nii)  OFFLOAD\niii) THROTTLE\niv)  REJECT",
             bg=SUB_BOX_BG2, fontsize=8, bold=True)

    # Internal arrows
    draw_arrow_custom(x5+stage_w/2+0.2, 8.0, x5+stage_w/2+0.2, 7.75, lw=1.2)
    draw_arrow_custom(x5+stage_w/2+0.2, 6.5, x5+stage_w/2+0.2, 6.25, lw=1.2)
    draw_arrow_custom(x5+stage_w/2+0.2, 5.0, x5+stage_w/2+0.2, 4.75, lw=1.2)
    draw_arrow_custom(x5+stage_w/2+0.2, 3.5, x5+stage_w/2+0.2, 3.25, lw=1.2)

    # Arrow: stage 4 -> stage 5 (state output)
    draw_arrow_h(x4+stage_w, 8.5, x5, 8.5)
    ax.text(x4+stage_w+0.15, 8.7, "State", fontsize=8,
            fontweight="bold", color=TEXT_COLOR, family="serif")

    # Arrow: stage 3 -> stage 5 (risk score to budget)
    draw_line(x3+stage_w, 4.2, x3+stage_w+0.6, 4.2, lw=1.5)
    draw_line(x3+stage_w+0.6, 4.2, x3+stage_w+0.6, 2.0, lw=1.5)
    draw_arrow_h(x3+stage_w+0.6, 2.0, x5, 5.5)
    ax.text(x3+stage_w+0.15, 3.6, "R(t)", fontsize=8,
            fontweight="bold", color=TEXT_COLOR, family="serif")

    # Arrow: task input -> stage 5
    draw_arrow_h(1.8, 2.1, x5, 2.5)
    ax.text(4.5, 2.45, "Task (weight, priority, cpu_load)", fontsize=8,
            fontweight="bold", color=TEXT_COLOR, family="serif")

    # =====================================================================
    #  STAGE 6: Execution & Output (hatched boxes like reference)
    # =====================================================================
    x6 = col[5]
    draw_stage_header(x6, stage_top, stage_w, header_h,
                      "6. Execution\n& Telemetry", bg=STAGE_BG_ALT)

    # LOCAL execution (hatched)
    draw_box(x6+0.15, 7.6, stage_w-0.3, 1.5,
             "Local\nExecution\n(On-Device)",
             bg=OUTPUT_BG, fontsize=9, bold=True, hatch="//")

    # Cloud offload (hatched)
    draw_box(x6+0.15, 5.6, stage_w-0.3, 1.5,
             "Cloud\nOffload\n(Remote API)",
             bg=OUTPUT_BG, fontsize=9, bold=True, hatch="//")

    # Telemetry Logger (hatched)
    draw_box(x6+0.15, 3.6, stage_w-0.3, 1.5,
             "Telemetry\nLogger\n(CSV / JSON)",
             bg=OUTPUT_BG, fontsize=9, bold=True, hatch="//")

    # Output labels on far right
    ax.text(x6+stage_w+0.2, 8.35, "Tasks\nexecuted\nlocally",
            fontsize=8, color=TEXT_COLOR, family="serif", va="center")
    ax.text(x6+stage_w+0.2, 6.35, "Tasks\nrouted\nto Cloud",
            fontsize=8, color=TEXT_COLOR, family="serif", va="center")
    ax.text(x6+stage_w+0.2, 4.35, "Diagnostic\nData\nRecorded",
            fontsize=8, color=TEXT_COLOR, family="serif", va="center")

    # Arrows: stage 5 -> stage 6
    draw_arrow_h(x5+stage_w+0.4, 8.5, x6+0.15, 8.35)
    draw_arrow_h(x5+stage_w+0.4, 6.5, x6+0.15, 6.35)
    # Line from routing decision to telemetry
    draw_line(x5+stage_w+0.4, 2.5, x6-0.3, 2.5, lw=1.5)
    draw_arrow_custom(x6-0.3, 2.5, x6+0.15, 4.35, lw=1.5)

    # Output arrows to far right
    draw_arrow_h(x6+stage_w-0.15, 8.35, x6+stage_w+0.1, 8.35)
    draw_arrow_h(x6+stage_w-0.15, 6.35, x6+stage_w+0.1, 6.35)
    draw_arrow_h(x6+stage_w-0.15, 4.35, x6+stage_w+0.1, 4.35)

    # =====================================================================
    #  FEEDBACK LOOP (bottom)
    # =====================================================================
    fb_y = 0.6
    # Line from Local Execution down and back to inputs
    draw_line(x6+stage_w/2, 3.6, x6+stage_w/2, fb_y, lw=1.5,
              color="#606060", ls="--")
    draw_line(x6+stage_w/2, fb_y, 0.9, fb_y, lw=1.5,
              color="#606060", ls="--")
    draw_arrow_custom(0.9, fb_y, 0.9, 3.6, lw=1.5, color="#606060")

    ax.text(10.5, 0.25,
            "Feedback Loop: Local execution changes CPU load / temperature "
            "--- sensed in next sampling cycle",
            ha="center", va="center", fontsize=8, fontstyle="italic",
            color="#606060", family="serif")

    # =====================================================================
    #  SAVE
    # =====================================================================
    plt.subplots_adjust(left=0.01, right=0.99, top=0.90, bottom=0.03)
    out = os.path.join("diagrams", "bodyguard_workflow_diagram.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    plt.savefig(out, dpi=250, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  -> Saved: {out}")
    return out


if __name__ == "__main__":
    print("=" * 65)
    print("  Bodyguard System Workflow Diagram (Grayscale Patent Style)")
    print("=" * 65)
    print("\n  Generating diagram...")
    path = make_workflow_diagram()
    print(f"\n  Done! Output: {path}")
