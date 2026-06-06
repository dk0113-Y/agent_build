from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dk_agent.llm.gateway import LLMResult
from dk_agent.routing.meta_controller import MetaController


class FakeGateway:
    def __init__(self, content: str) -> None:
        self.content = content
        self.messages: list[tuple[str, str]] | None = None
        self.model_role: str | None = None

    def chat(
        self,
        messages: list[tuple[str, str]],
        *,
        model_role: str = "pro",
    ) -> LLMResult:
        self.messages = messages
        self.model_role = model_role
        return LLMResult(
            content=self.content,
            usage={"total_tokens": 9},
            model_name="fake-meta",
        )


def meta_json(**overrides: object) -> str:
    payload: dict[str, object] = {
        "user_goal": "Explain LangGraph",
        "task_boundary": None,
        "need_clarification": False,
        "clarification_question": None,
        "missing_info": [],
        "need_meta_high": False,
        "meta_high_reason": None,
        "executor_role": "fast",
        "reasoning_profile": "low",
        "autonomy_mode": "answer_only",
        "tools": [],
        "skills": ["general"],
        "verifiers": ["self_check"],
        "risk_level": "low",
        "need_human_approval": False,
        "short_reason": "clear low-risk question",
    }
    payload.update(overrides)
    return json.dumps(payload)


class MetaControllerTests(unittest.TestCase):
    def test_parses_gateway_json(self) -> None:
        gateway = FakeGateway(meta_json())
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            handle.write("Return JSON only.")
            prompt_path = Path(handle.name)

        controller = MetaController(gateway, prompt_path=prompt_path)
        result = controller.analyze(user_text="What is LangGraph?")

        self.assertEqual(gateway.model_role, "meta")
        self.assertEqual(result.decision.executor_role, "fast")
        self.assertEqual(result.decision.reasoning_profile, "low")
        self.assertEqual(result.meta_usage, {"total_tokens": 9})

    def test_non_json_falls_back_without_raising(self) -> None:
        controller = MetaController(FakeGateway("not json"))

        result = controller.analyze(user_text="hello")

        self.assertFalse(result.decision.need_clarification)
        self.assertEqual(result.decision.executor_role, "pro")
        self.assertEqual(result.decision.reasoning_profile, "medium")
        self.assertIn("meta parse failed fallback", result.decision.short_reason)


if __name__ == "__main__":
    unittest.main()
