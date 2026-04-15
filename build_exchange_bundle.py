#!/usr/bin/env python
"""Build a formal_train automation round from an existing real run directory.

See docs/codex_local_index.md for the local file map before tracing cross-repo roles.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from automation_protocol import (
    GPT_INPUT_FILENAME,
    ProtocolError,
    ingest_decision_payload,
    normalize_round_id,
    relative_repo_path,
    repo_root,
    update_round_state_file,
    write_json_file,
)
from comparability import build_comparability_report, get_comparability_group, get_git_commit_sha
from formal_round_summary import (
    build_round_summary,
    maybe_read_json,
    read_json,
    render_codex_report,
    render_formal_gpt_input,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a formal_train exchange bundle from an existing run.")
    parser.add_argument("--round-id", required=True, help="Target round id, for example round_0022.")
    parser.add_argument("--run-dir", required=True, type=Path, help="Real run directory under the source-of-truth repo outputs/.")
    parser.add_argument("--source-of-truth-repo", type=Path, default=Path("../代码1"))
    parser.add_argument("--baseline-run-dir", type=Path, help="Optional baseline run directory.")
    parser.add_argument("--baseline-round-id", help="Optional published baseline round id.")
    parser.add_argument("--source-round-id", help="Optional lineage source round id.")
    parser.add_argument("--target-program", default="train_q_agent.py")
    parser.add_argument("--decision-status", default="")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--cli-arg",
        dest="cli_args",
        action="append",
        default=None,
        help="CLI args to reconstruct the target training command. Repeat the flag for multiple args.",
    )
    parser.add_argument("--controller-notes", default="")
    return parser.parse_args()


def required_run_artifact_paths(run_dir: Path) -> dict[str, Path]:
    logs_dir = run_dir / "logs"
    return {
        "metric_snapshot.json": logs_dir / "metric_snapshot.json",
        "benchmark_summary.json": logs_dir / "benchmark_summary.json",
        "config_snapshot.json": logs_dir / "config_snapshot.json",
        "artifact_index.json": logs_dir / "artifact_index.json",
    }


def ensure_required_run_artifacts(run_dir: Path) -> dict[str, Path]:
    artifact_paths = required_run_artifact_paths(run_dir)
    missing = [name for name, path in artifact_paths.items() if not path.exists()]
    if missing:
        raise ProtocolError(
            f"Run directory is missing required formal artifacts: {', '.join(missing)} ({run_dir})"
        )
    return artifact_paths


PATH_LIKE_KEYS = {
    "run_dir",
    "target_run_dir",
    "baseline_run_dir",
    "output_root",
    "best_known_reference",
}


def repo_identity_from_remote_url(remote_url: str) -> str | None:
    text = remote_url.strip()
    if not text:
        return None
    if text.endswith(".git"):
        text = text[:-4]
    if "://" in text:
        tail = text.split("://", 1)[1]
        if "/" in tail:
            return tail.split("/", 1)[1].strip("/") or None
    if "@" in text and ":" in text:
        return text.rsplit(":", 1)[1].strip("/") or None
    cleaned = text.strip("/").replace("\\", "/")
    return cleaned or None


def source_repo_identity(source_repo: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=str(source_repo),
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception:
        return source_repo.name
    return repo_identity_from_remote_url(result.stdout) or source_repo.name


def repo_relative_text(source_repo: Path, value: str | Path | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    path = Path(text)
    if path.is_absolute():
        try:
            return path.resolve().relative_to(source_repo.resolve()).as_posix()
        except ValueError:
            return text
    return Path(text).as_posix()


def sanitize_exchange_payload(
    payload: Any,
    *,
    source_repo: Path,
    repo_identity: str,
    local_execution_repo_path: str,
    parent_key: str | None = None,
) -> Any:
    if isinstance(payload, dict):
        sanitized: dict[str, Any] = {}
        for key, value in payload.items():
            if key == "source_of_truth_repo":
                sanitized[key] = repo_identity
                continue
            if key == "local_execution_repo_path":
                sanitized[key] = local_execution_repo_path
                continue
            sanitized[key] = sanitize_exchange_payload(
                value,
                source_repo=source_repo,
                repo_identity=repo_identity,
                local_execution_repo_path=local_execution_repo_path,
                parent_key=key,
            )
        if "source_of_truth_repo" in sanitized and "local_execution_repo_path" not in sanitized:
            sanitized["local_execution_repo_path"] = local_execution_repo_path
        return sanitized
    if isinstance(payload, list):
        return [
            sanitize_exchange_payload(
                item,
                source_repo=source_repo,
                repo_identity=repo_identity,
                local_execution_repo_path=local_execution_repo_path,
                parent_key=parent_key,
            )
            for item in payload
        ]
    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            return payload
        if parent_key == "source_of_truth_repo":
            return repo_identity
        if parent_key == "local_execution_repo_path":
            return local_execution_repo_path
        if parent_key in PATH_LIKE_KEYS or text.startswith(str(source_repo.resolve())):
            relative = repo_relative_text(source_repo, text)
            return relative if relative is not None else payload
    return payload


def ensure_historical_baseline_summary(source_repo: Path) -> Path | None:
    summary_path = source_repo / "formal_artifacts" / "historical_baseline_summary.json"
    if summary_path.exists():
        return summary_path
    script_path = source_repo / "tools" / "generate_historical_baseline_summary.py"
    if not script_path.exists():
        return None
    try:
        subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(source_repo),
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise ProtocolError(
            "Failed to generate historical_baseline_summary.json: "
            f"{exc.stderr.strip() or exc.stdout.strip() or 'unknown error'}"
        ) from exc
    return summary_path if summary_path.exists() else None


def copy_round_artifacts(
    *,
    artifact_paths: dict[str, Path],
    round_dir: Path,
    source_repo: Path,
    repo_identity: str,
    local_execution_repo_path: str,
    historical_baseline_summary_path: Path | None,
) -> None:
    for name, source_path in artifact_paths.items():
        if source_path.suffix.lower() == ".json":
            payload = read_json(source_path)
            sanitized = sanitize_exchange_payload(
                payload,
                source_repo=source_repo,
                repo_identity=repo_identity,
                local_execution_repo_path=local_execution_repo_path,
            )
            write_json_file(round_dir / name, sanitized)
        else:
            shutil.copy2(source_path, round_dir / name)
    training_summary = artifact_paths["metric_snapshot.json"].parent / "training_summary.txt"
    if training_summary.exists():
        training_summary_text = training_summary.read_text(encoding="utf-8")
        source_repo_text = str(source_repo.resolve())
        training_summary_text = training_summary_text.replace(f"{source_repo_text}\\", "")
        training_summary_text = training_summary_text.replace(f"{source_repo_text}/", "")
        training_summary_text = training_summary_text.replace(source_repo_text, repo_identity)
        training_summary_text = training_summary_text.replace("\\", "/")
        (round_dir / "training_summary.txt").write_text(training_summary_text, encoding="utf-8")
    if historical_baseline_summary_path and historical_baseline_summary_path.exists():
        sanitized_historical = sanitize_exchange_payload(
            read_json(historical_baseline_summary_path),
            source_repo=source_repo,
            repo_identity=repo_identity,
            local_execution_repo_path=local_execution_repo_path,
        )
        write_json_file(round_dir / "historical_baseline_summary.json", sanitized_historical)


def render_formal_codex_request(
    *,
    round_id: str,
    round_dir: Path,
    run_dir: str,
    source_of_truth_repo: str,
    local_execution_repo_path: str,
    baseline_run_dir: str | None,
    comparability_report: dict[str, Any],
    round_summary: dict[str, Any],
    historical_baseline_summary_available: bool,
) -> str:
    tracked_files = [
        "metric_snapshot.json",
        "benchmark_summary.json",
        "config_snapshot.json",
        "artifact_index.json",
        "comparability_report.json",
        "round_summary.json",
    ]
    if historical_baseline_summary_available:
        tracked_files.append("historical_baseline_summary.json")
    lines = [
        "# Codex Analysis Request",
        "",
        "## 1. Formal Train Context",
        f"- Round id: `{round_id}`",
        f"- Source of truth repo: `{source_of_truth_repo}`",
        f"- Local execution repo path: `{local_execution_repo_path}`",
        f"- Target run directory: `{run_dir}`",
        f"- Baseline run directory: `{baseline_run_dir}`" if baseline_run_dir else "- Baseline run directory: `UNSET`",
        f"- Comparability status: `{comparability_report.get('comparability_status', 'UNSET')}`",
        f"- Decision zone: `{round_summary.get('decision_zone', 'UNSET')}`",
        "",
        "## 2. Primary Evidence Files",
    ]
    for name in tracked_files:
        lines.append(f"- `{relative_repo_path(round_dir / name)}`")
    lines.extend(
        [
            "",
            "## 3. Required Judgement Order",
            "1. Check comparability first. If comparability failed or evidence is insufficient, do not claim formal improvement.",
            "2. Review `metric_snapshot.json` with emphasis on `final_probe` as the formal acceptance object, `training_dynamics_summary` as ranking/support evidence, and `recent_train_support_summary` / `train_final_consistency_summary` as train-to-final consistency checks.",
            "3. Treat `best_eval`, `last_eval`, and `best.pt` as optional legacy diagnostic context only when they are present; they are not formal gates.",
            "4. Review `benchmark_summary.json` only as supporting efficiency evidence; missing runtime data must remain flagged.",
            "5. Use `round_summary.json` only as a structured synthesis layer, not as a substitute for the underlying artifacts.",
            "",
            "## 4. Questions",
            "1. Is this round formally comparable to the referenced baseline, bootstrap-comparable only, or not comparable?",
            "2. What do `final_probe`, `training_dynamics_summary`, and `train_final_consistency_summary` imply about formal quality and training-process quality?",
            "3. Should the next controller action be `run_next_round`, `stop_experiment`, `pause_for_manual_review`, or `analyze_only`?",
            "4. Which evidence gaps must remain explicit in the next GPT decision payload?",
            "",
            "## 5. Output Requirement",
            f"- Write the analysis report to `{relative_repo_path(round_dir / 'codex_report.md')}`.",
            "- Base every formal conclusion on the structured JSON files above rather than on synthetic rehearsal assumptions.",
        ]
    )
    return "\n".join(lines) + "\n"


def default_controller_notes(args: argparse.Namespace, run_dir: Path) -> str:
    if args.controller_notes.strip():
        return args.controller_notes.strip()
    return (
        f"Imported formal_train round from `{run_dir.name}`. "
        "This bundle is grounded in real training artifacts from the source-of-truth repo."
    )


def build_decision_payload(
    *,
    args: argparse.Namespace,
    round_id: str,
    run_dir: Path,
    source_of_truth_repo: str,
    local_execution_repo_path: str,
    source_repo_root: Path,
    baseline_run_dir: Path | None,
    config_snapshot: dict[str, Any],
    round_summary: dict[str, Any],
) -> dict[str, Any]:
    cli_args = args.cli_args or ["--device", "cuda"]
    return {
        "schema_version": "2.0",
        "round_id": round_id,
        "experiment_mode": "formal_train",
        "source_of_truth_repo": source_of_truth_repo,
        "local_execution_repo_path": local_execution_repo_path,
        "decision_status": args.decision_status.strip() or round_summary["stop_window_state"]["recommended_action"],
        "evaluation_mode": "formal_artifact_review",
        "comparability_group": get_comparability_group(config_snapshot),
        "baseline_round_id": args.baseline_round_id,
        "baseline_commit_sha": round_summary.get("baseline_commit_sha"),
        "decision_zone": round_summary["decision_zone"],
        "stop_window_state": round_summary["stop_window_state"],
        "manual_review_reasons": round_summary["manual_review_reasons"],
        "insufficient_evidence_flags": round_summary["insufficient_evidence_flags"],
        "target_program": args.target_program,
        "run_args": {
            "cli_args": cli_args,
            "run_name": run_dir.name,
            "output_root": repo_relative_text(source_repo_root, run_dir.parent),
            "notes": "Imported historical formal run bundle; rerun only after comparability review.",
        },
        "parameter_changes": [],
        "codex_analysis_focus": {
            "compare_targets": ["best_known_reference"] if baseline_run_dir else [],
            "required_logs": [
                "metric_snapshot.json",
                "benchmark_summary.json",
                "config_snapshot.json",
                "artifact_index.json",
                "comparability_report.json",
                "round_summary.json",
            ],
            "required_plots": [],
            "questions": [
                "Is the round formally comparable to the referenced baseline or only bootstrap-comparable?",
                "Do final_probe, training_dynamics_summary, and train_final_consistency_summary support improvement, regression, hold, or insufficient evidence, and do any legacy diagnostic artifacts disagree?",
                "Does the stop_window_state justify run_next_round, stop_experiment, pause_for_manual_review, or analyze_only?",
            ],
            "expected_output_style": "Write a structured Markdown report grounded in the formal JSON artifacts.",
        },
        "reference_targets": {
            "best_known_reference": repo_relative_text(source_repo_root, baseline_run_dir) if baseline_run_dir else None,
            "manual_compare_targets": [],
        },
        "controller_notes": default_controller_notes(args, run_dir),
    }


def main() -> int:
    args = parse_args()
    try:
        round_id = normalize_round_id(args.round_id)
        source_of_truth_repo = args.source_of_truth_repo.resolve()
        source_of_truth_repo_identity = source_repo_identity(source_of_truth_repo)
        local_execution_repo_path = str(source_of_truth_repo)
        run_dir = args.run_dir.resolve()
        if not run_dir.exists():
            raise ProtocolError(f"Run directory does not exist: {run_dir}")
        run_dir_exchange_path = repo_relative_text(source_of_truth_repo, run_dir) or run_dir.name

        target_artifact_paths = ensure_required_run_artifacts(run_dir)
        baseline_run_dir = args.baseline_run_dir.resolve() if args.baseline_run_dir else None
        baseline_run_dir_exchange_path = (
            repo_relative_text(source_of_truth_repo, baseline_run_dir)
            if baseline_run_dir else None
        )
        baseline_artifact_paths = ensure_required_run_artifacts(baseline_run_dir) if baseline_run_dir else None

        target_metric_snapshot = read_json(target_artifact_paths["metric_snapshot.json"])
        target_benchmark_summary = read_json(target_artifact_paths["benchmark_summary.json"])
        target_config_snapshot = read_json(target_artifact_paths["config_snapshot.json"])
        target_artifact_index = read_json(target_artifact_paths["artifact_index.json"])

        baseline_metric_snapshot = (
            read_json(baseline_artifact_paths["metric_snapshot.json"])
            if baseline_artifact_paths else None
        )
        baseline_benchmark_summary = (
            read_json(baseline_artifact_paths["benchmark_summary.json"])
            if baseline_artifact_paths else None
        )
        baseline_config_snapshot = (
            read_json(baseline_artifact_paths["config_snapshot.json"])
            if baseline_artifact_paths else None
        )
        historical_baseline_summary_path = ensure_historical_baseline_summary(source_of_truth_repo)
        historical_baseline_summary = maybe_read_json(historical_baseline_summary_path)

        comparability_report = build_comparability_report(
            round_id=round_id,
            experiment_mode="formal_train",
            source_of_truth_repo=source_of_truth_repo_identity,
            local_execution_repo_path=local_execution_repo_path,
            target_run_dir=run_dir_exchange_path,
            target_metric_snapshot=target_metric_snapshot,
            target_benchmark_summary=target_benchmark_summary,
            target_config_snapshot=target_config_snapshot,
            baseline_round_id=args.baseline_round_id,
            baseline_run_dir=baseline_run_dir_exchange_path,
            baseline_metric_snapshot=baseline_metric_snapshot,
            baseline_benchmark_summary=baseline_benchmark_summary,
            baseline_config_snapshot=baseline_config_snapshot,
            historical_baseline_summary=historical_baseline_summary,
            historical_baseline_summary_path=(
                "historical_baseline_summary.json" if historical_baseline_summary else None
            ),
        )
        round_summary = build_round_summary(
            round_id=round_id,
            experiment_mode="formal_train",
            source_of_truth_repo=source_of_truth_repo_identity,
            local_execution_repo_path=local_execution_repo_path,
            run_dir=run_dir_exchange_path,
            evaluation_mode="formal_artifact_review",
            metric_snapshot=target_metric_snapshot,
            benchmark_summary=target_benchmark_summary,
            config_snapshot=target_config_snapshot,
            artifact_index=target_artifact_index,
            comparability_report=comparability_report,
            baseline_round_id=args.baseline_round_id,
            baseline_commit_sha=get_git_commit_sha(baseline_config_snapshot),
            baseline_metric_snapshot=baseline_metric_snapshot,
            baseline_benchmark_summary=baseline_benchmark_summary,
            historical_baseline_summary=historical_baseline_summary,
        )

        decision_payload = build_decision_payload(
            args=args,
            round_id=round_id,
            run_dir=run_dir,
            source_of_truth_repo=source_of_truth_repo_identity,
            local_execution_repo_path=local_execution_repo_path,
            source_repo_root=source_of_truth_repo,
            baseline_run_dir=baseline_run_dir,
            config_snapshot=target_config_snapshot,
            round_summary=round_summary,
        )

        _, round_dir = ingest_decision_payload(
            payload=decision_payload,
            target_round_id=round_id,
            source_round_id=args.source_round_id,
            force=args.force,
        )
        copy_round_artifacts(
            artifact_paths=target_artifact_paths,
            round_dir=round_dir,
            source_repo=source_of_truth_repo,
            repo_identity=source_of_truth_repo_identity,
            local_execution_repo_path=local_execution_repo_path,
            historical_baseline_summary_path=historical_baseline_summary_path,
        )
        write_json_file(round_dir / "comparability_report.json", comparability_report)
        write_json_file(round_dir / "round_summary.json", round_summary)

        codex_request_text = render_formal_codex_request(
            round_id=round_id,
            round_dir=round_dir,
            run_dir=run_dir_exchange_path,
            source_of_truth_repo=source_of_truth_repo_identity,
            local_execution_repo_path=local_execution_repo_path,
            baseline_run_dir=baseline_run_dir_exchange_path,
            comparability_report=comparability_report,
            round_summary=round_summary,
            historical_baseline_summary_available=historical_baseline_summary is not None,
        )
        (round_dir / "codex_request.md").write_text(codex_request_text, encoding="utf-8")
        (round_dir / "codex_report.md").write_text(
            render_codex_report(
                round_summary=round_summary,
                comparability_report=comparability_report,
                metric_snapshot=target_metric_snapshot,
                benchmark_summary=target_benchmark_summary,
            ),
            encoding="utf-8",
        )
        (round_dir / GPT_INPUT_FILENAME).write_text(
            render_formal_gpt_input(
                decision=decision_payload,
                round_state={
                    "status": "success",
                    "run_dir": run_dir_exchange_path,
                },
                round_summary=round_summary,
                comparability_report=comparability_report,
                metric_snapshot=target_metric_snapshot,
                benchmark_summary=target_benchmark_summary,
                historical_baseline_summary=historical_baseline_summary,
            ),
            encoding="utf-8",
        )

        update_round_state_file(
            round_dir / "round_state.json",
            experiment_mode="formal_train",
            source_of_truth_repo=source_of_truth_repo_identity,
            local_execution_repo_path=local_execution_repo_path,
            evaluation_mode="formal_artifact_review",
            status="success",
            run_dir=run_dir_exchange_path,
            training_return_code=0,
            bridge_invoked=False,
            bridge_status="not_invoked",
        )

        print("status=bundle_ready")
        print(f"round_id={round_id}")
        print(f"round_dir={round_dir}")
        print(f"run_dir={run_dir}")
        print(f"comparability_status={comparability_report['comparability_status']}")
        print(f"recommended_action={round_summary['stop_window_state']['recommended_action']}")
        return 0
    except ProtocolError as exc:
        print("status=error", file=sys.stderr)
        print(f"error={exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
