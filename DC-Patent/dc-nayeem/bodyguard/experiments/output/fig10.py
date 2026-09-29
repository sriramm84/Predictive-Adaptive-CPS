import matplotlib.pyplot as plt

# Data from the Recovery Timeline
time = [40, 45, 50, 55, 60, 65, 70, 75, 80, 85]
temp = [72.5, 76.8, 80.2, 82.5, 81.1, 78.4, 75.2, 71.8, 68.4, 64.1]
risk = [0.612, 0.745, 0.842, 0.895, 0.871, 0.835, 0.712, 0.585, 0.284, 0.231]

fig, ax1 = plt.subplots(figsize=(12, 7))

# Left Axis: Temperature
ax1.set_xlabel('Time (Seconds)', fontsize=12)
ax1.set_ylabel('Temperature (T) in °C', color='tab:red', fontsize=12, fontweight='bold')
line1 = ax1.plot(time, temp, color='tab:red', marker='s', linewidth=3, label='SoC Temperature (T)')
ax1.tick_params(axis='y', labelcolor='tab:red')
ax1.grid(True, which='both', linestyle='--', alpha=0.5)

# Right Axis: Risk Score
ax2 = ax1.twinx()
ax2.set_ylabel('Risk Score (R)', color='tab:blue', fontsize=12, fontweight='bold')
line2 = ax2.plot(time, risk, color='tab:blue', marker='o', linestyle='--', linewidth=2, label='Risk Score (R)')
ax2.tick_params(axis='y', labelcolor='tab:blue')

# Threshold Annotation
plt.axhline(y=0.85, color='black', linestyle=':', alpha=0.7)
plt.annotate('EMERGENCY THRESHOLD (0.85)', xy=(55, 0.85), xytext=(60, 0.90),
             arrowprops=dict(facecolor='black', shrink=0.05), fontsize=10, fontweight='bold')

# Emergency Zone Highlight
plt.axvspan(55, 60, color='red', alpha=0.15, label='Survival Mode (Sleep Interleave)')

# Title and Legend
plt.title('Result 8: Survival Mode Efficacy - Physical Recovery via Sleep Interleaving', fontsize=14, pad=20)
lns = line1 + line2
labs = [l.get_label() for l in lns]
ax1.legend(lns, labs, loc='upper right')

plt.tight_layout()
plt.show()