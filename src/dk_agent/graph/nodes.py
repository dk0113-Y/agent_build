from __future__ import annotations

from typing import Any, Callable

from dk_agent.core.session_state import PendingClarification
from dk_agent.core.types import AgentRequest, AgentResponse
from dk_agent.executor.direct_executor import DirectExecutor
from dk_agent.graph.routing import decision_value, meta_decision_to_dict
from dk_agent.graph.state import AgentGraphState
from dk_agent.routing.meta_controller import MetaController
from dk_agent.routing.meta_schema import MetaDecision


SAFE_CLARIFICATION_FALLBACK = (
    "This V0.4 prototype cannot execute high-privilege actions directly. "
    "Please clarify a safe answer-only or plan-only scope."
)


def make_meta_node(meta_controller: MetaController) -> Callable[[AgentGraphState], dict[str, Any]]:
    def meta_node(state: AgentGraphState) -> dict[str, Any]:
        result = meta_controller.analyze(
            user_text=state["effective_user_text"],
            selected_text=state.get("selected_text"),
            is_clarification_resume=state.get("is_clarification_resume", False),
        )
        return {
            "meta_decision": result.decision,
            "meta_usage": result.meta_usage,
            "meta_model_name": result.meta_model_name,
            "meta_elapsed_seconds": result.meta_elapsed_seconds,
        }

    return meta_node


def make_clarification_node() -> Callable[[AgentGraphState], dict[str, Any]]:
    def clarification_node(state: AgentGraphState) -> dict[str, Any]:
        decision = state["meta_decision"]
        question = decision_value(decision, "clarification_question") or SAFE_CLARIFICATION_FALLBACK
        decision_metadata = meta_decision_to_dict(decision)
        pending = PendingClarification(
            original_user_text=state["effective_user_text"],
            clarification_question=question,
            missing_info=list(decision_value(decision, "missing_info", [])),
            meta_decision=_decision_model(decision),
        )
        response = AgentResponse(
            reply_text=question,
            route="meta->clarify",
            model_role="meta",
            model_name=state.get("meta_model_name") or "unknown-meta",
            reasoning_profile="medium",
            tools=list(decision_value(decision, "tools", [])),
            skills=list(decision_value(decision, "skills", [])),
            verifiers=list(decision_value(decision, "verifiers", [])),
            usage=state.get("meta_usage"),
            elapsed_seconds=state.get("meta_elapsed_seconds", 0.0),
            error=None,
            metadata={
                "meta_decision": decision_metadata,
                "meta_usage": state.get("meta_usage"),
                "pending_clarification": True,
            },
            meta_decision=decision_metadata,
            meta_route="meta->clarify",
            need_clarification=True,
            pending_clarification=True,
        )
        return {
            "response": response,
            "route": "meta->clarify",
            "pending_clarification": pending,
        }

    return clarification_node


def make_execute_node(direct_executor: DirectExecutor) -> Callable[[AgentGraphState], dict[str, Any]]:
    def execute_node(state: AgentGraphState) -> dict[str, Any]:
        request = state["request"]
        effective_request = AgentRequest(
            user_text=state["effective_user_text"],
            mode=request.mode if not state.get("is_clarification_resume", False) else "chat",
            selected_text=state.get("selected_text"),
            metadata=dict(request.metadata),
        )
        decision = _decision_model(state["meta_decision"])
        response = direct_executor.run(effective_request, decision)
        decision_metadata = meta_decision_to_dict(decision)
        response.route = "meta->direct-chat"
        response.meta_route = response.route
        response.meta_decision = decision_metadata
        response.need_clarification = False
        response.pending_clarification = False
        response.metadata.update(
            {
                "meta_decision": decision_metadata,
                "meta_usage": state.get("meta_usage"),
                "meta_model_name": state.get("meta_model_name"),
                "meta_elapsed_seconds": state.get("meta_elapsed_seconds", 0.0),
                "executor_usage": response.usage,
                "executor_elapsed_seconds": response.elapsed_seconds,
            }
        )
        return {
            "response": response,
            "route": "meta->direct-chat",
            "pending_clarification": None,
        }

    return execute_node


def make_response_node() -> Callable[[AgentGraphState], dict[str, Any]]:
    def response_node(state: AgentGraphState) -> dict[str, Any]:
        if state.get("response") is not None:
            return {}
        return {
            "response": AgentResponse(
                reply_text="Agent graph did not produce a response.",
                route=state.get("route") or "graph-error",
                model_role="runtime",
                model_name=state.get("meta_model_name") or "unknown",
                reasoning_profile="none",
                error=state.get("error") or "missing response",
            ),
            "route": state.get("route") or "graph-error",
        }

    return response_node


def _decision_model(meta_decision: object) -> MetaDecision:
    if isinstance(meta_decision, MetaDecision):
        return meta_decision
    if isinstance(meta_decision, dict):
        return MetaDecision.model_validate(meta_decision)
    raise TypeError("meta_decision is missing or invalid")
