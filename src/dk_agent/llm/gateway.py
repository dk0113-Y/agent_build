from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(slots=True)
class LLMResult:
    content: str
    usage: dict[str, Any] | None
    model_name: str
    error: str | None = None


class ModelGateway(Protocol):
    def chat(
        self,
        messages: list[tuple[str, str]],
        *,
        model_role: str = "pro",
    ) -> LLMResult:
        ...
