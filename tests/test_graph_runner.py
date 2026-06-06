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
from dk_agent.graph.runner import AgentGraphRunner
from dk_agent.llm.gateway import LLMResult
from dk_agent.routing.meta_controller import MetaControllerResult
from dk_agent.routing.meta_schema import MetaDecision


def decision(**overrides: object) -> MetaDecision:
    payload: dict[str, object] = {
        "user_goal": "Answer",
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
        "short_reason": "test",
    }
    payload.update(overrides)
    return MetaDecision.model_validate(payload)


class UnusedGateway:
    def chat(
        self,
        messages: list[tuple[str, str]],
        *,
        model_role: str = "pro",
    ) -> LLMResult:
        raise AssertionError("gateway should not be called")


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


class GraphRunnerTests(unittest.TestCase):
    def test_pending_clarification_resume_reenters_graph_and_clears_pending(self) -> None:
        meta = FakeMetaController(
            [
                decision(
                    need_clarification=True,
                    clarification_question="What should I optimize?",
                    missing_info=["scope"],
                ),
                decision(),
            ]
        )
        executor = FakeDirectExecutor()
        runner = AgentGraphRunner(meta_controller=meta, direct_executor=executor)

        first = runner.run(AgentRequest(user_text="Optimize this"))
        second = runner.run(AgentRequest(user_text="Discuss architecture only"))

        self.assertEqual(first.route, "meta->clarify")
        self.assertEqual(second.route, "meta->direct-chat")
        self.assertIsNone(runner.pending_clarification)
        self.assertTrue(meta.calls[1]["is_clarification_resume"])
        enriched = meta.calls[1]["user_text"]
        self.assertIn("Original user request:", enriched)
        self.assertIn("Optimize this", enriched)
        self.assertIn("What should I optimize?", enriched)
        self.assertIn("Discuss architecture only", enriched)
        self.assertEqual(executor.requests[0].user_text, enriched)

    def test_agent_runtime_run_still_returns_agent_response(self) -> None:
        meta = FakeMetaController([decision()])
        executor = FakeDirectExecutor()
        runtime = AgentRuntime(UnusedGateway(), meta_controller=meta, direct_executor=executor)

        response = runtime.run(AgentRequest(user_text="Explain LangGraph"))

        self.assertIsInstance(response, AgentResponse)
        self.assertEqual(response.route, "meta->direct-chat")
        self.assertIsNone(runtime.pending_clarification)


if __name__ == "__main__":
    unittest.main()
