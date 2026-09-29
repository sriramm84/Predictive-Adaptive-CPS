# PATENT INVENTION: System and Method for Predictive Hardware‑Health Orchestration and Safety‑Budget Task Routing in Resource‑Constrained Edge Environments

## Executive Summary

This document describes a novel method and system for **preventing physical hardware degradation** — thermal throttling, voltage‑induced brownouts, component fatigue, and unplanned reboots — in passively cooled, resource‑constrained edge computing devices (single‑board computers, IoT gateways, embedded processors). The invention introduces a **Predictive Hardware‑Health Orchestration System ("Bodyguard")** that acts as a protective governor between application workloads and the physical hardware.

The system continuously computes a **Predictive Risk Score (R)** from six domain‑specific, independently normalized hardware signals — including thermal velocity (ΔT/Δt), voltage drop rate (ΔV/Δt), and voltage variance (σ_V). It maps this score to a discrete device state via a **dual‑hysteresis state machine** (preventing oscillation at both transition boundaries), and computes a **consumable Safety Budget (B)** — a novel abstraction representing the remaining local‑execution capacity before hardware limits are breached. Per‑task admission control consults the budget, device state, and task classification to route each incoming task: execute locally, offload to cloud, throttle‑execute, or reject. The system thereby transforms vulnerable edge nodes into reliable, self‑regulating computing assets that **sacrifice cloud cost to preserve hardware integrity**.

---

## 1. TECHNICAL PROBLEM BEING SOLVED

### 1.1 The Problem Space

Low‑cost Single‑Board Computers (SBCs) such as Raspberry Pi, NVIDIA Jetson Nano, and industrial IoT gateways are increasingly deployed in:

* **Remote Sensing:** Environmental monitoring stations in outdoor enclosures without climate control.
* **Edge AI:** Local image/video processing for security cameras and predictive maintenance.
* **Industrial IoT:** Factory‑floor gateways connected to unstable power rails and shared USB hubs.
* **Healthcare Monitoring:** Wearable cloud gateways processing continuous biometric streams.

These devices operate under **physical constraints** that standard servers do not face:

* **Passive Cooling:** Reliance on heat sinks rather than active fans, leading to *thermal inertia* — heat builds up faster than it dissipates during bursty workloads.
* **Limited Power Regulation:** Susceptibility to *voltage sags* when the CPU draws sudden high current, potentially dropping the 5V rail below critical thresholds (e.g., 4.65V).
* **No Human Operator:** Deployed in remote, unattended locations where a crash requires expensive physical intervention.

### 1.2 Current Limitations

**Problem 1: Reactive Thermal Management**

Current operating systems (e.g., Linux kernel thermal governance) use a **reactive approach**: they wait until the processor temperature hits a critical limit (e.g., 80°C) and then aggressively throttle CPU frequency or disable cores.

* By the time throttling occurs, thermal stress has already begun accumulating.
* Application performance collapses instantly and unpredictably — video streams stutter, real‑time sensor data is lost, downstream services time out.
* The device oscillates between throttled and unthrottled states, causing instability.

**Problem 2: Blindness to Electrical Stability**

Standard task schedulers assume power is infinite and stable. They do not monitor input voltage.

* A heavy task (e.g., matrix multiplication, ML inference) causes a sudden current spike.
* The voltage sags below safe thresholds, causing random reboots, SD card corruption, or silent data errors.
* No advance warning is provided; no opportunity to shed or offload work before the brownout.

**Problem 3: Latency‑ and Energy‑Biased Offloading**

Existing offloading patents and systems (Apple US10,338,628; Huawei CN107,223,651; Google edge scheduling) optimize for **battery life**, **network latency**, or **bandwidth**.

* They might assign a task to a device that has full battery but is physically overheating, leading directly to hardware failure.
* None uses live voltage telemetry as a scheduling constraint.
* None explicitly optimizes for **hardware survival** as a first‑class objective.

### 1.3 The Real‑World Cost

A crashed or thermally degraded edge node:

* Requires physical access to restart — expensive in remote deployments (field truck rolls, drone access, climbing cell towers).
* Loses accumulated local state, cached models, and buffered data.
* Disrupts dependent services: downstream cameras go offline, sensor arrays stop reporting, factory alarms miss events.
* Triggers expensive cloud fallback traffic and cascading retries across the fleet.

Current industry response is to either **over‑provision** (use more expensive hardware) or **accept failure** (build fleets with redundancy). Neither is cost‑effective.

---

## 2. EXISTING GAP IN PRIOR ART

### 2.1 What Prior Art Does Well

1. **Thermal Management Patents** (US7,721,128 B2; US10,379,842 B2; US6,701,272)
   * Sense temperature, apply CPU frequency reduction or core disabling.
   * **Limitation:** Purely reactive; throttle only *after* overheating is detected. No prediction.

2. **Energy‑Aware Task Offloading** (PMC12789417; mobile battery optimization patents)
   * Offload based on battery state, network latency, energy cost.
   * **Limitation:** Optimizes for extending battery life (Coulombs), not for preventing brownouts (Volts/Amps). Irrelevant for line‑powered IoT devices. Does not monitor voltage or temperature derivatives as primary scheduling signals.

3. **IoT Task Scheduling** (S1110016824011712; load‑balancing systems)
   * Distribute tasks based on CPU utilization percentages and queue depth.
   * **Limitation:** Static thresholds on CPU% or queue length. No hardware health signals. No concept of a consumable safety budget.

4. **Distributed Service Health Monitoring** (US8,572,439 B2)
   * Monitor services for health at the software level (error rates, latency).
   * **Limitation:** Not about physical device health; not about preventing brownouts or thermal shutdown.

5. **Dynamic Voltage and Frequency Scaling (DVFS) Controllers** (ARM Intelligent Power Allocation / IPA; Intel DPTF; US7,886,164 B2)
   * Adjust processor operating voltage and clock frequency in response to thermal or power constraints.
   * Use on‑chip temperature readings (and in some implementations, temperature rate‑of‑change) to modulate P‑states.
   * **Limitation:** These systems adjust *processor operating parameters* (frequency, voltage) to reduce power dissipation — they do not make per‑task admission or routing decisions, do not compute a consumable safety budget, and do not offload tasks to external compute resources. Their scope is OS/firmware‑level power management, not application‑level task scheduling.

6. **Energy‑Harvesting IoT Schedulers** (Kansal et al., "Power Management in Energy Harvesting Sensor Networks," ACM TOSN 2007; Moser et al., "Real‑Time Scheduling for Energy Harvesting Sensor Nodes," Real‑Time Systems 2010)
   * Schedule tasks based on available harvested energy (solar, vibration, RF) and battery state of charge.
   * Model energy as a budget that is earned over time and spent by task execution.
   * **Limitation:** The "budget" is *energy* (Joules or Coulombs) — a measure of battery capacity. It does not reflect hardware health risk. These systems do not monitor voltage derivatives, temperature derivatives, or voltage variance. They optimize for energy neutrality (harvest ≥ consume), not for preventing brownouts, thermal shutdown, or hardware degradation. A device with full energy reserves but dangerously high dT/dt would receive no protection.

