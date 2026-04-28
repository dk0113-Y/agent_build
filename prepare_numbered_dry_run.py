#!/usr/bin/env python
"""Stage a numbered-protocol dry-run bundle without launching training."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from rrl_numbered_protocol import (
    BASELINE_ROUND_ID,
    BASELINE_ROLE,
    BASELINE_RUN_NAME,
    FORMAL_INPUT_KEYS,
    FORMAL_PROTOCOL,
    GENERATED_BY,
    METHOD_MAINLINE,
    PROTOCOL_VERSION,
    NumberedProtocolError,
    build_baseline_context,
    build_current_round_payload,
    ensure_no_checkpoint_artifacts,
    ensure_numbered_docs,
    normalize_round_id,
    now_iso,
    run_preflight,
    write_current_round,
    write_json,
)


REQUIRED_FILES = [
    ("index_manifest.json", "index_manifest"),
    ("round_summary.json", "round_summary"),
    ("artifact_digest.json", "artifact_digest"),
    ("config_diff.json", "config_diff"),
    ("comparability_report.json", "comparability_report"),
    ("gpt_decision_placeholder.json", "gpt_decision_placeholder"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare a numbered-protocol dry-run bundle in a staging directory."
    )
    parser.add_argument("--exchange-root", required=True, type=Path, help="Reference RRL_test repository root.")
    parser.add_argument("--staging-root", required=True, type=Path, help="Temporary local staging root.")
    parser.add_argument("--target-round-id", required=True, help="Target round id, for example round_0002.")
    parser.add_argument(
        "--baseline-round-id",
        default=BASELINE_ROUND_ID,
        help="Reference baseline round id. Defaults to round_0001.",
    )
    parser.add_argument(
        "--no-publish",
        action="store_true",
        default=True,
        help="Required safety flag. Real publish is not implemented in this script.",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Unsupported. This script only stages a dry-run bundle and never publishes.",
    )
    return parser.parse_args()


def build_round_summary(*, round_id: str, baseline_round_id: str) -> dict[str, Any]:
    return {
        "round_id": round_id,
        "round_type": "dry_run_no_train",
        "operating_mode": "dry_run_no_train",
        "baseline_round_id": baseline_round_id,
        "baseline_run_name": BASELINE_RUN_NAME,
        "baseline_role": BASELINE_ROLE,
        "purpose": "dry-run controller/protocol validation without training",
        "formal_protocol": FORMAL_PROTOCOL,
        "method_mainline": list(METHOD_MAINLINE),
        "formal_input_keys": list(FORMAL_INPUT_KEYS),
        "claim_boundary": [
            "protocol_review_only",
            "analysis_only",
        ],
        "evidence_condition": [
            "no formal training evidence",
            "no method-performance claim",
        ],
        "training_launched": False,
        "checkpoint_copied": False,
        "outbox_used": False,
        "next_gpt_decision_used": False,
        "decision_required_from_gpt": False,
    }


def build_artifact_digest(*, round_id: str) -> dict[str, Any]:
    return {
        "round_id": round_id,
        "source_run_dir": None,
        "dry_run": True,
        "artifacts": [],
        "missing_expected_files": [],
        "copied_files": [],
        "skipped_large_or_binary_files": [],
        "note": "training artifacts are intentionally absent in dry_run_no_train mode",
    }


def build_config_diff(
    *,
    baseline_round_id: str,
    candidate_round_id: str,
    preflight_result: Any,
) -> dict[str, Any]:
    return {
        "baseline_round_id": baseline_round_id,
        "candidate_round_id": candidate_round_id,
        "changed_fields": list(preflight_result.changed_fields),
        "field_categories": list(preflight_result.field_categories),
        "preflight_status": preflight_result.preflight_status,
        "unknown_fields_present": preflight_result.unknown_fields_present,
        "frozen_field_violations": list(preflight_result.frozen_field_violations),
        "manual_review_required": preflight_result.manual_review_required,
        "comparability_impact": "dry_run_no_train_not_formal_comparison",
    }


def build_comparability_report(*, round_id: str, preflight_result: Any) -> dict[str, Any]:
    return {
        "round_id": round_id,
        "comparability_status": "not_applicable",
        "comparability_group": preflight_result.comparability_group,
        "reason": "dry-run validates controller path and does not create formal performance evidence",
        "same_group_claim_allowed": False,
        "formal_improvement_claim_allowed": False,
        "manual_review_required": preflight_result.manual_review_required,
    }


def build_gpt_decision_placeholder(*, round_id: str) -> dict[str, Any]:
    return {
        "schema_version": "output_contract_v1",
        "round_id": round_id,
        "decision_status": "not_requested",
        "reason": "No formal GPT decision is required for dry_run_no_train protocol validation.",
        "next_decision_stage": "after dry-run bundle validation",
        "created_at": now_iso(),
    }


def build_index_manifest(
    *,
    round_id: str,
    round_dir: Path,
) -> dict[str, Any]:
    files = [
        {
            "file": name,
            "role": role,
            "required": True,
        }
        for name, role in REQUIRED_FILES
    ]
    ensure_no_checkpoint_artifacts([round_dir / item["file"] for item in files])
    return {
        "round_id": round_id,
        "round_type": "dry_run_no_train",
        "operating_mode": "dry_run_no_train",
        "generated_at": now_iso(),
        "files": files,
        "protocol_version": PROTOCOL_VERSION,
        "generated_by": GENERATED_BY,
    }


def main() -> int:
    args = parse_args()
    try:
        if args.publish:
            raise NumberedProtocolError("Real publish is not implemented for dry_run_no_train.")
        if not args.no_publish:
            raise NumberedProtocolError("--no-publish must remain enabled for dry-run staging.")

        exchange_root = args.exchange_root.resolve()
        staging_root = args.staging_root.resolve()
        round_id = normalize_round_id(args.target_round_id)
        baseline_round_id = normalize_round_id(args.baseline_round_id)

        ensure_numbered_docs(exchange_root)
        baseline_context = build_baseline_context(
            exchange_root=exchange_root,
            baseline_round_id=baseline_round_id,
        )
        preflight_result = run_preflight({}, baseline_context, "dry_run_no_train")
        round_dir = staging_root / "rounds" / round_id
        if round_dir.exists():
            raise NumberedProtocolError(f"Target staging round directory already exists: {round_dir}")
        round_dir.mkdir(parents=True, exist_ok=False)

        artifact_digest = build_artifact_digest(round_id=round_id)
        round_summary = build_round_summary(
            round_id=round_id,
            baseline_round_id=baseline_round_id,
        )
        config_diff = build_config_diff(
            baseline_round_id=baseline_round_id,
            candidate_round_id=round_id,
            preflight_result=preflight_result,
        )
        comparability_report = build_comparability_report(
            round_id=round_id,
            preflight_result=preflight_result,
        )
        placeholder = build_gpt_decision_placeholder(round_id=round_id)

        write_json(round_dir / "artifact_digest.json", artifact_digest)
        write_json(round_dir / "round_summary.json", round_summary)
        write_json(round_dir / "config_diff.json", config_diff)
        write_json(round_dir / "comparability_report.json", comparability_report)
        write_json(round_dir / "gpt_decision_placeholder.json", placeholder)
        write_json(
            round_dir / "index_manifest.json",
            build_index_manifest(round_id=round_id, round_dir=round_dir),
        )

        write_current_round(
            staging_root / "CURRENT_ROUND.json",
            build_current_round_payload(
                round_id=round_id,
                round_path=f"rounds/{round_id}",
            ),
        )

        print("status=staged")
        print(f"round_dir={round_dir}")
        print(f"current_round={staging_root / 'CURRENT_ROUND.json'}")
        print("training_launched=false")
        print("checkpoint_copied=false")
        print("outbox_created=false")
        print("next_gpt_decision_created=false")
        print("published_to_exchange=false")
        print(f"baseline_round_id={baseline_round_id}")
        print(f"preflight_status={preflight_result.preflight_status}")
        return 0
    except NumberedProtocolError as exc:
        print("status=error", file=sys.stderr)
        print(f"error={exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
