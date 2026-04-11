#!/usr/bin/env python
"""
Minimal scheduler for the local fake training completion demo.

The scheduler launches fake_train.py itself, watches for a new run directory
under outputs/, waits for the child process to exit, and then validates the
expected artifacts. It does not invoke the Codex bridge yet.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


EXPECTED_SUBDIRS = ("checkpoints", "logs", "plots")
EXPECTED_LOG_FILES = (
    "train_steps.csv",
    "train_episodes.csv",
    "eval_metrics.csv",
    "final_probe.csv",
)
EXPECTED_PLOT_FILES = (
    "reward_curve.png",
    "coverage_curve.png",
    "success_rate_curve.png",
    "loss_curve.png",
)
EXPECTED_CHECKPOINT_FILES = ("best.pt", "last.pt")


@dataclass
class ValidationResult:
    success: bool
    missing_items: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch fake training and validate completion.")
    parser.add_argument("--turn-penalty", type=float, required=True)
    parser.add_argument("--revisit-penalty", type=float, required=True)
    parser.add_argument("--entry-k", type=int, required=True)
    parser.add_argument("--steps", type=int, default=24)
    parser.add_argument("--sleep-sec", type=float, default=0.35)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--poll-sec", type=float, default=0.5)
    parser.add_argument("--run-dir-timeout-sec", type=float, default=20.0)
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parent


def outputs_dir() -> Path:
    path = repo_root() / "outputs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def snapshot_existing_runs(base_dir: Path) -> set[str]:
    return {path.name for path in base_dir.iterdir() if path.is_dir()}


def launch_training_process(args: argparse.Namespace) -> subprocess.Popen[bytes]:
    command = [
        sys.executable,
        str(repo_root() / "fake_train.py"),
        "--turn-penalty",
        str(args.turn_penalty),
        "--revisit-penalty",
        str(args.revisit_penalty),
        "--entry-k",
        str(args.entry_k),
        "--steps",
        str(args.steps),
        "--sleep-sec",
        str(args.sleep_sec),
        "--seed",
        str(args.seed),
    ]
    return subprocess.Popen(command, cwd=str(repo_root()))


def choose_newest_run_dir(base_dir: Path, run_names: set[str]) -> Path | None:
    candidates = [base_dir / name for name in run_names]
    candidates = [path for path in candidates if path.exists() and path.is_dir()]
    if not candidates:
        return None
    candidates.sort(key=lambda path: path.stat().st_mtime)
    return candidates[-1]


def wait_for_new_run_dir(
    *,
    base_dir: Path,
    baseline_runs: set[str],
    process: subprocess.Popen[bytes],
    timeout_sec: float,
    poll_sec: float,
) -> Path | None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        current_runs = snapshot_existing_runs(base_dir)
        new_runs = current_runs - baseline_runs
        if new_runs:
            return choose_newest_run_dir(base_dir, new_runs)
        if process.poll() is not None:
            break
        time.sleep(poll_sec)

    current_runs = snapshot_existing_runs(base_dir)
    new_runs = current_runs - baseline_runs
    if new_runs:
        return choose_newest_run_dir(base_dir, new_runs)
    return None


def wait_for_process_exit(process: subprocess.Popen[bytes], poll_sec: float) -> int:
    while True:
        return_code = process.poll()
        if return_code is not None:
            return return_code
        time.sleep(poll_sec)


def validate_non_empty_file(path: Path, missing_items: list[str], relative_path: str) -> None:
    if not path.exists():
        missing_items.append(relative_path)
        return
    if path.stat().st_size <= 0:
        missing_items.append(f"{relative_path} (empty)")


def validate_run_artifacts(run_dir: Path) -> ValidationResult:
    missing_items: list[str] = []

    for subdir_name in EXPECTED_SUBDIRS:
        subdir = run_dir / subdir_name
        if not subdir.exists() or not subdir.is_dir():
            missing_items.append(subdir_name)

    logs_dir = run_dir / "logs"
    if logs_dir.exists():
        for filename in EXPECTED_LOG_FILES:
            validate_non_empty_file(logs_dir / filename, missing_items, f"logs/{filename}")

    plots_dir = run_dir / "plots"
    if plots_dir.exists():
        for filename in EXPECTED_PLOT_FILES:
            validate_non_empty_file(plots_dir / filename, missing_items, f"plots/{filename}")

    checkpoints_dir = run_dir / "checkpoints"
    if checkpoints_dir.exists():
        for filename in EXPECTED_CHECKPOINT_FILES:
            validate_non_empty_file(checkpoints_dir / filename, missing_items, f"checkpoints/{filename}")

    return ValidationResult(success=not missing_items, missing_items=missing_items)


def main() -> int:
    args = parse_args()
    base_dir = outputs_dir()
    baseline_runs = snapshot_existing_runs(base_dir)

    print("status=launching", flush=True)
    process = launch_training_process(args)

    print("status=waiting_for_run_dir", flush=True)
    run_dir = wait_for_new_run_dir(
        base_dir=base_dir,
        baseline_runs=baseline_runs,
        process=process,
        timeout_sec=args.run_dir_timeout_sec,
        poll_sec=args.poll_sec,
    )
    if run_dir is None:
        return_code = wait_for_process_exit(process, args.poll_sec)
        print("status=failed", flush=True)
        print("run_dir=", flush=True)
        print(f"return_code={return_code}", flush=True)
        print("missing_artifacts=[run_dir_not_detected]", flush=True)
        return 1

    print("status=run_dir_detected", flush=True)
    print(f"run_dir={run_dir}", flush=True)

    print("status=waiting_for_process_exit", flush=True)
    return_code = wait_for_process_exit(process, args.poll_sec)

    print("status=validating_artifacts", flush=True)
    validation = validate_run_artifacts(run_dir)
    success = return_code == 0 and validation.success

    # Future phase: invoke the Codex bridge here after a completed run is validated.
    print(f"status={'success' if success else 'failed'}", flush=True)
    print(f"run_dir={run_dir}", flush=True)
    print(f"return_code={return_code}", flush=True)
    missing_items = validation.missing_items if validation.missing_items else []
    print(f"missing_artifacts={missing_items}", flush=True)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
