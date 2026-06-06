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
    def test_interrupt_resume_reenters_graph_with_same_thread_and_clears_pending(self) -> None:
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
        runner = AgentGraphRunner(meta_controller=meta, direct_executor=executor, thread_id="thread-a")

        first = runner.run(AgentRequest(user_text="Optimize this"))
        second = runner.run(AgentRequest(user_text="Discuss architecture only"))

        self.assertEqual(first.route, "meta->clarify")
        self.assertEqual(first.metadata["thread_id"], "thread-a")
        self.assertEqual(first.metadata["interrupt_payload"]["question"], "What should I optimize?")
        self.assertEqual(second.route, "meta->direct-chat")
        self.assertEqual(second.metadata["thread_id"], "thread-a")
        self.assertFalse(runner.awaiting_clarification)
        self.assertIsNone(runner.pending_clarification)
        self.assertTrue(meta.calls[1]["is_clarification_resume"])
        enriched = meta.calls[1]["user_text"]
        self.assertIn("Original user request:", enriched)
        self.assertIn("Optimize this", enriched)
        self.assertIn("What should I optimize?", enriched)
        self.assertIn("Discuss architecture only", enriched)
        self.assertEqual(executor.requests[0].user_text, enriched)

    def test_resume_can_interrupt_again_when_meta_still_needs_clarification(self) -> None:
        meta = FakeMetaController(
            [
                decision(
                    need_clarification=True,
                    clarification_question="What should I optimize?",
                    missing_info=["scope"],
                ),
                decision(
                    need_clarification=True,
                    clarification_question="Which part of the architecture?",
                    missing_info=["component"],
                ),
            ]
        )
        executor = FakeDirectExecutor()
        runner = AgentGraphRunner(meta_controller=meta, direct_executor=executor, thread_id="thread-repeat")

        first = runner.run(AgentRequest(user_text="Optimize this"))
        second = runner.run(AgentRequest(user_text="The architecture"))

        self.assertEqual(first.reply_text, "What should I optimize?")
        self.assertEqual(second.route, "meta->clarify")
        self.assertEqual(second.reply_text, "Which part of the architecture?")
        self.assertTrue(runner.awaiting_clarification)
        self.assertEqual(executor.requests, [])
        self.assertTrue(meta.calls[1]["is_clarification_resume"])

    def test_different_thread_ids_keep_interrupt_state_isolated(self) -> None:
        runner_a = AgentGraphRunner(
            meta_controller=FakeMetaController(
                [
                    decision(
                        need_clarification=True,
                        clarification_question="Question A?",
                        missing_info=["a"],
                    ),
                    decision(),
                ]
            ),
            direct_executor=FakeDirectExecutor(),
            thread_id="thread-a",
        )
        runner_b = AgentGraphRunner(
            meta_controller=FakeMetaController(
                [
                    decision(
                        need_clarification=True,
                        clarification_question="Question B?",
                        missing_info=["b"],
                    )
                ]
            ),
            direct_executor=FakeDirectExecutor(),
            thread_id="thread-b",
        )

        first_a = runner_a.run(AgentRequest(user_text="Optimize A"))
        first_b = runner_b.run(AgentRequest(user_text="Optimize B"))
        second_a = runner_a.run(AgentRequest(user_text="Discuss A only"))

        self.assertEqual(first_a.reply_text, "Question A?")
        self.assertEqual(first_b.reply_text, "Question B?")
        self.assertEqual(second_a.route, "meta->direct-chat")
        self.assertFalse(runner_a.awaiting_clarification)
        self.assertTrue(runner_b.awaiting_clarification)
        self.assertIsNotNone(runner_b.pending_clarification)
        self.assertEqual(runner_b.pending_clarification.clarification_question, "Question B?")

    def test_clear_request_does_not_interrupt(self) -> None:
        meta = FakeMetaController([decision()])
        executor = FakeDirectExecutor()
        runner = AgentGraphRunner(meta_controller=meta, direct_executor=executor)

        response = runner.run(AgentRequest(user_text="Explain LangGraph"))

        self.assertEqual(response.route, "meta->direct-chat")
        self.assertFalse(response.pending_clarification)
        self.assertFalse(runner.awaiting_clarification)

    def test_agent_runtime_run_still_returns_agent_response(self) -> None:
        meta = FakeMetaController([decision()])
        executor = FakeDirectExecutor()
        runtime = AgentRuntime(UnusedGateway(), meta_controller=meta, direct_executor=executor, thread_id="runtime")

        response = runtime.run(AgentRequest(user_text="Explain LangGraph"))

        self.assertIsInstance(response, AgentResponse)
        self.assertEqual(response.route, "meta->direct-chat")
        self.assertIsNone(runtime.pending_clarification)


if __name__ == "__main__":
    unittest.main()
