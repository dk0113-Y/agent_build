from __future__ import annotations

from typing import Any, TypedDict

from dk_agent.core.session_state import PendingClarification
from dk_agent.core.types import AgentRequest, AgentResponse
from dk_agent.routing.meta_schema import MetaDecision


class AgentGraphState(TypedDict, total=False):
    request: AgentRequest
    effective_user_text: str
    selected_text: str | None
    is_clarification_resume: bool
    meta_decision: MetaDecision | dict[str, Any] | None
    meta_usage: dict[str, Any] | None
    meta_model_name: str | None
    meta_elapsed_seconds: float
    route: str | None
    response: AgentResponse | None
    pending_clarification: PendingClarification | None
    error: str | None
