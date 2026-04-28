#!/usr/bin/env python
"""Helpers for the RRL numbered protocol dry-run path.

This module is intentionally isolated from the legacy rehearsal/formal_train
pipeline. It provides the minimum protocol surface needed to stage a numbered
`dry_run_no_train` round bundle without launching training, touching the real
exchange repo, or depending on global outbox files.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


PROTOCOL_VERSION = "numbered_protocol_v1"
GENERATED_BY = "codex_ui_bridge_demo"
NUMBERED_DOCS = [
    "docs/00_gpt_entry_guide.md",
    "docs/01_project_context.md",
    "docs/02_system_architecture.md",
    "docs/03_current_mainline.md",
    "docs/04_automation_scope.md",
    "docs/05_round_protocol.md",
    "docs/06_formal_artifact_map.md",
    "docs/07_tuning_policy.md",
    "docs/08_evaluation_charter.md",
    "docs/09_stopping_policy.md",
    "docs/10_output_contract.md",
    "docs/README.md",
]
ROUND_TYPES = {
    "baseline_registration",
    "protocol_review",
    "dry_run_no_train",
    "formal_train_result",
    "analysis_only",
    "failed_or_rejected",
}
OPERATING_MODES = {
    "protocol_review",
    "dry_run_no_train",
    "formal_train",
    "analysis_only",
    "synthetic_rehearsal",
}
ACTIONS = {
    "accept_baseline",
    "run_next_round",
    "continue_local_search",
    "branch_new_direction",
    "stop_direction",
    "reject_round",
    "pause_for_manual_review",
    "analyze_only",
}
EVALUATION_VERDICTS = {
    "analysis_only",
    "not_applicable",
    "reference_only",
    "protocol_review_only",
}
ALLOWED_TUNING_FIELDS = {
    "total_env_steps",
    "epsilon_decay_steps",
    "epsilon_end",
    "warmup_steps",
    "posthoc_candidate_selection_thresholds",
    "final_probe_candidate_count",
    "stopping_policy",
    "logging",
    "artifact_summarization",
}
FROZEN_FIELDS = {
    "state tensor schema",
    "formal input keys",
    "dynamic cumulative belief map semantics",
    "shared semantic layer semantics",
    "advantage-side state meaning",
    "value-side block / entry representation meaning",
    "value masks meaning",
    "dual-branch encoding role separation",
    "semantic dueling decision head semantics",
    "reward semantics",
    "formal_posthoc_trainselect_v1 semantics",
    "held-out final probe definition",
    "checkpoint winner policy",
    "environment distribution",
    "evaluation seed policy",
    "metric definitions",
}
MANUAL_REVIEW_FIELDS = {
    "reward coefficients",
    "reward terms",
    "reward structure",
    "network architecture",
    "state tensor schema",
    "semantic layer behavior",
    "value branch semantics",
    "advantage branch semantics",
    "dueling head semantics",
    "formal protocol",
    "final probe protocol",
    "checkpoint winner policy",
    "environment generator",
    "map distribution",
    "evaluation seed policy",
    "major runtime mode affecting numerical behavior",
    "training loop behavior changing optimization semantics",
}
RUNTIME_BASELINE_TOGGLES = {
    "amp": False,
    "inference_amp": False,
    "torch_compile": False,
    "channels_last": False,
    "tf32": True,
    "cudnn_benchmark": True,
}
BASELINE_ROUND_ID = "round_0001"
BASELINE_RUN_NAME = "value_bcchild_gated_statequery_effopt_formal_500k_decay240k_end005_20260422_210814"
BASELINE_ROLE = "engineering_speed_baseline_candidate"
FORMAL_PROTOCOL = "formal_posthoc_trainselect_v1"
FORMAL_INPUT_KEYS = [
    "advantage_canvas",
    "value_block_features",
    "value_entry_features",
    "value_block_mask",
    "value_entry_mask",
]
METHOD_MAINLINE = [
    "Dynamic Cumulative Belief Map",
    "Shared Semantic Layer",
    "Dual-State Input / Dual-Branch Encoding",
    "Semantic Dueling Decision Head",
]
CHECKPOINT_BINARY_SUFFIXES = {".pt", ".pth", ".ckpt", ".bin"}
CURRENT_ROUND_REQUIRED_FIELDS = {
    "current_round_id",
    "current_round_path",
    "current_phase",
    "status",
    "baseline_run_name",
    "next_expected_action",
    "decision_required_from_gpt",
}
ROUND_ID_PATTERN = re.compile(r"^round_(\d{4})$")
FIELD_ALIASES = {
    "total_env_steps": "total_env_steps",
    "epsilon_decay_steps": "epsilon_decay_steps",
    "epsilon_end": "epsilon_end",
    "warmup_steps": "warmup_steps",
    "posthoc_candidate_selection_thresholds": "posthoc_candidate_selection_thresholds",
    "final_probe_candidate_count": "final_probe_candidate_count",
    "stopping_policy": "stopping_policy",
    "logging": "logging",
    "artifact_summarization": "artifact_summarization",
    "reward_coefficients": "reward coefficients",
    "reward_terms": "reward terms",
    "reward_structure": "reward structure",
    "network_architecture": "network architecture",
    "state_tensor_schema": "state tensor schema",
    "semantic_layer_behavior": "semantic layer behavior",
    "value_branch_semantics": "value branch semantics",
    "advantage_branch_semantics": "advantage branch semantics",
    "dueling_head_semantics": "dueling head semantics",
    "formal_protocol": "formal protocol",
    "final_probe_protocol": "final probe protocol",
    "checkpoint_winner_policy": "checkpoint winner policy",
    "environment_generator": "environment generator",
    "map_distribution": "map distribution",
    "evaluation_seed_policy": "evaluation seed policy",
    "major_runtime_mode_affecting_numerical_behavior": "major runtime mode affecting numerical behavior",
    "training_loop_behavior_changing_optimization_semantics": "training loop behavior changing optimization semantics",
    "formal_input_keys": "formal input keys",
    "dynamic_cumulative_belief_map_semantics": "dynamic cumulative belief map semantics",
    "shared_semantic_layer_semantics": "shared semantic layer semantics",
    "advantage_side_state_meaning": "advantage-side state meaning",
    "value_side_block_entry_representation_meaning": "value-side block / entry representation meaning",
    "value_masks_meaning": "value masks meaning",
    "dual_branch_encoding_role_separation": "dual-branch encoding role separation",
    "semantic_dueling_decision_head_semantics": "semantic dueling decision head semantics",
    "reward_semantics": "reward semantics",
    "formal_posthoc_trainselect_v1_semantics": "formal_posthoc_trainselect_v1 semantics",
    "held_out_final_probe_definition": "held-out final probe definition",
    "environment_distribution": "environment distribution",
    "metric_definitions": "metric definitions",
}


class NumberedProtocolError(ValueError):
    """Raised when the numbered protocol staging flow is invalid."""


@dataclass
class PreflightResult:
    mode: str
    preflight_status: str
    changed_fields: list[str]
    field_categories: list[dict[str, str]]
    unknown_fields_present: bool
    frozen_field_violations: list[str]
    manual_review_required: bool
    comparability_group: str | None
    runtime_toggle_policy: dict[str, Any]
    checkpoint_binary_exclusion: bool
    no_global_outbox: bool
    blocked_reasons: list[str]


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise NumberedProtocolError(f"Missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise NumberedProtocolError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise NumberedProtocolError(f"Expected JSON object in {path}.")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_numbered_docs(exchange_root: Path) -> None:
    missing = [rel for rel in NUMBERED_DOCS if not (exchange_root / rel).exists()]
    if missing:
        raise NumberedProtocolError(
            "Exchange root is missing numbered protocol docs: " + ", ".join(missing)
        )


def normalize_field_name(name: str) -> str:
    key = str(name).strip()
    if not key:
        return ""
    return FIELD_ALIASES.get(key, key.replace("_", " "))


def normalize_round_id(value: str) -> str:
    text = str(value).strip()
    if ROUND_ID_PATTERN.fullmatch(text):
        return text
    raise NumberedProtocolError(f"Invalid round id '{value}'. Expected round_0001 style.")


def build_baseline_context(*, exchange_root: Path, baseline_round_id: str) -> dict[str, Any]:
    current_round_path = exchange_root / "CURRENT_ROUND.json"
    payload = read_json(current_round_path)
    for field in CURRENT_ROUND_REQUIRED_FIELDS:
        if field not in payload:
            raise NumberedProtocolError(
                f"CURRENT_ROUND.json is missing required field '{field}'."
            )
    baseline_round_dir = exchange_root / "rounds" / baseline_round_id
    if not baseline_round_dir.exists():
        raise NumberedProtocolError(f"Baseline round directory not found: {baseline_round_dir}")
    return {
        "exchange_root": str(exchange_root.resolve()),
        "current_round": payload,
        "baseline_round_id": baseline_round_id,
        "baseline_run_name": payload.get("baseline_run_name") or BASELINE_RUN_NAME,
        "baseline_round_dir": str(baseline_round_dir.resolve()),
        "formal_protocol": FORMAL_PROTOCOL,
        "method_mainline": list(METHOD_MAINLINE),
        "formal_input_keys": list(FORMAL_INPUT_KEYS),
        "runtime_baseline_toggles": dict(RUNTIME_BASELINE_TOGGLES),
    }


def _candidate_changes(candidate_config: dict[str, Any]) -> dict[str, Any]:
    changes = candidate_config.get("changes", {})
    if changes is None:
        return {}
    if not isinstance(changes, dict):
        raise NumberedProtocolError("candidate_config.changes must be an object when provided.")
    return changes


def _candidate_runtime_toggles(candidate_config: dict[str, Any]) -> dict[str, Any]:
    toggles = candidate_config.get("runtime_toggles", {})
    if toggles is None:
        return {}
    if not isinstance(toggles, dict):
        raise NumberedProtocolError(
            "candidate_config.runtime_toggles must be an object when provided."
        )
    return toggles


def run_preflight(
    candidate_config: dict[str, Any],
    baseline_context: dict[str, Any],
    mode: str,
) -> PreflightResult:
    if mode not in OPERATING_MODES:
        raise NumberedProtocolError(f"Unsupported operating mode: {mode}")

    changes = _candidate_changes(candidate_config)
    runtime_toggles = _candidate_runtime_toggles(candidate_config)
    changed_fields: list[str] = []
    field_categories: list[dict[str, str]] = []
    frozen_field_violations: list[str] = []
    blocked_reasons: list[str] = []
    unknown_fields_present = False
    manual_review_required = False

    for raw_name in changes:
        normalized = normalize_field_name(raw_name)
        changed_fields.append(normalized)
        category = "unknown"
        if normalized in ALLOWED_TUNING_FIELDS:
            category = "allowed_tuning"
        elif normalized in FROZEN_FIELDS:
            category = "frozen"
            frozen_field_violations.append(normalized)
        elif normalized in MANUAL_REVIEW_FIELDS:
            category = "manual_review"
            manual_review_required = True
        else:
            unknown_fields_present = True
        field_categories.append({"field": normalized, "category": category})

    runtime_policy = {
        "baseline_toggles": dict(baseline_context.get("runtime_baseline_toggles", {})),
        "candidate_toggles": runtime_toggles,
        "matches_runtime_baseline": True,
    }
    for key, baseline_value in runtime_policy["baseline_toggles"].items():
        if key not in runtime_toggles:
            continue
        if runtime_toggles[key] != baseline_value:
            runtime_policy["matches_runtime_baseline"] = False
            manual_review_required = True
            field_categories.append(
                {
                    "field": f"runtime_toggles.{key}",
                    "category": "manual_review",
                }
            )

    if unknown_fields_present:
        blocked_reasons.append("unknown_fields_fail_closed")
    if frozen_field_violations:
        blocked_reasons.append("frozen_field_violation_fail_closed")
    if not runtime_policy["matches_runtime_baseline"]:
        blocked_reasons.append("runtime_toggle_manual_review_required")

    if unknown_fields_present or frozen_field_violations:
        preflight_status = "failed_closed"
    elif manual_review_required:
        preflight_status = "manual_review_required"
    else:
        preflight_status = "passed"

    if mode == "formal_train" and preflight_status != "passed":
        blocked_reasons.append("formal_train_blocked_until_preflight_passes")

    comparability_group = "dry_run_no_train" if mode == "dry_run_no_train" else None
    return PreflightResult(
        mode=mode,
        preflight_status=preflight_status,
        changed_fields=changed_fields,
        field_categories=field_categories,
        unknown_fields_present=unknown_fields_present,
        frozen_field_violations=frozen_field_violations,
        manual_review_required=manual_review_required,
        comparability_group=comparability_group,
        runtime_toggle_policy=runtime_policy,
        checkpoint_binary_exclusion=True,
        no_global_outbox=True,
        blocked_reasons=blocked_reasons,
    )


def ensure_no_checkpoint_artifacts(paths: list[Path]) -> None:
    banned = [path.name for path in paths if path.suffix.lower() in CHECKPOINT_BINARY_SUFFIXES]
    if banned:
        raise NumberedProtocolError(
            "Checkpoint binaries must not be emitted in numbered dry-run bundles: "
            + ", ".join(sorted(banned))
        )


def build_current_round_payload(*, round_id: str, round_path: str) -> dict[str, Any]:
    return {
        "current_round_id": round_id,
        "current_round_path": round_path,
        "current_phase": "bundle_generation",
        "status": "dry_run_bundle_generated",
        "baseline_run_name": BASELINE_RUN_NAME,
        "next_expected_action": "validate_dry_run_bundle",
        "decision_required_from_gpt": False,
    }


def load_current_round(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    missing = [field for field in CURRENT_ROUND_REQUIRED_FIELDS if field not in payload]
    if missing:
        raise NumberedProtocolError(
            "CURRENT_ROUND payload missing required fields: " + ", ".join(sorted(missing))
        )
    return payload


def write_current_round(path: Path, payload: dict[str, Any]) -> None:
    missing = [field for field in CURRENT_ROUND_REQUIRED_FIELDS if field not in payload]
    if missing:
        raise NumberedProtocolError(
            "Cannot write CURRENT_ROUND payload missing required fields: "
            + ", ".join(sorted(missing))
        )
    write_json(path, payload)
