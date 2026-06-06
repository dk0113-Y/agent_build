from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from dk_agent.graph.state import AgentGraphState


HIGH_PRIVILEGE_AUTONOMY_MODES = {
    "read_files",
    "edit_files",
    "execute_commands",
    "external_delegate",
}


def decision_value(meta_decision: object, field: str, default: Any = None) -> Any:
    if isinstance(meta_decision, Mapping):
        return meta_decision.get(field, default)
    return getattr(meta_decision, field, default)


def should_stop_at_clarification_gate(meta_decision: object) -> bool:
    return bool(
        decision_value(meta_decision, "need_clarification", False)
        or decision_value(meta_decision, "need_human_approval", False)
        or decision_value(meta_decision, "autonomy_mode") in HIGH_PRIVILEGE_AUTONOMY_MODES
    )


def route_after_meta(state: AgentGraphState) -> Literal["clarify", "execute"]:
    if should_stop_at_clarification_gate(state.get("meta_decision")):
        return "clarify"
    return "execute"


def meta_decision_to_dict(meta_decision: object) -> dict[str, Any]:
    if isinstance(meta_decision, Mapping):
        return dict(meta_decision)
    if hasattr(meta_decision, "model_dump"):
        return meta_decision.model_dump()
    if hasattr(meta_decision, "to_metadata"):
        return dict(meta_decision.to_metadata())
    return {}
