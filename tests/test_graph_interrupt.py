from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from langgraph.types import Command

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
            reply_text=f"executed: {request.user_text}",
            route="direct-chat",
            model_role=meta_decision.executor_role,
            model_name="fake-direct",
            reasoning_profile=meta_decision.reasoning_profile,
        )


class GraphInterruptTests(unittest.TestCase):
    def initial_state(self, text: str) -> dict[str, object]:
        request = AgentRequest(user_text=text)
        return {
            "request_data": {
                "user_text": request.user_text,
                "mode": request.mode,
                "selected_text": request.selected_text,
                "metadata": request.metadata,
            },
            "original_user_text": request.user_text,
            "effective_user_text": request.user_text,
            "selected_text": request.selected_text,
            "mode": request.mode,
            "is_clarification_resume": False,
            "meta_decision": None,
            "meta_usage": None,
            "meta_model_name": None,
            "meta_elapsed_seconds": 0.0,
            "route": None,
            "response_data": None,
            "pending_interrupt": False,
            "error": None,
        }

    def test_graph_interrupt_payload_and_command_resume(self) -> None:
        meta = FakeMetaController(
            [
                decision(
                    need_clarification=True,
                    clarification_question="What should I optimize?",
                    missing_info=["scope"],
                    risk_level="medium",
                ),
                decision(),
            ]
        )
        executor = FakeDirectExecutor()
        graph = build_agent_graph(meta, executor)
        config = {"configurable": {"thread_id": "interrupt-resume"}}

        first = graph.invoke(self.initial_state("Optimize this"), config=config)

        payload = first["__interrupt__"][0].value
        self.assertEqual(payload["question"], "What should I optimize?")
        self.assertEqual(payload["original_user_text"], "Optimize this")
        self.assertEqual(payload["missing_info"], ["scope"])
        self.assertEqual(payload["route"], "meta->clarify")

        second = graph.invoke(Command(resume="Discuss architecture only"), config=config)

        response = AgentResponse(**second["response_data"])
        self.assertEqual(response.route, "meta->direct-chat")
        self.assertTrue(meta.calls[1]["is_clarification_resume"])
        enriched = meta.calls[1]["user_text"]
        self.assertIn("Original user request:", enriched)
        self.assertIn("Optimize this", enriched)
        self.assertIn("What should I optimize?", enriched)
        self.assertIn("Discuss architecture only", enriched)
        self.assertEqual(executor.requests[0].user_text, enriched)


if __name__ == "__main__":
    unittest.main()
