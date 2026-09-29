"""
Bodyguard Simulation Runner.

Runs complete simulations for patent evidence generation:
  - Experiment 1: Voltage sag stress test
  - Experiment 2: Thermal inertia test
  - Experiment 3: Multi-node scenario (stub)
  - Experiment 4: Component ablation study

Usage:
  python simulate.py              # Run all experiments
  python simulate.py --ablation   # Run ablation study only
  python simulate.py --quick      # Quick 2-minute test
"""

import argparse
import os
import random
import sys
import time

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bodyguard.admission import Task, TaskPriority
from bodyguard.config import BodyguardConfig
from bodyguard.controller import BodyguardController


def print_header(title: str) -> None:
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def print_results(results: dict, mode_label: str) -> None:
    """Print experiment results in a readable format."""
    print(f"\n--- {mode_label} ---")
    print(f"  Duration:          {results['duration_sec']:.1f}s")
    print(f"  Failures:          {results['failure_count']}")
    print(f"  First failure at:  {results['first_failure_sec']:.1f}s"
          if results['first_failure_sec'] is not None else
          f"  First failure at:  None (survived)")
    print(f"  Peak temperature:  {results['peak_temperature_C']:.1f}°C")
    print(f"  Voltage floor:     {results['voltage_floor_V']:.3f}V")
    routing = results['routing']
    print(f"  Tasks — local: {routing['local']}, offloaded: {routing['offloaded']}, "
          f"throttled: {routing['throttled']}, rejected: {routing['rejected']}")
    if routing['total'] > 0:
        print(f"  Offload ratio:     {routing['offload_ratio']:.1%}")
    print(f"  CSV:               {results['csv_path']}")


