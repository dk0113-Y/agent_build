from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from dk_agent.llm.gateway import ModelGateway
from dk_agent.routing.meta_schema import MetaDecision


PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "meta_controller.md"


@dataclass(slots=True)
class MetaControllerResult:
    decision: MetaDecision
    meta_usage: dict[str, Any] | None
    meta_model_name: str
    meta_elapsed_seconds: float


class MetaController:
    def __init__(self, gateway: ModelGateway, prompt_path: Path = PROMPT_PATH) -> None:
        self.gateway = gateway
        self.prompt_path = prompt_path

    def analyze(
        self,
        *,
        user_text: str,
        selected_text: str | None = None,
        is_clarification_resume: bool = False,
    ) -> MetaControllerResult:
        started_at = time.monotonic()
        result = self.gateway.chat(
            self._build_messages(
                user_text=user_text,
                selected_text=selected_text,
                is_clarification_resume=is_clarification_resume,
            ),
            model_role="meta",
        )
        elapsed_seconds = time.monotonic() - started_at

        decision = self._parse_or_fallback(result.content, user_text=user_text)
        return MetaControllerResult(
            decision=decision,
            meta_usage=result.usage,
            meta_model_name=result.model_name,
            meta_elapsed_seconds=elapsed_seconds,
        )

    def _build_messages(
        self,
        *,
        user_text: str,
        selected_text: str | None,
        is_clarification_resume: bool,
    ) -> list[tuple[str, str]]:
        selected_block = selected_text if selected_text else "(none)"
        resume_flag = "true" if is_clarification_resume else "false"
        human = (
            "Analyze this user input for routing only.\n\n"
            f"is_clarification_resume: {resume_flag}\n\n"
            f"selected_text:\n{selected_block}\n\n"
            f"user_text:\n{user_text}"
        )
        return [("system", self._load_prompt()), ("human", human)]

    def _load_prompt(self) -> str:
        try:
            return self.prompt_path.read_text(encoding="utf-8")
        except OSError:
            return (
                "You are dk-agent MetaController. Return strict JSON only. "
                "Do not answer the user's original request."
            )

    def _parse_or_fallback(self, content: str, *, user_text: str) -> MetaDecision:
        try:
            payload = json.loads(self._extract_json_text(content))
            return MetaDecision.model_validate(payload)
        except (json.JSONDecodeError, TypeError, ValidationError, ValueError) as exc:
            return self._fallback_decision(user_text=user_text, reason=type(exc).__name__)

    def _extract_json_text(self, content: str) -> str:
        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        if not text.startswith("{"):
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                text = text[start : end + 1]
        return text

    def _fallback_decision(self, *, user_text: str, reason: str) -> MetaDecision:
        goal = user_text.strip() or "(empty request)"
        return MetaDecision(
            user_goal=goal,
            task_boundary=None,
            need_clarification=False,
            clarification_question=None,
            missing_info=[],
            need_meta_high=False,
            meta_high_reason=None,
            executor_role="pro",
            reasoning_profile="medium",
            autonomy_mode="answer_only",
            tools=[],
            skills=["general"],
            verifiers=["self_check"],
            risk_level="medium",
            need_human_approval=False,
            short_reason=f"meta parse failed fallback: {reason}",
        )
