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


def get_evaluation_contract(config_snapshot: dict[str, Any] | None) -> dict[str, Any]:
    contract = (config_snapshot or {}).get("evaluation_contract", {})
    return contract if isinstance(contract, dict) else {}


def get_formal_protocol_revision(config_snapshot: dict[str, Any] | None) -> str | None:
    contract = get_evaluation_contract(config_snapshot)
    revision = contract.get("protocol_revision")
    if isinstance(revision, str) and revision.strip():
        return revision.strip()
    return None


def get_formal_protocol_id(config_snapshot: dict[str, Any] | None) -> str | None:
    return get_formal_protocol_revision(config_snapshot)


def detect_legacy_formal_protocol(config_snapshot: dict[str, Any] | None) -> str | None:
    contract = get_evaluation_contract(config_snapshot)
    final_probe_rule = contract.get("final_probe_rule", {})
    if not isinstance(final_probe_rule, dict):
        return None
    source = final_probe_rule.get("source")
    if not isinstance(source, str):
        return None
    if source.strip() == "best_checkpoint_if_available_else_online_last":
        return "legacy_best_checkpoint_packet_v1"
    return None


def resolve_formal_protocol_mode(config_snapshot: dict[str, Any] | None) -> str | None:
    revision = get_formal_protocol_revision(config_snapshot)
    if revision:
        return revision
    return detect_legacy_formal_protocol(config_snapshot)


def get_raw_eval_header(config_snapshot: dict[str, Any] | None) -> list[str]:
    observed = (config_snapshot or {}).get("observed_run_contract", {})
    if not isinstance(observed, dict):
        return []
    header = observed.get("eval_metrics_header", [])
    if not isinstance(header, list):
        return []
    return [str(item) for item in header]


def get_raw_train_steps_header(config_snapshot: dict[str, Any] | None) -> list[str]:
    observed = (config_snapshot or {}).get("observed_run_contract", {})
    if not isinstance(observed, dict):
        return []
    header = observed.get("train_steps_header", [])
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


