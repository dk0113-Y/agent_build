#!/usr/bin/env python
"""Structured summary helpers for formal_train exchange rounds."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from comparability import PRIMARY_METRICS, SECONDARY_METRICS, STABILITY_METRICS


PROTOCOL_SCHEMA_VERSION = "formal_exchange/v2"
PRIMARY_TOLERANCES = {
    "success_rate": 0.02,
    "coverage": 0.01,
    "reward": 5.0,
}
SECONDARY_TOLERANCES = {
    "episode_length": 20.0,
    "repeat_visit_ratio": 0.03,
}
STABILITY_TOLERANCES = {
    "timeout_flag": 0.15,
    "stall_trigger_count": 25.0,
    "zero_info_step_count": 25.0,
    "recent_revisit_trigger_count": 15.0,
}
EFFICIENCY_TOLERANCES = {
    "diagnostic_env_steps_to_best": 20_000.0,
    "total_runtime_sec": 600.0,
}
RECENT_TRAIN_SUPPORT_TOLERANCES = {
    "success_rate": 0.10,
    "coverage": 0.05,
    "reward": 20.0,
    "episode_length": 50.0,
    "repeat_visit_ratio": 0.08,
}
RECENT_TRAIN_SUPPORT_DIRECTIONS = {
    "success_rate": True,
    "coverage": True,
    "reward": True,
    "episode_length": False,
    "repeat_visit_ratio": False,
}
TRAINING_DYNAMICS_TOLERANCES = {
    "recent_mean_reward": 20.0,
    "recent_mean_coverage": 0.05,
    "recent_success_rate": 0.10,
    "recent_mean_episode_length": 50.0,
    "recent_mean_repeat_visit_ratio": 0.08,
    "growth_rate_reward": 1.0,
    "growth_rate_coverage": 0.002,
    "growth_rate_success_rate": 0.002,
    "growth_rate_repeat_visit_ratio": 0.002,
    "threshold_reach_steps_success_050": 10_000.0,
    "threshold_reach_steps_coverage_090": 10_000.0,
    "late_stage_variance_reward": 20.0,
    "late_stage_variance_coverage": 0.005,
    "late_stage_variance_success_rate": 0.005,
    "late_stage_variance_repeat_visit_ratio": 0.005,
}
TRAINING_DYNAMICS_DIRECTIONS = {
    "recent_mean_reward": True,
    "recent_mean_coverage": True,
    "recent_success_rate": True,
    "recent_mean_episode_length": False,
    "recent_mean_repeat_visit_ratio": False,
    "growth_rate_reward": True,
    "growth_rate_coverage": True,
    "growth_rate_success_rate": True,
    "growth_rate_repeat_visit_ratio": False,
    "threshold_reach_steps_success_050": False,
    "threshold_reach_steps_coverage_090": False,
    "late_stage_variance_reward": False,
    "late_stage_variance_coverage": False,
    "late_stage_variance_success_rate": False,
    "late_stage_variance_repeat_visit_ratio": False,
}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def maybe_read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return read_json(path)


def collect_unique_flags(*flag_lists: list[str]) -> list[str]:
    collected: list[str] = []
    for flag_list in flag_lists:
        for item in flag_list:
            text = str(item).strip()
            if text and text not in collected:
                collected.append(text)
    return collected


def merge_insufficient_flags(*payloads: dict[str, Any] | None) -> list[str]:
    collected: list[str] = []
    for payload in payloads:
        if not payload:
            continue
        values = payload.get("insufficient_evidence_flags", [])
        if not isinstance(values, list):
            continue
        collected = collect_unique_flags(collected, [str(item) for item in values])
    return collected


def _source_block(metric_snapshot: dict[str, Any], block_name: str) -> dict[str, Any]:
    block = metric_snapshot.get(block_name, {})
    return block if isinstance(block, dict) else {}


def metric_value(metric_snapshot: dict[str, Any], block_name: str, metric_name: str) -> float | None:
    block = _source_block(metric_snapshot, block_name)
    metrics = block.get("metrics", {})
    if not isinstance(metrics, dict):
        return None
    value = metrics.get(metric_name)
    return float(value) if isinstance(value, (int, float)) else None


def stability_value(metric_snapshot: dict[str, Any], block_name: str, metric_name: str) -> float | None:
    block = _source_block(metric_snapshot, block_name)
    reward_events = block.get("reward_events", {})
    if not isinstance(reward_events, dict):
        return None
    value = reward_events.get(metric_name)
    if value is None and metric_name == "recent_revisit_trigger_count":
        value = reward_events.get("recent_revisit_count")
    return float(value) if isinstance(value, (int, float)) else None


def semantic_value(metric_snapshot: dict[str, Any], block_name: str, metric_name: str) -> float | None:
    block = _source_block(metric_snapshot, block_name)
    semantic = block.get("semantic_monitoring", {})
    if not isinstance(semantic, dict):
        return None
    value = semantic.get(metric_name)
    return float(value) if isinstance(value, (int, float)) else None


def diagnostic_steps_to_best(benchmark_summary: dict[str, Any]) -> float | None:
    value = benchmark_summary.get("diagnostic_env_steps_to_best", benchmark_summary.get("env_steps_to_best"))
    return float(value) if isinstance(value, (int, float)) else None


def classify_delta(
    *,
    target: float | None,
    baseline: float | None,
    tolerance: float,
    higher_is_better: bool,
) -> str:
    if target is None or baseline is None:
        return "insufficient_evidence"
    delta = target - baseline
    if abs(delta) <= tolerance:
        return "hold"
    improved = delta > 0 if higher_is_better else delta < 0
    return "improved" if improved else "regressed"


def summarize_metric_family(
    *,
    target_metric_snapshot: dict[str, Any],
    baseline_metric_snapshot: dict[str, Any] | None,
    block_name: str,
    metric_names: tuple[str, ...],
    tolerances: dict[str, float],
    higher_is_better_map: dict[str, bool],
    value_getter,
) -> dict[str, Any]:
    details: dict[str, Any] = {}
    counts = {"improved": 0, "regressed": 0, "hold": 0, "insufficient_evidence": 0}
    for metric_name in metric_names:
        target = value_getter(target_metric_snapshot, block_name, metric_name)
        baseline = value_getter(baseline_metric_snapshot or {}, block_name, metric_name) if baseline_metric_snapshot else None
        verdict = classify_delta(
            target=target,
            baseline=baseline,
            tolerance=tolerances[metric_name],
            higher_is_better=higher_is_better_map[metric_name],
        )
        counts[verdict] += 1
        details[metric_name] = {
            "target": target,
            "baseline": baseline,
            "delta": target - baseline if target is not None and baseline is not None else None,
            "verdict": verdict,
        }

    if counts["insufficient_evidence"] == len(metric_names):
        family_verdict = "insufficient_evidence"
    elif counts["regressed"] >= max(1, len(metric_names) // 2):
        family_verdict = "regression"
    elif counts["improved"] >= max(1, len(metric_names) // 2) and counts["regressed"] == 0:
        family_verdict = "improvement"
    else:
        family_verdict = "hold"
    return {"verdict": family_verdict, "details": details, "counts": counts}


def _nested_value(payload: dict[str, Any] | None, *keys: str) -> float | None:
    current: Any = payload or {}
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return float(current) if isinstance(current, (int, float)) else None


def _compare_flat_metrics(
    *,
    target_values: dict[str, Any] | None,
    baseline_values: dict[str, Any] | None,
    metric_names: tuple[str, ...],
    tolerances: dict[str, float],
    higher_is_better_map: dict[str, bool],
) -> dict[str, Any]:
    details: dict[str, Any] = {}
    counts = {"improved": 0, "regressed": 0, "hold": 0, "insufficient_evidence": 0}
    for metric_name in metric_names:
        target = _nested_value(target_values, metric_name)
        baseline = _nested_value(baseline_values, metric_name)
        verdict = classify_delta(
            target=target,
            baseline=baseline,
            tolerance=tolerances[metric_name],
            higher_is_better=higher_is_better_map[metric_name],
        )
        counts[verdict] += 1
        details[metric_name] = {
            "target": target,
            "baseline": baseline,
            "delta": target - baseline if target is not None and baseline is not None else None,
            "verdict": verdict,
        }
    if counts["insufficient_evidence"] == len(metric_names):
        verdict = "insufficient_evidence"
    elif counts["regressed"] >= max(1, len(metric_names) // 2):
        verdict = "regression"
    elif counts["improved"] >= max(1, len(metric_names) // 2) and counts["regressed"] == 0:
        verdict = "improvement"
    else:
        verdict = "hold"
    return {"verdict": verdict, "details": details, "counts": counts}


def build_efficiency_summary(
    *,
    target_benchmark_summary: dict[str, Any],
    baseline_benchmark_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    details: dict[str, Any] = {}
    counts = {"improved": 0, "regressed": 0, "hold": 0, "insufficient_evidence": 0}
    for metric_name, tolerance in EFFICIENCY_TOLERANCES.items():
        if metric_name == "diagnostic_env_steps_to_best":
            target = diagnostic_steps_to_best(target_benchmark_summary)
            baseline = diagnostic_steps_to_best(baseline_benchmark_summary or {})
        else:
            target = target_benchmark_summary.get(metric_name)
            baseline = (baseline_benchmark_summary or {}).get(metric_name)
        target_value = float(target) if isinstance(target, (int, float)) else None
        baseline_value = float(baseline) if isinstance(baseline, (int, float)) else None
        verdict = classify_delta(
            target=target_value,
            baseline=baseline_value,
            tolerance=tolerance,
            higher_is_better=False,
        )
        counts[verdict] += 1
        details[metric_name] = {
            "target": target_value,
            "baseline": baseline_value,
            "delta": target_value - baseline_value if target_value is not None and baseline_value is not None else None,
            "verdict": verdict,
        }
    if counts["insufficient_evidence"] == len(EFFICIENCY_TOLERANCES):
        verdict = "insufficient_evidence"
    elif counts["regressed"] >= 1:
        verdict = "regression"
    elif counts["improved"] >= 1 and counts["regressed"] == 0:
        verdict = "improvement"
    else:
        verdict = "hold"
    return {"verdict": verdict, "details": details, "counts": counts}


def semantic_monitoring_notes(
    *,
    target_metric_snapshot: dict[str, Any],
    baseline_metric_snapshot: dict[str, Any] | None,
) -> list[str]:
    notes: list[str] = []
    if not baseline_metric_snapshot:
        return notes
    target_cap = semantic_value(target_metric_snapshot, "final_probe", "value_entry_cap_hit_flag")
    baseline_cap = semantic_value(baseline_metric_snapshot, "final_probe", "value_entry_cap_hit_flag")
    if target_cap is not None and baseline_cap is not None and target_cap - baseline_cap > 0.03:
        notes.append("value_entry_cap_hit_flag increased materially in final_probe.")

    target_trunc = semantic_value(target_metric_snapshot, "final_probe", "value_truncated_entry_count")
    baseline_trunc = semantic_value(baseline_metric_snapshot, "final_probe", "value_truncated_entry_count")
    if target_trunc is not None and baseline_trunc is not None and target_trunc - baseline_trunc > 0.05:
        notes.append("value_truncated_entry_count increased materially in final_probe.")

    target_local_frontier = semantic_value(target_metric_snapshot, "final_probe", "local_frontier_coverage")
    baseline_local_frontier = semantic_value(baseline_metric_snapshot, "final_probe", "local_frontier_coverage")
    if (
        target_local_frontier is not None
        and baseline_local_frontier is not None
        and baseline_local_frontier - target_local_frontier > 0.01
    ):
        notes.append("local_frontier_coverage fell by more than the bootstrap warning threshold.")
    return notes


def build_recent_train_support_summary(metric_snapshot: dict[str, Any]) -> dict[str, Any]:
    existing = metric_snapshot.get("recent_train_support_summary")
    if isinstance(existing, dict) and existing.get("verdict"):
        return existing

    details: dict[str, Any] = {}
    counts = {
        "aligned": 0,
        "final_probe_stronger": 0,
        "final_probe_weaker": 0,
        "insufficient_evidence": 0,
    }
    for metric_name, tolerance in RECENT_TRAIN_SUPPORT_TOLERANCES.items():
        recent_value = metric_value(metric_snapshot, "recent_train", metric_name)
        final_value = metric_value(metric_snapshot, "final_probe", metric_name)
        if recent_value is None or final_value is None:
            counts["insufficient_evidence"] += 1
            details[metric_name] = {
                "recent_train": recent_value,
                "final_probe": final_value,
                "delta": None,
                "verdict": "insufficient_evidence",
            }
            continue
        delta = final_value - recent_value
        if abs(delta) <= tolerance:
            verdict = "aligned"
        else:
            higher_is_better = RECENT_TRAIN_SUPPORT_DIRECTIONS[metric_name]
            strengthened = delta > 0 if higher_is_better else delta < 0
            verdict = "final_probe_stronger" if strengthened else "final_probe_weaker"
        counts[verdict] += 1
        details[metric_name] = {
            "recent_train": recent_value,
            "final_probe": final_value,
            "delta": delta,
            "verdict": verdict,
        }

    if counts["insufficient_evidence"] == len(RECENT_TRAIN_SUPPORT_TOLERANCES):
        verdict = "insufficient_evidence"
    elif counts["final_probe_weaker"] >= 2:
        verdict = "diverges_from_final_probe"
    elif counts["final_probe_weaker"] == 0 and (counts["aligned"] + counts["final_probe_stronger"]) >= 4:
        verdict = "supports_final_probe"
    else:
        verdict = "mixed"

    notes: list[str] = []
    weaker_metrics = [name for name, payload in details.items() if payload["verdict"] == "final_probe_weaker"]
    stronger_metrics = [name for name, payload in details.items() if payload["verdict"] == "final_probe_stronger"]
    if verdict == "supports_final_probe":
        notes.append("recent_train broadly supports the held-out final_probe direction.")
    elif verdict == "diverges_from_final_probe":
        notes.append("recent_train is materially stronger than the held-out final_probe on several metrics.")
    elif verdict == "mixed":
        notes.append("recent_train and final_probe provide mixed support signals across tracked metrics.")
    else:
        notes.append("recent_train support is incomplete because one or more support metrics are unavailable.")
    if weaker_metrics:
        notes.append(f"Metrics where final_probe underperformed recent_train: {', '.join(sorted(weaker_metrics))}.")
    if stronger_metrics:
        notes.append(f"Metrics where final_probe outperformed recent_train: {', '.join(sorted(stronger_metrics))}.")
    return {"verdict": verdict, "details": details, "counts": counts, "notes": notes}


def build_training_dynamics_quality_summary(
    *,
    target_metric_snapshot: dict[str, Any],
    baseline_metric_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    target_summary = target_metric_snapshot.get("training_dynamics_summary", {})
    baseline_summary = (baseline_metric_snapshot or {}).get("training_dynamics_summary", {})
    target_final_window = target_summary.get("final_window_stats", {})
    baseline_final_window = baseline_summary.get("final_window_stats", {})
    target_growth = target_summary.get("growth_rates", {})
    baseline_growth = baseline_summary.get("growth_rates", {})
    target_thresholds = target_summary.get("threshold_reach_steps", {})
    baseline_thresholds = baseline_summary.get("threshold_reach_steps", {})
    target_variance = target_summary.get("late_stage_variance", {})
    baseline_variance = baseline_summary.get("late_stage_variance", {})

    final_window_summary = _compare_flat_metrics(
        target_values=target_final_window,
        baseline_values=baseline_final_window,
        metric_names=(
            "recent_mean_reward",
            "recent_mean_coverage",
            "recent_success_rate",
            "recent_mean_episode_length",
            "recent_mean_repeat_visit_ratio",
        ),
        tolerances=TRAINING_DYNAMICS_TOLERANCES,
        higher_is_better_map=TRAINING_DYNAMICS_DIRECTIONS,
    )
    growth_rate_summary = _compare_flat_metrics(
        target_values=target_growth,
        baseline_values=baseline_growth,
        metric_names=(
            "growth_rate_reward",
            "growth_rate_coverage",
            "growth_rate_success_rate",
            "growth_rate_repeat_visit_ratio",
        ),
        tolerances=TRAINING_DYNAMICS_TOLERANCES,
        higher_is_better_map=TRAINING_DYNAMICS_DIRECTIONS,
    )
    threshold_reach_summary = _compare_flat_metrics(
        target_values=target_thresholds,
        baseline_values=baseline_thresholds,
        metric_names=(
            "threshold_reach_steps_success_050",
            "threshold_reach_steps_coverage_090",
        ),
        tolerances=TRAINING_DYNAMICS_TOLERANCES,
        higher_is_better_map=TRAINING_DYNAMICS_DIRECTIONS,
    )
    late_stage_variance_summary = _compare_flat_metrics(
        target_values=target_variance,
        baseline_values=baseline_variance,
        metric_names=(
            "late_stage_variance_reward",
            "late_stage_variance_coverage",
            "late_stage_variance_success_rate",
            "late_stage_variance_repeat_visit_ratio",
        ),
        tolerances=TRAINING_DYNAMICS_TOLERANCES,
        higher_is_better_map=TRAINING_DYNAMICS_DIRECTIONS,
    )

    sub_verdicts = [
        final_window_summary["verdict"],
        growth_rate_summary["verdict"],
        threshold_reach_summary["verdict"],
        late_stage_variance_summary["verdict"],
    ]
    if all(verdict == "insufficient_evidence" for verdict in sub_verdicts):
        verdict = "insufficient_evidence"
    elif sub_verdicts.count("regression") >= 2:
        verdict = "regression"
    elif sub_verdicts.count("improvement") >= 2 and "regression" not in sub_verdicts:
        verdict = "improvement"
    else:
        verdict = "hold"

    notes: list[str] = []
    if verdict == "improvement":
        notes.append("training_dynamics improved across multiple ranking dimensions.")
    elif verdict == "regression":
        notes.append("training_dynamics regressed on multiple ranking dimensions.")
    elif verdict == "hold":
        notes.append("training_dynamics is mixed or approximately flat versus baseline.")
    else:
        notes.append("training_dynamics is unavailable or missing on one or both sides.")

    return {
        "verdict": verdict,
        "final_window_summary": final_window_summary,
        "growth_rate_summary": growth_rate_summary,
        "threshold_reach_summary": threshold_reach_summary,
        "late_stage_variance_summary": late_stage_variance_summary,
        "target": target_summary,
        "baseline": baseline_summary if baseline_summary else None,
        "notes": notes,
    }


def build_stop_window_state(
    *,
    comparability_report: dict[str, Any],
    verdicts: dict[str, str],
    manual_review_reasons: list[str],
    insufficient_evidence_flags: list[str],
    historical_baseline_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    comparability_status = str(comparability_report.get("comparability_status", "")).strip()
    history_bootstrap_only = bool((historical_baseline_summary or {}).get("insufficient_history_for_calibration"))
    basis = "bootstrap_thresholds" if history_bootstrap_only else "calibrated_history"

    if comparability_status == "not_comparable":
        recommended_action = "analyze_only"
        decision_zone = "not_comparable"
    elif comparability_status == "insufficient_evidence":
        recommended_action = "pause_for_manual_review"
        decision_zone = "insufficient_evidence"
    elif manual_review_reasons:
        recommended_action = "pause_for_manual_review"
        decision_zone = "manual_review_required"
    elif verdicts["overall_round_verdict"] == "improvement":
        recommended_action = "run_next_round"
        decision_zone = "promotion_candidate"
    elif verdicts["overall_round_verdict"] == "regression":
        recommended_action = "stop_experiment" if not history_bootstrap_only else "pause_for_manual_review"
        decision_zone = "plateau_or_regression"
    else:
        recommended_action = "pause_for_manual_review" if history_bootstrap_only else "stop_experiment"
        decision_zone = "plateau_or_regression"

    reasons: list[str] = []
    if comparability_status == "not_comparable":
        reasons.append("comparability_failed")
    if comparability_status == "insufficient_evidence":
        reasons.append("comparability_inputs_incomplete")
    if history_bootstrap_only:
        reasons.append("historical_thresholds_are_bootstrap_only")
    if verdicts["overall_round_verdict"] == "hold":
        reasons.append("plateau_or_mixed_signal")
    if verdicts["overall_round_verdict"] == "regression":
        reasons.append("net_regression_detected")
    reasons.extend(manual_review_reasons)
    reasons.extend(insufficient_evidence_flags)

    unique_reasons = collect_unique_flags(reasons)
    return {
        "window_basis": basis,
        "comparability_status": comparability_status,
        "plateau_detected": verdicts["overall_round_verdict"] == "hold",
        "hard_stop_triggered": recommended_action == "stop_experiment",
        "manual_review_required": recommended_action == "pause_for_manual_review",
        "insufficient_evidence": bool(insufficient_evidence_flags),
        "recommended_action": recommended_action,
        "decision_zone": decision_zone,
        "reasons": unique_reasons,
    }


def build_round_summary(
    *,
    round_id: str,
    experiment_mode: str,
    source_of_truth_repo: str,
    local_execution_repo_path: str | None,
    run_dir: str,
    evaluation_mode: str,
    metric_snapshot: dict[str, Any],
    benchmark_summary: dict[str, Any],
    config_snapshot: dict[str, Any],
    artifact_index: dict[str, Any],
    comparability_report: dict[str, Any],
    baseline_round_id: str | None = None,
    baseline_commit_sha: str | None = None,
    baseline_metric_snapshot: dict[str, Any] | None = None,
    baseline_benchmark_summary: dict[str, Any] | None = None,
    historical_baseline_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    primary = summarize_metric_family(
        target_metric_snapshot=metric_snapshot,
        baseline_metric_snapshot=baseline_metric_snapshot,
        block_name="final_probe",
        metric_names=PRIMARY_METRICS,
        tolerances=PRIMARY_TOLERANCES,
        higher_is_better_map={"success_rate": True, "coverage": True, "reward": True},
        value_getter=metric_value,
    )
    secondary = summarize_metric_family(
        target_metric_snapshot=metric_snapshot,
        baseline_metric_snapshot=baseline_metric_snapshot,
        block_name="final_probe",
        metric_names=SECONDARY_METRICS,
        tolerances=SECONDARY_TOLERANCES,
        higher_is_better_map={"episode_length": False, "repeat_visit_ratio": False},
        value_getter=metric_value,
    )
    stability = summarize_metric_family(
        target_metric_snapshot=metric_snapshot,
        baseline_metric_snapshot=baseline_metric_snapshot,
        block_name="final_probe",
        metric_names=STABILITY_METRICS,
        tolerances=STABILITY_TOLERANCES,
        higher_is_better_map={
            "timeout_flag": False,
            "stall_trigger_count": False,
            "zero_info_step_count": False,
            "recent_revisit_trigger_count": False,
        },
        value_getter=stability_value,
    )
    efficiency = build_efficiency_summary(
        target_benchmark_summary=benchmark_summary,
        baseline_benchmark_summary=baseline_benchmark_summary,
    )
    recent_train_support = build_recent_train_support_summary(metric_snapshot)
    consistency_summary = metric_snapshot.get("train_final_consistency_summary", recent_train_support)
    training_dynamics_summary = build_training_dynamics_quality_summary(
        target_metric_snapshot=metric_snapshot,
        baseline_metric_snapshot=baseline_metric_snapshot,
    )

    insufficient_evidence_flags = merge_insufficient_flags(
        metric_snapshot,
        benchmark_summary,
        config_snapshot,
        artifact_index,
        comparability_report,
    )
    if historical_baseline_summary and historical_baseline_summary.get("insufficient_history_for_calibration"):
        insufficient_evidence_flags = collect_unique_flags(
            insufficient_evidence_flags,
            ["historical_thresholds_bootstrap_only"],
        )

    manual_review_reasons = semantic_monitoring_notes(
        target_metric_snapshot=metric_snapshot,
        baseline_metric_snapshot=baseline_metric_snapshot,
    )
    if recent_train_support.get("verdict") == "diverges_from_final_probe":
        manual_review_reasons = collect_unique_flags(manual_review_reasons, ["recent_train_final_probe_divergence"])
    if training_dynamics_summary.get("verdict") == "regression" and primary["verdict"] == "improvement":
        manual_review_reasons = collect_unique_flags(manual_review_reasons, ["training_dynamics_regressed_despite_final_probe_gain"])
    if comparability_report.get("comparability_status") == "bootstrap_comparable":
        manual_review_reasons = collect_unique_flags(manual_review_reasons, ["comparability_only_bootstrap_confirmed"])
    if benchmark_summary.get("total_runtime_sec") is None:
        manual_review_reasons = collect_unique_flags(manual_review_reasons, ["runtime_summary_missing"])

    overall = "hold"
    if comparability_report.get("comparability_status") == "not_comparable":
        overall = "not_comparable"
    elif comparability_report.get("comparability_status") == "insufficient_evidence":
        overall = "insufficient_evidence"
    elif primary["verdict"] == "regression" or stability["verdict"] == "regression":
        overall = "regression"
    elif primary["verdict"] == "improvement" and stability["verdict"] != "regression":
        overall = "improvement"
    elif primary["verdict"] == "insufficient_evidence":
        overall = "insufficient_evidence"

    verdicts = {
        "primary_metric_verdict": primary["verdict"],
        "secondary_metric_verdict": secondary["verdict"],
        "stability_verdict": stability["verdict"],
        "efficiency_verdict": efficiency["verdict"],
        "training_dynamics_verdict": training_dynamics_summary["verdict"],
        "train_final_consistency_verdict": consistency_summary.get("verdict"),
        "overall_round_verdict": overall,
    }
    stop_window_state = build_stop_window_state(
        comparability_report=comparability_report,
        verdicts=verdicts,
        manual_review_reasons=manual_review_reasons,
        insufficient_evidence_flags=insufficient_evidence_flags,
        historical_baseline_summary=historical_baseline_summary,
    )

    notes = [
        "Formal judgement is based on final_probe of the last checkpoint under the held-out suite.",
        "recent_train and training_dynamics_summary are screening and ranking support signals only.",
        "periodic eval and best checkpoint artifacts are legacy diagnostic-only context when they are present.",
        "Current thresholds are bootstrap-only whenever historical_baseline_summary.json reports insufficient calibration history.",
    ]

    return {
        "schema_version": PROTOCOL_SCHEMA_VERSION,
        "artifact_type": "round_summary",
        "round_id": round_id,
        "generated_at": now_iso(),
        "experiment_mode": experiment_mode,
        "source_of_truth_repo": source_of_truth_repo,
        "local_execution_repo_path": local_execution_repo_path,
        "evaluation_mode": evaluation_mode,
        "run_dir": run_dir,
        "baseline_round_id": baseline_round_id,
        "baseline_commit_sha": baseline_commit_sha,
        "historical_baseline_summary_path": "historical_baseline_summary.json" if historical_baseline_summary is not None else None,
        "historical_calibration": {
            "available": historical_baseline_summary is not None,
            "insufficient_history_for_calibration": bool((historical_baseline_summary or {}).get("insufficient_history_for_calibration")),
            "run_count_total": (historical_baseline_summary or {}).get("run_count_total"),
        },
        "comparability_group": config_snapshot.get("comparability", {}).get("comparability_group"),
        "decision_zone": stop_window_state["decision_zone"],
        "stop_window_state": stop_window_state,
        "manual_review_reasons": manual_review_reasons,
        "insufficient_evidence_flags": insufficient_evidence_flags,
        "verdicts": verdicts,
        "final_probe_formal_summary": {
            "primary_metric_summary": primary,
            "secondary_metric_summary": secondary,
            "stability_summary": stability,
        },
        "primary_metric_summary": primary,
        "secondary_metric_summary": secondary,
        "stability_summary": stability,
        "efficiency_summary": efficiency,
        "recent_train_support_summary": recent_train_support,
        "train_final_consistency_summary": consistency_summary,
        "training_dynamics_summary": training_dynamics_summary,
        "comparability_status": comparability_report.get("comparability_status"),
        "notes": notes,
    }


def render_codex_report(
    *,
    round_summary: dict[str, Any],
    comparability_report: dict[str, Any],
    metric_snapshot: dict[str, Any],
    benchmark_summary: dict[str, Any],
) -> str:
    verdicts = round_summary["verdicts"]
    final_probe = metric_snapshot.get("final_probe", {})
    final_probe_metrics = final_probe.get("metrics", {})
    final_probe_reward_events = final_probe.get("reward_events", {})
    training_dynamics = round_summary.get("training_dynamics_summary", {})
    train_final_consistency = round_summary.get("train_final_consistency_summary", {})
    legacy_context = metric_snapshot.get("legacy_diagnostic_context", {})
    lines = [
        "# Codex Report",
        "",
        "## 1. Formal Round",
        f"- Round id: `{round_summary['round_id']}`",
        f"- Experiment mode: `{round_summary['experiment_mode']}`",
        f"- Source of truth repo: `{round_summary['source_of_truth_repo']}`",
        f"- Local execution repo path: `{round_summary.get('local_execution_repo_path') or 'UNSET'}`",
        f"- Target run: `{round_summary['run_dir']}`",
        f"- Baseline round id: `{round_summary.get('baseline_round_id') or 'UNSET'}`",
        f"- Baseline commit sha: `{round_summary.get('baseline_commit_sha') or 'UNSET'}`",
        f"- Comparability group: `{round_summary.get('comparability_group') or 'UNSET'}`",
        "",
        "## 2. Comparability Gate",
        f"- Comparability status: `{comparability_report.get('comparability_status', 'UNSET')}`",
        f"- Decision zone: `{round_summary['decision_zone']}`",
        f"- Stop action: `{round_summary['stop_window_state']['recommended_action']}`",
        f"- Manual review reasons: {', '.join(round_summary['manual_review_reasons']) or 'NONE'}",
        f"- Insufficient evidence flags: {', '.join(round_summary['insufficient_evidence_flags']) or 'NONE'}",
        "",
        "## 3. Formal Verdicts",
        f"- Primary verdict: `{verdicts['primary_metric_verdict']}`",
        f"- Secondary verdict: `{verdicts['secondary_metric_verdict']}`",
        f"- Stability verdict: `{verdicts['stability_verdict']}`",
        f"- Training dynamics verdict: `{verdicts['training_dynamics_verdict']}`",
        f"- Train-final consistency verdict: `{verdicts['train_final_consistency_verdict']}`",
        f"- Overall verdict: `{verdicts['overall_round_verdict']}`",
        "",
        "## 4. Final Probe (Formal Acceptance Object)",
        f"- Source: `{metric_snapshot.get('final_probe_source')}`",
        f"- Reward: `{final_probe_metrics.get('reward')}`",
        f"- Coverage: `{final_probe_metrics.get('coverage')}`",
        f"- Success rate: `{final_probe_metrics.get('success_rate')}`",
        f"- Episode length: `{final_probe_metrics.get('episode_length')}`",
        f"- Repeat visit ratio: `{final_probe_metrics.get('repeat_visit_ratio')}`",
        f"- Recent revisit trigger count: `{final_probe_reward_events.get('recent_revisit_trigger_count', final_probe_reward_events.get('recent_revisit_count'))}`",
        "",
        "## 5. Training Dynamics Summary",
        f"- Final window summary verdict: `{training_dynamics.get('final_window_summary', {}).get('verdict', 'UNSET')}`",
        f"- Growth rate summary verdict: `{training_dynamics.get('growth_rate_summary', {}).get('verdict', 'UNSET')}`",
        f"- Threshold reach summary verdict: `{training_dynamics.get('threshold_reach_summary', {}).get('verdict', 'UNSET')}`",
        f"- Late-stage variance summary verdict: `{training_dynamics.get('late_stage_variance_summary', {}).get('verdict', 'UNSET')}`",
        f"- Target training dynamics: `{training_dynamics.get('target', {})}`",
        "",
        "## 6. Train-Final Consistency",
        f"- Consistency verdict: `{train_final_consistency.get('verdict', 'UNSET')}`",
        f"- Notes: `{train_final_consistency.get('notes', [])}`",
        f"- Details: `{train_final_consistency.get('details', {})}`",
        "",
        "## 7. Optional Legacy Diagnostic Context",
        f"- periodic_eval_available: `{legacy_context.get('periodic_eval_available')}`",
        f"- last_eval_diagnostic: `{metric_snapshot.get('last_eval', {}).get('metrics', {})}`",
        f"- best_eval_diagnostic: `{metric_snapshot.get('best_eval', {}).get('metrics', {})}`",
        f"- best_checkpoint_exists: `{legacy_context.get('best_checkpoint_exists')}`",
        "",
        "## 8. Efficiency",
        f"- total_runtime_sec: `{benchmark_summary.get('total_runtime_sec')}`",
        f"- diagnostic_env_steps_to_best: `{benchmark_summary.get('diagnostic_env_steps_to_best', benchmark_summary.get('env_steps_to_best'))}`",
        "",
        "## 9. Recommendation",
        f"- Recommended next step: `{round_summary['stop_window_state']['recommended_action']}`",
        f"- Confidence / caveat: `comparability={comparability_report.get('comparability_status')}; bootstrap_thresholds={'historical_thresholds_bootstrap_only' in round_summary['insufficient_evidence_flags']}`",
    ]
    return "\n".join(lines) + "\n"


def render_formal_gpt_input(
    *,
    decision: dict[str, Any],
    round_state: dict[str, Any],
    round_summary: dict[str, Any],
    comparability_report: dict[str, Any],
    metric_snapshot: dict[str, Any],
    benchmark_summary: dict[str, Any],
    historical_baseline_summary: dict[str, Any] | None = None,
) -> str:
    verdicts = round_summary["verdicts"]
    stop_window_state = round_summary["stop_window_state"]
    training_dynamics = round_summary.get("training_dynamics_summary", {})
    consistency_summary = round_summary.get("train_final_consistency_summary", {})
    final_probe_metrics = metric_snapshot.get("final_probe", {}).get("metrics", {})
    legacy_context = metric_snapshot.get("legacy_diagnostic_context", {})
    return "\n".join(
        [
            "# GPT Input Package",
            "",
            "## 1. Current Round Basics",
            f"- Round id: `{round_summary['round_id']}`",
            f"- Experiment mode: `{round_summary['experiment_mode']}`",
            f"- Source of truth repo: `{round_summary['source_of_truth_repo']}`",
            f"- Local execution repo path: `{round_summary.get('local_execution_repo_path') or 'UNSET'}`",
            f"- Round state status: `{round_state.get('status', 'UNSET')}`",
            f"- Run directory: `{round_summary['run_dir']}`",
            f"- Target program: `{decision.get('target_program', 'UNSET')}`",
            "",
            "## 2. Comparability",
            f"- Comparability status: `{comparability_report.get('comparability_status', 'UNSET')}`",
            f"- Comparability group: `{round_summary.get('comparability_group') or 'UNSET'}`",
            f"- Baseline round id: `{round_summary.get('baseline_round_id') or 'UNSET'}`",
            f"- Baseline commit sha: `{round_summary.get('baseline_commit_sha') or 'UNSET'}`",
            f"- Checks: `{comparability_report.get('checks', {})}`",
            "",
            "## 3. Final Probe (Formal Acceptance Object)",
            f"- final_probe: `{final_probe_metrics}`",
            f"- final_probe_source: `{metric_snapshot.get('final_probe_source')}`",
            f"- formal_final_object: `{metric_snapshot.get('formal_final_object', {})}`",
            f"- formal_verdicts: `primary={verdicts['primary_metric_verdict']}, secondary={verdicts['secondary_metric_verdict']}, stability={verdicts['stability_verdict']}`",
            "",
            "## 4. Training Dynamics Summary",
            f"- training_dynamics_verdict: `{training_dynamics.get('verdict', 'UNSET')}`",
            f"- final_window_summary: `{training_dynamics.get('final_window_summary', {})}`",
            f"- growth_rate_summary: `{training_dynamics.get('growth_rate_summary', {})}`",
            f"- threshold_reach_summary: `{training_dynamics.get('threshold_reach_summary', {})}`",
            f"- late_stage_variance_summary: `{training_dynamics.get('late_stage_variance_summary', {})}`",
            f"- target_training_dynamics: `{training_dynamics.get('target', {})}`",
            "",
            "## 5. Train-Final Consistency",
            f"- recent_train_support_summary: `{round_summary.get('recent_train_support_summary', {})}`",
            f"- train_final_consistency_summary: `{consistency_summary}`",
            "",
            "## 6. Optional Legacy Diagnostic Context",
            f"- periodic_eval_available: `{legacy_context.get('periodic_eval_available')}`",
            f"- last_eval_diagnostic: `{metric_snapshot.get('last_eval', {}).get('metrics', {})}`",
            f"- best_eval_diagnostic: `{metric_snapshot.get('best_eval', {}).get('metrics', {})}`",
            f"- benchmark_summary: `runtime={benchmark_summary.get('total_runtime_sec')}, diagnostic_env_steps_to_best={benchmark_summary.get('diagnostic_env_steps_to_best', benchmark_summary.get('env_steps_to_best'))}`",
            "",
            "## 7. Stop Window",
            f"- decision_zone: `{round_summary['decision_zone']}`",
            f"- recommended_action: `{stop_window_state['recommended_action']}`",
            f"- plateau_detected: `{stop_window_state['plateau_detected']}`",
            f"- manual_review_required: `{stop_window_state['manual_review_required']}`",
            f"- reasons: {', '.join(stop_window_state['reasons']) or 'NONE'}",
            "",
            "## 8. Manual Review / Evidence Gaps",
            f"- manual_review_reasons: {', '.join(round_summary['manual_review_reasons']) or 'NONE'}",
            f"- insufficient_evidence_flags: {', '.join(round_summary['insufficient_evidence_flags']) or 'NONE'}",
            f"- historical_baseline_summary: `path={round_summary.get('historical_baseline_summary_path') or 'UNSET'}, run_count_total={(historical_baseline_summary or {}).get('run_count_total')}, insufficient_history_for_calibration={(historical_baseline_summary or {}).get('insufficient_history_for_calibration')}`",
            "",
            "## 9. What GPT Should Output",
            "- Read `docs/evaluation_charter.md` and `docs/output_contract.md` before drafting the next decision.",
            "- Any claim of improvement must remain subordinate to comparability. If comparability failed or evidence is insufficient, do not accumulate a positive formal conclusion.",
            "- Output a single `next_gpt_decision.json` payload aligned with `docs/output_contract.md` and the dual-mode protocol schema.",
        ]
    ) + "\n"


def load_formal_bundle(round_dir: Path) -> dict[str, Any]:
    metric_snapshot = read_json(round_dir / "metric_snapshot.json")
    benchmark_summary = read_json(round_dir / "benchmark_summary.json")
    config_snapshot = read_json(round_dir / "config_snapshot.json")
    artifact_index = read_json(round_dir / "artifact_index.json")
    historical_baseline_summary = maybe_read_json(round_dir / "historical_baseline_summary.json")
    comparability_report = maybe_read_json(round_dir / "comparability_report.json")
    round_summary = maybe_read_json(round_dir / "round_summary.json")
    return {
        "metric_snapshot": metric_snapshot,
        "benchmark_summary": benchmark_summary,
        "config_snapshot": config_snapshot,
        "artifact_index": artifact_index,
        "historical_baseline_summary": historical_baseline_summary,
        "comparability_report": comparability_report,
        "round_summary": round_summary,
    }


def round_is_formal(round_dir: Path) -> bool:
    decision_path = round_dir / "gpt_decision.json"
    if not decision_path.exists():
        return False
    decision = read_json(decision_path)
    return str(decision.get("experiment_mode", "")).strip() == "formal_train"
