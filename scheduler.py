#!/usr/bin/env python
"""
Minimal scheduler for the local fake training completion demo.

It supports two launch modes:

1. Direct CLI arguments for fake_train.py
2. A machine-readable decision file that drives the same launch path

This script still does not invoke the Codex bridge. It only prepares the
protocol-layer files that a later bridge can consume.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from automation_protocol import (
    GPTDecision,
    ProtocolError,
    RunArgs,
    decision_to_fake_train_cli_args,
    load_decision_file,
    render_codex_request,
    repo_root,
)


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


@dataclass
class SchedulerContext:
    mode: str
    run_args: RunArgs | None
    round_dir: Path | None
    decision: GPTDecision | None
    should_launch: bool
    exit_status: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch fake training and validate completion.")
    parser.add_argument("--decision-file", type=Path, help="Path to gpt_decision.json for round-driven mode.")
    parser.add_argument("--turn-penalty", type=float)
    parser.add_argument("--revisit-penalty", type=float)
    parser.add_argument("--entry-k", type=int)
    parser.add_argument("--steps", type=int, default=24)
    parser.add_argument("--sleep-sec", type=float, default=0.35)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--poll-sec", type=float, default=0.5)
    parser.add_argument("--run-dir-timeout-sec", type=float, default=20.0)
    return parser.parse_args()


def outputs_dir() -> Path:
    path = repo_root() / "outputs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def snapshot_existing_runs(base_dir: Path) -> set[str]:
    return {path.name for path in base_dir.iterdir() if path.is_dir()}


def resolve_context(args: argparse.Namespace) -> SchedulerContext:
    if args.decision_file is not None:
        decision_file = args.decision_file.resolve()
        decision = load_decision_file(decision_file)
        round_dir = decision_file.parent
        if decision.decision_status != "run_next_round":
            return SchedulerContext(
                mode="decision",
                run_args=None,
                round_dir=round_dir,
                decision=decision,
                should_launch=False,
                exit_status=decision.decision_status,
            )
        return SchedulerContext(
            mode="decision",
            run_args=decision.run_args,
            round_dir=round_dir,
            decision=decision,
            should_launch=True,
            exit_status="run_next_round",
        )

    missing = []
    for cli_name, value in (
        ("--turn-penalty", args.turn_penalty),
        ("--revisit-penalty", args.revisit_penalty),
        ("--entry-k", args.entry_k),
    ):
        if value is None:
            missing.append(cli_name)
    if missing:
        raise ProtocolError(
            "Direct mode requires these arguments when --decision-file is not used: "
            + ", ".join(missing)
        )

    run_args = RunArgs(
        turn_penalty=float(args.turn_penalty),
        revisit_penalty=float(args.revisit_penalty),
        entry_k=int(args.entry_k),
        steps=int(args.steps),
        sleep_sec=float(args.sleep_sec),
        seed=int(args.seed),
    )
    return SchedulerContext(
        mode="direct",
        run_args=run_args,
        round_dir=None,
        decision=None,
        should_launch=True,
        exit_status="run_next_round",
    )


def launch_training_process(context: SchedulerContext) -> subprocess.Popen[bytes]:
    assert context.run_args is not None
    if context.decision is not None:
        launch_args = decision_to_fake_train_cli_args(context.decision)
    else:
        launch_args = [
            "--turn-penalty",
            str(context.run_args.turn_penalty),
            "--revisit-penalty",
            str(context.run_args.revisit_penalty),
            "--entry-k",
            str(context.run_args.entry_k),
            "--steps",
            str(context.run_args.steps),
            "--sleep-sec",
            str(context.run_args.sleep_sec),
            "--seed",
            str(context.run_args.seed),
        ]

    command = [sys.executable, str(repo_root() / "fake_train.py"), *launch_args]
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


def emit_terminal_summary(
    *,
    status: str,
    round_dir: Path | None,
    run_dir: Path | None,
    return_code: int | str | None,
    missing_artifacts: list[str],
    codex_request_path: Path | None,
) -> None:
    print(f"status={status}", flush=True)
    print(f"round_dir={'' if round_dir is None else round_dir}", flush=True)
    print(f"run_dir={'' if run_dir is None else run_dir}", flush=True)
    print(f"return_code={'' if return_code is None else return_code}", flush=True)
    print(f"missing_artifacts={missing_artifacts}", flush=True)
    if codex_request_path is not None:
        print(f"codex_request_path={codex_request_path}", flush=True)


def main() -> int:
    args = parse_args()
    try:
        context = resolve_context(args)
    except ProtocolError as exc:
        emit_terminal_summary(
            status="invalid_config",
            round_dir=None,
            run_dir=None,
            return_code=None,
            missing_artifacts=[],
            codex_request_path=None,
        )
        print(f"error={exc}", file=sys.stderr)
        return 1

    codex_request_path = None if context.round_dir is None else context.round_dir / "codex_request.md"
    if not context.should_launch:
        emit_terminal_summary(
            status=context.exit_status,
            round_dir=context.round_dir,
            run_dir=None,
            return_code="not_started",
            missing_artifacts=[],
            codex_request_path=codex_request_path,
        )
        return 0

    base_dir = outputs_dir()
    baseline_runs = snapshot_existing_runs(base_dir)

    print("status=launching", flush=True)
    print(f"round_dir={'' if context.round_dir is None else context.round_dir}", flush=True)
    process = launch_training_process(context)

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
        emit_terminal_summary(
            status="failed",
            round_dir=context.round_dir,
            run_dir=None,
            return_code=return_code,
            missing_artifacts=["run_dir_not_detected"],
            codex_request_path=codex_request_path,
        )
        return 1

    print("status=run_dir_detected", flush=True)
    print(f"run_dir={run_dir}", flush=True)

    print("status=waiting_for_process_exit", flush=True)
    return_code = wait_for_process_exit(process, args.poll_sec)

    print("status=validating_artifacts", flush=True)
    validation = validate_run_artifacts(run_dir)
    success = return_code == 0 and validation.success

    generated_request_path = None
    if success and context.decision is not None and context.round_dir is not None:
        generated_request_path = context.round_dir / "codex_request.md"
        generated_request_path.write_text(
            render_codex_request(context.decision, run_dir=run_dir, round_dir=context.round_dir),
            encoding="utf-8",
        )
        # Future hook: pass generated_request_path to demo_codex_bridge.py after this file is written.

    emit_terminal_summary(
        status="success" if success else "failed",
        round_dir=context.round_dir,
        run_dir=run_dir,
        return_code=return_code,
        missing_artifacts=validation.missing_items if validation.missing_items else [],
        codex_request_path=generated_request_path if generated_request_path is not None else codex_request_path,
    )
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
