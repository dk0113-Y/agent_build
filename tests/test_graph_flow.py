from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dk_agent.core.types import AgentRequest, AgentResponse
from dk_agent.graph.graph import build_agent_graph
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


class FakeMetaController:
    def __init__(self, meta_decision: MetaDecision) -> None:
        self.meta_decision = meta_decision

    def analyze(
        self,
        *,
        user_text: str,
        selected_text: str | None = None,
        is_clarification_resume: bool = False,
    ) -> MetaControllerResult:
        return MetaControllerResult(
            decision=self.meta_decision,
            meta_usage={"total_tokens": 7},
            meta_model_name="fake-meta",
            meta_elapsed_seconds=0.01,
        )


class FakeDirectExecutor:
    def run(self, request: AgentRequest, meta_decision: MetaDecision) -> AgentResponse:
        return AgentResponse(
            reply_text=f"executed: {request.user_text}",
            route="direct-chat",
            model_role=meta_decision.executor_role,
            model_name="fake-direct",
            reasoning_profile=meta_decision.reasoning_profile,
            usage={"total_tokens": 3},
        )


class GraphFlowTests(unittest.TestCase):
    def test_build_agent_graph_compiles_and_routes_direct(self) -> None:
        graph = build_agent_graph(FakeMetaController(decision()), FakeDirectExecutor())

        final_state = graph.invoke(
            {
                "request": AgentRequest(user_text="Explain LangGraph"),
                "effective_user_text": "Explain LangGraph",
                "selected_text": None,
                "is_clarification_resume": False,
            }
        )

        response = final_state["response"]
        self.assertEqual(response.route, "meta->direct-chat")
        self.assertEqual(response.reply_text, "executed: Explain LangGraph")
        self.assertIsNone(final_state["pending_clarification"])

    def test_graph_routes_ambiguous_request_to_clarify(self) -> None:
        graph = build_agent_graph(
            FakeMetaController(
                decision(
                    need_clarification=True,
                    clarification_question="What should I optimize?",
                    missing_info=["scope"],
                    risk_level="medium",
                )
            ),
            FakeDirectExecutor(),
        )

        final_state = graph.invoke(
            {
                "request": AgentRequest(user_text="Optimize this"),
                "effective_user_text": "Optimize this",
                "selected_text": None,
                "is_clarification_resume": False,
            }
        )

        response = final_state["response"]
        self.assertEqual(response.route, "meta->clarify")
        self.assertEqual(response.reply_text, "What should I optimize?")
        self.assertIsNotNone(final_state["pending_clarification"])

    def test_graph_routes_high_privilege_autonomy_to_clarify(self) -> None:
        graph = build_agent_graph(
            FakeMetaController(
                decision(
                    autonomy_mode="execute_commands",
                    need_human_approval=True,
                    risk_level="high",
                )
            ),
            FakeDirectExecutor(),
        )

        final_state = graph.invoke(
            {
                "request": AgentRequest(user_text="Delete files"),
                "effective_user_text": "Delete files",
                "selected_text": None,
                "is_clarification_resume": False,
            }
        )

        self.assertEqual(final_state["response"].route, "meta->clarify")
        self.assertIsNotNone(final_state["pending_clarification"])


if __name__ == "__main__":
    unittest.main()
