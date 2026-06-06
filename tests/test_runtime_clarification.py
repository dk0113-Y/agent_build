from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dk_agent.core.runtime import AgentRuntime
from dk_agent.core.types import AgentRequest, AgentResponse
from dk_agent.llm.gateway import LLMResult
from dk_agent.routing.meta_controller import MetaControllerResult
from dk_agent.routing.meta_schema import MetaDecision


class UnusedGateway:
    def chat(
        self,
        messages: list[tuple[str, str]],
        *,
        model_role: str = "pro",
    ) -> LLMResult:
        raise AssertionError("gateway should not be called by this test")


def decision(**overrides: object) -> MetaDecision:
    payload: dict[str, object] = {
        "user_goal": "Answer a question",
        "task_boundary": None,
        "need_clarification": False,
        "clarification_question": None,
        "missing_info": [],
        "need_meta_high": False,
        "meta_high_reason": None,
        "executor_role": "pro",
        "reasoning_profile": "medium",
        "autonomy_mode": "answer_only",
        "tools": [],
        "skills": ["general"],
        "verifiers": ["self_check"],
        "risk_level": "low",
        "need_human_approval": False,
        "short_reason": "test decision",
    }
    payload.update(overrides)
    return MetaDecision.model_validate(payload)


class FakeMetaController:
    def __init__(self, decisions: list[MetaDecision]) -> None:
        self.decisions = decisions
        self.calls: list[dict[str, object]] = []

    def analyze(
        self,
        *,
        user_text: str,
        selected_text: str | None = None,
        is_clarification_resume: bool = False,
    ) -> MetaControllerResult:
        self.calls.append(
            {
                "user_text": user_text,
                "selected_text": selected_text,
                "is_clarification_resume": is_clarification_resume,
            }
        )
        return MetaControllerResult(
            decision=self.decisions.pop(0),
            meta_usage={"total_tokens": 5},
            meta_model_name="fake-meta",
            meta_elapsed_seconds=0.01,
        )


class FakeDirectExecutor:
    def __init__(self) -> None:
        self.requests: list[AgentRequest] = []

    def run(self, request: AgentRequest, meta_decision: MetaDecision) -> AgentResponse:
        self.requests.append(request)
        return AgentResponse(
            reply_text="direct ok",
            route="direct-chat",
            model_role=meta_decision.executor_role,
            model_name="fake-direct",
            reasoning_profile=meta_decision.reasoning_profile,
            usage={"total_tokens": 3},
        )


class RuntimeClarificationTests(unittest.TestCase):
    def test_clear_request_routes_to_direct_chat(self) -> None:
        meta = FakeMetaController([decision()])
        executor = FakeDirectExecutor()
        runtime = AgentRuntime(UnusedGateway(), meta_controller=meta, direct_executor=executor)

        response = runtime.run(AgentRequest(user_text="Explain LangGraph briefly"))

        self.assertEqual(response.route, "meta->direct-chat")
        self.assertEqual(response.reply_text, "direct ok")
        self.assertEqual(response.model_role, "pro")
        self.assertFalse(response.pending_clarification)
        self.assertEqual(len(executor.requests), 1)

    def test_ambiguous_request_routes_to_clarify(self) -> None:
        meta = FakeMetaController(
            [
                decision(
                    need_clarification=True,
                    clarification_question="What should I optimize?",
                    missing_info=["optimization target"],
                    risk_level="medium",
                )
            ]
        )
        runtime = AgentRuntime(UnusedGateway(), meta_controller=meta, direct_executor=FakeDirectExecutor())

        response = runtime.run(AgentRequest(user_text="Optimize this project"))

        self.assertEqual(response.route, "meta->clarify")
        self.assertEqual(response.model_role, "meta")
        self.assertTrue(response.need_clarification)
        self.assertTrue(response.pending_clarification)
        self.assertIsNotNone(runtime.pending_clarification)

    def test_high_privilege_autonomy_does_not_execute(self) -> None:
        meta = FakeMetaController(
            [
                decision(
                    autonomy_mode="execute_commands",
                    need_human_approval=True,
                    risk_level="high",
                    short_reason="command execution is high privilege",
                )
            ]
        )
        executor = FakeDirectExecutor()
        runtime = AgentRuntime(UnusedGateway(), meta_controller=meta, direct_executor=executor)

        response = runtime.run(AgentRequest(user_text="Delete unused files"))

        self.assertEqual(response.route, "meta->clarify")
        self.assertTrue(response.pending_clarification)
        self.assertEqual(executor.requests, [])

    def test_pending_clarification_resume_enriches_and_clears_pending(self) -> None:
        meta = FakeMetaController(
            [
                decision(
                    need_clarification=True,
                    clarification_question="What should I optimize?",
                    missing_info=["optimization target"],
                ),
                decision(),
            ]
        )
        executor = FakeDirectExecutor()
        runtime = AgentRuntime(UnusedGateway(), meta_controller=meta, direct_executor=executor)

        first = runtime.run(AgentRequest(user_text="Optimize this project"))
        second = runtime.run(AgentRequest(user_text="Discuss architecture only; do not edit files"))

        self.assertEqual(first.route, "meta->clarify")
        self.assertEqual(second.route, "meta->direct-chat")
        self.assertIsNone(runtime.pending_clarification)
        self.assertTrue(meta.calls[1]["is_clarification_resume"])
        enriched = meta.calls[1]["user_text"]
        self.assertIn("Original user request:", enriched)
        self.assertIn("Optimize this project", enriched)
        self.assertIn("What should I optimize?", enriched)
        self.assertIn("Discuss architecture only", enriched)
        self.assertEqual(executor.requests[0].user_text, enriched)


if __name__ == "__main__":
    unittest.main()