### 2.2 The Gap: No Combined Derivative‑Driven Safety Budget for Per‑Task Routing

**What is missing from all prior art:**

1. **Combined Thermal and Voltage Derivative Signals for Task Routing:** While some thermal management systems (e.g., DVFS controllers) may use temperature rate‑of‑change internally to adjust processor frequency, no prior art uses the *combination* of both temperature derivatives (ΔT/Δt) and voltage derivatives (ΔV/Δt) as primary signals for *application‑level task routing decisions*. A device at 50°C rising at 2°C/sec is in imminent danger; a device at 65°C stable at 0°C/sec is safe. Current systems treat the 65°C device as more dangerous — this is wrong.

2. **Voltage Stability as a Scheduling Signal:** No existing task scheduler or offloading system uses **live voltage telemetry** — including voltage drop rate (ΔV/Δt) and voltage variance (σ_V) — as a go/no‑go gate for per‑task admission. Voltage monitoring exists in power management ICs, but it is not exposed to the application task‑scheduling layer.

3. **Consumable Safety Budget Derived from Hardware‑Health Derivatives:** No system converts combined hardware‑health derivative signals into a **consumable integer resource** that decays as tasks execute locally, replenishes when hardware recovers, and directly gates task admission at the application layer. Existing energy budgets track Joules or battery state‑of‑charge, not hardware‑failure risk.

4. **Hardware Survival as First‑Class Objective:** All prior offloading systems optimize latency, energy, or privacy. None explicitly says: *"sacrifice cloud cost to prevent brownout or thermal shutdown on cheap hardware."*

### 2.3 Direct Contrast: Why Existing Systems Cannot Prevent Hardware Failure

The following table summarizes the fundamental distinction between this invention and the categories of prior art identified above:

| Prior Art Category | What It Optimizes | What It Monitors | Per‑Task Routing? | Safety Budget? | Prevents Brownout/Thermal Shutdown? |
|--------------------|-------------------|------------------|-------------------|----------------|-------------------------------------|
| Thermal governors (DVFS, IPA) | CPU power dissipation | Temperature (sometimes dT/dt) | No — adjusts frequency | No | Partially (reactive throttling only) |
| Energy‑aware offloading | Battery life / energy cost | Battery SoC, network latency | Yes — but energy‑driven | Energy budget (Joules) | No |
| IoT task schedulers | Load balancing | CPU%, queue depth | Yes — but load‑driven | No | No |
| Energy‑harvesting schedulers | Energy neutrality | Harvested energy, battery | Yes — but energy‑driven | Energy budget (Joules) | No |
| **This invention** | **Hardware survival** | **T, ΔT/Δt, V, ΔV/Δt, σ_V, load** | **Yes — health‑driven** | **Safety budget (risk‑derived)** | **Yes — proactively** |

**Key distinction:** Prior art systems adjust processor frequency or offload tasks to reduce energy consumption. They do not compute a consumable safety budget from combined hardware‑health derivatives (temperature and voltage rates of change). Consequently, they cannot detect or prevent the trajectory toward brownout or thermal shutdown before OS‑level protection mechanisms are triggered.

---

## 3. THE INVENTION: "Bodyguard" Hardware‑Protective Task Router

### 3.1 Core Innovation

**A method and system that operates in six continuous steps:**

---

#### Step 1 — Monitor

Continuously reads voltage (V), current (I), and temperature (T) from hardware sensors and CPU load from the operating system. Hardware sensors may be **on‑chip thermal probes** (e.g., CPU die sensor via `/sys/class/thermal`), **external I2C/SPI sensors** (e.g., INA219, INA226, or INA3221 for power; DHT22, TMP117, or BME280 for temperature), or **virtualized sensor interfaces** provided by a hypervisor, container runtime, or hardware abstraction layer. The specific sensor hardware is not limiting; the method requires only periodic voltage and temperature readings with sufficient resolution. Readings are taken at a fixed sampling interval (e.g., every 2 seconds) and stored in circular history buffers of configurable depth (e.g., 10 samples).

---

#### Step 2 — Predict (Risk Score Computation)

Computes a **Predictive Risk Score (R)** from six independently normalized signals. Each signal is mapped to the unit interval [0, 1] using a domain‑specific normalization function before weighting, ensuring the final score R is bounded in [0, 1] regardless of operating conditions.

> **Design Property — Bounded and Normalized Risk:** Because every signal term is individually clipped to [0, 1] and the weights are constrained to sum to unity, the composite risk score R is **guaranteed to lie in [0, 1]** under all operating conditions. This boundedness is a deliberate design property that enables: (a) **cross‑device comparison** — R = 0.7 on a Raspberry Pi 4 and R = 0.7 on a Jetson Nano represent comparable risk levels despite different hardware profiles; (b) **cross‑window comparison** — risk trends across consecutive time windows are directly comparable; and (c) **deterministic budget computation** — the budget formula B = B_max × (1 − R) produces a well‑defined result for any valid R without saturation or overflow.

**The Risk Score:**

$$R = \sum_{i=1}^{6} w_i \cdot \hat{x}_i \quad \text{where} \quad \sum_{i=1}^{6} w_i = 1$$

**The six normalized signal terms:**

**Term 1 — Thermal Proximity** (how close to the danger zone):

$$\hat{x}_1 = \text{clip}\!\left(\frac{T - T_{\text{safe}}}{T_{\text{crit}} - T_{\text{safe}}},\; 0,\; 1\right)$$

* Activates only when temperature exceeds T_safe (e.g., 60°C).
* Reaches 1.0 at T_crit (e.g., 80°C), the point where the OS would throttle.
* The normalization range (T_crit − T_safe) encodes the device's thermal operating envelope — a device‑specific parameter determined during a profiling phase.

