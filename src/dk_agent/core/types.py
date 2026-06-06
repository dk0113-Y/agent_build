from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


AgentMode = Literal["chat", "selected_text_question"]


@dataclass(slots=True)
class AgentRequest:
    user_text: str
    mode: AgentMode = "chat"
    selected_text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentResponse:
    reply_text: str
    route: str
    model_role: str
    model_name: str
    reasoning_profile: str
    tools: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    verifiers: list[str] = field(default_factory=list)
    usage: dict[str, Any] | None = None
    elapsed_seconds: float = 0.0
    error: str | None = None
