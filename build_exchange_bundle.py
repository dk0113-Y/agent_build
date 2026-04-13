#!/usr/bin/env python
"""Build a formal_train automation round from an existing real run directory."""

from __future__ import annotations

import argparse
import shutil
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


def copy_round_artifacts(*, artifact_paths: dict[str, Path], round_dir: Path) -> None:
    for name, source_path in artifact_paths.items():
        shutil.copy2(source_path, round_dir / name)
    training_summary = artifact_paths["metric_snapshot.json"].parent / "training_summary.txt"
    if training_summary.exists():
        shutil.copy2(training_summary, round_dir / "training_summary.txt")


def render_formal_codex_request(
    *,
    round_id: str,
    round_dir: Path,
    run_dir: Path,
    source_of_truth_repo: Path,
    baseline_run_dir: Path | None,
    comparability_report: dict[str, Any],
    round_summary: dict[str, Any],
) -> str:
    tracked_files = [
        "metric_snapshot.json",
        "benchmark_summary.json",
        "config_snapshot.json",
        "artifact_index.json",
        "comparability_report.json",
        "round_summary.json",
    ]
    lines = [
        "# Codex Analysis Request",
        "",
        "## 1. Formal Train Context",
        f"- Round id: `{round_id}`",
        f"- Source of truth repo: `{source_of_truth_repo.resolve()}`",
        f"- Target run directory: `{run_dir.resolve()}`",
        f"- Baseline run directory: `{baseline_run_dir.resolve()}`" if baseline_run_dir else "- Baseline run directory: `UNSET`",
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
            "2. Review `metric_snapshot.json` with emphasis on best_eval, last_eval, and final_probe together.",
            "3. Review `benchmark_summary.json` only as supporting efficiency evidence; missing runtime data must remain flagged.",
            "4. Use `round_summary.json` only as a structured synthesis layer, not as a substitute for the underlying artifacts.",
            "",
            "## 4. Questions",
            "1. Is this round formally comparable to the referenced baseline, bootstrap-comparable only, or not comparable?",
            "2. What do best_eval, last_eval, and final_probe jointly imply about primary task quality and stability?",
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
    source_of_truth_repo: Path,
    baseline_run_dir: Path | None,
    config_snapshot: dict[str, Any],
    round_summary: dict[str, Any],
) -> dict[str, Any]:
    cli_args = args.cli_args or ["--device", "cuda"]
    return {
        "schema_version": "2.0",
        "round_id": round_id,
        "experiment_mode": "formal_train",
        "source_of_truth_repo": str(source_of_truth_repo.resolve()),
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
            "output_root": str(run_dir.parent.resolve()),
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
                "Do best_eval, last_eval, and final_probe support improvement, regression, hold, or insufficient evidence?",
                "Does the stop_window_state justify run_next_round, stop_experiment, pause_for_manual_review, or analyze_only?",
            ],
            "expected_output_style": "Write a structured Markdown report grounded in the formal JSON artifacts.",
        },
        "reference_targets": {
            "best_known_reference": str(baseline_run_dir.resolve()) if baseline_run_dir else None,
            "manual_compare_targets": [],
        },
        "controller_notes": default_controller_notes(args, run_dir),
    }


def main() -> int:
    args = parse_args()
    try:
        round_id = normalize_round_id(args.round_id)
        source_of_truth_repo = args.source_of_truth_repo.resolve()
        run_dir = args.run_dir.resolve()
        if not run_dir.exists():
            raise ProtocolError(f"Run directory does not exist: {run_dir}")

        target_artifact_paths = ensure_required_run_artifacts(run_dir)
        baseline_run_dir = args.baseline_run_dir.resolve() if args.baseline_run_dir else None
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
        historical_baseline_summary = maybe_read_json(
            source_of_truth_repo / "formal_artifacts" / "historical_baseline_summary.json"
        )

        comparability_report = build_comparability_report(
            round_id=round_id,
            experiment_mode="formal_train",
            source_of_truth_repo=str(source_of_truth_repo),
            target_run_dir=str(run_dir),
            target_metric_snapshot=target_metric_snapshot,
            target_benchmark_summary=target_benchmark_summary,
            target_config_snapshot=target_config_snapshot,
            baseline_round_id=args.baseline_round_id,
            baseline_run_dir=str(baseline_run_dir) if baseline_run_dir else None,
            baseline_metric_snapshot=baseline_metric_snapshot,
            baseline_benchmark_summary=baseline_benchmark_summary,
            baseline_config_snapshot=baseline_config_snapshot,
        )
        round_summary = build_round_summary(
            round_id=round_id,
            experiment_mode="formal_train",
            source_of_truth_repo=str(source_of_truth_repo),
            run_dir=str(run_dir),
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
            source_of_truth_repo=source_of_truth_repo,
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
        copy_round_artifacts(artifact_paths=target_artifact_paths, round_dir=round_dir)
        write_json_file(round_dir / "comparability_report.json", comparability_report)
        write_json_file(round_dir / "round_summary.json", round_summary)

        codex_request_text = render_formal_codex_request(
            round_id=round_id,
            round_dir=round_dir,
            run_dir=run_dir,
            source_of_truth_repo=source_of_truth_repo,
            baseline_run_dir=baseline_run_dir,
            comparability_report=comparability_report,
            round_summary=round_summary,
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
                    "run_dir": str(run_dir),
                },
                round_summary=round_summary,
                comparability_report=comparability_report,
                metric_snapshot=target_metric_snapshot,
                benchmark_summary=target_benchmark_summary,
            ),
            encoding="utf-8",
        )

        update_round_state_file(
            round_dir / "round_state.json",
            experiment_mode="formal_train",
            source_of_truth_repo=source_of_truth_repo,
            evaluation_mode="formal_artifact_review",
            status="success",
            run_dir=run_dir,
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
