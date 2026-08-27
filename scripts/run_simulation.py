"""Headless simulation runner.

    python -m scripts.run_simulation --miners 50 --validators 5 --tasks 100

Prints the resulting leaderboard and emission vector. Useful for verifying the
mechanism without starting the API or the frontend.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from subnet.simulation import SimulationConfig, SubnetNetwork  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Run a VERITENSOR network simulation")
    ap.add_argument("--miners", type=int, default=25)
    ap.add_argument("--validators", type=int, default=3)
    ap.add_argument("--tasks", type=int, default=100)
    ap.add_argument("--difficulty", default="adaptive",
                    choices=["easy", "normal", "hard", "adaptive"])
    ap.add_argument("--seed", type=int, default=1337)
    ap.add_argument("--json", action="store_true", help="emit machine-readable output")
    args = ap.parse_args()

    net = SubnetNetwork(seed=args.seed)
    net.populate(miners=args.miners, validators=args.validators)
    result = net.run_simulation(SimulationConfig(
        miners=args.miners, validators=args.validators, tasks=args.tasks,
        difficulty_mode=args.difficulty, seed=args.seed))

    if args.json:
        print(json.dumps({"stats": result["stats"],
                          "leaderboard": result["leaderboard"]}, default=str))
        return 0

    stats = result["stats"]
    print(f"\nVERITENSOR — LOCAL SIMULATION (mode={stats['mode']}, netuid={stats['netuid']})")
    print(f"  miners={args.miners} validators={args.validators} tasks={args.tasks} "
          f"difficulty={args.difficulty} seed={args.seed}")
    print(f"  wall clock: {result['elapsed_seconds']}s")
    print(f"  network accuracy: {stats['network_accuracy']:.3f}   "
          f"mean task score: {stats['mean_task_score']:.3f}")
    print(f"  mean latency: {stats['mean_latency_ms']:.0f} ms   "
          f"p95: {stats['p95_latency_ms']:.0f} ms")
    print(f"  robustness probes: {stats['robustness_probes']} "
          f"({stats['robustness_hold_rate']:.1%} held)")
    print(f"  rejected responses: {stats['rejected_responses']}   "
          f"emission gini: {stats['emission_gini']:.3f}\n")

    header = (f"{'#':>3} {'miner':<14} {'archetype':<17} {'rep':>6} {'acc':>6} "
              f"{'rob':>6} {'cal':>6} {'lat(ms)':>8} {'tasks':>6} {'emission':>9}  flags")
    print(header)
    print("-" * len(header))
    for row in result["leaderboard"]:
        c = row["components"]
        print(f"{row['rank']:>3} {row['name']:<14} {row['profile']:<17} "
              f"{row['reputation']:>6.3f} {row['accuracy']:>6.3f} "
              f"{c.get('robustness', 0):>6.2f} {c.get('calibration', 0):>6.2f} "
              f"{row['mean_latency_ms']:>8.0f} {row['task_count']:>6} "
              f"{row['emission_weight']:>8.2%}  {','.join(row['flags']) or '-'}")
    total = sum(r["emission_weight"] for r in result["leaderboard"])
    print(f"\n  Σ emission weight = {total:.9f}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
