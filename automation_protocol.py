#!/usr/bin/env python
"""
Helpers for the local automation control-plane protocol.

This module keeps the decision-file schema, round directory helpers, and the
Markdown rendering needed by the scheduler and round-preparation tooling.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
SUPPORTED_TARGET_PROGRAM = "fake_train.py"
ALLOWED_DECISION_STATUS = {"run_next_round", "hold", "stop"}
ROUND_ID_PATTERN = re.compile(r"^round_(\d{4})$")


class ProtocolError(ValueError):
    """Raised when a protocol file is missing required fields or values."""


@dataclass
class RunArgs:
    turn_penalty: float
    revisit_penalty: float
    entry_k: int
    steps: int
    sleep_sec: float
    seed: int


@dataclass
class ParameterChange:
    name: str
    old_value: int | float | None
    new_value: int | float | None
    delta: int | float | None
    reason: str


@dataclass
class CodexAnalysisFocus:
    compare_targets: list[str]
    required_logs: list[str]
    required_plots: list[str]
    questions: list[str]
    expected_output_style: str


@dataclass
class GPTDecision:
    schema_version: str
    round_id: str
    decision_status: str
    target_program: str
    run_args: RunArgs
    parameter_changes: list[ParameterChange]
    codex_analysis_focus: CodexAnalysisFocus
    controller_notes: str


def repo_root() -> Path:
    return Path(__file__).resolve().parent


def templates_dir() -> Path:
    return repo_root() / "templates"


def rounds_root() -> Path:
    return repo_root() / "automation_rounds"


def normalize_round_id(value: str | int) -> str:
    text = str(value).strip()
    if text.isdigit():
        return f"round_{int(text):04d}"
    match = ROUND_ID_PATTERN.fullmatch(text)
    if match:
        return f"round_{int(match.group(1)):04d}"
    raise ProtocolError(
        f"Invalid round_id '{value}'. Expected forms like 'round_0001' or '1'."
    )


def next_round_id(base_dir: Path | None = None) -> str:
    root = rounds_root() if base_dir is None else base_dir
    root.mkdir(parents=True, exist_ok=True)
    max_index = 0
    for path in root.iterdir():
        if not path.is_dir():
            continue
        match = ROUND_ID_PATTERN.fullmatch(path.name)
        if match:
            max_index = max(max_index, int(match.group(1)))
    return f"round_{max_index + 1:04d}"


def read_json_file(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProtocolError(f"Decision file was not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"Invalid JSON in {path}: {exc.msg} (line {exc.lineno})") from exc
    if not isinstance(raw, dict):
        raise ProtocolError(f"Expected top-level JSON object in {path}, got {type(raw).__name__}.")
    return raw


def write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_template_json(filename: str) -> dict[str, Any]:
    return read_json_file(templates_dir() / filename)


def load_template_text(filename: str) -> str:
    return (templates_dir() / filename).read_text(encoding="utf-8")


def build_decision_template(round_id: str) -> dict[str, Any]:
    payload = load_template_json("gpt_decision.template.json")
    payload["round_id"] = normalize_round_id(round_id)
    return payload


def _require_mapping(parent: dict[str, Any], field_name: str) -> dict[str, Any]:
    value = parent.get(field_name)
    if not isinstance(value, dict):
        raise ProtocolError(f"Missing or invalid object field '{field_name}'.")
    return value


def _require_list(parent: dict[str, Any], field_name: str) -> list[Any]:
    value = parent.get(field_name)
    if not isinstance(value, list):
        raise ProtocolError(f"Missing or invalid list field '{field_name}'.")
    return value


def _require_string(parent: dict[str, Any], field_name: str) -> str:
    value = parent.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ProtocolError(f"Missing or invalid string field '{field_name}'.")
    return value.strip()


def _require_float(parent: dict[str, Any], field_name: str) -> float:
    value = parent.get(field_name)
    if not isinstance(value, (int, float)):
        raise ProtocolError(f"Missing or invalid numeric field '{field_name}'.")
    return float(value)


def _require_int(parent: dict[str, Any], field_name: str) -> int:
    value = parent.get(field_name)
    if not isinstance(value, int):
        raise ProtocolError(f"Missing or invalid integer field '{field_name}'.")
    return int(value)


def _optional_numeric(change: dict[str, Any], field_name: str) -> int | float | None:
    value = change.get(field_name)
    if value is None:
        return None
    if not isinstance(value, (int, float)):
        raise ProtocolError(f"Field 'parameter_changes.{field_name}' must be numeric or null.")
    return value


def load_decision_file(path: Path) -> GPTDecision:
    payload = read_json_file(path)
    schema_version = _require_string(payload, "schema_version")
    round_id = normalize_round_id(_require_string(payload, "round_id"))
    decision_status = _require_string(payload, "decision_status")
    if decision_status not in ALLOWED_DECISION_STATUS:
        raise ProtocolError(
            f"Invalid decision_status '{decision_status}'. "
            f"Expected one of: {sorted(ALLOWED_DECISION_STATUS)}."
        )

    target_program = _require_string(payload, "target_program")

    run_args_raw = _require_mapping(payload, "run_args")
    run_args = RunArgs(
        turn_penalty=_require_float(run_args_raw, "turn_penalty"),
        revisit_penalty=_require_float(run_args_raw, "revisit_penalty"),
        entry_k=_require_int(run_args_raw, "entry_k"),
        steps=_require_int(run_args_raw, "steps"),
        sleep_sec=_require_float(run_args_raw, "sleep_sec"),
        seed=_require_int(run_args_raw, "seed"),
    )

    parameter_changes: list[ParameterChange] = []
    for index, change in enumerate(_require_list(payload, "parameter_changes"), start=1):
        if not isinstance(change, dict):
            raise ProtocolError(f"parameter_changes[{index}] must be an object.")
        name = _require_string(change, "name")
        reason = _require_string(change, "reason")
        old_value = _optional_numeric(change, "old_value")
        new_value = _optional_numeric(change, "new_value")
        delta = _optional_numeric(change, "delta")
        if delta is None and old_value is not None and new_value is not None:
            delta = new_value - old_value
        parameter_changes.append(
            ParameterChange(
                name=name,
                old_value=old_value,
                new_value=new_value,
                delta=delta,
                reason=reason,
            )
        )

    focus_raw = _require_mapping(payload, "codex_analysis_focus")
    focus = CodexAnalysisFocus(
        compare_targets=[str(item) for item in _require_list(focus_raw, "compare_targets")],
        required_logs=[str(item) for item in _require_list(focus_raw, "required_logs")],
        required_plots=[str(item) for item in _require_list(focus_raw, "required_plots")],
        questions=[str(item) for item in _require_list(focus_raw, "questions")],
        expected_output_style=_require_string(focus_raw, "expected_output_style"),
    )

    controller_notes = _require_string(payload, "controller_notes")

    return GPTDecision(
        schema_version=schema_version,
        round_id=round_id,
        decision_status=decision_status,
        target_program=target_program,
        run_args=run_args,
        parameter_changes=parameter_changes,
        codex_analysis_focus=focus,
        controller_notes=controller_notes,
    )


def decision_to_fake_train_cli_args(decision: GPTDecision) -> list[str]:
    if decision.target_program != SUPPORTED_TARGET_PROGRAM:
        raise ProtocolError(
            f"Unsupported target_program '{decision.target_program}'. "
            f"Current scheduler only supports '{SUPPORTED_TARGET_PROGRAM}'."
        )
    args = decision.run_args
    return [
        "--turn-penalty",
        str(args.turn_penalty),
        "--revisit-penalty",
        str(args.revisit_penalty),
        "--entry-k",
        str(args.entry_k),
        "--steps",
        str(args.steps),
        "--sleep-sec",
        str(args.sleep_sec),
        "--seed",
        str(args.seed),
    ]


def render_codex_request_placeholder(round_id: str) -> str:
    normalized_round_id = normalize_round_id(round_id)
    return (
        f"# Codex Analysis Request\n\n"
        f"Round: `{normalized_round_id}`\n\n"
        f"This file is a placeholder created by `prepare_round.py`.\n\n"
        f"`scheduler.py --decision-file ...` will replace this file after a successful run "
        f"with a structured request for Codex.\n"
    )


def render_codex_report_stub(round_id: str) -> str:
    content = load_template_text("codex_report.template.md")
    return content.replace("{{ROUND_ID}}", normalize_round_id(round_id))


def relative_repo_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root()).as_posix()
    except ValueError:
        return str(path.resolve())


def render_codex_request(decision: GPTDecision, run_dir: Path, round_dir: Path) -> str:
    logs = [f"- `{relative_repo_path(run_dir / rel_path)}`" for rel_path in decision.codex_analysis_focus.required_logs]
    plots = [f"- `{relative_repo_path(run_dir / rel_path)}`" for rel_path in decision.codex_analysis_focus.required_plots]
    compares = [f"- {item}" for item in decision.codex_analysis_focus.compare_targets]
    questions = [f"{index}. {question}" for index, question in enumerate(decision.codex_analysis_focus.questions, start=1)]

    if decision.parameter_changes:
        parameter_lines = [
            "| Parameter | Old | New | Delta | Reason |",
            "| --- | --- | --- | --- | --- |",
        ]
        for change in decision.parameter_changes:
            parameter_lines.append(
                f"| `{change.name}` | `{change.old_value}` | `{change.new_value}` | "
                f"`{change.delta}` | {change.reason} |"
            )
        parameter_summary = "\n".join(parameter_lines)
    else:
        parameter_summary = "No parameter changes were recorded in `gpt_decision.json`."

    report_target = relative_repo_path(round_dir / "codex_report.md")
    return "\n".join(
        [
            "# Codex Analysis Request",
            "",
            "## 1. 任务背景",
            f"- Round: `{decision.round_id}`",
            f"- Schema version: `{decision.schema_version}`",
            f"- Decision status: `{decision.decision_status}`",
            f"- Target program: `{decision.target_program}`",
            f"- Controller notes: {decision.controller_notes}",
            "",
            "## 2. 本轮目标 run",
            f"- Run directory: `{relative_repo_path(run_dir)}`",
            f"- Logs directory: `{relative_repo_path(run_dir / 'logs')}`",
            f"- Plots directory: `{relative_repo_path(run_dir / 'plots')}`",
            f"- Checkpoints directory: `{relative_repo_path(run_dir / 'checkpoints')}`",
            "",
            "## 3. 本轮参数变更摘要",
            parameter_summary,
            "",
            "## 4. 需要重点检查的文件",
            "### Logs",
            *logs,
            "### Plots",
            *plots,
            "",
            "## 5. 需要对比的对象",
            *compares,
            "",
            "## 6. 必须回答的问题",
            *questions,
            "",
            "## 7. 输出格式要求",
            f"- Expected output style: {decision.codex_analysis_focus.expected_output_style}",
            f"- Write the final Markdown report to `{report_target}`.",
            "- 请只基于当前工作区真实文件，不要假设尚未实现的自动化能力。",
        ]
    )