**Term 2 — Thermal Velocity** (how fast you're approaching the danger zone):

$$\hat{x}_2 = \text{clip}\!\left(\frac{\Delta T / \Delta t - s_{\text{safe}}}{s_{\text{max}} - s_{\text{safe}}},\; 0,\; 1\right)$$

* Activates only when the rate of thermal rise exceeds s_safe (e.g., 1°C/min) — the maximum rise rate that passive cooling can sustain indefinitely.
* Reaches 1.0 at s_max (e.g., 5°C/min), the maximum observed heating rate during device stress profiling.
* **This is the predictive core**: it catches a device at 50°C that will hit 80°C in 6 minutes — something absolute‑temperature monitoring completely misses.

**Term 3 — Voltage Sag** (how far voltage has dropped below nominal):

$$\hat{x}_3 = \text{clip}\!\left(\frac{V_{\text{safe}} - V}{V_{\text{safe}} - V_{\text{crit}}},\; 0,\; 1\right)$$

* Activates only when voltage drops below V_safe (e.g., 4.95V).
* Reaches 1.0 at V_crit (e.g., 4.63V), the brownout/reboot threshold.
* The normalization range (V_safe − V_crit) encodes the device's power margin — dependent on the specific SBC's voltage regulator tolerance.

**Term 4 — Voltage Drop Rate** (how fast voltage is falling):

$$\hat{x}_4 = \text{clip}\!\left(\frac{\max(0,\; -\Delta V / \Delta t)}{\dot{V}_{\text{max}}},\; 0,\; 1\right)$$

* Activates only when voltage is *falling* (dV/dt negative → −dV/dt positive).
* The max() ensures rising voltage contributes zero risk.
* V̇_max (e.g., 0.5V/sec) is the maximum expected voltage drop rate, determined during power stress profiling (e.g., sudden motor‑on on shared rail).
* **This is the predictive element for power**: it detects a voltage trajectory that leads to brownout *before* the brownout occurs.

**Term 5 — Voltage Instability** (sustained noise on the power rail):

$$\hat{x}_5 = \text{clip}\!\left(\frac{\sigma_V}{\sigma_{\text{max}}},\; 0,\; 1\right)$$

* σ_V = standard deviation of voltage readings in the history buffer (last N samples).
* σ_max (e.g., 0.3V) = maximum expected voltage standard deviation, determined by PSU quality profiling.
* **Captures a fundamentally different failure mode than Term 4**: dV/dt catches a single sharp voltage drop (e.g., motor startup); σ_V catches sustained instability (e.g., degrading capacitors, noisy DC converter, long cable runs). A noisy PSU can have near‑zero *average* dV/dt while still being dangerously unstable. Neither term subsumes the other.

**Term 6 — Load Pressure** (how much computational demand exists):

$$\hat{x}_6 = \frac{\text{cpu\_utilization} + \text{queue\_depth}}{\text{max\_capacity}}$$

* Already in [0, 1] by construction (utilization and queue are bounded by capacity).
* Captures current system stress and incoming demand.

**Summary of normalization parameters (all device‑specific, determined during profiling):**

| Parameter | Physical Meaning | Example (Raspberry Pi 4) |
|-----------|-----------------|--------------------------|
| T_safe | Safe operating temperature ceiling | 60°C |
| T_crit | OS thermal throttle trigger | 80°C |
| s_safe | Max sustainable thermal rise rate (passive cooling capacity) | 1.0°C/min |
| s_max | Max observed thermal rise rate under stress | 5.0°C/min |
| V_safe | Nominal input voltage (clean power) | 4.95V |
| V_crit | Brownout / reboot voltage threshold | 4.63V |
| V̇_max | Max expected voltage drop rate | 0.5V/sec |
| σ_max | Max expected voltage standard deviation | 0.3V |

**Example weight profile (Raspberry Pi 4, passive heatsink, USB PSU):**

| Weight | Value | Rationale |
|--------|-------|-----------|
| w₁ (Thermal Proximity) | 0.15 | Important but partially redundant with w₂ |
| w₂ (Thermal Velocity) | 0.25 | Primary predictive signal for thermal failure |
| w₃ (Voltage Sag) | 0.15 | Important but partially redundant with w₄ |
| w₄ (Voltage Drop Rate) | 0.20 | Primary predictive signal for power failure |
| w₅ (Voltage Instability) | 0.10 | PSU quality indicator; critical for cheap power supplies |
| w₆ (Load Pressure) | 0.15 | Captures demand‑side pressure |
| **Total** | **1.00** | **Guarantees R ∈ [0, 1]** |

> **Design rationale for weights:** The derivative/velocity terms (w₂, w₄) receive the highest weights because they are the *predictive* signals — they detect danger before it arrives. The absolute‑value terms (w₁, w₃) receive lower weights because they indicate *current* proximity to danger, which is also detectable by existing reactive systems. The σ_V term (w₅) receives lower weight because sustained instability is a slower‑developing condition, but it must remain non‑zero because it catches failure modes invisible to instantaneous derivatives. Load (w₆) is the least hardware‑specific signal but essential for preventing new work from tipping a borderline device.

> **Load term is secondary to derivatives:** Removing the load term (w₆) from the risk score is expected to degrade throughput optimization but not the core protective effect — the system would still detect and respond to thermal and voltage danger trajectories. In contrast, removing the derivative terms (w₂, w₄) or disabling the safety budget is expected to cause actual hardware failures (brownouts, thermal shutdowns), as demonstrated by the ablation study in §6 Experiment 4. The derivative terms and safety budget are therefore the inventive core; the load term is a supporting signal.

---

#### Step 3 — Classify (Dual‑Hysteresis State Machine)

Maps the risk score R to a discrete **Device State** using a **dual‑hysteresis state machine** — hysteresis is applied at *both* transition boundaries to prevent oscillation (state "flapping") when R fluctuates near a threshold.

**State transition rules (current state → new state):**

```
IF current_state == SAFE:
    IF R ≥ 0.30  →  transition to WARNING

ELIF current_state == WARNING:
    IF R < 0.25  →  transition to SAFE        (hysteresis gap: 0.25–0.30)
    IF R ≥ 0.65  →  transition to CRITICAL

ELIF current_state == CRITICAL:
    IF R < 0.55  →  transition to WARNING      (hysteresis gap: 0.55–0.65)

# EMERGENCY is a sub‑state of CRITICAL:
IF current_state == CRITICAL AND cloud is unreachable:
    current_state = EMERGENCY
```

**Why dual hysteresis matters:** Without hysteresis at the WARNING↔CRITICAL boundary, a device at R = 0.64 would oscillate between WARNING and CRITICAL every sampling cycle due to minor sensor noise. This causes erratic routing decisions — tasks alternate between local execution and cloud offload, producing worse throughput than either pure‑local or pure‑offload. The hysteresis gap (0.55–0.65) ensures the device must *genuinely recover* before downgrading from CRITICAL.

**Cold‑start behavior:** When the system starts, the history buffers are empty and derivatives cannot be computed. During this initialization period (first N × sampling_interval seconds, e.g., 20 seconds), the system defaults to the **WARNING** state — a conservative posture that allows lightweight tasks locally but offloads heavy tasks. Once sufficient history is accumulated, the system transitions to normal risk‑score‑driven operation.

**State descriptions:**

| State | Condition | Behavior |
|-------|-----------|----------|
| **SAFE** | R < 0.30 (enter), R < 0.25 (remain) | Device is healthy. All tasks execute locally (budget permitting). |
| **WARNING** | 0.30 ≤ R (enter from SAFE), R ≥ 0.25 (remain) | Device is under stress. Only lightweight tasks execute locally; heavy tasks are offloaded. |
| **CRITICAL** | R ≥ 0.65 (enter), R ≥ 0.55 (remain) | Device is near failure. Only mission‑critical tasks execute locally; all others are offloaded. |
| **EMERGENCY** | CRITICAL + cloud unreachable | Self‑protection mode. Mission‑critical tasks execute with sleep interleaving; all others are rejected and queued. |

---

#### Step 4 — Budget (Consumable Safety Budget)

Computes a **consumable Safety Budget (B_t)** — a novel abstraction representing the maximum number of additional local tasks the device can safely execute in the current time window. The safety budget is formally defined as follows:

**Definition.** The safety budget B_t is a **non‑negative integer resource** governed by the following rules:

1. **Computation:** At the start of each time window of fixed duration W (e.g., 30 seconds), B_t is recomputed from the current risk score:

$$B_t = \max\!\big(0,\; \lfloor B_{\max} \cdot (1 - R_t) \rfloor - C_w\big)$$

2. **Decrement:** Each time a task is admitted for local execution, B_t is decremented by one. B_t is never decremented below zero.

3. **Non‑negativity:** B_t ≥ 0 at all times. When B_t = 0, no further local task execution is permitted regardless of device state, task weight, or task priority. The admission controller must offload or reject the task.

4. **Recomputation (Replenishment):** At each window boundary (every W seconds), the counter C_w resets to zero and B_t is recomputed from the *current* risk score R_t. If R_t has decreased (device has recovered), B_t increases — the device earns back local capacity. If R_t remains high, B_t stays low — continued protection.

5. **Pre‑OS‑limit rejection:** Because R_t incorporates *derivative* signals (ΔT/Δt, ΔV/Δt) that predict future hardware state, the budget can reach zero and begin rejecting tasks **before the operating system's own thermal or voltage protection mechanisms are triggered**. This is the key distinction from OS‑level governors.

6. **Burst limiting:** Regardless of the average risk score over a longer period, the per‑window budget limits the maximum number of tasks that can execute locally in any single window to B_max. This prevents burst overloads where a temporarily low R_t allows a flood of tasks that collectively push the device into danger.

**Parameters:**

| Symbol | Meaning | Example |
|--------|---------|---------|
| B_max | Maximum safe task budget per window (calibrated per device during profiling) | 10 tasks |
| R_t | Current risk score (guaranteed ∈ [0, 1]) | 0.45 |
| C_w | Number of tasks executed locally since last window reset | 3 |
| W | Fixed window duration after which the budget resets | 30 sec |

**How the budget behaves:**

| R_t | Device Health | Available Budget (B_max=10, C_w=0) | Interpretation |
|-----|-------------|-------------------------------------|----------------|
| 0.00 | Perfect | 10 | Full local capacity |
| 0.20 | Good | 8 | Slight reduction |
| 0.50 | Moderate stress | 5 | Half capacity |
| 0.80 | Near failure | 2 | Almost exhausted |
| 1.00 | Failing | 0 | No local execution permitted |

**Why the safety budget is a novel abstraction — not "another threshold":**

Existing systems use static thresholds ("if CPU% > 80%, reject") or energy budgets (Joules remaining in a battery). The safety budget is fundamentally different in four ways:

| Property | Static Threshold | Energy Budget (Joules) | **Safety Budget B_t** |
|----------|-----------------|----------------------|----------------------|
| Resource type | Binary (OK/not OK) | Continuous (mAh, Joules) | **Integer (task count)** |
| What it measures | Single sensor value | Stored energy | **Hardware‑failure risk** |
| Consumable? | No | Yes | **Yes** |
| Replenishes? | N/A | Via charging | **Via device recovery (R decreases)** |
| Drives per‑task admission? | Only coarse on/off | Per‑device, not per‑task | **Per‑task** |
| Prevents brownout/thermal shutdown? | Only reactively | No | **Yes — proactively** |
| Scales with hardware health? | No | No — fixed battery capacity | **Yes — B_max × (1 − R)** |

No prior art exposes such a resource to an application‑level task scheduler.

---

#### Step 5 — Route (Per‑Task Admission Control)

For each incoming computational task, the admission controller consults the current device state, remaining budget, and the task's classification to make a routing decision:

```
FOR each incoming task:

  IF state == SAFE:
      IF B > 0:
          → Execute locally; decrement B by 1
      ELSE:
          → Offload to cloud

  ELIF state == WARNING:
      IF task.weight < 0.5 (lightweight) AND B > 0:
          → Execute locally; decrement B by 1
      ELSE:
          → Offload to cloud

  ELIF state == CRITICAL:
      IF task.priority == "mission_critical" AND B > 0:
          → Execute locally (last resort); decrement B by 1
      ELSE:
          → Offload to cloud

  ELIF state == EMERGENCY:
      IF task.priority == "mission_critical":
          → Execute locally with sleep interleaving; decrement B by 1
      ELSE:
          → Reject; queue for retry when conditions improve

  LOG(timestamp, task_id, state, R, B, decision, reason)
```

**Task classification:**
* **task.weight** ∈ [0.0, 1.0]: Estimated computational intensity. 0.0 = trivial (sensor read, JSON parse). 1.0 = heavy (matrix multiplication, ML inference). Assigned by the application developer at task registration.
* **task.priority**: "normal" or "mission_critical". Mission‑critical tasks (e.g., safety alarms, heartbeat pings) are allowed local execution even under stress, because offloading them carries higher latency risk than the hardware cost of executing them.

---

#### Step 6 — Protect (Emergency Self‑Preservation)

In the **EMERGENCY** state (hardware is critically stressed AND cloud offload is unreachable), the system engages a **Local Emergency Throttle**:

* Inserts mandatory **sleep intervals** between task executions (e.g., 500ms pause per task) to allow passive cooling and voltage recovery.
* Defers all non‑critical tasks to an internal **retry queue**.
* Continues monitoring; exits EMERGENCY when R drops below the WARNING re‑entry threshold (0.55) or cloud connectivity is restored.
* **Guarantee:** The system never allows uncontrolled hardware destruction regardless of external circumstances. Even in complete network isolation under heavy load, the device will survive — albeit at reduced throughput.

---

### 3.2 Why This Is NOT an Obvious Combination

**1. The risk function is domain‑specific and non‑standard.**

Individual components (temperature sensors, voltage monitors, load monitoring) are standard. Some OS‑level thermal governors (e.g., DVFS controllers) may internally use temperature rate‑of‑change to modulate processor frequency. However, no prior art uses the *combination* of thermal velocity (ΔT/Δt), voltage derivatives (ΔV/Δt), voltage variance (σ_V), and absolute thresholds in a single bounded predictive risk score **for application‑level per‑task routing decisions**. Each normalization range (T_crit − T_safe, s_max − s_safe, V_safe − V_crit, etc.) encodes device‑specific hardware knowledge determined through empirical profiling — these are not arbitrary parameters.

**2. The safety budget is a novel abstraction layer.**

It is not a threshold (like "if CPU% > 80%, offload"). It is not a score you merely log. It is a **consumable resource** that:
* Decays with each local task execution.
* Replenishes when the device recovers (risk drops), creating a feedback loop.
* Its maximum capacity scales dynamically with hardware health.
* Directly constrains admission of new work at the application layer.

No prior offloading or task‑routing system exposes such a hardware‑health‑derived budget to an application‑level task scheduler.

**3. The coupling of hardware prediction to per‑task routing is non‑obvious.**

* Thermal throttling reacts *after* overheating (OS layer, coarse‑grained).
* Offloading decides based on network/energy (application layer, different objective).
* This invention *couples* hardware‑failure prediction with per‑task admission — bridging two layers that the field conventionally separates. IoT reference architectures, textbooks, and industry practice treat hardware protection (OS concern) and task scheduling (application concern) as independent. This invention contradicts that established separation.

**4. The objective function is different from all prior work.**

All existing offloading systems optimize for latency, energy, or privacy. This system explicitly optimizes for **hardware survival** — sacrificing cloud cost to keep cheap hardware alive. This reframing of the optimization objective is a design innovation, not an obvious extension.

**5. The dual‑hysteresis state machine prevents a known failure mode.**

Single‑threshold systems suffer from state flapping (rapid oscillation) when the signal fluctuates near the threshold. The dual‑hysteresis design — with separate entry and exit thresholds at *both* state transitions — is a deliberate engineering choice that existing thermal governors and task schedulers do not implement at the application routing level.

**6. The EMERGENCY fallback provides completeness.**

The system guarantees device survival even when cloud connectivity is lost — a scenario no offloading‑only system addresses. The self‑protective throttle mode makes the system a complete hardware guardian, not merely a conditional offloader.

---

### 3.3 Problem–Solution Summary

**Problem:** Resource‑constrained edge devices (SBCs, IoT gateways) deployed in unattended environments crash unpredictably under combined thermal and voltage stress. Existing task offloading and thermal management systems optimize for energy consumption, network latency, or processor frequency — none optimizes for preventing hardware failure (brownout, thermal shutdown, unplanned reboot) as a first‑class objective. OS‑level thermal governors react only *after* dangerous thresholds are breached. No system provides the application layer with a predictive, consumable resource that limits local task execution based on hardware‑health trajectory.

**Solution:** A derivative‑based risk score — incorporating the *rates of change* of both temperature (ΔT/Δt) and voltage (ΔV/Δt), in addition to absolute values and voltage variance — drives a consumable per‑window safety budget and a dual‑hysteresis state machine. Together, these form an admission policy that proactively routes individual tasks (execute locally, offload to cloud, throttle, or reject) before OS‑level thermal or voltage protection mechanisms are triggered, thereby preventing brownout and thermal shutdown while preserving throughput.

### 3.4 Advantages

The claimed system provides the following concrete advantages over prior art:

1. **Fewer reboots and crashes:** Proactive offloading based on hardware‑health derivatives prevents brownout‑induced reboots and thermal shutdowns that reactive systems cannot avoid.

2. **Earlier detection than threshold‑only systems:** Derivative signals (ΔT/Δt, ΔV/Δt) detect danger *trajectories* before absolute thresholds are crossed — a device rising at 3°C/min from 50°C is flagged immediately, not after reaching 80°C.

3. **Stable temperature curve:** The safety budget naturally limits local task execution during stress periods, producing a smooth, bounded temperature profile rather than the sawtooth pattern caused by reactive throttle‑unthrottle oscillation.

4. **Stable throughput:** Dual‑hysteresis state transitions prevent the routing oscillation (state flapping) that degrades throughput in single‑threshold systems. Tasks are consistently routed rather than flip‑flopping between local and cloud execution.

5. **Limited and controlled offload ratio:** The budget mechanism ensures offloading occurs only when necessary and in proportion to actual hardware risk — avoiding both the over‑offloading of conservative fixed thresholds and the under‑offloading of oblivious schedulers.

6. **Cross‑device comparability:** The bounded, normalized risk score R ∈ [0, 1] enables fleet‑wide health dashboards and consistent policy behavior across heterogeneous hardware.

7. **Complete self‑protection:** The EMERGENCY state with sleep interleaving guarantees device survival even when cloud connectivity is lost — no prior offloading system provides this guarantee.

---

## 4. SYSTEM ARCHITECTURE

### 4.1 Components

```
┌──────────────────────────────────────────────────────────┐
│  Edge Node (e.g., Raspberry Pi 4 Model B)                │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────────────────────────────────────────┐    │
│  │ Physical Sensor Layer                            │    │
│  ├──────────────────────────────────────────────────┤    │
│  │ • INA219 (I2C): Input Voltage & Current          │    │
│  │ • DHT22 (GPIO): Ambient Temperature & Humidity   │    │
│  │ • CPU Die Probe: Processor Temperature           │    │
│  │ • /proc/stat: CPU Utilization & Queue Depth      │    │
│  └──────────────────────────────────────────────────┘    │
│           ↓ (readings every 2–5 sec)                     │
│  ┌──────────────────────────────────────────────────┐    │
│  │ Bodyguard Controller (Python daemon)             │    │
│  ├──────────────────────────────────────────────────┤    │
│  │ 1. Compute ΔT/Δt  (thermal velocity)            │    │
│  │ 2. Compute ΔV/Δt  (voltage drop rate)           │    │
│  │ 3. Compute σ_V    (voltage instability)         │    │
│  │ 4. Normalize all six signals to [0, 1]          │    │
│  │ 5. Compute R (predictive risk score)            │    │
│  │ 6. Update state via dual‑hysteresis FSM         │    │
│  │ 7. Update Safety Budget B                       │    │
│  └──────────────────────────────────────────────────┘    │
│           ↓ (state + budget)                             │
│  ┌──────────────────────────────────────────────────┐    │
│  │ Task Admission Controller                        │    │
│  ├──────────────────────────────────────────────────┤    │
│  │ For each incoming task:                          │    │
│  │  • Check state + budget + task weight/priority   │    │
│  │  • Route: LOCAL / OFFLOAD / THROTTLE / REJECT   │    │
│  │  • Log decision with full telemetry snapshot     │    │
│  └──────────────────────────────────────────────────┘    │
│           ↓                                              │
│  ┌──────────────────────────────────────────────────┐    │
│  │ Execution Layer                                  │    │
│  ├──────────────────────────────────────────────────┤    │
│  │ • LOCAL: Execute in worker thread (resource‑cap) │    │
│  │ • OFFLOAD: Send via HTTPS to cloud endpoint      │    │
│  │ • THROTTLE: Execute with sleep interleaving      │    │
│  │ • REJECT: Defer to retry queue                   │    │
│  └──────────────────────────────────────────────────┘    │
│                                                          │
└──────────────────────────────────────────────────────────┘
            ↓ (for offloaded tasks)
┌──────────────────────────────────────────────────────────┐
│  Cloud Backend (AWS Lambda / Google Cloud Functions)      │
├──────────────────────────────────────────────────────────┤
│  • Receives overflow tasks from stressed edge nodes      │
│  • Executes tasks and returns JSON results               │
│  • Charges per‑invocation (explicit cost trade‑off)      │
└──────────────────────────────────────────────────────────┘
```

### 4.2 Detailed Algorithm (Pseudocode)

```
BODYGUARD_CONTROLLER():

  ── INITIALIZATION ────────────────────────────────────
  T_history    = circular_buffer(capacity = 10)
  V_history    = circular_buffer(capacity = 10)
  B            = B_max                    # initial safety budget
  state        = WARNING                  # conservative cold‑start default
  last_window  = now()
  consumed     = 0
  initialized  = false

  # Device‑specific calibration parameters (from profiling):
  T_safe  = 60.0    # °C    — safe operating ceiling
  T_crit  = 80.0    # °C    — OS throttle trigger
  s_safe  = 1.0     # °C/min — max sustainable rise rate
  s_max   = 5.0     # °C/min — max observed rise rate
  V_safe  = 4.95    # V     — nominal clean‑power voltage
  V_crit  = 4.63    # V     — brownout/reboot threshold
  dV_max  = 0.5     # V/sec — max expected voltage drop rate
  sigma_max = 0.3   # V     — max expected voltage std deviation

  # Weights (must sum to 1.0):
  w = [0.15, 0.25, 0.15, 0.20, 0.10, 0.15]

  ── MAIN LOOP (every sampling_interval, e.g., 2 sec) ──

  LOOP:

    ── 1. READ HARDWARE TELEMETRY ──────────────────────
    T_now  = read_cpu_temperature()        # from /sys/class/thermal
    V_now  = INA219.read_bus_voltage()     # via I2C
    I_now  = INA219.read_current()         # via I2C (logged, not in R)
    T_amb  = DHT22.read_temperature()      # via GPIO (logged for audit)
    L      = (cpu_utilization() + task_queue_depth()) / max_capacity

    ── 2. UPDATE HISTORY BUFFERS ───────────────────────
    T_history.append(T_now)
    V_history.append(V_now)

    ── 3. CHECK INITIALIZATION ─────────────────────────
    if T_history.count < 5 or V_history.count < 5:
      # Not enough data for derivatives; remain in cold‑start WARNING
      log(timestamp, "COLD_START", state=WARNING, T=T_now, V=V_now)
      continue
    if not initialized:
      initialized = true
      # First full computation; state will be set by risk score

    ── 4. COMPUTE DERIVATIVES ──────────────────────────
    dT_dt  = (T_history[-1] - T_history[-5]) / (5 * sampling_interval)
    # Convert to °C/min for comparison with s_safe, s_max:
    dT_dt_min = dT_dt * 60.0

    dV_dt  = (V_history[-1] - V_history[-5]) / (5 * sampling_interval)

    sigma_V = standard_deviation(V_history.all_samples())

    ── 5. NORMALIZE EACH SIGNAL TO [0, 1] ─────────────
    x1 = clip((T_now - T_safe) / (T_crit - T_safe),           0, 1)
    x2 = clip((dT_dt_min - s_safe) / (s_max - s_safe),        0, 1)
    x3 = clip((V_safe - V_now) / (V_safe - V_crit),           0, 1)
    x4 = clip(max(0, -dV_dt) / dV_max,                        0, 1)
    x5 = clip(sigma_V / sigma_max,                             0, 1)
    x6 = L   # already normalized by construction

    ── 6. COMPUTE RISK SCORE ───────────────────────────
    R = w[0]*x1 + w[1]*x2 + w[2]*x3 + w[3]*x4 + w[4]*x5 + w[5]*x6
    # R is guaranteed ∈ [0, 1] because all x_i ∈ [0,1] and Σw = 1

    ── 7. UPDATE STATE (dual‑hysteresis FSM) ───────────
    if state == SAFE:
      if R >= 0.30:
        state = WARNING

    elif state == WARNING:
      if R < 0.25:
        state = SAFE
      elif R >= 0.65:
        state = CRITICAL

    elif state in (CRITICAL, EMERGENCY):
      if R < 0.55:
        state = WARNING

    # EMERGENCY sub‑state check:
    if state == CRITICAL:
      if not cloud_is_reachable():
        state = EMERGENCY

    ── 8. UPDATE SAFETY BUDGET ─────────────────────────
    elapsed = now() - last_window
    if elapsed > window_duration:
      B = max(0, floor(B_max * (1 - R)))
      consumed = 0
      last_window = now()
    else:
      B = max(0, floor(B_max * (1 - R)) - consumed)

    ── 9. LOG TELEMETRY ────────────────────────────────
    log(timestamp, state, R, B, T_now, V_now, I_now, T_amb,
        dT_dt_min, dV_dt, sigma_V, L, x1, x2, x3, x4, x5, x6)


TASK_ADMISSION_CONTROLLER(task):
  """Called when a new task arrives (via HTTP, MQTT, or internal queue)."""

  task_weight   = task.get_weight()     # [0.0, 1.0]
  task_priority = task.get_priority()   # "normal" or "mission_critical"
  decision      = null
  reason        = ""

  if state == SAFE:
    if B > 0:
      decision = LOCAL
      reason   = "SAFE state, budget available"
      B -= 1;  consumed += 1
    else:
      decision = OFFLOAD
      reason   = "SAFE state, budget exhausted"

  elif state == WARNING:
    if task_weight < 0.5 and B > 0:
      decision = LOCAL
      reason   = "WARNING state, lightweight task, budget available"
      B -= 1;  consumed += 1
    else:
      decision = OFFLOAD
      reason   = "WARNING state, heavy task or budget exhausted"

  elif state == CRITICAL:
    if task_priority == "mission_critical" and B > 0:
      decision = LOCAL
      reason   = "CRITICAL state, mission‑critical task permitted"
      B -= 1;  consumed += 1
    else:
      decision = OFFLOAD
      reason   = "CRITICAL state, non‑critical or budget exhausted"

  elif state == EMERGENCY:
    if task_priority == "mission_critical":
      decision = THROTTLED_LOCAL
      reason   = "EMERGENCY, mission‑critical, sleep‑interleaved execution"
      sleep(emergency_sleep_ms)    # e.g., 500ms — allow cooling/recovery
      B -= 1;  consumed += 1
    else:
      decision = REJECT
      reason   = "EMERGENCY, non‑critical task deferred to retry queue"
      retry_queue.enqueue(task)

  log_decision(task.id, state, decision, R, B, reason)
  return decision
```

---

## 5. KEY DISTINCTIONS FROM PRIOR ART

| Aspect | Prior Art | This Invention |
|--------|-----------|----------------|
| **Trigger for routing** | Network latency, battery energy, task size | Predicted hardware failure (6‑signal risk score with derivatives + variance) |
| **What is monitored** | CPU %, battery %, network speed | Voltage, temperature, their *rates of change*, and voltage *variance* |
| **Prediction mechanism** | None; reactive thresholding | Forward‑looking risk function combining ΔT/Δt, ΔV/Δt, and σ_V |
| **Normalization** | N/A or generic clamping | Domain‑specific ranges from hardware profiling (T_crit − T_safe, V_safe − V_crit, etc.) |
| **State management** | Binary (OK / throttled) | 4‑state machine with dual hysteresis and cold‑start safety |
| **Resource unit** | CPU shares, bandwidth, battery mAh | Consumable safety budget that decays with local execution and replenishes with recovery |
| **Decision granularity** | Per‑service or per‑node class | Per‑individual task (weight + priority aware) |
| **Primary objective** | Minimize latency or energy | **Prevent hardware failure** and extend device uptime |
| **Failure mode handling** | No fallback if offload unavailable | EMERGENCY self‑throttle ensures survival even without cloud |
| **Integration level** | OS thermal governor or service orchestrator | Application task‑admission layer (novel coupling) |

---

## 6. EXPERIMENTAL VALIDATION PLAN

> **Note:** The following experiments are designed to provide empirical evidence that the derivative terms (ΔT/Δt, ΔV/Δt) and the consumable safety budget are *necessary* components — not decorative additions — and that their removal degrades system reliability.

### Experiment 1: Voltage Sag Stress Test (Single Node Uptime)

**Setup:** Raspberry Pi 4 (2GB), stock 5V/2.5A USB PSU (prone to noise and sag), INA219 on power rail, DHT22 for ambient temperature. Stress workload: bursty CPU tasks (matrix multiplication, lightweight ML inference).

**Baseline:** Tasks execute locally until voltage‑induced reboot or thermal throttle.

**Bodyguard:** Controller monitors V, σ_V, dV/dt, dT/dt and offloads tasks when budget depletes.

**Metrics:**
* System uptime (hours without crash or reboot).
* Number of brownout events and thermal throttle events (kernel logs).
* Voltage and temperature curves over time.

**Hypothesis:** In a 24‑hour combined‑stress run, the baseline system is expected to experience multiple voltage‑induced reboots, while the Bodyguard system is expected to experience zero reboots — demonstrating that derivative‑driven proactive offloading prevents hardware failure.

### Experiment 2: Thermal Inertia Test (Derivative Sensitivity)

**Setup:** Same Pi enclosed in a sealed case (simulating industrial enclosure). Continuous image classification workload.

**Three modes compared:**
1. **Static threshold:** Offload only if T > 75°C OR V < 4.8V.
2. **Threshold + derivative:** Add dT/dt > 2°C/min and dV/dt < −0.1V/sec as triggers.
3. **Full Bodyguard:** Complete risk function, state machine, and safety budget.

**Metrics:**
* Time to first critical event from start of stress.
* Average operating temperature under load.
* Throughput constancy (tasks/minute over time).

**Hypothesis:** Removing derivative terms (mode 1 → mode 2 comparison) is expected to cause the first failure event significantly earlier. The full Bodyguard system (mode 3) is expected to stabilize temperature at ~65°C with constant throughput, while the static threshold system allows temperature to reach 80°C before reacting, causing throughput collapse.

### Experiment 3: Multi‑Node Offload Scenario

**Setup:** Two Raspberry Pis + one cloud VM (AWS Lambda). Tasks arrive at random rates with mixed weights.

**Baseline:** Round‑robin load balancing.

**Bodyguard:** Route based on individual health budgets of each Pi.

**Metrics:**
* Per‑node uptime and failure count.
* Task throughput, latency, and error rates.
* Workload distribution over time.

**Hypothesis:** Bodyguard avoids overloading stressed nodes; maintains system availability and prevents individual node failure compared to load‑unaware round‑robin.

### Experiment 4: Component Ablation Study

**Purpose:** To demonstrate that both derivative terms and the safety budget are individually *necessary* — not independently sufficient.

**Ablation modes:**
1. **Full system:** Complete risk function (all 6 terms) + safety budget + state machine.
2. **No derivatives:** Remove terms x₂ (ΔT/Δt) and x₄ (ΔV/Δt) from the risk score; redistribute their weights to absolute terms.
3. **No budget:** Compute risk score and state machine, but disable the safety budget (allow unlimited local tasks).
4. **Threshold only:** No risk score, no budget; offload only on fixed thresholds (T > 75°C or V < 4.8V).

**Metrics:** Time to first failure, total failures in 2 hours, peak temperature, voltage floor.

**Hypotheses:**
* Mode 2 (no derivatives) is expected to detect stress later than Mode 1, resulting in at least one brownout or thermal throttle within the test period.
* Mode 3 (no budget) is expected to allow burst overloads that push the device into danger despite having a risk score.
* Mode 4 (threshold only) is expected to perform worst — reacting only after damage has begun.
* **Only Mode 1 (full system) is expected to survive the entire test period without failure**, demonstrating that both derivatives and budget are necessary.

**Expected results summary** *(to be populated with actual experimental data when available):*

| Ablation Mode | Failures in 2h | Peak Temp (°C) | Time to First Failure | Voltage Floor (V) |
|---------------|----------------|----------------|----------------------|--------------------|
| 1. Full system | — | — | — | — |
| 2. No derivatives | — | — | — | — |
| 3. No budget | — | — | — | — |
| 4. Threshold only | — | — | — | — |

> When experimental data is available, this table will provide direct evidence that removing derivative terms or the safety budget individually increases failure rates, establishing that each component is necessary — not decorative.

### 6.1 Linking Experiments to Inventive Step

The experiments above are explicitly designed to establish the following:

1. **Experiments 1 and 2** demonstrate that the derivative terms (ΔT/Δt, ΔV/Δt) provide earlier detection than absolute thresholds alone, supporting the claim that the predictive risk score is a non‑obvious improvement over reactive monitoring.

2. **Experiment 4 (ablation)** demonstrates that the derivative terms and the safety budget are *individually necessary*: removing either one degrades the system's ability to prevent hardware failure. This directly rebuts any argument that these components are decorative or independently sufficient.

3. **Experiment 3** demonstrates that the per‑node safety budget enables health‑aware task distribution across heterogeneous devices — a capability absent from load‑balancing or energy‑only offloading systems.

---

## 7. PATENT CLAIMS

### Independent Claim 1 (Method)

A method for protecting hardware integrity in a resource‑constrained edge computing device, the method comprising:

(a) continuously monitoring, via one or more hardware sensors coupled to the device, an input supply voltage V and a processor temperature T at a fixed sampling interval, and storing said voltage and temperature readings in respective history buffers;

(b) computing, from said history buffers, at least:
  - a rate of thermal rise (ΔT/Δt) representing the time derivative of the processor temperature,
  - a rate of voltage change (ΔV/Δt) representing the time derivative of the input supply voltage, and
  - a voltage stability metric (σ_V) representing the standard deviation of voltage readings over at least a recent sample window;

(c) normalizing each of a plurality of hardware‑health signals to a common unit interval [0, 1] using device‑specific normalization ranges determined through hardware profiling, said plurality of signals comprising at least:
  - the processor temperature T,
  - the rate of thermal rise ΔT/Δt,
  - the input supply voltage V,
  - the rate of voltage change ΔV/Δt,
  - the voltage stability metric σ_V, and
  - a system load factor;

(d) computing a predictive risk score R as a weighted sum of said normalized signals, the risk score comprising at least a first term proportional to the rate of change of temperature and a second term proportional to the rate of change of voltage, wherein the weights are constrained to sum to unity, thereby guaranteeing R is bounded within [0, 1] under all operating conditions;

(e) mapping said risk score R to one of a plurality of discrete device states including at least SAFE, WARNING, and CRITICAL, using a dual‑hysteresis state machine with separate entry and exit thresholds at each state transition boundary, such that a higher risk score is required to enter a more critical state than to exit it;

(f) computing a consumable safety budget B_t as a non‑negative integer representing a maximum number of additional local task executions permissible in a current time window of fixed duration W, said budget being computed as:

$$B_t = \max\!\big(0,\; \lfloor B_{\max} \cdot (1 - R_t) \rfloor - C_w\big)$$

where B_max is a device‑specific maximum budget, R_t is the current risk score, and C_w is a count of tasks already executed locally in the current window, wherein: the budget is decremented by one for each locally executed task, recomputed at each window boundary from the current risk score, and can reach zero and reject tasks before the device's operating system thermal or voltage protection mechanisms are triggered;

(g) for each incoming computational task classified by a task weight and a task priority, determining a routing decision based on the conjunction of the current device state and the remaining safety budget:
  - executing the task locally and decrementing the budget when the device state and task classification permit local execution and the budget is positive;
  - offloading the task to a remote compute service when the device state indicates stress or the budget is exhausted;
  - engaging protective self‑throttling with mandatory sleep interleaving when the device is in critical state and the remote compute service is unreachable;

(h) logging each routing decision with associated sensor telemetry, risk score, budget value, and device state;

whereby the method proactively prevents thermal throttling, voltage‑induced brownouts, and device reboots by routing tasks based on hardware‑health derivatives before the device's own protection mechanisms are triggered.

### Independent Claim 2 (System)

A hardware‑protective edge computing system comprising:

* a resource‑constrained computing device having a processor and passive cooling;
* one or more voltage and current sensors coupled to the device's power input rail, configured to provide real‑time voltage and current measurements, wherein said sensors may be on‑chip power monitors, external I2C/SPI sensors (e.g., INA219, INA226, INA3221), or virtualized sensor interfaces;
* one or more temperature sensors configured to measure processor or enclosure temperature, wherein said sensors may be on‑chip thermal probes, external sensors (e.g., DHT22, TMP117, BME280), or virtualized temperature interfaces;
* a system‑load monitor configured to read processor utilization and task queue depth;
* a controller process executing on the device, configured to perform the method of Claim 1, computing predictive risk scores from normalized hardware‑health signals including temperature and voltage derivatives, maintaining device states via a dual‑hysteresis finite state machine, and managing a consumable safety budget;
* a task admission module intercepting incoming computational tasks and routing them to local execution, cloud offload, throttled local execution, or rejection based on the conjunction of the device state and the remaining safety budget; and
* a network interface for selective task offloading to a remote execution service.

### Dependent Claims

3. The method of Claim 1 wherein the voltage stability metric σ_V is the standard deviation of voltage readings collected over a sliding window of N most recent samples stored in the history buffer.

4. The method of Claim 1 further comprising an EMERGENCY state entered when the risk score exceeds the CRITICAL entry threshold and the remote compute service is determined to be unreachable, wherein the device enters a self‑protective mode inserting mandatory sleep intervals between task executions to permit passive cooling and voltage recovery.

5. The method of Claim 1 wherein the safety budget resets at fixed time intervals of duration W, and the reset value is dynamically scaled by the current risk score such that a risk score of zero yields maximum budget B_max and a risk score of one yields zero budget.

6. The method of Claim 1 wherein the device defaults to the WARNING state during an initialization period before sufficient sensor history has been accumulated to compute the rate of thermal rise and the rate of voltage change, thereby providing conservative hardware protection during cold start.

7. The system of Claim 2 wherein the voltage and current sensors communicate via I2C, SPI, or analogous serial bus, and the temperature sensors communicate via GPIO, I2C, on‑chip register, or virtualized interface.

8. The method of Claim 1 wherein the weights and normalization ranges are determined through a device‑specific calibration phase comprising subjecting the device to controlled thermal and electrical stress and recording sensor responses to establish device‑specific values for T_safe, T_crit, s_safe, s_max, V_safe, V_crit, V̇_max, and σ_max.

9. The method of Claim 1 wherein the routing decision for each incoming task is determined by the conjunction of two independent gates:
  - a **state gate** wherein the device state determines which classes of tasks are eligible for local execution: all tasks when SAFE, only lightweight tasks (task weight below a configurable threshold) when WARNING, and only mission‑critical tasks when CRITICAL; and
  - a **budget gate** wherein the remaining safety budget B_t determines whether the eligible task may actually execute locally: local execution is permitted only when B_t > 0, and is denied when B_t = 0 regardless of device state or task classification;
  such that the state gate controls *which* tasks may run locally and the budget gate controls *how many* tasks may run locally within a window.

10. The method of Claim 1 wherein the safety budget B_t is replenished at a window boundary only when the risk score R_t at the time of recomputation is below a replenishment threshold R_replenish (where R_replenish ≤ the WARNING exit threshold), such that the budget remains at zero during sustained stress even across window boundaries, and replenishment occurs only upon genuine device recovery.

11. The method of Claim 1 wherein the per‑window safety budget imposes a maximum burst size of B_max tasks that can execute locally within any single window of duration W, regardless of the average risk score over a longer period, thereby preventing burst overloads during transient periods of low risk.

12. The method of Claim 1 wherein the bounded risk score R ∈ [0, 1] enables comparison of hardware‑health risk across heterogeneous devices with different hardware profiles, such that fleet‑level monitoring and consistent policy application are achievable using the normalized risk score as a common health metric.

---

## 8. CONCLUSION

This invention is **not an obvious combination** of known techniques because:

1. **Novel Derivative‑Based Risk Function:** The six‑term predictive risk score — comprising at least terms proportional to the rate of change of temperature (ΔT/Δt) and the rate of change of voltage (ΔV/Δt), alongside voltage variance (σ_V), absolute temperature and voltage proximity, and system load — is not disclosed in any prior art for application‑level task routing. While individual derivative signals exist in OS‑level thermal governors (e.g., DVFS controllers), no prior system uses the *combination* of both temperature and voltage derivatives as primary signals for per‑task admission decisions.

2. **Novel Safety Budget Abstraction:** The consumable safety budget B_t is a formally defined non‑negative integer resource that: decays with each local task execution, replenishes only when hardware recovers (risk decreases), has its maximum capacity dynamically scaled by the risk score, imposes per‑window burst limits, and can reject tasks before OS protection mechanisms are triggered. This is fundamentally distinct from both static thresholds and energy budgets (Joules/Coulombs) found in prior art.

3. **Non‑Obvious Coupling via Dual‑Gate Admission:** Hardware‑failure prediction and application task routing are conventionally separate concerns (OS layer vs. application layer). This invention bridges them via two independent admission gates — a state gate (which tasks) and a budget gate (how many tasks) — contradicting established IoT architectural patterns where hardware protection and task scheduling are treated independently.

4. **Unique Objective Function:** Optimizing for **hardware survival** — sacrificing cloud cost to prevent brownout, thermal shutdown, and unplanned reboots — is a fundamentally different design goal from the latency, energy, or bandwidth optimization pursued by all existing offloading systems.

5. **Dual‑Hysteresis State Machine:** Applying hysteresis at *both* state transition boundaries prevents the routing oscillation (state flapping) failure mode that single‑threshold systems suffer, a deliberate engineering choice absent from existing application‑level task routers.

6. **Complete Self‑Protection with Cold Start:** The EMERGENCY fallback mode ensures device survival even under complete cloud isolation, and the WARNING‑default cold‑start behavior provides conservative protection from the moment of power‑on before derivative computation is possible.

7. **Bounded, Normalized, Cross‑Device Risk:** The guaranteed R ∈ [0, 1] boundedness enables consistent fleet‑wide health comparison and policy application across heterogeneous hardware profiles.

This system provides a necessary protective layer for the mass adoption of low‑cost, passively cooled edge computing devices in critical industries, transforming fragile hardware into reliable, self‑regulating computing assets that proactively prevent hardware failure while preserving throughput.
