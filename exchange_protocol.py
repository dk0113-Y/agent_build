#!/usr/bin/env python
"""Exchange protocol helpers for publishing local rounds to the exchange repository."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


EXCHANGE_SCHEMA_VERSION = "2.0"


def get_now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def stable_context_files_for_mode(experiment_mode: str) -> list[str]:
    if experiment_mode == "formal_train":
        return [
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


def initialize_exchange_repo(exchange_dir: Path) -> None:
    (exchange_dir / "docs").mkdir(parents=True, exist_ok=True)
    (exchange_dir / "rounds").mkdir(parents=True, exist_ok=True)
    (exchange_dir / "outbox").mkdir(parents=True, exist_ok=True)

    placeholders = {
        "docs/project_context.md": "# Project Context\n\nPending formal context publication.\n",
        "docs/automation_scope.md": "# Automation Scope\n\nPending automation scope publication.\n",
        "docs/output_contract.md": "# Output Contract\n\nPending output contract publication.\n",
    }
    for rel_path, text in placeholders.items():
        target_path = exchange_dir / rel_path
        if not target_path.exists():
            target_path.write_text(text, encoding="utf-8")


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
            f"`comparability_report.json`, `round_summary.json`).\n\n"
            f"Formal judgement rules:\n"
            f"- Treat the real training repository artifacts as the only source of truth.\n"
            f"- Do not reuse rehearsal semantics as evidence for formal improvement.\n"
            f"- Check comparability before claiming improvement, regression, plateau, or stopping.\n"
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
