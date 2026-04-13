#!/usr/bin/env python
"""Comparability helpers for formal_train exchange rounds."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROTOCOL_SCHEMA_VERSION = "formal_exchange/v2"
PRIMARY_METRICS = ("success_rate", "coverage", "reward")
SECONDARY_METRICS = ("episode_length", "repeat_visit_ratio")
STABILITY_METRICS = (
    "timeout_flag",
    "stall_trigger_count",
    "zero_info_step_count",
    "recent_revisit_count",
)


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def maybe_read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return read_json(path)


def collect_insufficient_flags(*payloads: dict[str, Any] | None) -> list[str]:
    flags: list[str] = []
    for payload in payloads:
        if not payload:
            continue
        value = payload.get("insufficient_evidence_flags", [])
        if not isinstance(value, list):
            continue
        for item in value:
            text = str(item).strip()
            if text and text not in flags:
                flags.append(text)
    return flags


def get_comparability_group(config_snapshot: dict[str, Any] | None) -> str | None:
    if not config_snapshot:
        return None
    comparability = config_snapshot.get("comparability", {})
    if not isinstance(comparability, dict):
        return None
    value = comparability.get("comparability_group")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def get_git_commit_sha(config_snapshot: dict[str, Any] | None) -> str | None:
    if not config_snapshot:
        return None
    value = config_snapshot.get("git_commit_sha")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def get_raw_eval_header(config_snapshot: dict[str, Any] | None) -> list[str]:
    observed = (config_snapshot or {}).get("observed_run_contract", {})
    if not isinstance(observed, dict):
        return []
    header = observed.get("eval_metrics_header", [])
    if not isinstance(header, list):
        return []
    return [str(item) for item in header]


def get_raw_final_probe_header(config_snapshot: dict[str, Any] | None) -> list[str]:
    observed = (config_snapshot or {}).get("observed_run_contract", {})
    if not isinstance(observed, dict):
        return []
    header = observed.get("final_probe_header", [])
    if not isinstance(header, list):
        return []
    return [str(item) for item in header]


def get_final_env_steps(config_snapshot: dict[str, Any] | None) -> int | None:
    observed = (config_snapshot or {}).get("observed_run_contract", {})
    if not isinstance(observed, dict):
        return None
    value = observed.get("final_env_steps")
    return int(value) if isinstance(value, int) else None


def has_full_config(config_snapshot: dict[str, Any] | None) -> bool:
    full_config = (config_snapshot or {}).get("full_train_config")
    return isinstance(full_config, dict) and bool(full_config)


def _metric_value(metric_snapshot: dict[str, Any] | None, block_name: str, metric_name: str) -> float | None:
    if not metric_snapshot:
        return None
    block = metric_snapshot.get(block_name, {})
    if not isinstance(block, dict):
        return None
    metrics = block.get("metrics", {})
    if not isinstance(metrics, dict):
        return None
    value = metrics.get(metric_name)
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _stability_value(metric_snapshot: dict[str, Any] | None, block_name: str, metric_name: str) -> float | None:
    if not metric_snapshot:
        return None
    block = metric_snapshot.get(block_name, {})
    if not isinstance(block, dict):
        return None
    reward_events = block.get("reward_events", {})
    if not isinstance(reward_events, dict):
        return None
    value = reward_events.get(metric_name)
    if isinstance(value, (int, float)):
        return float(value)
    return None


def build_metric_comparison(
    *,
    target_metric_snapshot: dict[str, Any] | None,
    baseline_metric_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    comparison: dict[str, Any] = {
        "final_probe_primary_metrics": {},
        "final_probe_secondary_metrics": {},
        "final_probe_stability_metrics": {},
    }
    for metric_name in PRIMARY_METRICS:
        target_value = _metric_value(target_metric_snapshot, "final_probe", metric_name)
        baseline_value = _metric_value(baseline_metric_snapshot, "final_probe", metric_name)
        comparison["final_probe_primary_metrics"][metric_name] = {
            "target": target_value,
            "baseline": baseline_value,
            "delta": (
                target_value - baseline_value
                if target_value is not None and baseline_value is not None
                else None
            ),
        }
    for metric_name in SECONDARY_METRICS:
        target_value = _metric_value(target_metric_snapshot, "final_probe", metric_name)
        baseline_value = _metric_value(baseline_metric_snapshot, "final_probe", metric_name)
        comparison["final_probe_secondary_metrics"][metric_name] = {
            "target": target_value,
            "baseline": baseline_value,
            "delta": (
                target_value - baseline_value
                if target_value is not None and baseline_value is not None
                else None
            ),
        }
    for metric_name in STABILITY_METRICS:
        target_value = _stability_value(target_metric_snapshot, "final_probe", metric_name)
        baseline_value = _stability_value(baseline_metric_snapshot, "final_probe", metric_name)
        comparison["final_probe_stability_metrics"][metric_name] = {
            "target": target_value,
            "baseline": baseline_value,
            "delta": (
                target_value - baseline_value
                if target_value is not None and baseline_value is not None
                else None
            ),
        }
    return comparison


def build_efficiency_comparison(
    *,
    target_benchmark_summary: dict[str, Any] | None,
    baseline_benchmark_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    target_runtime = (target_benchmark_summary or {}).get("total_runtime_sec")
    baseline_runtime = (baseline_benchmark_summary or {}).get("total_runtime_sec")
    target_steps_to_best = (target_benchmark_summary or {}).get("env_steps_to_best")
    baseline_steps_to_best = (baseline_benchmark_summary or {}).get("env_steps_to_best")
    return {
        "total_runtime_sec": {
            "target": target_runtime if isinstance(target_runtime, (int, float)) else None,
            "baseline": baseline_runtime if isinstance(baseline_runtime, (int, float)) else None,
            "delta": (
                float(target_runtime) - float(baseline_runtime)
                if isinstance(target_runtime, (int, float))
                and isinstance(baseline_runtime, (int, float))
                else None
            ),
        },
        "env_steps_to_best": {
            "target": int(target_steps_to_best) if isinstance(target_steps_to_best, int) else None,
            "baseline": int(baseline_steps_to_best) if isinstance(baseline_steps_to_best, int) else None,
            "delta": (
                int(target_steps_to_best) - int(baseline_steps_to_best)
                if isinstance(target_steps_to_best, int) and isinstance(baseline_steps_to_best, int)
                else None
            ),
        },
    }


def build_comparability_report(
    *,
    round_id: str,
    experiment_mode: str,
    source_of_truth_repo: str,
    target_run_dir: str,
    target_metric_snapshot: dict[str, Any],
    target_benchmark_summary: dict[str, Any],
    target_config_snapshot: dict[str, Any],
    baseline_round_id: str | None = None,
    baseline_run_dir: str | None = None,
    baseline_metric_snapshot: dict[str, Any] | None = None,
    baseline_benchmark_summary: dict[str, Any] | None = None,
    baseline_config_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target_group = get_comparability_group(target_config_snapshot)
    baseline_group = get_comparability_group(baseline_config_snapshot)
    target_eval_header = get_raw_eval_header(target_config_snapshot)
    baseline_eval_header = get_raw_eval_header(baseline_config_snapshot)
    target_final_probe_header = get_raw_final_probe_header(target_config_snapshot)
    baseline_final_probe_header = get_raw_final_probe_header(baseline_config_snapshot)
    target_env_steps = get_final_env_steps(target_config_snapshot)
    baseline_env_steps = get_final_env_steps(baseline_config_snapshot)

    checks = {
        "baseline_available": baseline_metric_snapshot is not None and baseline_config_snapshot is not None,
        "same_comparability_group": bool(target_group and baseline_group and target_group == baseline_group),
        "same_eval_metrics_header": bool(target_eval_header and baseline_eval_header and target_eval_header == baseline_eval_header),
        "same_final_probe_header": bool(
            target_final_probe_header
            and baseline_final_probe_header
            and target_final_probe_header == baseline_final_probe_header
        ),
        "same_final_env_steps": bool(
            target_env_steps is not None
            and baseline_env_steps is not None
            and target_env_steps == baseline_env_steps
        ),
        "target_has_full_config_snapshot": has_full_config(target_config_snapshot),
        "baseline_has_full_config_snapshot": has_full_config(baseline_config_snapshot),
    }

    insufficient_flags = collect_insufficient_flags(
        target_metric_snapshot,
        target_benchmark_summary,
        target_config_snapshot,
        baseline_metric_snapshot,
        baseline_benchmark_summary,
        baseline_config_snapshot,
    )
    notes: list[str] = []
    status = "insufficient_evidence"

    if not checks["baseline_available"]:
        notes.append("Baseline artifacts are missing, so formal comparability cannot be established.")
    elif not target_group or not baseline_group:
        notes.append("Comparability group metadata is missing on at least one side.")
    elif not checks["same_comparability_group"]:
        status = "not_comparable"
        notes.append("Target and baseline belong to different comparability groups.")
    elif not checks["same_eval_metrics_header"] or not checks["same_final_probe_header"]:
        status = "not_comparable"
        notes.append("Observed CSV schemas diverged between target and baseline.")
    elif not checks["same_final_env_steps"]:
        status = "not_comparable"
        notes.append("Target and baseline ended at different final env_steps.")
    elif checks["target_has_full_config_snapshot"] and checks["baseline_has_full_config_snapshot"]:
        status = "comparable"
        notes.append("Exact comparability is supported by full config snapshots and matching observed contracts.")
    else:
        status = "bootstrap_comparable"
        notes.append(
            "Observed contracts match, but one or both runs only have bootstrap/backfilled config metadata."
        )

    if status == "insufficient_evidence" and not insufficient_flags:
        insufficient_flags.append("comparability_inputs_incomplete")
    if status == "bootstrap_comparable" and "bootstrap_thresholds_required" not in insufficient_flags:
        insufficient_flags.append("bootstrap_thresholds_required")

    return {
        "schema_version": PROTOCOL_SCHEMA_VERSION,
        "artifact_type": "comparability_report",
        "round_id": round_id,
        "generated_at": now_iso(),
        "experiment_mode": experiment_mode,
        "source_of_truth_repo": source_of_truth_repo,
        "evaluation_mode": "formal_artifact_review",
        "target_run_dir": target_run_dir,
        "baseline_round_id": baseline_round_id,
        "baseline_run_dir": baseline_run_dir,
        "baseline_commit_sha": get_git_commit_sha(baseline_config_snapshot),
        "comparability_group": target_group,
        "baseline_comparability_group": baseline_group,
        "comparability_status": status,
        "checks": checks,
        "metric_comparison": build_metric_comparison(
            target_metric_snapshot=target_metric_snapshot,
            baseline_metric_snapshot=baseline_metric_snapshot,
        ),
        "efficiency_comparison": build_efficiency_comparison(
            target_benchmark_summary=target_benchmark_summary,
            baseline_benchmark_summary=baseline_benchmark_summary,
        ),
        "insufficient_evidence_flags": insufficient_flags,
        "notes": notes,
    }


def is_formally_comparable(report: dict[str, Any]) -> bool:
    return str(report.get("comparability_status", "")).strip() in {"comparable", "bootstrap_comparable"}
