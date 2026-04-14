#!/usr/bin/env python
"""Exchange protocol helpers for publishing local rounds to the exchange repository."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


EXCHANGE_SCHEMA_VERSION = "2.0"
EXCHANGE_ANCHOR_DEFINITION = "published_bundle_commit_reachable_from_current_head"


def get_now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def stable_context_files_for_mode(experiment_mode: str) -> list[str]:
    if experiment_mode == "formal_train":
        return [
            "docs/gpt_index_guide.md",
            "docs/project_context.md",
            "docs/automation_scope.md",
            "docs/reading_order.md",
            "docs/current_mainline.md",
            "docs/evaluation_charter.md",
            "docs/stopping_policy.md",
            "docs/output_contract.md",
            "docs/formal_artifact_map.md",
            "docs/tuning_policy.md",
        ]
    return [
        "docs/project_context.md",
        "docs/automation_scope.md",
        "docs/output_contract.md",
    ]


def recommended_entry_docs_for_mode(experiment_mode: str) -> list[str]:
    if experiment_mode == "formal_train":
        return [
            "docs/gpt_index_guide.md",
            "docs/reading_order.md",
            "docs/project_context.md",
            "docs/current_mainline.md",
            "docs/evaluation_charter.md",
            "docs/stopping_policy.md",
            "docs/output_contract.md",
        ]
    return [
        "docs/project_context.md",
        "docs/automation_scope.md",
        "docs/output_contract.md",
    ]


def project_name_for_mode(experiment_mode: str) -> str:
    if experiment_mode == "formal_train":
        return "DRL-path-finding formal_train exchange"
    return "Automation rehearsal exchange"


def build_empty_current_round(*, exchange_url: str = "", branch: str = "main") -> dict[str, Any]:
    experiment_mode = "formal_train"
    return {
        "schema_version": EXCHANGE_SCHEMA_VERSION,
        "project_name": project_name_for_mode(experiment_mode),
        "exchange_repo_url": exchange_url,
        "branch": branch,
        "exchange_state": "awaiting_new_round_publish",
        "current_round_id": None,
        "current_round_manifest": None,
        "experiment_mode": experiment_mode,
        "source_of_truth_repo": "dk0113-Y/DRL-path-finding",
        "local_execution_repo_path": None,
        "evaluation_mode": "formal_artifact_review",
        "decision_zone": "insufficient_evidence",
        "stop_window_state": {
            "window_basis": "awaiting_new_round_publish",
            "comparability_status": "insufficient_evidence",
            "plateau_detected": False,
            "hard_stop_triggered": False,
            "manual_review_required": False,
            "insufficient_evidence": True,
            "recommended_action": "analyze_only",
            "decision_zone": "insufficient_evidence",
            "reasons": [
                "exchange_repo_cleared_waiting_for_new_formal_round",
            ],
        },
        "recommended_entry_docs": recommended_entry_docs_for_mode(experiment_mode),
        "stable_context_files": stable_context_files_for_mode(experiment_mode),
        "expected_output_file": "next_gpt_decision.json",
        "exchange_anchor_commit_sha": None,
        "last_exchange_commit_sha": None,
        "exchange_anchor_definition": EXCHANGE_ANCHOR_DEFINITION,
        "notes": [
            "This exchange repository is in a clean waiting state.",
            "Publish a new formal round before expecting any round bundle under rounds/.",
            "`exchange_anchor_commit_sha` records the published bundle commit, not the later CURRENT_ROUND pointer-update commit.",
            "`last_exchange_commit_sha` is a deprecated compatibility alias for the same anchor when a round is published.",
        ],
        "updated_at": get_now_iso(),
    }


def initialize_exchange_repo(exchange_dir: Path) -> None:
    (exchange_dir / "docs").mkdir(parents=True, exist_ok=True)
    (exchange_dir / "rounds").mkdir(parents=True, exist_ok=True)
    (exchange_dir / "outbox").mkdir(parents=True, exist_ok=True)
    (exchange_dir / "rounds" / ".gitkeep").touch(exist_ok=True)
    (exchange_dir / "outbox" / ".gitkeep").touch(exist_ok=True)

    placeholders = {
        "docs/project_context.md": "# Project Context\n\nPending formal context publication.\n",
        "docs/automation_scope.md": "# Automation Scope\n\nPending automation scope publication.\n",
        "docs/output_contract.md": "# Output Contract\n\nPending output contract publication.\n",
    }
    for rel_path, text in placeholders.items():
        target_path = exchange_dir / rel_path
        if not target_path.exists():
            target_path.write_text(text, encoding="utf-8")
    current_round_path = exchange_dir / "CURRENT_ROUND.json"
    if not current_round_path.exists():
        current_round_path.write_text(
            json.dumps(build_empty_current_round(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def sync_file_to_exchange(source_path: Path, target_dir: Path, target_name: str | None = None) -> Path:
    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found: {source_path}")
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / (target_name or source_path.name)
    shutil.copy2(source_path, target_path)
    return target_path


def load_round_summary(local_round_dir: Path, decision_payload: dict[str, Any], round_state: dict[str, Any]) -> dict[str, Any]:
    summary_path = local_round_dir / "round_summary.json"
    if summary_path.exists():
        return read_json(summary_path)
    return {
        "schema_version": EXCHANGE_SCHEMA_VERSION,
        "artifact_type": "round_summary",
        "round_id": round_state.get("round_id"),
        "generated_at": get_now_iso(),
        "experiment_mode": decision_payload.get("experiment_mode", "synthetic_rehearsal"),
        "source_of_truth_repo": decision_payload.get("source_of_truth_repo", ""),
        "local_execution_repo_path": decision_payload.get("local_execution_repo_path", ""),
        "evaluation_mode": decision_payload.get("evaluation_mode", "synthetic_oracle"),
        "run_dir": round_state.get("run_dir", ""),
        "baseline_round_id": decision_payload.get("baseline_round_id"),
        "baseline_commit_sha": decision_payload.get("baseline_commit_sha"),
        "comparability_group": decision_payload.get("comparability_group"),
        "decision_zone": decision_payload.get("decision_zone", "insufficient_evidence"),
        "stop_window_state": decision_payload.get("stop_window_state", {}),
        "manual_review_reasons": decision_payload.get("manual_review_reasons", []),
        "insufficient_evidence_flags": decision_payload.get("insufficient_evidence_flags", []),
        "verdicts": {
            "overall_round_verdict": "insufficient_evidence",
        },
        "notes": [
            "round_summary.json was absent locally; this is a minimal compatibility fallback."
        ],
    }


def build_web_index_message(
    *,
    exchange_url: str,
    round_id: str,
    branch: str,
    experiment_mode: str,
    manifest_path: str,
    recommended_entry_docs: list[str],
) -> str:
    if experiment_mode == "formal_train":
        entry_docs = "\n".join(f"{index}. Read `{doc}`" for index, doc in enumerate(recommended_entry_docs, start=1))
        return (
            f"# New Formal Train Round: {round_id}\n\n"
            f"A new formal_train exchange bundle is ready.\n\n"
            f"Repository: {exchange_url}\n"
            f"Branch: {branch}\n"
            f"Manifest: `{manifest_path}`\n\n"
            f"Required reading order:\n{entry_docs}\n\n"
            f"After the docs, read `CURRENT_ROUND.json`, then `{manifest_path}`, then the structured round files "
            f"(`metric_snapshot.json`, `benchmark_summary.json`, `config_snapshot.json`, `artifact_index.json`, "
            f"`historical_baseline_summary.json`, "
            f"`comparability_report.json`, `round_summary.json`).\n\n"
            f"Formal judgement rules:\n"
            f"- Treat the real training repository artifacts as the only source of truth.\n"
            f"- Do not reuse rehearsal semantics as evidence for formal improvement.\n"
            f"- Check comparability before claiming improvement, regression, plateau, or stopping.\n"
            f"- Read `CURRENT_ROUND.json.exchange_anchor_commit_sha` as the published bundle anchor commit, not as a self-referential CURRENT_ROUND HEAD sha.\n"
            f"- If evidence is insufficient or comparability failed, keep that explicit in the next decision JSON.\n\n"
            f"Return only one JSON payload wrapped between `DECISION_JSON_BEGIN` and `DECISION_JSON_END`.\n"
        )
    return (
        f"# New Automation Round: {round_id}\n\n"
        f"Repository: {exchange_url}\n"
        f"Branch: {branch}\n"
        f"Manifest: `{manifest_path}`\n\n"
        f"Read `CURRENT_ROUND.json`, then `{manifest_path}`, then `docs/output_contract.md`.\n"
        f"Return only one JSON payload wrapped between `DECISION_JSON_BEGIN` and `DECISION_JSON_END`.\n"
    )
