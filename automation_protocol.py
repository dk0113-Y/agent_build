#!/usr/bin/env python
"""
Helpers for the local automation control-plane protocol.

This module keeps the decision-file schema, round directory helpers, and the
Markdown rendering needed by the scheduler and round-preparation tooling.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
SUPPORTED_TARGET_PROGRAM = "fake_train.py"
ALLOWED_DECISION_STATUS = {"run_next_round", "hold", "stop"}
ROUND_ID_PATTERN = re.compile(r"^round_(\d{4})$")
ROUND_STATE_FILENAME = "round_state.json"
GPT_INPUT_FILENAME = "gpt_input.md"
GPT_RESPONSE_FILENAME = "gpt_decision_response.md"
NEXT_DECISION_FILENAME = "next_gpt_decision.json"
SUCCESSFUL_ROUND_STATUSES = {"success"}


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
class ReferenceTargets:
    best_known_reference: str | None
    manual_compare_targets: list[str]


@dataclass
class GPTDecision:
    schema_version: str
    round_id: str
    decision_status: str
    target_program: str
    run_args: RunArgs
    parameter_changes: list[ParameterChange]
    codex_analysis_focus: CodexAnalysisFocus
    reference_targets: ReferenceTargets
    controller_notes: str


@dataclass
class RoundState:
    schema_version: str
    round_id: str
    status: str
    decision_file: str
    codex_request_path: str
    codex_report_path: str
    gpt_input_path: str
    run_dir: str
    training_return_code: int | None
    bridge_invoked: bool
    bridge_status: str
    source_round_id: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass
class ResolvedCompareTarget:
    label: str
    value: str
    resolved: bool


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


def is_round_xxxx(value: str) -> bool:
    return str(value).strip().lower() == "round_xxxx"


def normalize_round_id_lenient(value: str | int) -> str:
    """Allows round_xxxx as a valid ID for template/extraction purposes."""
    if is_round_xxxx(str(value)):
        return "round_xxxx"
    return normalize_round_id(value)


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


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def round_id_index(round_id: str) -> int:
    match = ROUND_ID_PATTERN.fullmatch(normalize_round_id(round_id))
    if match is None:
        raise ProtocolError(f"Invalid round_id '{round_id}'.")
    return int(match.group(1))


def round_state_path(round_dir: Path) -> Path:
    return round_dir / ROUND_STATE_FILENAME


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


def _optional_string(parent: dict[str, Any], field_name: str) -> str | None:
    value = parent.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProtocolError(f"Field '{field_name}' must be a string or null.")
    text = value.strip()
    return text or None


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
    round_id = normalize_round_id_lenient(_require_string(payload, "round_id"))
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

    reference_targets_raw = payload.get("reference_targets")
    if reference_targets_raw is None:
        reference_targets = ReferenceTargets(best_known_reference=None, manual_compare_targets=[])
    else:
        if not isinstance(reference_targets_raw, dict):
            raise ProtocolError("Field 'reference_targets' must be an object when provided.")
        manual_compare_targets = reference_targets_raw.get("manual_compare_targets", [])
        if not isinstance(manual_compare_targets, list):
            raise ProtocolError("Field 'reference_targets.manual_compare_targets' must be a list.")
        reference_targets = ReferenceTargets(
            best_known_reference=_optional_string(reference_targets_raw, "best_known_reference"),
            manual_compare_targets=[str(item).strip() for item in manual_compare_targets if str(item).strip()],
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
        reference_targets=reference_targets,
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


def render_gpt_input_placeholder(round_id: str) -> str:
    normalized_round_id = normalize_round_id(round_id)
    return (
        f"# GPT Input Package\n\n"
        f"Round: `{normalized_round_id}`\n\n"
        f"This file is a placeholder created by `prepare_round.py`.\n\n"
        f"Run `python prepare_gpt_input.py --round-id {normalized_round_id}` after `codex_report.md` "
        f"contains a real report to replace this file with the GPT input package.\n"
    )


def relative_repo_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root()).as_posix()
    except ValueError:
        return str(path.resolve())


def build_round_state(
    *,
    round_id: str,
    decision_file: Path,
    codex_request_path: Path,
    codex_report_path: Path,
    gpt_input_path: Path,
) -> RoundState:
    timestamp = now_iso()
    return RoundState(
        schema_version=SCHEMA_VERSION,
        round_id=normalize_round_id(round_id),
        status="prepared",
        decision_file=relative_repo_path(decision_file),
        codex_request_path=relative_repo_path(codex_request_path),
        codex_report_path=relative_repo_path(codex_report_path),
        gpt_input_path=relative_repo_path(gpt_input_path),
        run_dir="",
        training_return_code=None,
        bridge_invoked=False,
        bridge_status="not_invoked",
        source_round_id="",
        created_at=timestamp,
        updated_at=timestamp,
    )


def round_state_to_dict(state: RoundState) -> dict[str, Any]:
    return {
        "schema_version": state.schema_version,
        "round_id": state.round_id,
        "status": state.status,
        "decision_file": state.decision_file,
        "codex_request_path": state.codex_request_path,
        "codex_report_path": state.codex_report_path,
        "gpt_input_path": state.gpt_input_path,
        "run_dir": state.run_dir,
        "training_return_code": state.training_return_code,
        "bridge_invoked": state.bridge_invoked,
        "bridge_status": state.bridge_status,
        "source_round_id": state.source_round_id,
        "created_at": state.created_at,
        "updated_at": state.updated_at,
    }


def write_round_state_file(path: Path, state: RoundState) -> None:
    write_json_file(path, round_state_to_dict(state))


def load_round_state_file(path: Path) -> RoundState:
    payload = read_json_file(path)
    training_return_code = payload.get("training_return_code")
    if training_return_code is not None and not isinstance(training_return_code, int):
        raise ProtocolError(f"Field 'training_return_code' in {path} must be an integer or null.")
    bridge_invoked = payload.get("bridge_invoked")
    if not isinstance(bridge_invoked, bool):
        raise ProtocolError(f"Field 'bridge_invoked' in {path} must be a boolean.")
    gpt_input_path = payload.get("gpt_input_path")
    if gpt_input_path is None:
        gpt_input_path = relative_repo_path(path.parent / GPT_INPUT_FILENAME)
    elif not isinstance(gpt_input_path, str) or not gpt_input_path.strip():
        raise ProtocolError(f"Field 'gpt_input_path' in {path} must be a non-empty string.")
    return RoundState(
        schema_version=_require_string(payload, "schema_version"),
        round_id=normalize_round_id(_require_string(payload, "round_id")),
        status=_require_string(payload, "status"),
        decision_file=_require_string(payload, "decision_file"),
        codex_request_path=_require_string(payload, "codex_request_path"),
        codex_report_path=_require_string(payload, "codex_report_path"),
        gpt_input_path=gpt_input_path.strip(),
        run_dir=str(payload.get("run_dir", "")).strip(),
        training_return_code=training_return_code,
        bridge_invoked=bridge_invoked,
        bridge_status=_require_string(payload, "bridge_status"),
        source_round_id=str(payload.get("source_round_id", "")).strip(),
        created_at=_require_string(payload, "created_at"),
        updated_at=_require_string(payload, "updated_at"),
    )


def ensure_round_state_file(
    *,
    round_dir: Path,
    round_id: str,
    decision_file: Path,
    codex_request_path: Path,
    codex_report_path: Path,
    gpt_input_path: Path,
) -> Path:
    path = round_state_path(round_dir)
    if not path.exists():
        write_round_state_file(
            path,
            build_round_state(
                round_id=round_id,
                decision_file=decision_file,
                codex_request_path=codex_request_path,
                codex_report_path=codex_report_path,
                gpt_input_path=gpt_input_path,
            ),
        )
    return path


def update_round_state_file(path: Path, **changes: Any) -> RoundState:
    state = load_round_state_file(path)
    for key, value in changes.items():
        if not hasattr(state, key):
            raise ProtocolError(f"Unknown round_state field '{key}'.")
        if key in {"decision_file", "codex_request_path", "codex_report_path", "gpt_input_path", "run_dir"}:
            if value is None:
                value = ""
            elif isinstance(value, Path):
                value = relative_repo_path(value)
            else:
                value = str(value).strip()
        setattr(state, key, value)
    state.updated_at = now_iso()
    write_round_state_file(path, state)
    return state


def _safe_load_round_state(path: Path) -> RoundState | None:
    try:
        return load_round_state_file(path)
    except ProtocolError:
        return None


def list_round_states(base_dir: Path | None = None) -> list[RoundState]:
    root = rounds_root() if base_dir is None else base_dir
    if not root.exists():
        return []
    collected: list[tuple[int, RoundState]] = []
    for round_dir in root.iterdir():
        if not round_dir.is_dir():
            continue
        try:
            index = round_id_index(round_dir.name)
        except ProtocolError:
            continue
        state = _safe_load_round_state(round_state_path(round_dir))
        if state is not None:
            collected.append((index, state))
    collected.sort(key=lambda item: item[0])
    return [state for _, state in collected]


def _resolve_existing_path(text: str) -> str | None:
    candidate = Path(text)
    if not candidate.is_absolute():
        candidate = repo_root() / candidate
    if candidate.exists():
        return relative_repo_path(candidate)
    return None


def find_previous_successful_round_state(current_round_id: str) -> RoundState | None:
    current_index = round_id_index(current_round_id)
    previous_candidates: list[tuple[int, RoundState]] = []
    for state in list_round_states():
        state_index = round_id_index(state.round_id)
        if state_index >= current_index:
            continue
        if state.status not in SUCCESSFUL_ROUND_STATUSES:
            continue
        if not state.run_dir:
            continue
        previous_candidates.append((state_index, state))
    if not previous_candidates:
        return None
    previous_candidates.sort(key=lambda item: item[0])
    return previous_candidates[-1][1]


def render_compare_target_line(target: ResolvedCompareTarget) -> str:
    if target.resolved:
        return f"- {target.label}: `{target.value}`"
    return f"- {target.label}: {target.value}"


def format_parameter_changes_markdown(parameter_changes: list[ParameterChange]) -> str:
    if parameter_changes:
        lines = [
            "| Parameter | Old | New | Delta | Reason |",
            "| --- | --- | --- | --- | --- |",
        ]
        for change in parameter_changes:
            lines.append(
                f"| `{change.name}` | `{change.old_value}` | `{change.new_value}` | "
                f"`{change.delta}` | {change.reason} |"
            )
        return "\n".join(lines)
    return "No parameter changes were recorded in `gpt_decision.json`."


def codex_report_is_ready(round_id: str, report_text: str) -> tuple[bool, str]:
    stripped_report = report_text.strip()
    if not stripped_report:
        return False, "codex_report.md was empty."
    if stripped_report == render_codex_report_stub(round_id).strip():
        return False, "codex_report.md is still the untouched template stub."

    lines = report_text.splitlines()
    inline_required_fields = {
        "- Target run:",
        "1.",
        "2.",
        "3.",
    }
    block_required_fields = {
        "- Logs inspected:",
        "- Plots inspected:",
        "- Checkpoints inspected:",
        "- Reward:",
        "- Coverage:",
        "- Success rate:",
        "- Loss:",
        "- Compare target 1:",
        "- Compare target 2:",
        "- train_steps.csv:",
        "- train_episodes.csv:",
        "- eval_metrics.csv:",
        "- final_probe.csv:",
        "- reward_curve.png:",
        "- coverage_curve.png:",
        "- success_rate_curve.png:",
        "- loss_curve.png:",
        "- Recommended next step:",
        "- Confidence / caveat:",
    }

    def next_non_empty_line(index: int) -> str | None:
        for next_index in range(index + 1, len(lines)):
            candidate = lines[next_index]
            if candidate.strip():
                return candidate
        return None

    unresolved_placeholders: list[str] = []
    for index, raw_line in enumerate(lines):
        stripped_line = raw_line.strip()
        if stripped_line in inline_required_fields:
            unresolved_placeholders.append(stripped_line)
            continue
        if stripped_line in block_required_fields:
            next_line = next_non_empty_line(index)
            if next_line is None or not next_line.startswith(("  ", "\t")):
                unresolved_placeholders.append(stripped_line)
    if unresolved_placeholders:
        deduped = list(dict.fromkeys(unresolved_placeholders))
        return False, (
            "codex_report.md still contains unfilled template placeholders: "
            + ", ".join(deduped[:5])
        )
    return True, ""


def resolve_compare_targets(decision: GPTDecision, current_round_id: str) -> list[ResolvedCompareTarget]:
    resolved_targets: list[ResolvedCompareTarget] = []
    seen: set[tuple[str, str, bool]] = set()

    def append_target(label: str, value: str, resolved: bool) -> None:
        key = (label, value, resolved)
        if key in seen:
            return
        seen.add(key)
        resolved_targets.append(ResolvedCompareTarget(label=label, value=value, resolved=resolved))

    for item in decision.codex_analysis_focus.compare_targets:
        raw = str(item).strip()
        if not raw:
            continue
        if raw == "previous_round_run":
            previous_state = find_previous_successful_round_state(current_round_id)
            if previous_state is None:
                append_target(
                    "Previous successful run",
                    "UNRESOLVED (no earlier successful round_state.json with a run_dir)",
                    False,
                )
                continue
            normalized_run_dir = _resolve_existing_path(previous_state.run_dir)
            if normalized_run_dir is None:
                append_target(
                    "Previous successful run",
                    f"UNRESOLVED (recorded run_dir was not found: {previous_state.run_dir})",
                    False,
                )
                continue
            append_target("Previous successful run", normalized_run_dir, True)
            continue

        if raw == "best_known_reference":
            configured_reference = decision.reference_targets.best_known_reference
            if configured_reference is None:
                append_target(
                    "Best known reference",
                    "UNRESOLVED (not provided in gpt_decision.json)",
                    False,
                )
                continue
            normalized_reference = _resolve_existing_path(configured_reference)
            if normalized_reference is None:
                append_target(
                    "Best known reference",
                    f"UNRESOLVED (configured path was not found: {configured_reference})",
                    False,
                )
                continue
            append_target("Best known reference", normalized_reference, True)
            continue

        normalized_path = _resolve_existing_path(raw)
        append_target("Compare target", normalized_path or raw, True)

    for manual_target in decision.reference_targets.manual_compare_targets:
        normalized_path = _resolve_existing_path(manual_target)
        append_target("Manual compare target", normalized_path or manual_target, True)

    return resolved_targets


def render_gpt_input_package(
    *,
    decision: GPTDecision,
    round_state: RoundState,
    codex_request_text: str,
    codex_report_text: str,
) -> str:
    request_lines = [line.rstrip() for line in codex_request_text.splitlines()]
    required_file_lines = [
        line.strip()
        for line in request_lines
        if line.strip().startswith("- `") and ("/logs/" in line or "/plots/" in line)
    ]
    question_lines = [
        line.strip()
        for line in request_lines
        if re.match(r"^\d+\.\s", line.strip())
    ]
    compare_target_lines = [render_compare_target_line(item) for item in resolve_compare_targets(decision, decision.round_id)]
    manual_reference_lines = [
        f"- Manual compare target: `{item}`" for item in decision.reference_targets.manual_compare_targets
    ]
    if not required_file_lines:
        required_file_lines = ["- No focused files were extracted from codex_request.md."]
    if not question_lines:
        question_lines = ["- No numbered questions were extracted from codex_request.md."]
    if not manual_reference_lines:
        manual_reference_lines = ["- Manual compare target: UNSET"]
    report_body = codex_report_text.strip()
    gpt_input_path = round_state.gpt_input_path or relative_repo_path(rounds_root() / decision.round_id / GPT_INPUT_FILENAME)
    parameter_summary = format_parameter_changes_markdown(decision.parameter_changes)
    best_known_reference_text = decision.reference_targets.best_known_reference or "UNSET"

    return "\n".join(
        [
            "# GPT Input Package",
            "",
            "## 1. Round metadata",
            f"- Round id: `{round_state.round_id}`",
            f"- Round state status: `{round_state.status}`",
            f"- Run directory: `{round_state.run_dir or 'UNSET'}`",
            f"- Training return code: `{round_state.training_return_code}`",
            f"- Bridge status: `{round_state.bridge_status}`",
            "",
            "## 2. Previous decision summary",
            f"- Decision status: `{decision.decision_status}`",
            f"- Target program: `{decision.target_program}`",
            "- Parameter changes:",
            parameter_summary,
            "- Compare target requests:",
            *[f"  {line}" for line in compare_target_lines],
            "- Raw compare target tokens from decision:",
            *[f"  - `{item}`" for item in decision.codex_analysis_focus.compare_targets],
            "- Explicit reference targets:",
            f"  - Best known reference: `{best_known_reference_text}`",
            *[f"  {line}" for line in manual_reference_lines],
            "",
            "## 3. Codex request summary",
            "- Required files / focus objects:",
            *[f"  {line}" for line in required_file_lines],
            "- Core questions from codex_request.md:",
            *[f"  {line}" for line in question_lines],
            "",
            "## 4. Codex report",
            report_body,
            "",
            "## 5. What GPT should decide next",
            "- Decide whether to continue to another round or stop.",
            "- If continuing, specify which parameters should change, in what direction, and by approximately how much.",
            "- Decide whether the next round needs updated Codex analysis focus or different required logs / plots.",
            "- Decide whether compare targets should be updated, including any explicit best-known reference.",
            "",
            "## 6. Output contract",
            f"- Produce the next full `gpt_decision.json` content for a future round in this repository.",
            "- Include the next round decision_status, target_program, run_args, parameter_changes, codex_analysis_focus, reference_targets, and controller_notes.",
            "- Explicitly state the next round Codex analysis focus and compare targets.",
            f"- This GPT input package was generated from `{gpt_input_path}`.",
        ]
    )


def render_codex_request(
    decision: GPTDecision,
    run_dir: Path,
    round_dir: Path,
    resolved_compare_targets: list[ResolvedCompareTarget] | None = None,
) -> str:
    logs = [f"- `{relative_repo_path(run_dir / rel_path)}`" for rel_path in decision.codex_analysis_focus.required_logs]
    plots = [f"- `{relative_repo_path(run_dir / rel_path)}`" for rel_path in decision.codex_analysis_focus.required_plots]
    compare_targets = resolved_compare_targets or resolve_compare_targets(decision, decision.round_id)
    compares = [render_compare_target_line(item) for item in compare_targets]
    questions = [f"{index}. {question}" for index, question in enumerate(decision.codex_analysis_focus.questions, start=1)]

    parameter_summary = format_parameter_changes_markdown(decision.parameter_changes)

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


###############################################################################
# Shared Ingestion Logic
###############################################################################

def ingest_decision_payload(
    payload: dict[str, Any],
    target_round_id: str | None = None,
    source_round_id: str | None = None,
    force: bool = False,
) -> tuple[str, Path]:
    """
    Common ingestion logic for both local GPT bridge and Exchange mode.
    Returns (actual_target_id, round_dir).
    """
    # 1. Determine target round ID
    base_dir = rounds_root()
    base_dir.mkdir(parents=True, exist_ok=True)
    actual_target_id = (
        normalize_round_id(target_round_id)
        if target_round_id
        else next_round_id(base_dir)
    )
    round_dir = base_dir / actual_target_id

    # 2. Handle existing directory
    if round_dir.exists():
        if force:
            import shutil

            shutil.rmtree(round_dir)
        else:
            raise ProtocolError(
                f"Round directory already exists: {round_dir}. Use force=True to overwrite."
            )

    round_dir.mkdir(parents=True, exist_ok=False)

    # 3. Path setup
    decision_file = round_dir / "gpt_decision.json"
    codex_request_path = round_dir / "codex_request.md"
    codex_report_path = round_dir / "codex_report.md"
    gpt_input_path = round_dir / GPT_INPUT_FILENAME
    round_state_path = round_dir / ROUND_STATE_FILENAME

    # 4. Normalize and write decision
    # Replace placeholder round_id if present
    if payload.get("round_id") == "round_xxxx" or not payload.get("round_id"):
        payload["round_id"] = actual_target_id
    else:
        # We always enforce the determined target_round_id for consistency
        payload["round_id"] = actual_target_id

    write_json_file(decision_file, payload)

    # Validate schema
    try:
        load_decision_file(decision_file)
    except ProtocolError as exc:
        # If invalid, cleanup and error out
        import shutil

        shutil.rmtree(round_dir)
        raise ProtocolError(f"Input JSON failed schema validation: {exc}")

    # 5. Initialize other protocol files
    codex_request_path.write_text(
        render_codex_request_placeholder(actual_target_id), encoding="utf-8"
    )
    codex_report_path.write_text(
        render_codex_report_stub(actual_target_id), encoding="utf-8"
    )
    gpt_input_path.write_text(
        render_gpt_input_placeholder(actual_target_id), encoding="utf-8"
    )

    # 6. Initialize Metadata (State)
    ensure_round_state_file(
        round_dir=round_dir,
        round_id=actual_target_id,
        decision_file=decision_file,
        codex_request_path=codex_request_path,
        codex_report_path=codex_report_path,
        gpt_input_path=gpt_input_path,
    )

    if source_round_id:
        src_id = normalize_round_id(source_round_id)
        update_round_state_file(round_state_path, source_round_id=src_id)

    return actual_target_id, round_dir
