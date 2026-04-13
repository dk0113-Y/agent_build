#!/usr/bin/env python
"""Structured summary helpers for formal_train exchange rounds."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from comparability import PRIMARY_METRICS, SECONDARY_METRICS, STABILITY_METRICS, is_formally_comparable


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
    "recent_revisit_count": 15.0,
}
EFFICIENCY_TOLERANCES = {
    "env_steps_to_best": 20_000.0,
    "total_runtime_sec": 600.0,
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
    return float(value) if isinstance(value, (int, float)) else None


def semantic_value(metric_snapshot: dict[str, Any], block_name: str, metric_name: str) -> float | None:
    block = _source_block(metric_snapshot, block_name)
    semantic = block.get("semantic_monitoring", {})
    if not isinstance(semantic, dict):
        return None
    value = semantic.get(metric_name)
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
            "delta": (
                target - baseline
                if target is not None and baseline is not None
                else None
            ),
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


def build_efficiency_summary(
    *,
    target_benchmark_summary: dict[str, Any],
    baseline_benchmark_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    details: dict[str, Any] = {}
    counts = {"improved": 0, "regressed": 0, "hold": 0, "insufficient_evidence": 0}
    for metric_name, tolerance in EFFICIENCY_TOLERANCES.items():
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
            "delta": (
                target_value - baseline_value
                if target_value is not None and baseline_value is not None
                else None
            ),
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
    if (
        target_cap is not None
        and baseline_cap is not None
        and target_cap - baseline_cap > 0.03
    ):
        notes.append("value_entry_cap_hit_flag increased materially in final_probe.")

    target_trunc = semantic_value(target_metric_snapshot, "final_probe", "value_truncated_entry_count")
    baseline_trunc = semantic_value(baseline_metric_snapshot, "final_probe", "value_truncated_entry_count")
    if (
        target_trunc is not None
        and baseline_trunc is not None
        and target_trunc - baseline_trunc > 0.05
    ):
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
        higher_is_better_map={
            "success_rate": True,
            "coverage": True,
            "reward": True,
        },
        value_getter=metric_value,
    )
    secondary = summarize_metric_family(
        target_metric_snapshot=metric_snapshot,
        baseline_metric_snapshot=baseline_metric_snapshot,
        block_name="final_probe",
        metric_names=SECONDARY_METRICS,
        tolerances=SECONDARY_TOLERANCES,
        higher_is_better_map={
            "episode_length": False,
            "repeat_visit_ratio": False,
        },
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
            "recent_revisit_count": False,
        },
        value_getter=stability_value,
    )
    efficiency = build_efficiency_summary(
        target_benchmark_summary=benchmark_summary,
        baseline_benchmark_summary=baseline_benchmark_summary,
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
    if comparability_report.get("comparability_status") == "bootstrap_comparable":
        manual_review_reasons = collect_unique_flags(
            manual_review_reasons,
            ["comparability_only_bootstrap_confirmed"],
        )
    if benchmark_summary.get("total_runtime_sec") is None:
        manual_review_reasons = collect_unique_flags(
            manual_review_reasons,
            ["runtime_summary_missing"],
        )

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
        "Formal round verdicts are gated by comparability before any improvement claim is considered valid.",
        "Primary judgement combines best_eval, last_eval, and final_probe with emphasis on final_probe stability and success behavior.",
        "Current thresholds are bootstrap-only whenever historical_baseline_summary.json reports insufficient calibration history.",
    ]

    return {
        "schema_version": PROTOCOL_SCHEMA_VERSION,
        "artifact_type": "round_summary",
        "round_id": round_id,
        "generated_at": now_iso(),
        "experiment_mode": experiment_mode,
        "source_of_truth_repo": source_of_truth_repo,
        "evaluation_mode": evaluation_mode,
        "run_dir": run_dir,
        "baseline_round_id": baseline_round_id,
        "baseline_commit_sha": baseline_commit_sha,
        "comparability_group": config_snapshot.get("comparability", {}).get("comparability_group"),
        "decision_zone": stop_window_state["decision_zone"],
        "stop_window_state": stop_window_state,
        "manual_review_reasons": manual_review_reasons,
        "insufficient_evidence_flags": insufficient_evidence_flags,
        "verdicts": verdicts,
        "primary_metric_summary": primary,
        "secondary_metric_summary": secondary,
        "stability_summary": stability,
        "efficiency_summary": efficiency,
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
    lines = [
        "# Codex Report",
        "",
        "## 1. Formal Round",
        f"- Round id: `{round_summary['round_id']}`",
        f"- Experiment mode: `{round_summary['experiment_mode']}`",
        f"- Source of truth repo: `{round_summary['source_of_truth_repo']}`",
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
        "## 3. Verdicts",
        f"- Primary verdict: `{verdicts['primary_metric_verdict']}`",
        f"- Secondary verdict: `{verdicts['secondary_metric_verdict']}`",
        f"- Stability verdict: `{verdicts['stability_verdict']}`",
        f"- Efficiency verdict: `{verdicts['efficiency_verdict']}`",
        f"- Overall verdict: `{verdicts['overall_round_verdict']}`",
        "",
        "## 4. Final Probe",
        f"- Reward: `{final_probe_metrics.get('reward')}`",
        f"- Coverage: `{final_probe_metrics.get('coverage')}`",
        f"- Success rate: `{final_probe_metrics.get('success_rate')}`",
        f"- Episode length: `{final_probe_metrics.get('episode_length')}`",
        f"- Repeat visit ratio: `{final_probe_metrics.get('repeat_visit_ratio')}`",
        "",
        "## 5. Stability / Monitoring",
        f"- Timeout flag: `{final_probe_reward_events.get('timeout_flag')}`",
        f"- Stall trigger count: `{final_probe_reward_events.get('stall_trigger_count')}`",
        f"- Zero info step count: `{final_probe_reward_events.get('zero_info_step_count')}`",
        f"- Recent revisit count: `{final_probe_reward_events.get('recent_revisit_count')}`",
        "",
        "## 6. Efficiency",
        f"- total_runtime_sec: `{benchmark_summary.get('total_runtime_sec')}`",
        f"- env_steps_to_best: `{benchmark_summary.get('env_steps_to_best')}`",
        "",
        "## 7. Recommendation",
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
) -> str:
    verdicts = round_summary["verdicts"]
    stop_window_state = round_summary["stop_window_state"]
    final_probe_metrics = metric_snapshot.get("final_probe", {}).get("metrics", {})
    best_eval_metrics = metric_snapshot.get("best_eval", {}).get("metrics", {})
    last_eval_metrics = metric_snapshot.get("last_eval", {}).get("metrics", {})
    return "\n".join(
        [
            "# GPT Input Package",
            "",
            "## 1. Current Round Basics",
            f"- Round id: `{round_summary['round_id']}`",
            f"- Experiment mode: `{round_summary['experiment_mode']}`",
            f"- Source of truth repo: `{round_summary['source_of_truth_repo']}`",
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
            "## 3. Metric Verdict Layer",
            f"- Primary verdict: `{verdicts['primary_metric_verdict']}`",
            f"- Secondary verdict: `{verdicts['secondary_metric_verdict']}`",
            f"- Stability verdict: `{verdicts['stability_verdict']}`",
            f"- Efficiency verdict: `{verdicts['efficiency_verdict']}`",
            f"- Overall verdict: `{verdicts['overall_round_verdict']}`",
            "",
            "## 4. Best Eval / Last Eval / Final Probe",
            f"- best_eval: `{best_eval_metrics}`",
            f"- last_eval: `{last_eval_metrics}`",
            f"- final_probe: `{final_probe_metrics}`",
            f"- benchmark_summary: `runtime={benchmark_summary.get('total_runtime_sec')}, env_steps_to_best={benchmark_summary.get('env_steps_to_best')}`",
            "",
            "## 5. Stop Window",
            f"- decision_zone: `{round_summary['decision_zone']}`",
            f"- recommended_action: `{stop_window_state['recommended_action']}`",
            f"- plateau_detected: `{stop_window_state['plateau_detected']}`",
            f"- manual_review_required: `{stop_window_state['manual_review_required']}`",
            f"- reasons: {', '.join(stop_window_state['reasons']) or 'NONE'}",
            "",
            "## 6. Manual Review / Evidence Gaps",
            f"- manual_review_reasons: {', '.join(round_summary['manual_review_reasons']) or 'NONE'}",
            f"- insufficient_evidence_flags: {', '.join(round_summary['insufficient_evidence_flags']) or 'NONE'}",
            "",
            "## 7. What GPT Should Output",
            "- Read `docs/reading_order.md`, `docs/current_mainline.md`, `docs/evaluation_charter.md`, and `docs/output_contract.md` before drafting the next decision.",
            "- Any claim of improvement must remain subordinate to comparability. If comparability failed or evidence is insufficient, do not accumulate a positive formal conclusion.",
            "- Output a single `next_gpt_decision.json` payload aligned with `docs/output_contract.md` and the dual-mode protocol schema.",
        ]
    ) + "\n"


def load_formal_bundle(round_dir: Path) -> dict[str, Any]:
    metric_snapshot = read_json(round_dir / "metric_snapshot.json")
    benchmark_summary = read_json(round_dir / "benchmark_summary.json")
    config_snapshot = read_json(round_dir / "config_snapshot.json")
    artifact_index = read_json(round_dir / "artifact_index.json")
    comparability_report = maybe_read_json(round_dir / "comparability_report.json")
    round_summary = maybe_read_json(round_dir / "round_summary.json")
    return {
        "metric_snapshot": metric_snapshot,
        "benchmark_summary": benchmark_summary,
        "config_snapshot": config_snapshot,
        "artifact_index": artifact_index,
        "comparability_report": comparability_report,
        "round_summary": round_summary,
    }


def round_is_formal(round_dir: Path) -> bool:
    decision_path = round_dir / "gpt_decision.json"
    if not decision_path.exists():
        return False
    decision = read_json(decision_path)
    return str(decision.get("experiment_mode", "")).strip() == "formal_train"
