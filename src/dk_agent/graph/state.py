from __future__ import annotations

from typing import Any, TypedDict


class AgentGraphState(TypedDict, total=False):
    request_data: dict[str, Any]
    original_user_text: str
    effective_user_text: str
    selected_text: str | None
    mode: str
    is_clarification_resume: bool
    meta_decision: dict[str, Any] | None
    meta_usage: dict[str, Any] | None
    meta_model_name: str | None
    meta_elapsed_seconds: float
    route: str | None
    response_data: dict[str, Any] | None
    pending_interrupt: bool
    error: str | None
