#!/usr/bin/env python
"""
Exchange Protocol for GitHub-based round synchronization.
Handles manifests, summaries, and directory structure for the exchange repository.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from automation_protocol import (
    GPT_INPUT_FILENAME,
    ROUND_STATE_FILENAME,
    ProtocolError,
    load_round_state_file,
    normalize_round_id,
    read_json_file,
    write_json_file,
    repo_root,
)

EXCHANGE_SCHEMA_VERSION = "1.0"

@dataclass
class RoundSummary:
    schema_version: str
    round_id: str
    status: str
    source_round_id: str
    run_dir: str
    parameter_changes: list[dict[str, Any]]
    compare_targets: list[str]
    core_questions: list[str]
    recommended_next_step: str
    confidence_or_caveat: str
    updated_at: str

@dataclass
class IndexManifest:
    schema_version: str
    round_id: str
    task_type: str
    stable_context_files: list[str]
    round_files: list[str]
    expected_output_file: str
    notes: str

@dataclass
class CurrentRound:
    schema_version: str
    project_name: str
    exchange_repo_url: str
    branch: str
    current_round_id: str
    current_round_manifest: str
    recommended_entry_docs: list[str]
    expected_output_file: str
    updated_at: str


def get_now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def extract_field_from_markdown(text: str, field_name: str) -> str:
    """Extracts the content after a specific bullet point in a markdown report."""
    pattern = rf"- {re.escape(field_name)}:\s*(.*)"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        content = match.group(1).strip()
        # If it's a multi-line field, we might need more logic, 
        # but for now we take the line or the next indented block.
        # This is a simple implementation.
        return content
    return "UNSET"


def parse_round_summary(
    round_dir: Path, 
    decision: dict[str, Any], 
    state: Any, 
    report_text: str
) -> RoundSummary:
    
    # Extract parameter changes in a flattened way for summary
    param_changes = []
    for change in decision.get("parameter_changes", []):
        param_changes.append({
            "name": change.get("name"),
            "old": change.get("old_value"),
            "new": change.get("new_value"),
            "reason": change.get("reason")
        })

    # Extract compare targets
    compare_targets = decision.get("codex_analysis_focus", {}).get("compare_targets", [])
    
    # Extract questions
    questions = decision.get("codex_analysis_focus", {}).get("questions", [])

    return RoundSummary(
        schema_version=EXCHANGE_SCHEMA_VERSION,
        round_id=state.round_id,
        status=state.status,
        source_round_id=state.source_round_id,
        run_dir=state.run_dir,
        parameter_changes=param_changes,
        compare_targets=compare_targets,
        core_questions=questions,
        recommended_next_step=extract_field_from_markdown(report_text, "Recommended next step"),
        confidence_or_caveat=extract_field_from_markdown(report_text, "Confidence / caveat"),
        updated_at=get_now_iso()
    )


def initialize_exchange_repo(exchange_dir: Path):
    """Initializes the standard directory structure and docs in the exchange repo."""
    (exchange_dir / "docs").mkdir(parents=True, exist_ok=True)
    (exchange_dir / "rounds").mkdir(parents=True, exist_ok=True)
    (exchange_dir / "outbox").mkdir(parents=True, exist_ok=True)

    # Seed documents - source them from main repo if possible
    seed_docs = {
        "docs/project_context.md": (
            "# Project Context\n\n"
            "This exchange repository (`RRL_test`) is currently used for **\"automated engineering joint-debugging / pipeline rehearsal\"**, not for GPT to focus primarily on DRL research and algorithm discussions itself.\n\n"
            "## Purpose\n\n"
            "The repository stores:\n"
            "- Control plane materials\n"
            "- Round states\n"
            "- Index entries for automation loops\n"
            "- Output contracts\n"
            "- The analysis context for the current round\n\n"
            "## Context Roles\n\n"
            "In this rehearsal:\n"
            "- `DRL_automatic` (local environment) acts as the execution repository for training runs.\n"
            "- `RRL_test` (this repository) acts as the exchange and reading repository for GPT/Codex.\n\n"
            "## Agent Focus\n\n"
            "GPT should prioritize:\n"
            "1. Ensuring the automation loop is closed.\n"
            "2. Promoting the round forward successfully.\n"
            "3. Aligning strictly with the unified protocol and output format.\n"
            "4. Outputting a correctly formed `decision_json` that can be successfully ingested by the system.\n"
            "General discussions or algorithmic deep-dives into the DRL method itself should be avoided in this rehearsal phase."
        ),
        "docs/automation_scope.md": (
            "# Automation Scope\n\n"
            "The primary recommended track for automation is currently **Exchange Mode**.\n\n"
            "## Understanding a Round Cycle\n\n"
            "A single round iteration in the mainline cycle should be understood as follows:\n\n"
            "1. Local `round` / `scheduler` / training outputs\n"
            "2. → `codex_request.md`\n"
            "3. → Codex analyzes to produce `codex_report.md`\n"
            "4. → `prepare_gpt_input.py` running\n"
            "5. → `publish_round_to_exchange.py`\n"
            "6. → `RRL_test/outbox/web_index_message_round_xxxx.md`\n"
            "7. → `exchange_web_bridge.py`\n"
            "8. → `tmp/round_xxxx_gpt_reply.md`\n"
            "9. → `tmp/next_real_decision_round_xxxx.json`\n"
            "10. → `ingest_exchange_decision.py`\n"
            "11. → New round created\n"
            "12. → `scheduler.py`\n\n"
            "## Current Rehearsal Objective\n\n"
            "The current objective is **\"single round promotion / single round closure validation\"**. It is **not** a \"fully unattended closed-loop\".\n\n"
            "- **Operationally Passing:** Execution of the training run, markdown report generation, publishing to the exchange repo, and the bridge cycle creating and ingesting the reply into a new round have been successfully tested in sequence.\n"
            "- **Pending Validation:** The continuous, unattended triggering of the full cycle remains under integration test. Do not assume the system is running completely hands-off yet."
        ),
        "docs/tuning_policy.md": repo_root() / "tuning_policy.md",
        "docs/output_contract.md": repo_root() / "templates/gpt_decision_output_contract.md"
    }

    for rel_path, source in seed_docs.items():
        target_path = exchange_dir / rel_path
        if isinstance(source, Path):
            if source.exists():
                shutil.copy2(source, target_path)
        else:
            target_path.write_text(source, encoding="utf-8")


def sync_file_to_exchange(source_path: Path, target_dir: Path, target_name: str | None = None) -> Path:
    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found: {source_path}")
    
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / (target_name or source_path.name)
    shutil.copy2(source_path, target_path)
    return target_path


def build_web_index_message(exchange_url: str, round_id: str, branch: str = "main") -> str:
    return (
        f"# New Automation Round: {round_id}\n\n"
        f"A new set of experimental results and analysis is ready for review.\n\n"
        f"**Repository Information:**\n"
        f"- Exchange Repository: {exchange_url}\n"
        f"- Branch: {branch}\n"
        f"- Target Round: {round_id}\n\n"
        f"**Instructions:**\n"
        f"1. Read `CURRENT_ROUND.json` for the high-level task and entry points.\n"
        f"2. Follow the manifest at `rounds/{round_id}/index_manifest.json` to access relevant reports and logs.\n"
        f"3. Note that these files are automation materials representing the current state of an automation rehearsal and protocol-driven decision logic.\n"
        f"4. Provide only a single JSON code block as your response, containing a valid `next_gpt_decision.json`.\n"
        f"5. **Format Requirement**: Your entire response MUST just be the JSON block wrapped between `DECISION_JSON_BEGIN` and `DECISION_JSON_END`.\n"
        f"   - Write the literal marker `DECISION_JSON_BEGIN` on its own line.\n"
        f"   - Then provide the JSON block.\n"
        f"   - Then write the literal marker `DECISION_JSON_END` on its own line.\n"
        f"   - Do not include any explanations, prose, or reasoning outside these markers. Do not add comments inside the JSON.\n"
        f"   - Inside the JSON, you can use `\"round_id\": \"round_xxxx\"`.\n\n"
        f"Refer to `docs/output_contract.md` for the full format requirements."
    )