def run_simulation(
    duration_sec: float,
    mode_label: str,
    output_dir: str = "results",
    seed: int = 42,
    disable_derivatives: bool = False,
    disable_budget: bool = False,
    disable_state_machine: bool = False,
    task_interval: float = 3.0,
    base_load: float = 40.0,
    burst_probability: float = 0.15,
    burst_load: float = 85.0,
) -> dict:
    """Run a complete Bodyguard simulation.

    Args:
        duration_sec: Total simulation duration in seconds.
        mode_label: Human-readable label for this mode.
        output_dir: Output directory for CSV files.
        seed: Random seed for reproducibility.
        disable_derivatives: Ablation mode 2.
        disable_budget: Ablation mode 3.
        disable_state_machine: Ablation mode 4 (threshold-only).
        task_interval: Average seconds between task arrivals.
        base_load: Base CPU load percentage.
        burst_probability: Probability of a burst load event per cycle.
        burst_load: CPU load during burst events.

    Returns:
        Experiment results dict.
    """
    config = BodyguardConfig()
    config.validate()

    ctrl = BodyguardController(
        config=config,
        output_dir=output_dir,
        log_prefix=mode_label.lower().replace(" ", "_"),
        seed=seed,
        disable_derivatives=disable_derivatives,
        disable_budget=disable_budget,
        disable_state_machine=disable_state_machine,
    )

    rng = random.Random(seed + 1)  # Separate RNG for task generation
    dt = config.sampling.interval   # Simulated time step
    steps = int(duration_sec / dt)
    task_counter = 0
    next_task_time = 0.0
    burst_active = False
    burst_end_time = 0.0
    sim_time = 0.0

    print(f"Running [{mode_label}] for {duration_sec:.0f}s ({steps} steps)...")

    try:
        for step in range(steps):
            sim_time = step * dt

            # --- Simulate workload ---
            # Random load bursts
            if not burst_active and rng.random() < burst_probability:
                burst_active = True
                burst_duration = rng.uniform(10, 40)  # 10–40 seconds
                burst_end_time = sim_time + burst_duration
                ctrl.set_load(burst_load, queue_depth=rng.randint(3, 10))
            elif burst_active and sim_time >= burst_end_time:
                burst_active = False
                ctrl.set_load(base_load, queue_depth=rng.randint(0, 3))

            # --- Core Bodyguard cycle ---
            breakdown = ctrl.sample(dt=dt)

            # --- Submit tasks periodically ---
            if sim_time >= next_task_time:
                task_counter += 1
                weight = rng.uniform(0.1, 0.9)
                priority = rng.choice([
                    TaskPriority.LOW, TaskPriority.NORMAL,
                    TaskPriority.HIGH, TaskPriority.CRITICAL
                ])
                task = Task(
                    task_id=f"task_{task_counter:04d}",
                    weight=weight,
                    priority=priority,
                )
                result = ctrl.submit_task(task)
                next_task_time = sim_time + rng.expovariate(1.0 / task_interval)

                # Remove task load after estimated duration
                # (simplified: just reduce load after submission)
                if result.decision.value == "LOCAL":
                    ctrl._simulator.remove_load(task.cpu_load * 0.3)

            # --- Progress ---
            if steps >= 10 and step % (steps // 10) == 0 and step > 0:
                pct = step / steps * 100
                print(f"  [{pct:3.0f}%] t={sim_time:.0f}s  R={breakdown.risk_score:.3f}  "
                      f"state={ctrl.state.value}  B={ctrl.budget_remaining}  "
                      f"T={ctrl._latest_reading.temperature:.1f}°C  "
                      f"V={ctrl._latest_reading.voltage:.3f}V  "
                      f"failures={ctrl.failure_count}")

    finally:
        results = ctrl.get_experiment_results()
        ctrl.close()

    print_results(results, mode_label)
    return results


def run_ablation_study(duration_sec: float = 120.0, output_dir: str = "results") -> None:
    """Run the complete 4-mode ablation study (Experiment 4).

    Modes:
      1. Full system — all components active
      2. No derivatives — x2, x4 zeroed out
      3. No budget — unlimited local tasks
      4. Threshold only — no risk score, no state machine
    """
    print_header("EXPERIMENT 4: Component Ablation Study")
    print(f"Duration: {duration_sec:.0f}s per mode")
    print(f"Seed: 42 (deterministic, reproducible)\n")

    all_results = {}

    # Mode 1: Full system
    all_results["Full system"] = run_simulation(
        duration_sec=duration_sec,
        mode_label="Mode 1 Full System",
        output_dir=output_dir,
        seed=42,
        burst_probability=0.20,
        burst_load=90.0,
    )

    # Mode 2: No derivatives
    all_results["No derivatives"] = run_simulation(
        duration_sec=duration_sec,
        mode_label="Mode 2 No Derivatives",
        output_dir=output_dir,
        seed=42,
        disable_derivatives=True,
        burst_probability=0.20,
        burst_load=90.0,
    )

    # Mode 3: No budget
    all_results["No budget"] = run_simulation(
        duration_sec=duration_sec,
        mode_label="Mode 3 No Budget",
        output_dir=output_dir,
        seed=42,
        disable_budget=True,
        burst_probability=0.20,
        burst_load=90.0,
    )

    # Mode 4: Threshold only
    all_results["Threshold only"] = run_simulation(
        duration_sec=duration_sec,
        mode_label="Mode 4 Threshold Only",
        output_dir=output_dir,
        seed=42,
        disable_state_machine=True,
        disable_budget=True,
        burst_probability=0.20,
        burst_load=90.0,
    )

    # --- Summary table ---
    print_header("ABLATION STUDY SUMMARY")
    print(f"{'Mode':<20} {'Failures':>10} {'Peak Temp':>12} {'1st Fail':>12} {'V Floor':>10}")
    print("-" * 70)
    for mode, res in all_results.items():
        fail_time = f"{res['first_failure_sec']:.1f}s" if res['first_failure_sec'] else "None"
        print(f"{mode:<20} {res['failure_count']:>10} "
              f"{res['peak_temperature_C']:>10.1f}°C "
              f"{fail_time:>12} "
              f"{res['voltage_floor_V']:>9.3f}V")

    return all_results


def run_quick_test(output_dir: str = "results") -> None:
    """Quick 60-second sanity check across all modes."""
    print_header("QUICK TEST (60s per mode)")
    run_ablation_study(duration_sec=60.0, output_dir=output_dir)


def main():
    parser = argparse.ArgumentParser(
        description="Bodyguard System Simulation Runner"
    )
    parser.add_argument("--ablation", action="store_true",
                        help="Run ablation study (Experiment 4)")
    parser.add_argument("--quick", action="store_true",
                        help="Quick 60-second sanity test")
    parser.add_argument("--duration", type=float, default=120.0,
                        help="Duration per mode in seconds (default: 120)")
    parser.add_argument("--output", type=str, default="results",
                        help="Output directory for CSV files")

    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    if args.quick:
        run_quick_test(output_dir=args.output)
    elif args.ablation:
        run_ablation_study(duration_sec=args.duration, output_dir=args.output)
    else:
        # Default: run a single full-system test
        print_header("BODYGUARD FULL SYSTEM TEST")
        run_simulation(
            duration_sec=args.duration,
            mode_label="Full System",
            output_dir=args.output,
        )


if __name__ == "__main__":
    main()