def _diagnostic_steps_to_best(benchmark_summary: dict[str, Any] | None) -> int | None:
    if not benchmark_summary:
        return None
    value = benchmark_summary.get("diagnostic_env_steps_to_best", benchmark_summary.get("env_steps_to_best"))
    return int(value) if isinstance(value, int) else None


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
    target_steps_to_best = _diagnostic_steps_to_best(target_benchmark_summary)
    baseline_steps_to_best = _diagnostic_steps_to_best(baseline_benchmark_summary)
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
        "diagnostic_env_steps_to_best": {
            "target": int(target_steps_to_best) if isinstance(target_steps_to_best, int) else None,
            "baseline": int(baseline_steps_to_best) if isinstance(baseline_steps_to_best, int) else None,
            "delta": (
                int(target_steps_to_best) - int(baseline_steps_to_best)
                if isinstance(target_steps_to_best, int) and isinstance(baseline_steps_to_best, int)
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
    local_execution_repo_path: str | None,
    target_run_dir: str,
    target_metric_snapshot: dict[str, Any],
    target_benchmark_summary: dict[str, Any],
    target_config_snapshot: dict[str, Any],
    baseline_round_id: str | None = None,
    baseline_run_dir: str | None = None,
    baseline_metric_snapshot: dict[str, Any] | None = None,
    baseline_benchmark_summary: dict[str, Any] | None = None,
    baseline_config_snapshot: dict[str, Any] | None = None,
    historical_baseline_summary: dict[str, Any] | None = None,
    historical_baseline_summary_path: str | None = None,
) -> dict[str, Any]:
    target_group = get_comparability_group(target_config_snapshot)
    baseline_group = get_comparability_group(baseline_config_snapshot)
    target_protocol_revision = get_formal_protocol_revision(target_config_snapshot)
    baseline_protocol_revision = get_formal_protocol_revision(baseline_config_snapshot)
    target_protocol = resolve_formal_protocol_mode(target_config_snapshot)
    baseline_protocol = resolve_formal_protocol_mode(baseline_config_snapshot)
    target_train_steps_header = get_raw_train_steps_header(target_config_snapshot)
    baseline_train_steps_header = get_raw_train_steps_header(baseline_config_snapshot)
    target_eval_header = get_raw_eval_header(target_config_snapshot)
    baseline_eval_header = get_raw_eval_header(baseline_config_snapshot)
    target_final_probe_header = get_raw_final_probe_header(target_config_snapshot)
    baseline_final_probe_header = get_raw_final_probe_header(baseline_config_snapshot)
    target_env_steps = get_final_env_steps(target_config_snapshot)
    baseline_env_steps = get_final_env_steps(baseline_config_snapshot)

    checks = {
        "baseline_available": baseline_metric_snapshot is not None and baseline_config_snapshot is not None,
        "target_protocol_revision_present": bool(target_protocol_revision),
        "baseline_protocol_revision_present": bool(baseline_protocol_revision),
        "protocol_revision_match": bool(
            target_protocol_revision and baseline_protocol_revision and target_protocol_revision == baseline_protocol_revision
        ),
        "same_formal_evaluation_protocol": bool(
            target_protocol and baseline_protocol and target_protocol == baseline_protocol
        ),
        "same_comparability_group": bool(target_group and baseline_group and target_group == baseline_group),
        "same_train_steps_header": bool(
            target_train_steps_header
            and baseline_train_steps_header
            and target_train_steps_header == baseline_train_steps_header
        ),
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
    using_legacy_protocol_fallback = bool(
        target_protocol == "legacy_best_checkpoint_packet_v1"
        and baseline_protocol == "legacy_best_checkpoint_packet_v1"
        and (not target_protocol_revision or not baseline_protocol_revision)
    )

    if not checks["baseline_available"]:
        notes.append("Baseline artifacts are missing, so formal comparability cannot be established.")
    elif not target_protocol or not baseline_protocol:
        notes.append("Formal protocol revision is missing or unrecognized on at least one side.")
    elif not checks["same_formal_evaluation_protocol"]:
        status = "not_comparable"
        notes.append("Formal evaluation contracts differ between target and baseline.")
    elif not target_group or not baseline_group:
        notes.append("Comparability group metadata is missing on at least one side.")
    elif not checks["same_comparability_group"]:
        status = "not_comparable"
        notes.append("Target and baseline belong to different comparability groups.")
    elif target_protocol == "formal_last_checkpoint_v2" and (
        not checks["same_train_steps_header"]
        or not checks["same_final_probe_header"]
    ):
        status = "not_comparable"
        notes.append("Observed formal CSV schemas diverged between target and baseline.")
    elif target_protocol == "legacy_best_checkpoint_packet_v1" and (
        not checks["same_train_steps_header"]
        or not checks["same_eval_metrics_header"]
        or not checks["same_final_probe_header"]
    ):
        status = "not_comparable"
        notes.append("Observed legacy formal CSV schemas diverged between target and baseline.")
    elif not checks["same_final_env_steps"]:
        status = "not_comparable"
        notes.append("Target and baseline ended at different final env_steps.")
    elif using_legacy_protocol_fallback:
        status = "bootstrap_comparable"
        notes.append(
            "Legacy formal protocol was inferred from final_probe_rule.source because protocol_revision is absent."
        )
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
    if (not target_protocol_revision or not baseline_protocol_revision) and status == "insufficient_evidence":
        insufficient_flags.append("protocol_revision_missing")
    if (
        checks["same_eval_metrics_header"] is False
        and target_eval_header
        and baseline_eval_header
        and target_protocol == "formal_last_checkpoint_v2"
    ):
        notes.append("Diagnostic periodic eval CSV headers differ, but they are not part of the formal gate.")
    if historical_baseline_summary and historical_baseline_summary.get("insufficient_history_for_calibration"):
        notes.append("Historical baseline calibration is bootstrap-only.")

    return {
        "schema_version": PROTOCOL_SCHEMA_VERSION,
        "artifact_type": "comparability_report",
        "round_id": round_id,
        "generated_at": now_iso(),
        "experiment_mode": experiment_mode,
        "source_of_truth_repo": source_of_truth_repo,
        "local_execution_repo_path": local_execution_repo_path,
        "evaluation_mode": "formal_artifact_review",
        "target_run_dir": target_run_dir,
        "baseline_round_id": baseline_round_id,
        "baseline_run_dir": baseline_run_dir,
        "baseline_commit_sha": get_git_commit_sha(baseline_config_snapshot),
        "historical_baseline_summary_path": historical_baseline_summary_path,
        "historical_calibration": {
            "available": historical_baseline_summary is not None,
            "insufficient_history_for_calibration": bool(
                (historical_baseline_summary or {}).get("insufficient_history_for_calibration")
            ),
            "run_count_total": (historical_baseline_summary or {}).get("run_count_total"),
        },
        "comparability_group": target_group,
        "baseline_comparability_group": baseline_group,
        "formal_protocol_revision": target_protocol_revision,
        "baseline_formal_protocol_revision": baseline_protocol_revision,
        "formal_protocol_id": target_protocol,
        "baseline_formal_protocol_id": baseline_protocol,
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
