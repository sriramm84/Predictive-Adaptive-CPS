# Predictive-Adaptive-CPS

> **System and Method for Predictive Hardware-Health Orchestration and Safety-Budget Task Routing in Resource-Constrained Edge Environments ("Bodyguard")**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: Proprietary / Patent Pending](https://img.shields.io/badge/License-Patent%20Pending-orange.svg)]()

---

## 📌 Overview

**Bodyguard** is an autonomic, predictive cyber-physical governance architecture designed for passively cooled, resource-constrained edge computing platforms (Single-Board Computers, IoT gateways, edge AI inference nodes). 

Unlike conventional reactive OS schedulers and thermal governors that react only after critical thresholds (e.g., thermal ceiling or brownout voltage) are violated, **Bodyguard** employs:
1. **Multi-Signal Predictive Risk Scoring ($R$)**: Continuous derivation from thermal velocity ($\Delta T/\Delta t$), voltage drop rate ($\Delta V/\Delta t$), electrical variance ($\sigma_V$), and system load metrics.
2. **Dual-Hysteresis State Machine**: Prevents state chatter and rapid limit oscillation between NORMAL, WARNING, and CRITICAL operating regions.
3. **Consumable Safety Budget ($B$)**: Quantifies available local headroom before thermal or electrical boundaries are exceeded.
4. **Hardware-Health Aware Task Routing**: Dynamically decides whether incoming workloads should execute locally, throttle, offload to cloud infrastructure, or reject—sacrificing cloud cost to preserve physical edge device longevity.

---

## 📂 Repository Structure

```text
Predictive-Adaptive-CPS/
├── DC-Patent/
│   ├── dc-nayeem/
│   │   ├── bodyguard/
│   │   │   ├── bodyguard/               # Core Python package
│   │   │   │   ├── admission.py         # Workload admission control
│   │   │   │   ├── budget.py            # Safety budget management
│   │   │   │   ├── config.py            # System configuration & thresholds
│   │   │   │   ├── controller.py        # Central health orchestrator
│   │   │   │   ├── logger.py            # Telemetry logging
│   │   │   │   ├── risk_engine.py       # Predictive risk scoring engine
│   │   │   │   ├── sensors.py           # Hardware telemetry interfaces
│   │   │   │   └── state_machine.py     # Dual-hysteresis state machine
│   │   │   ├── diagrams/                # System workflows & architecture diagrams
│   │   │   ├── evidence/                # Experimental logs & validation traces
│   │   │   ├── experiments/             # Experiment runners & benchmark scripts
│   │   │   ├── venv/                    # Virtual environment
│   │   │   ├── exp1_uptime.py           # Uptime validation test
│   │   │   ├── read_stress.py           # Stress telemetry reader
│   │   │   ├── simulate.py              # Workload & health simulator
│   │   │   └── test_stress.py           # Stress generation script
│   │   └── bodyguard_patent_final.md   # Complete patent specification
│   └── experiments/
│       └── output/                      # Telemetry logs, task routing plots & CSV results
└── README.md
```

---

## 🔬 Core Components

* **`risk_engine.py`**: Computes normalized multi-parameter risk scores based on hardware derivatives and rates of change.
* **`state_machine.py`**: Implements asymmetric upper/lower hysteresis boundaries to ensure operational stability under heavy load swings.
* **`budget.py`**: Calculates the consumable safety budget $B(t)$ remaining before hardware constraints trip.
* **`admission.py`**: Evaluates task priority, execution cost, and health state to perform optimal local vs. cloud routing.

---

## 📊 Experimental Evaluation

The repository includes end-to-end benchmark scripts and collected empirical evidence:
- **Experiment 1 (Uptime & Longevity)**: Evaluates device survival time under sustained stress vs. unmanaged baselines.
- **Experiment 2 (Lead Time & Warning)**: Measures predictive lead-time before thermal throttle engagement.
- **Experiment 6 (Hysteresis & Telemetry)**: Demonstrates elimination of state oscillation.
- **Experiment 7 (Task Routing)**: Validates safety-budget-driven offload and admission decisions.
- **Experiment 8 (Emergency Governance)**: Demonstrates graceful degradation and brownout prevention under severe power instability.

---

## 📜 Documentation

For full technical specifications, mathematical formulations, and claims, refer to [`DC-Patent/dc-nayeem/bodyguard_patent_final.md`](DC-Patent/dc-nayeem/bodyguard_patent_final.md).