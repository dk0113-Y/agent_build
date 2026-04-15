#!/usr/bin/env python
"""
Minimal scheduler for the local fake training completion demo.

It supports two launch modes:

1. Direct CLI arguments for fake_train.py
2. A machine-readable decision file that drives the same launch path

When requested, it can also hand the generated codex_request.md to the local
Codex bridge for one-way delivery into the desktop app.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from automation_protocol import (
    GPTDecision,
    ProtocolError,
    RunArgs,
    decision_to_execution_cli_args,
    ensure_round_state_file,
    load_decision_file,
    render_codex_request,
    resolve_compare_targets,
    repo_root,
    update_round_state_file,
)

REHEARSAL_EXPECTED_SUBDIRS = ("checkpoints", "logs", "plots")
REHEARSAL_EXPECTED_LOG_FILES = (
    "train_steps.csv",
    "train_episodes.csv",
    "eval_metrics.csv",
    "final_probe.csv",
)
REHEARSAL_EXPECTED_PLOT_FILES = (
    "reward_curve.png",
    "coverage_curve.png",
    "success_rate_curve.png",
    "loss_curve.png",
)
FORMAL_EXPECTED_SUBDIRS = ("checkpoints", "logs")
FORMAL_EXPECTED_LOG_FILES = (
    "train_steps.csv",
    "train_episodes.csv",
    "final_probe.csv",
    "metric_snapshot.json",
    "benchmark_summary.json",
    "config_snapshot.json",
    "artifact_index.json",
)
FORMAL_OPTIONAL_LOG_FILES = ("eval_metrics.csv",)
FORMAL_EXPECTED_CHECKPOINT_FILES = ("last.pt",)
REHEARSAL_EXPECTED_CHECKPOINT_FILES = ("best.pt", "last.pt")


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


@dataclass
class BridgeInvocationResult:
    invoked: bool
    status: str
    return_code: int | str | None
    log_path: str = ""
    error: str = ""


def sync_round_state(
    context: SchedulerContext,
    *,
    status: str,
    run_dir: Path | None = None,
    training_return_code: int | None = None,
    bridge_result: BridgeInvocationResult | None = None,
) -> Path | None:
    if context.round_dir is None or context.decision is None:
        return None
    state_path = ensure_round_state_file(
        round_dir=context.round_dir,
        round_id=context.decision.round_id,
        decision_file=context.round_dir / "gpt_decision.json",
        codex_request_path=context.round_dir / "codex_request.md",
        codex_report_path=context.round_dir / "codex_report.md",
        gpt_input_path=context.round_dir / "gpt_input.md",
    )
    update_kwargs: dict[str, object] = {
        "status": status,
        "run_dir": run_dir if run_dir is not None else "",
        "training_return_code": training_return_code,
    }
    if bridge_result is not None:
        update_kwargs["bridge_invoked"] = bridge_result.invoked
        update_kwargs["bridge_status"] = bridge_result.status
    update_round_state_file(state_path, **update_kwargs)
    return state_path


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
    parser.add_argument("--run-dir-timeout-sec", type=float, default=300.0)
    parser.add_argument("--training-no-progress-timeout-sec", type=float, default=2400.0, help="Fail if no artifact updates in this time.")
    parser.add_argument("--training-hard-timeout-sec", type=float, default=0.0, help="Fail if wall clock exceeds this time.")
    parser.add_argument("--invoke-codex-bridge", action="store_true", help="After a successful decision-driven run, send codex_request.md to the local Codex app.")
    parser.add_argument("--bridge-config", type=Path, default=repo_root() / "config_new_thread.json", help="Config file to use when invoking demo_codex_bridge.py.")
    parser.add_argument("--bridge-manual-confirm-send", action="store_true", help="Pass --manual-confirm-send to demo_codex_bridge.py when bridge invocation is enabled.")
    return parser.parse_args()


def execution_repo_root(decision: GPTDecision | None) -> Path:
    if decision is None or decision.experiment_mode != "formal_train":
        return repo_root()
    target_text = decision.local_execution_repo_path or decision.source_of_truth_repo
    target = Path(target_text)
    if not target.is_absolute():
        target = (repo_root() / target).resolve()
    return target


def target_program_path(decision: GPTDecision | None) -> Path:
    if decision is None:
        return repo_root() / "fake_train.py"
    return execution_repo_root(decision) / decision.target_program


def outputs_dir(decision: GPTDecision | None = None) -> Path:
    if decision is not None and decision.run_args.output_root:
        path = Path(decision.run_args.output_root)
        if not path.is_absolute():
            path = (execution_repo_root(decision) / path).resolve()
    else:
        path = execution_repo_root(decision) / "outputs"
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
        launch_args = decision_to_execution_cli_args(context.decision)
        program_path = target_program_path(context.decision)
        working_dir = execution_repo_root(context.decision)
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
        program_path = repo_root() / "fake_train.py"
        working_dir = repo_root()

    command = [sys.executable, str(program_path), *launch_args]
    return subprocess.Popen(command, cwd=str(working_dir))


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


def terminate_process_tree(process: subprocess.Popen, reason: str) -> dict[str, str]:
    """Attempt to kill the entire process tree, Windows-aware.
    
    Returns a diagnostics dict with keys:
      - training_termination_strategy
      - training_termination_reason
      - training_cleanup_succeeded
    """
    diag: dict[str, str] = {
        "training_termination_reason": reason,
        "training_termination_strategy": "unknown",
        "training_cleanup_succeeded": "false",
    }
    pid = process.pid
    import platform
    if platform.system() == "Windows":
        try:
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0:
                diag["training_termination_strategy"] = "taskkill_/T_/F"
                diag["training_cleanup_succeeded"] = "true"
                print(f"[ProcessTree] taskkill /PID {pid} /T /F succeeded.", flush=True)
                return diag
            else:
                print(f"[ProcessTree] taskkill failed (rc={result.returncode}): {result.stderr.strip()}", flush=True)
        except Exception as exc:
            print(f"[ProcessTree] taskkill exception: {exc}", flush=True)
    # Fallback: try terminate then kill
    try:
        process.terminate()
        diag["training_termination_strategy"] = "process.terminate_fallback"
        diag["training_cleanup_succeeded"] = "partial"
        print(f"[ProcessTree] process.terminate() sent to PID {pid}.", flush=True)
    except Exception as exc:
        print(f"[ProcessTree] process.terminate() exception: {exc}", flush=True)
        try:
            process.kill()
            diag["training_termination_strategy"] = "process.kill_fallback"
            diag["training_cleanup_succeeded"] = "partial"
            print(f"[ProcessTree] process.kill() sent to PID {pid}.", flush=True)
        except Exception as exc2:
            print(f"[ProcessTree] process.kill() also failed: {exc2}", flush=True)
            diag["training_termination_strategy"] = "all_failed"
    return diag


def wait_for_process_exit(process: subprocess.Popen[bytes], poll_sec: float, run_dir: Path | None = None, no_progress_timeout: float = 0, hard_timeout: float = 0) -> tuple[int | None, str]:
    start_time = time.time()
    last_heartbeat = start_time

    def get_latest_mtime() -> tuple[float, str]:
        if not run_dir:
            return start_time, ""
        latest = start_time
        updated_file = ""
        active_formal_paths = [
            "logs/train_steps.csv",
            "logs/train_episodes.csv",
            "logs/final_probe.csv",
            "checkpoints/last.pt",
        ]
        legacy_diagnostic_paths = [
            "logs/eval_metrics.csv",
            "checkpoints/best.pt",
        ]
        for relative_path in [*active_formal_paths, *legacy_diagnostic_paths]:
            p = run_dir / relative_path
            if p.exists():
                mtime = p.stat().st_mtime
                if mtime > latest:
                    latest = mtime
                    updated_file = relative_path
        return latest, updated_file

    while True:
        return_code = process.poll()
        if return_code is not None:
            return return_code, "exited"

        now = time.time()
        elapsed = now - start_time
        
        # Hard timeout check
        if hard_timeout > 0 and elapsed > hard_timeout:
            diag = terminate_process_tree(process, "training_hard_timeout")
            print(f"[Timeout] Hard timeout reached after {elapsed:.0f}s. "
                  f"strategy={diag['training_termination_strategy']} "
                  f"cleanup={diag['training_cleanup_succeeded']}", flush=True)
            return None, "training_hard_timeout"

        # No progress timeout check
        latest_mtime, latest_file = get_latest_mtime()
        no_progress_duration = now - latest_mtime
        if no_progress_timeout > 0 and no_progress_duration > no_progress_timeout:
            diag = terminate_process_tree(process, "training_no_progress_timeout")
            print(f"[Timeout] No-progress timeout after {no_progress_duration:.0f}s idle. "
                  f"Last file: {latest_file or 'none'}. "
                  f"strategy={diag['training_termination_strategy']} "
                  f"cleanup={diag['training_cleanup_succeeded']}", flush=True)
            return None, "training_no_progress_timeout"

        # Heartbeat every 60s
        if now - last_heartbeat >= 60.0:
            print(f"[Heartbeat] Training running for {elapsed/60:.1f}m. " 
                  f"Idle since last artifact update: {no_progress_duration/60:.1f}m. "
                  f"Latest file: {latest_file if latest_file else 'None'}", flush=True)
            last_heartbeat = now

        time.sleep(poll_sec)


def validate_non_empty_file(path: Path, missing_items: list[str], relative_path: str) -> None:
    if not path.exists():
        missing_items.append(relative_path)
        return
    if path.stat().st_size <= 0:
        missing_items.append(f"{relative_path} (empty)")


def validate_run_artifacts(run_dir: Path, target_program: str) -> ValidationResult:
    missing_items: list[str] = []

    if target_program == "train_q_agent.py":
        expected_subdirs = FORMAL_EXPECTED_SUBDIRS
        expected_logs = FORMAL_EXPECTED_LOG_FILES
        expected_checkpoints = FORMAL_EXPECTED_CHECKPOINT_FILES
        expected_plots: tuple[str, ...] = ()
    else:
        expected_subdirs = REHEARSAL_EXPECTED_SUBDIRS
        expected_logs = REHEARSAL_EXPECTED_LOG_FILES
        expected_checkpoints = REHEARSAL_EXPECTED_CHECKPOINT_FILES
        expected_plots = REHEARSAL_EXPECTED_PLOT_FILES

    for subdir_name in expected_subdirs:
        subdir = run_dir / subdir_name
        if not subdir.exists() or not subdir.is_dir():
            missing_items.append(subdir_name)

    logs_dir = run_dir / "logs"
    if logs_dir.exists():
        for filename in expected_logs:
            validate_non_empty_file(logs_dir / filename, missing_items, f"logs/{filename}")

    if expected_plots:
        plots_dir = run_dir / "plots"
        if plots_dir.exists():
            for filename in expected_plots:
                validate_non_empty_file(plots_dir / filename, missing_items, f"plots/{filename}")

    checkpoints_dir = run_dir / "checkpoints"
    if checkpoints_dir.exists():
        for filename in expected_checkpoints:
            validate_non_empty_file(checkpoints_dir / filename, missing_items, f"checkpoints/{filename}")

    return ValidationResult(success=not missing_items, missing_items=missing_items)


def bridge_logs_dir() -> Path:
    path = repo_root() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def snapshot_bridge_run_logs() -> set[str]:
    return {str(path.resolve()) for path in bridge_logs_dir().glob("run_*.json")}


def detect_new_bridge_log(before_logs: set[str]) -> str:
    current_logs = snapshot_bridge_run_logs()
    new_logs = sorted(current_logs - before_logs)
    if new_logs:
        return new_logs[-1]
    return ""


def parse_bridge_stdout(stdout: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def load_bridge_log_payload(log_path: str) -> dict[str, object]:
    if not log_path:
        return {}
    try:
        return json.loads(Path(log_path).read_text(encoding="utf-8"))
    except Exception:
        return {}


def bridge_send_confirmed(status: str) -> bool:
    return status == "sent_only"


def resolve_bridge_error(
    *,
    status: str,
    return_code: int,
    parsed_stdout: dict[str, str] | None = None,
    log_payload: dict[str, object] | None = None,
    stderr_text: str = "",
    stdout_text: str = "",
) -> str:
    parsed_stdout = parsed_stdout or {}
    log_payload = log_payload or {}
    reason = str(
        parsed_stdout.get("send_confirmation_reason")
        or log_payload.get("send_confirmation_reason")
        or log_payload.get("message")
        or stderr_text.strip()
        or stdout_text.strip()
        or ""
    ).strip()
    if bridge_send_confirmed(status) and return_code == 0:
        return ""
    if reason:
        return reason
    return f"Bridge send was not confirmed (status={status}, return_code={return_code})."


def invoke_codex_bridge(
    *,
    codex_request_path: Path,
    bridge_config: Path,
    manual_confirm_send: bool,
) -> BridgeInvocationResult:
    before_logs = snapshot_bridge_run_logs()
    command = [
        sys.executable,
        str(repo_root() / "demo_codex_bridge.py"),
        "--send-only",
        "--message-file",
        str(codex_request_path),
        "--config",
        str(bridge_config.resolve()),
    ]
    if manual_confirm_send:
        command.append("--manual-confirm-send")

    if manual_confirm_send:
        completed = subprocess.run(command, cwd=str(repo_root()))
        log_path = detect_new_bridge_log(before_logs)
        log_payload = load_bridge_log_payload(log_path)
        status = str(log_payload.get("status") or ("sent_only" if completed.returncode == 0 else "failed"))
        return BridgeInvocationResult(
            invoked=True,
            status=status,
            return_code=completed.returncode,
            log_path=log_path,
            error=resolve_bridge_error(
                status=status,
                return_code=completed.returncode,
                log_payload=log_payload,
            ),
        )

    completed = subprocess.run(
        command,
        cwd=str(repo_root()),
        capture_output=True,
        text=True,
    )
    parsed_stdout = parse_bridge_stdout(completed.stdout or "")
    log_path = parsed_stdout.get("log") or detect_new_bridge_log(before_logs)
    log_payload = load_bridge_log_payload(log_path)
    status = parsed_stdout.get("status") or str(log_payload.get("status") or ("sent_only" if completed.returncode == 0 else "failed"))
    return BridgeInvocationResult(
        invoked=True,
        status=status,
        return_code=completed.returncode,
        log_path=log_path,
        error=resolve_bridge_error(
            status=status,
            return_code=completed.returncode,
            parsed_stdout=parsed_stdout,
            log_payload=log_payload,
            stderr_text=completed.stderr or "",
            stdout_text=completed.stdout or "",
        ),
    )


def emit_terminal_summary(
    *,
    status: str,
    round_dir: Path | None,
    run_dir: Path | None,
    return_code: int | str | None,
    missing_artifacts: list[str],
    codex_request_path: Path | None,
    bridge_result: BridgeInvocationResult,
) -> None:
    print(f"status={status}", flush=True)
    print(f"round_dir={'' if round_dir is None else round_dir}", flush=True)
    print(f"run_dir={'' if run_dir is None else run_dir}", flush=True)
    print(f"return_code={'' if return_code is None else return_code}", flush=True)
    print(f"missing_artifacts={missing_artifacts}", flush=True)
    if codex_request_path is not None:
        print(f"codex_request_path={codex_request_path}", flush=True)
    print(f"bridge_invoked={'true' if bridge_result.invoked else 'false'}", flush=True)
    print(f"bridge_status={bridge_result.status}", flush=True)
    print(f"bridge_return_code={'' if bridge_result.return_code is None else bridge_result.return_code}", flush=True)
    if bridge_result.log_path:
        print(f"bridge_log_path={bridge_result.log_path}", flush=True)
    if bridge_result.error:
        print(f"bridge_error={bridge_result.error}", flush=True)


def main() -> int:
    args = parse_args()
    try:
        context = resolve_context(args)
    except ProtocolError as exc:
        bridge_result = BridgeInvocationResult(False, "not_invoked", None)
        emit_terminal_summary(
            status="invalid_config",
            round_dir=None,
            run_dir=None,
            return_code=None,
            missing_artifacts=[],
            codex_request_path=None,
            bridge_result=bridge_result,
        )
        print(f"error={exc}", file=sys.stderr)
        return 1

    bridge_result = BridgeInvocationResult(False, "not_invoked", None)
    codex_request_path = None if context.round_dir is None else context.round_dir / "codex_request.md"
    round_state_file = None
    if context.round_dir is not None and context.decision is not None:
        round_state_file = sync_round_state(
            context,
            status="prepared",
            run_dir=None,
            training_return_code=None,
            bridge_result=BridgeInvocationResult(False, "not_invoked", None),
        )
    if not context.should_launch:
        bridge_result = BridgeInvocationResult(False, f"skipped_{context.exit_status}", "not_started")
        if round_state_file is not None:
            update_round_state_file(
                round_state_file,
                status=context.exit_status,
                run_dir="",
                training_return_code=None,
                bridge_invoked=bridge_result.invoked,
                bridge_status=bridge_result.status,
            )
        emit_terminal_summary(
            status=context.exit_status,
            round_dir=context.round_dir,
            run_dir=None,
            return_code="not_started",
            missing_artifacts=[],
            codex_request_path=codex_request_path,
            bridge_result=bridge_result,
        )
        return 0

    base_dir = outputs_dir(context.decision)
    baseline_runs = snapshot_existing_runs(base_dir)

    print("status=launching", flush=True)
    print(f"round_dir={'' if context.round_dir is None else context.round_dir}", flush=True)
    sync_round_state(
        context,
        status="launching",
        run_dir=None,
        training_return_code=None,
        bridge_result=BridgeInvocationResult(False, "not_invoked", None),
    )
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
        _diag = terminate_process_tree(process, "run_dir_not_detected")
        return_code = process.poll()
        bridge_result = BridgeInvocationResult(False, "not_invoked", "not_started")
        print(f"[Scheduler] run_dir not detected. "
              f"strategy={_diag['training_termination_strategy']} "
              f"cleanup={_diag['training_cleanup_succeeded']}", flush=True)
        if round_state_file is not None:
            update_round_state_file(
                round_state_file,
                status="run_dir_not_detected",
                run_dir="",
                training_return_code=return_code,
                bridge_invoked=bridge_result.invoked,
                bridge_status=bridge_result.status,
            )
        emit_terminal_summary(
            status="run_dir_not_detected",
            round_dir=context.round_dir,
            run_dir=None,
            return_code=return_code,
            missing_artifacts=["run_dir_not_detected"],
            codex_request_path=codex_request_path,
            bridge_result=bridge_result,
        )
        return 1

    print("status=run_dir_detected", flush=True)
    print(f"run_dir={run_dir}", flush=True)
    sync_round_state(
        context,
        status="run_dir_detected",
        run_dir=run_dir,
        training_return_code=None,
        bridge_result=BridgeInvocationResult(False, "not_invoked", None),
    )

    print("status=waiting_for_process_exit", flush=True)
    return_code, timeout_reason = wait_for_process_exit(process, args.poll_sec, run_dir, args.training_no_progress_timeout_sec, args.training_hard_timeout_sec)

    print("status=validating_artifacts", flush=True)
    validation = validate_run_artifacts(
        run_dir,
        context.decision.target_program if context.decision is not None else "fake_train.py",
    )
    success = return_code == 0 and validation.success and (timeout_reason == "exited")
    
    missing_items = list(validation.missing_items) if validation.missing_items else []
    if timeout_reason != "exited":
        missing_items.append(timeout_reason)

    if timeout_reason != "exited":
        final_status = timeout_reason
    elif return_code != 0:
        final_status = "training_process_nonzero_exit"
    elif not validation.success:
        final_status = "artifact_validation_failed"
    else:
        final_status = "success"

    sync_round_state(
        context,
        status=final_status,
        run_dir=run_dir,
        training_return_code=return_code,
        bridge_result=BridgeInvocationResult(False, "not_invoked", None),
    )

    generated_request_path = None
    if success and context.decision is not None and context.round_dir is not None:
        generated_request_path = context.round_dir / "codex_request.md"
        resolved_compare_targets = resolve_compare_targets(context.decision, context.decision.round_id)
        generated_request_path.write_text(
            render_codex_request(
                context.decision,
                run_dir=run_dir,
                round_dir=context.round_dir,
                resolved_compare_targets=resolved_compare_targets,
            ),
            encoding="utf-8",
        )
        if args.invoke_codex_bridge:
            bridge_result = invoke_codex_bridge(
                codex_request_path=generated_request_path,
                bridge_config=args.bridge_config,
                manual_confirm_send=args.bridge_manual_confirm_send,
            )
        else:
            bridge_result = BridgeInvocationResult(False, "not_invoked", "not_started")
    elif args.invoke_codex_bridge:
        bridge_result = BridgeInvocationResult(False, "skipped_no_codex_request", "not_started")
    else:
        bridge_result = BridgeInvocationResult(False, "not_invoked", "not_started")

    if round_state_file is not None:
        update_round_state_file(
            round_state_file,
            status=final_status,
            run_dir=run_dir,
            training_return_code=return_code,
            bridge_invoked=bridge_result.invoked,
            bridge_status=bridge_result.status,
        )

    emit_terminal_summary(
        status=final_status,
        round_dir=context.round_dir,
        run_dir=run_dir,
        return_code=return_code,
        missing_artifacts=missing_items,
        codex_request_path=generated_request_path if generated_request_path is not None else codex_request_path,
        bridge_result=bridge_result,
    )
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
